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


def passes_preset6(
    price_df: pd.DataFrame,
    fundamentals: dict,
    available_cash: float | None = None,
) -> dict:
    """プリセット⑥（週足中期）の合否を判定する

    条件: ROE≥10% / 配当利回り≥2% / PER 8〜18倍 / 52週高値からの下落率 −20〜−5%
    ＋共通前提（株価帯・流動性・単元が買えるか）。

    財務データ（ROE/配当利回り/PER）が取得できない項目は None として扱い、
    「不合格」にはせず「要確認」フラグを立てる（無料APIで取れないことがあるため）。

    Returns:
        pass（bool）, checks（各条件の True/False/None）, flags（要確認理由）, drop_pct を持つdict
    """
    common_ok, common_reasons = passes_common_prereq(price_df, available_cash)
    drop_pct = drop_from_52w_high(price_df)

    checks = {
        "共通前提": common_ok,
        "ROE≥10%": (None if fundamentals.get("roe") is None
                    else fundamentals["roe"] >= P6_ROE_MIN),
        "配当利回り≥2%": (None if fundamentals.get("dividend_yield") is None
                       else fundamentals["dividend_yield"] >= P6_DIV_YIELD_MIN),
        "PER 8〜18倍": _range_check(fundamentals.get("per"), P6_PER_MIN, P6_PER_MAX),
        "52週高値から-20〜-5%": P6_DROP_FROM_52W_MIN <= drop_pct <= P6_DROP_FROM_52W_MAX,
    }

    # None（データ未取得）は不合格にせず要確認フラグに回す。False が1つでもあれば不合格。
    flags = [f"{k}=データ未取得（要手動確認）" for k, v in checks.items() if v is None]
    if not common_ok:
        flags.extend(common_reasons)
    passed = all(v is not False for v in checks.values())

    return {"pass": passed, "checks": checks, "flags": flags, "drop_pct": round(drop_pct, 1)}


def fetch_fundamentals(code: str) -> dict:
    """yfinanceから財務指標（ROE%・配当利回り%・PER）をベストエフォートで取得する

    取れない項目は None。日本株はyfinanceの財務データが欠けることが多いので、
    その場合は passes_preset6 側で「要確認」扱いになる。
    """
    result = {"roe": None, "dividend_yield": None, "per": None, "name": None}
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


def screen_preset6(
    codes: list[str],
    available_cash: float | None = None,
    price_data: dict[str, pd.DataFrame] | None = None,
    fundamentals_map: dict[str, dict] | None = None,
    days: int = 365,
) -> pd.DataFrame:
    """プリセット⑥で候補を絞り込み、チャート判定・注文水準まで付けて返す

    price_data / fundamentals_map を渡すとネットワーク取得をスキップする（テスト用）。

    Returns:
        合格銘柄1行=コード/銘柄名/現在値/52週下落%/ROE/配当/PER/チャート合否/
        指値/損切り/利確/RR/建玉額/かぶミニ/要確認 を持つDataFrame
    """
    available_cash = settings.AVAILABLE_CASH if available_cash is None else available_cash
    rows = []
    for code in codes:
        try:
            df = (price_data or {}).get(code)
            if df is None:
                df = data_fetcher.get_cached_or_fetch(code, days)
            fund = (fundamentals_map or {}).get(code)
            if fund is None:
                fund = fetch_fundamentals(code)

            verdict = passes_preset6(df, fund, available_cash)
            if not verdict["pass"]:
                continue

            # チャート3点チェック（週足＝26週MA）
            chart_ok, chart_detail = chart_filter.chart_check_weekly(df)
            if not chart_ok:
                continue  # 下降トレンド等はここで除外

            ind = indicators.calc_all(df)
            atr = float(ind["atr"].iloc[-1])
            close = float(df["close"].iloc[-1])
            order = order_calc.calc_order(close, atr, preset="weekly",
                                          entry_style="pullback", available_cash=available_cash)
            rows.append({
                "コード": code,
                "銘柄名": fund.get("name") or STOCK_NAMES.get(code, code),
                "プリセット": "⑥週足中期",
                "現在値": round(close, 1),
                "52週下落%": verdict["drop_pct"],
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
