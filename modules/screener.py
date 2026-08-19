"""
modules/screener.py
銘柄スクリーニングロジック（テクニカル条件＋レジーム判定）
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings
from modules import chart_filter, data_fetcher, indicators, order_calc, strategy_alpha, strategy_beta

# =====================================================================
# 週次スクリーニング（指示書ステップ6-1）
# 楽天スーパースクリーナーのプリセットをコード化する。まずメインの
# プリセット⑥（週足中期）だけを実装し、動いたら他プリセットを足していく。
# しきい値は定数にまとめ、11月に実績を見て調整しやすくする。
# =====================================================================

# ----- 全プリセット共通の前提条件 -----
PRICE_MIN = 1_000                    # 株価下限（円）
PRICE_MAX = 5_000                    # 株価上限（値がさ除外。円）
MIN_TURNOVER_5D_YEN = 500_000_000    # 5日平均売買代金の下限（5億円・流動性）
LOT_SIZE = 100                       # 単元株数（株価×100 > 余力 なら除外）

# ----- プリセット① 押し目（日足）-----
P1_RSI_MIN, P1_RSI_MAX = 30.0, 45.0
P1_DEV25_MIN, P1_DEV25_MAX = -5.0, -1.0     # 25日MA乖離%

# ----- プリセット② ブレイク（日足）-----
P2_RSI_MIN, P2_RSI_MAX = 55.0, 70.0
P2_DEV25_MIN, P2_DEV25_MAX = 1.0, 5.0       # 25日MA乖離%
P2_TURNOVER_SURGE = 1.5                      # 売買代金の前日比（倍）下限

# ----- プリセット③ 業績モメンタム（日足）-----
P3_RSI_MIN, P3_RSI_MAX = 30.0, 45.0
P3_ROE_MIN = 10.0
P3_ORDINARY_GROWTH_MIN = 5.0                 # 経常利益変化率（前年比%）下限
P3_PER_MIN, P3_PER_MAX = 8.0, 20.0

# ----- プリセット④ ボリンジャー逆張り（日足）-----
P4_RSI_MIN, P4_RSI_MAX = 25.0, 35.0          # -2σ〜-3σ到達＋株価>75日MA と併用

# ----- プリセット⑤ GC×高配当（週足チャート）-----
P5_DIV_YIELD_MIN = 3.0
P5_ROE_MIN = 8.0

# ----- プリセット⑥ 週足中期 のしきい値 -----
P6_ROE_MIN = 10.0                    # ROE 下限（%）
P6_DIV_YIELD_MIN = 2.0               # 配当利回り 下限（%）
P6_PER_MIN = 8.0                     # PER 下限（倍）
P6_PER_MAX = 18.0                    # PER 上限（倍）
P6_DROP_FROM_52W_MIN = -20.0         # 52週高値からの下落率 下限（%）
P6_DROP_FROM_52W_MAX = -5.0          # 52週高値からの下落率 上限（%・押し目ゾーン）

# 銘柄名（保有銘柄ユニバース用の簡易マスタ）
STOCK_NAMES: dict[str, str] = {
    "2432": "ディー・エヌ・エー",
    "2664": "カワチ薬品",
    "2914": "JT",
    "3196": "ホットランドHD",
    "4755": "楽天グループ",
    "6501": "日立製作所",
    "6526": "ソシオネクスト",
    "7011": "三菱重工業",
    "7012": "川崎重工業",
    "8267": "イオン",
    "9434": "ソフトバンク",
    "VOO": "Vanguard S&P500 ETF",
    "VYM": "Vanguard 高配当ETF",
    "MRAM": "Everspin Technologies",
}


def get_regime(adx: float) -> str:
    """ADX値からレジームを判定して返す

    ADX < 20: レンジ（平均回帰が有効） / ADX >= 25: トレンド（順張りが有効） / 中間: 中立
    """
    if pd.isna(adx):
        return "不明"
    if adx < settings.ADX_RANGE_THRESHOLD:
        return "レンジ"
    if adx >= settings.ADX_TREND_THRESHOLD:
        return "トレンド"
    return "中立"


def _check_conditions(latest: pd.Series, conditions: dict) -> tuple[bool, list[str]]:
    """最新行が条件に合致するか判定し、(合致したか, シグナル種別リスト) を返す"""
    matched: list[str] = []

    if conditions.get("rsi_oversold") and latest["rsi"] < settings.RSI_OVERSOLD:
        matched.append("RSI売られすぎ")
    if conditions.get("rsi_overbought") and latest["rsi"] > settings.RSI_OVERBOUGHT:
        matched.append("RSI買われすぎ")
    if conditions.get("bb_lower_touch") and latest["close"] <= latest["bb_lower"]:
        matched.append("BB下限タッチ")
    if conditions.get("bb_upper_touch") and latest["close"] >= latest["bb_upper"]:
        matched.append("BB上限タッチ")
    if conditions.get("kc_lower_touch") and latest["close"] <= latest["kc_lower"]:
        matched.append("Keltner下限タッチ")
    if conditions.get("above_vwap") and latest["close"] > latest["vwap"]:
        matched.append("VWAP上")
    if conditions.get("below_vwap") and latest["close"] < latest["vwap"]:
        matched.append("VWAP下")

    # レジームフィルター（指定時は不一致なら除外）
    regime_filter = conditions.get("regime")  # None / "レンジ" / "トレンド"
    if regime_filter and get_regime(latest["adx"]) != regime_filter:
        return False, matched

    # テクニカル条件が1つも指定されていなければ全銘柄表示（レジームのみで絞る）
    technical_keys = [
        "rsi_oversold", "rsi_overbought", "bb_lower_touch",
        "bb_upper_touch", "kc_lower_touch", "above_vwap", "below_vwap",
    ]
    any_specified = any(conditions.get(k) for k in technical_keys)
    return (not any_specified) or bool(matched), matched


def screen(universe: list[str], conditions: dict, days: int = 120) -> pd.DataFrame:
    """条件に合致する銘柄の一覧をDataFrameで返す

    Args:
        universe: 対象銘柄コードのリスト
        conditions: スクリーニング条件のdict
        days: 指標計算に使う日足データの日数
    Returns:
        コード・銘柄名・現在値・RSI・ADX・レジーム・シグナル・エラー列を持つDataFrame
    """
    rows = []
    for code in universe:
        try:
            df = data_fetcher.get_cached_or_fetch(code, days)
            df = indicators.calc_all(df)
            latest = df.iloc[-1]
            ok, matched = _check_conditions(latest, conditions)
            if not ok:
                continue
            # 戦略シグナル（最新足）
            sig_a = strategy_alpha.signal(df).iloc[-1]
            sig_b = strategy_beta.signal(df).iloc[-1]
            strategy_sigs = []
            if sig_a == 1:
                strategy_sigs.append("α:ロング")
            elif sig_a == -1:
                strategy_sigs.append("α:ショート")
            if sig_b == 1:
                strategy_sigs.append("β:ロング")
            rows.append({
                "コード": code,
                "銘柄名": STOCK_NAMES.get(code, code),
                "現在値": round(float(latest["close"]), 2),
                "RSI": round(float(latest["rsi"]), 1),
                "ADX": round(float(latest["adx"]), 1),
                "レジーム": get_regime(latest["adx"]),
                "シグナル": " / ".join(matched + strategy_sigs) or "-",
            })
        except Exception as e:
            rows.append({
                "コード": code,
                "銘柄名": STOCK_NAMES.get(code, code),
                "現在値": None, "RSI": None, "ADX": None,
                "レジーム": "取得失敗",
                "シグナル": f"エラー: {e}",
            })
    return pd.DataFrame(rows)


# ========== 週次スクリーニング（プリセット⑥ 週足中期） ==========

def drop_from_52w_high(price_df: pd.DataFrame) -> float:
    """52週高値からの下落率（%）を返す。マイナスなら高値より下にいる

    直近約252営業日（＝52週）の高値に対する現在値の位置。
    """
    window = price_df["close"].tail(252)
    high = float(window.max())
    close = float(window.iloc[-1])
    if high <= 0:
        return 0.0
    return (close / high - 1) * 100


def passes_common_prereq(
    price_df: pd.DataFrame, available_cash: float | None = None
) -> tuple[bool, list[str]]:
    """全プリセット共通の前提（株価帯・流動性・単元が買えるか）を判定する

    Returns:
        (合格か, 不合格理由のリスト)
    """
    available_cash = settings.AVAILABLE_CASH if available_cash is None else available_cash
    reasons: list[str] = []
    close = float(price_df["close"].iloc[-1])

    if not (PRICE_MIN <= close <= PRICE_MAX):
        reasons.append(f"株価{close:,.0f}円が対象帯（{PRICE_MIN:,}〜{PRICE_MAX:,}円）外")

    turnover_5d = float((price_df["close"] * price_df["volume"]).tail(5).mean())
    if turnover_5d < MIN_TURNOVER_5D_YEN:
        reasons.append(f"5日平均売買代金 {turnover_5d/1e8:.1f}億円が5億円未満（流動性不足）")

    if close * LOT_SIZE > available_cash:
        reasons.append(f"単元({LOT_SIZE}株={close*LOT_SIZE:,.0f}円)が余力{available_cash:,.0f}円超")

    return (not reasons), reasons


def _range_check(value, lo, hi):
    """value が [lo, hi] 内か。value が None（データ未取得）なら None を返す（＝不明）"""
    if value is None:
        return None
    return lo <= value <= hi


def _ge(value, threshold):
    """value >= threshold。value が None（未取得）なら None（＝不明）を返す"""
    return None if value is None else value >= threshold


def _finalize(checks: dict, extra_flags: list[str] | None = None) -> dict:
    """checks（True/False/None）から合否とフラグを組み立てる共通処理

    None（データ未取得）は不合格にせず「要確認」フラグに回す。
    False が1つでもあれば不合格。
    """
    flags = [f"{k}=データ未取得（要手動確認）" for k, v in checks.items() if v is None]
    if extra_flags:
        flags.extend(extra_flags)
    passed = all(v is not False for v in checks.values())
    return {"pass": passed, "checks": checks, "flags": flags}


def _preset6_specific(price_df: pd.DataFrame, fundamentals: dict) -> tuple[dict, float]:
    """プリセット⑥の固有条件（共通前提を除く）を判定して (checks, drop_pct) を返す"""
    drop_pct = drop_from_52w_high(price_df)
    checks = {
        "ROE≥10%": _ge(fundamentals.get("roe"), P6_ROE_MIN),
        "配当利回り≥2%": _ge(fundamentals.get("dividend_yield"), P6_DIV_YIELD_MIN),
        "PER 8〜18倍": _range_check(fundamentals.get("per"), P6_PER_MIN, P6_PER_MAX),
        "52週高値から-20〜-5%": P6_DROP_FROM_52W_MIN <= drop_pct <= P6_DROP_FROM_52W_MAX,
    }
    return checks, drop_pct


def passes_preset6(
    price_df: pd.DataFrame,
    fundamentals: dict,
    available_cash: float | None = None,
) -> dict:
    """プリセット⑥（週足中期）の合否を判定する（共通前提込み・後方互換API）

    条件: ROE≥10% / 配当利回り≥2% / PER 8〜18倍 / 52週高値からの下落率 −20〜−5%
    ＋共通前提（株価帯・流動性・単元が買えるか）。
    財務データ未取得の項目は不合格にせず「要確認」フラグに回す。
    """
    common_ok, common_reasons = passes_common_prereq(price_df, available_cash)
    checks6, drop_pct = _preset6_specific(price_df, fundamentals)
    checks = {"共通前提": common_ok, **checks6}
    result = _finalize(checks, extra_flags=(common_reasons if not common_ok else None))
    result["drop_pct"] = round(drop_pct, 1)
    return result


def fetch_fundamentals(code: str) -> dict:
    """yfinanceから財務指標（ROE%・配当利回り%・PER）をベストエフォートで取得する

    取れない項目は None。日本株はyfinanceの財務データが欠けることが多いので、
    その場合は passes_preset6 側で「要確認」扱いになる。
    """
    # ordinary_income_growth（経常利益変化率）は yfinance では取れないため常に None。
    # プリセット③で「要確認」扱いになる（本来は J-Quants 財務データが必要）。
    result = {"roe": None, "dividend_yield": None, "per": None,
              "ordinary_income_growth": None, "name": None}
    try:
        import yfinance as yf
        symbol = f"{code}.T" if data_fetcher.is_jp_code(code) else code
        info = yf.Ticker(symbol).info or {}
        roe = info.get("returnOnEquity")
        dy = info.get("dividendYield")
        per = info.get("trailingPE")
        result["roe"] = round(roe * 100, 1) if isinstance(roe, (int, float)) else None
        # dividendYield はライブラリのバージョンで小数(0.03)と%(3.0)の両表現がある
        if isinstance(dy, (int, float)):
            result["dividend_yield"] = round(dy * 100, 2) if dy < 1 else round(dy, 2)
        result["per"] = round(per, 1) if isinstance(per, (int, float)) else None
        result["name"] = info.get("shortName") or info.get("longName")
    except Exception:
        pass
    return result


# ========== 各プリセットの固有条件（共通前提を除く） ==========
# 各評価関数は (checks辞書, 指標メモ文字列, ブレイク用の直近高値or None) を返す。
# checks の値は True/False/None（Noneはデータ未取得＝要確認）。

def _dev25(latest) -> float:
    """25日移動平均からの乖離率（%）。sma25が無ければ NaN"""
    sma25 = latest.get("sma25")
    close = float(latest["close"])
    if sma25 is None or pd.isna(sma25) or sma25 == 0:
        return float("nan")
    return (close / float(sma25) - 1) * 100


def _above_sma75(latest) -> bool:
    sma75 = latest.get("sma75")
    return bool(sma75 is not None and pd.notna(sma75) and float(latest["close"]) > float(sma75))


def _preset1(df: pd.DataFrame, fund: dict):
    """① 押し目：RSI30〜45 / 25日乖離-5〜-1% / 株価>75日MA"""
    latest = df.iloc[-1]
    rsi = float(latest["rsi"]); dev = _dev25(latest)
    checks = {
        "RSI 30〜45": P1_RSI_MIN <= rsi <= P1_RSI_MAX,
        "25日乖離 -5〜-1%": (not pd.isna(dev)) and P1_DEV25_MIN <= dev <= P1_DEV25_MAX,
        "株価>75日MA": _above_sma75(latest),
    }
    return checks, f"RSI{rsi:.0f} / 25日乖離{dev:+.1f}%", None


def _preset2(df: pd.DataFrame, fund: dict):
    """② ブレイク：RSI55〜70 / 25日乖離+1〜+5% / 売買代金 前日比≥1.5倍"""
    latest = df.iloc[-1]; prev = df.iloc[-2]
    rsi = float(latest["rsi"]); dev = _dev25(latest)
    t_now = float(latest["close"]) * float(latest["volume"])
    t_prev = float(prev["close"]) * float(prev["volume"])
    surge = t_now / t_prev if t_prev > 0 else 0.0
    checks = {
        "RSI 55〜70": P2_RSI_MIN <= rsi <= P2_RSI_MAX,
        "25日乖離 +1〜+5%": (not pd.isna(dev)) and P2_DEV25_MIN <= dev <= P2_DEV25_MAX,
        "売買代金 前日比≥1.5倍": surge >= P2_TURNOVER_SURGE,
    }
    recent_high = float(df["high"].tail(60).max())  # ブレイク型の逆指値の基準
    return checks, f"RSI{rsi:.0f} / 乖離{dev:+.1f}% / 代金{surge:.1f}倍", recent_high


def _preset3(df: pd.DataFrame, fund: dict):
    """③ 業績モメンタム：RSI30〜45 / ROE≥10% / 経常利益変化率≥+5% / PER8〜20"""
    latest = df.iloc[-1]; rsi = float(latest["rsi"])
    checks = {
        "RSI 30〜45": P3_RSI_MIN <= rsi <= P3_RSI_MAX,
        "ROE≥10%": _ge(fund.get("roe"), P3_ROE_MIN),
        "経常利益変化率≥+5%": _ge(fund.get("ordinary_income_growth"), P3_ORDINARY_GROWTH_MIN),
        "PER 8〜20倍": _range_check(fund.get("per"), P3_PER_MIN, P3_PER_MAX),
    }
    return checks, f"RSI{rsi:.0f} / ROE{fund.get('roe')} / PER{fund.get('per')}", None


def _preset4(df: pd.DataFrame, fund: dict):
    """④ ボリンジャー逆張り：RSI25〜35 / BB -2σ〜-3σ到達 / 株価>75日MA"""
    latest = df.iloc[-1]
    rsi = float(latest["rsi"]); close = float(latest["close"])
    bb_lower = float(latest["bb_lower"]); bb_mid = float(latest["bb_mid"])  # bb_lower = -2σ
    sigma = (bb_mid - bb_lower) / 2 if bb_mid > bb_lower else 0.0
    lower3 = bb_lower - sigma  # -3σ
    touched = (lower3 <= close <= bb_lower) if sigma > 0 else False
    checks = {
        "RSI 25〜35": P4_RSI_MIN <= rsi <= P4_RSI_MAX,
        "BB -2σ〜-3σ到達": bool(touched),
        "株価>75日MA": _above_sma75(latest),
    }
    return checks, f"RSI{rsi:.0f} / 現在値{close:.0f}（-2σ{bb_lower:.0f}）", None


def _preset5(df: pd.DataFrame, fund: dict):
    """⑤ GC×高配当：5日/25日ゴールデンクロス / 配当利回り≥3% / ROE≥8%"""
    sma5 = df["close"].rolling(5).mean()
    sma25 = df["close"].rolling(25).mean()
    gc = False
    if len(df) >= 26 and pd.notna(sma25.iloc[-2]):
        gc = bool(sma5.iloc[-1] > sma25.iloc[-1] and sma5.iloc[-2] <= sma25.iloc[-2])
    checks = {
        "GC(5日/25日)": gc,
        "配当利回り≥3%": _ge(fund.get("dividend_yield"), P5_DIV_YIELD_MIN),
        "ROE≥8%": _ge(fund.get("roe"), P5_ROE_MIN),
    }
    return checks, f"GC{'○' if gc else '×'} / 配当{fund.get('dividend_yield')} / ROE{fund.get('roe')}", None


def _preset6(df: pd.DataFrame, fund: dict):
    """⑥ 週足中期：ROE≥10% / 配当≥2% / PER8〜18 / 52週高値から-20〜-5%"""
    checks, drop = _preset6_specific(df, fund)
    return checks, f"52週高値から{drop:+.1f}%", None


# ========== プリセット・レジストリ ==========
PRESET_NAMES = {
    "①": "①押し目", "②": "②ブレイク", "③": "③業績モメンタム",
    "④": "④ボリンジャー逆張り", "⑤": "⑤GC×高配当", "⑥": "⑥週足中期",
}
PRESET_TIMEFRAME = {  # チャート判定に使う移動平均（日足=75日 / 週足=26週）
    "①": "daily", "②": "daily", "③": "daily", "④": "daily", "⑤": "weekly", "⑥": "weekly",
}
PRESET_ENTRY = {"②": "break"}  # 未指定は "pullback"
PRESET_EVAL = {
    "①": _preset1, "②": _preset2, "③": _preset3,
    "④": _preset4, "⑤": _preset5, "⑥": _preset6,
}


def screen_preset(
    preset_id: str,
    codes: list[str],
    available_cash: float | None = None,
    price_data: dict[str, pd.DataFrame] | None = None,
    fundamentals_map: dict[str, dict] | None = None,
    days: int = 365,
) -> pd.DataFrame:
    """指定プリセットで候補を絞り、チャート判定・注文水準まで付けてDataFrameで返す

    共通前提（株価帯・流動性・単元）＋プリセット固有条件＋チャート3点チェックを通過した
    銘柄だけを返す。price_data / fundamentals_map を渡すとネットワーク取得を省略できる（テスト用）。
    """
    available_cash = settings.AVAILABLE_CASH if available_cash is None else available_cash
    timeframe = PRESET_TIMEFRAME[preset_id]
    entry_style = PRESET_ENTRY.get(preset_id, "pullback")
    evaluator = PRESET_EVAL[preset_id]
    rows = []
    for code in codes:
        try:
            df = (price_data or {}).get(code)
            if df is None:
                df = data_fetcher.get_cached_or_fetch(code, days)
            fund = (fundamentals_map or {}).get(code)
            if fund is None:
                fund = fetch_fundamentals(code)

            df_ind = indicators.calc_all(df)
            common_ok, common_reasons = passes_common_prereq(df, available_cash)
            specific, memo, recent_high = evaluator(df_ind, fund)
            checks = {"共通前提": common_ok, **specific}
            verdict = _finalize(checks, extra_flags=(common_reasons if not common_ok else None))
            if not verdict["pass"]:
                continue

            # チャート3点チェック（日足=75日MA / 週足=26週MA）
            if timeframe == "weekly":
                chart_ok, _ = chart_filter.chart_check_weekly(df)
            else:
                chart_ok, _ = chart_filter.chart_check_daily(df)
            if not chart_ok:
                continue  # 下降トレンド等はここで除外

            atr = float(df_ind["atr"].iloc[-1])
            close = float(df["close"].iloc[-1])
            order = order_calc.calc_order(
                close, atr, preset=timeframe, entry_style=entry_style,
                recent_high=recent_high, available_cash=available_cash,
            )
            rows.append({
                "コード": code,
                "銘柄名": fund.get("name") or STOCK_NAMES.get(code, code),
                "プリセット": PRESET_NAMES[preset_id],
                "現在値": round(close, 1),
                "指標メモ": memo,
                "ROE%": fund.get("roe"),
                "配当利回り%": fund.get("dividend_yield"),
                "PER": fund.get("per"),
                "チャート合格": "✅" if chart_ok else "❌",
                "指値": order["entry"],
                "損切り": order["stop"],
                "利確": order["take"],
                "RR": order["rr"],
                "建玉額": order["notional"],
                "かぶミニ": "⚠️" if order["kabumini"] else "",
                "要確認": " / ".join(verdict["flags"]) or "-",
            })
        except Exception:
            continue  # 取得失敗はスキップ
    return pd.DataFrame(rows)


def screen_preset6(
    codes: list[str],
    available_cash: float | None = None,
    price_data: dict[str, pd.DataFrame] | None = None,
    fundamentals_map: dict[str, dict] | None = None,
    days: int = 365,
) -> pd.DataFrame:
    """プリセット⑥（週足中期）のスクリーニング。screen_preset の薄いラッパ（後方互換）"""
    return screen_preset("⑥", codes, available_cash, price_data, fundamentals_map, days)


def screen_all_presets(
    codes: list[str],
    presets: list[str] | None = None,
    available_cash: float | None = None,
    price_data: dict[str, pd.DataFrame] | None = None,
    fundamentals_map: dict[str, dict] | None = None,
    days: int = 365,
) -> pd.DataFrame:
    """複数プリセットをまとめて実行し、1つの表に統合して返す

    複数プリセットでヒットした銘柄には「★重複」を付ける（マルチファクター重複の強調）。
    presets 未指定なら全6プリセットを実行する。
    """
    presets = presets or list(PRESET_NAMES.keys())
    frames = [
        screen_preset(pid, codes, available_cash, price_data, fundamentals_map, days)
        for pid in presets
    ]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    dup_count = out["コード"].value_counts()
    out.insert(3, "重複", out["コード"].map(lambda c: "★重複" if dup_count.get(c, 0) > 1 else ""))
    return out
