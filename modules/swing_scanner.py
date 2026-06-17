"""
modules/swing_scanner.py
スイングトレード候補の自動スキャン

テーマ別ユニバース（universe.py）の全銘柄を一括取得し、
3種類のセットアップを判定してスコア順に候補を返す。

セットアップ:
  1. トレンド押し目: ADX>=25の上昇トレンド中、EMA12近辺への押し（順張りスイング）
  2. 平均回帰リバウンド: ADX<20のレンジでBB/Keltner下限タッチ＋RSI低水準（戦略β系）
  3. ブレイクアウト: BB上限超え＋出来高急増＋ADX上昇（モメンタム）

デイトレ不可・朝夕のみ確認という運用前提のため、日足ベースで判定する。
"""
from __future__ import annotations

import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings
from modules import indicators, risk_manager, strategy_alpha, strategy_beta, universe

SCAN_PERIOD = "6mo"
MIN_ROWS = 60                       # 指標計算に必要な最低営業日数
MIN_TURNOVER_JP = 100_000_000       # 日本株: 20日平均売買代金 1億円以上
MIN_TURNOVER_US = 10_000_000        # 米国株: 20日平均売買代金 1,000万ドル以上
MAX_ATR_PCT = 8.0                   # ATR%上限（ボラ過大は除外）
MIN_ATR_PCT = 1.0                   # ATR%下限（値動きがなさすぎる銘柄は除外）


def _is_jp(code: str) -> bool:
    """日本株コード（4桁数字＋任意の英字1文字）かを判定する"""
    return bool(re.fullmatch(r"\d{3,4}[0-9A-Z]?", code))


def _yf_symbol(code: str) -> str:
    """yfinance用のシンボルに変換する"""
    return f"{code}.T" if _is_jp(code) else code


_FX_CACHE: dict[str, float] = {}


def get_usdjpy() -> float:
    """USD/JPYの最新レートを取得する（失敗時は概算155で代替）"""
    if "rate" in _FX_CACHE:
        return _FX_CACHE["rate"]
    rate = 155.0
    try:
        import yfinance as yf
        fx = yf.download("JPY=X", period="5d", auto_adjust=True, progress=False)
        if fx is not None and not fx.empty:
            close = fx["Close"]
            if hasattr(close, "columns"):  # MultiIndex列のDataFrameなら1列目を使う
                close = close.iloc[:, 0]
            val = float(close.dropna().iloc[-1])
            if 80 < val < 300:
                rate = val
    except Exception:
        pass
    _FX_CACHE["rate"] = rate
    return rate


def batch_fetch(codes: list[str], period: str = SCAN_PERIOD) -> dict[str, pd.DataFrame]:
    """yfinanceで全銘柄の日足を一括取得して {コード: DataFrame} で返す"""
    import yfinance as yf

    symbols = {_yf_symbol(c): c for c in codes}
    raw = yf.download(
        list(symbols.keys()), period=period,
        auto_adjust=True, progress=False, group_by="ticker", threads=True,
    )
    result: dict[str, pd.DataFrame] = {}
    for sym, code in symbols.items():
        try:
            sub = raw[sym] if isinstance(raw.columns, pd.MultiIndex) else raw
            df = sub.reset_index().rename(columns={
                "Date": "date", "Open": "open", "High": "high",
                "Low": "low", "Close": "close", "Volume": "volume",
            })[["date", "open", "high", "low", "close", "volume"]]
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
            df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
            if len(df) >= MIN_ROWS:
                result[code] = df
        except Exception:
            continue  # 取得失敗銘柄はスキップ
    return result


def _evaluate(code: str, name: str, df: pd.DataFrame) -> dict | None:
    """1銘柄を評価して候補dictを返す（候補でなければNone）"""
    df = indicators.calc_all(df)
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(latest["close"])
    is_jp = _is_jp(code)

    # --- 流動性フィルター ---
    turnover = float((df["close"] * df["volume"]).tail(20).mean())
    if turnover < (MIN_TURNOVER_JP if is_jp else MIN_TURNOVER_US):
        return None

    # --- ボラティリティフィルター ---
    atr_pct = float(latest["atr"]) / close * 100
    if not (MIN_ATR_PCT <= atr_pct <= MAX_ATR_PCT):
        return None

    rsi = float(latest["rsi"])
    adx = float(latest["adx"])
    plus_di = float(latest["plus_di"])
    minus_di = float(latest["minus_di"])
    vol_ratio = float(latest["volume"]) / max(float(df["volume"].tail(20).mean()), 1)

    setup = None
    score = 0.0
    reasons: list[str] = []
    direction = 1  # 全セットアップともロング前提（現物スイング想定）

    # --- 1. トレンド押し目（順張り） ---
    if adx >= settings.ADX_TREND_THRESHOLD and plus_di > minus_di and close > float(latest["ema_long"]):
        pullback = (close - float(latest["ema_short"])) / close * 100  # EMA12との乖離%
        if -1.0 <= pullback <= 3.0 and 35 <= rsi <= 60:
            setup = "トレンド押し目"
            score = 55 + min(adx - 25, 15)
            reasons.append(f"上昇トレンド（ADX {adx:.0f}・+DI>-DI）")
            reasons.append(f"EMA12近辺まで押し（乖離 {pullback:+.1f}%）")
            if 40 <= rsi <= 55:
                score += 10
                reasons.append(f"RSI {rsi:.0f} で過熱感なし")
            if float(latest["macd_hist"]) > float(prev["macd_hist"]):
                score += 5
                reasons.append("MACDヒストグラム改善中")

    # --- 2. 平均回帰リバウンド（戦略β系） ---
    if setup is None and adx < settings.ADX_RANGE_THRESHOLD:
        touch_kc = close <= float(latest["kc_lower"])
        touch_bb = close <= float(latest["bb_lower"])
        if (touch_kc or touch_bb) and rsi <= 35:
            setup = "平均回帰リバウンド"
            score = 55 + (12 if rsi <= 30 else 6)
            reasons.append(f"レンジ相場（ADX {adx:.0f}）で下限タッチ")
            reasons.append(f"RSI {rsi:.0f} の売られすぎ圏")
            if touch_kc and touch_bb:
                score += 8
                reasons.append("BB・Keltner両方の下限を割り込み")
            # 強気ダイバージェンス（直近20日）
            window = df.tail(21)
            if (window["low"].iloc[-1] < window["low"].iloc[:-1].min()
                    and window["rsi"].iloc[-1] > window["rsi"].loc[window["low"].iloc[:-1].idxmin()]):
                score += 10
                reasons.append("RSI強気ダイバージェンス")

    # --- 3. ブレイクアウト（モメンタム） ---
    if setup is None and close > float(latest["bb_upper"]) and vol_ratio >= 1.5:
        adx_rising = adx > float(prev["adx"])
        if adx_rising:
            setup = "ブレイクアウト"
            score = 50 + min((vol_ratio - 1.5) * 10, 15)
            reasons.append(f"BB上限ブレイク＋出来高 {vol_ratio:.1f}倍")
            reasons.append(f"ADX上昇中（{adx:.0f}）でトレンド発生の兆し")
            if float(latest["macd_hist"]) > 0:
                score += 5
                reasons.append("MACD陽転済み")

    # --- 監視リスト（あと一歩でセットアップ完成の銘柄） ---
    grade = "候補"
    if setup is None:
        grade = "監視"
        # トレンド継続中でEMA12への押しを待つ
        if adx >= settings.ADX_TREND_THRESHOLD and plus_di > minus_di and close > float(latest["ema_long"]):
            gap = (close - float(latest["ema_short"])) / close * 100
            if 3.0 < gap <= 7.0:
                setup = "トレンド押し目（待ち）"
                score = 45 - (gap - 3.0) * 2
                reasons.append(f"上昇トレンド継続（ADX {adx:.0f}）、EMA12まであと{gap:.1f}%の押しを待つ")
        # レンジ下限への接近を待つ
        elif adx < settings.ADX_RANGE_THRESHOLD + 3 and rsi <= 42:
            gap_kc = (close - float(latest["kc_lower"])) / close * 100
            if 0 < gap_kc <= 3.0:
                setup = "平均回帰（待ち）"
                score = 45 - gap_kc * 3
                reasons.append(f"Keltner下限まであと{gap_kc:.1f}%・RSI {rsi:.0f}、下限タッチで反発狙い")

    if setup is None:
        return None

    # --- リスク管理（SL/TP・株数・リスク額・投資額） ---
    sl, tp = risk_manager.calc_sl_tp(close, float(latest["atr"]), direction)
    fx = 1.0 if is_jp else get_usdjpy()
    risk_budget_yen = settings.SWING_CAPITAL * settings.SWING_RISK_PERCENT
    per_share_risk = close - sl  # 1株あたりの値幅（通貨建て）
    shares = int(risk_budget_yen / fx / per_share_risk) if per_share_risk > 0 else 0
    risk_yen = round(shares * per_share_risk * fx, 0)        # 実際の円リスク額
    invest_yen = round(shares * close * fx, 0)               # 円換算の投資額

    change_pct = (close / float(prev["close"]) - 1) * 100
    return {
        "コード": code,
        "銘柄名": name,
        "市場": "日本" if is_jp else "米国",
        "テーマ": " / ".join(universe.themes_of(code)),
        "種別": grade,
        "セットアップ": setup,
        "スコア": round(min(score, 95), 0),
        "終値": round(close, 2),
        "前日比%": round(change_pct, 2),
        "RSI": round(rsi, 0),
        "ADX": round(adx, 0),
        "ATR%": round(atr_pct, 1),
        "SL": round(sl, 2),
        "TP": round(tp, 2),
        "株数目安": int(shares) if shares else None,
        "リスク額": risk_yen,
        "投資額": invest_yen,
        "根拠": " ／ ".join(reasons),
    }


def _regime(adx: float) -> str:
    """ADX値からレジーム（レンジ/中立/トレンド）を判定する"""
    if adx < settings.ADX_RANGE_THRESHOLD:
        return "レンジ"
    if adx >= settings.ADX_TREND_THRESHOLD:
        return "トレンド"
    return "中立"


def _resolve_targets(theme_filter: list[str] | None) -> dict[str, str]:
    """テーマ指定から対象 {コード: 銘柄名} を返す（Noneなら全テーマ）"""
    if theme_filter:
        targets: dict[str, str] = {}
        for t in theme_filter:
            targets.update(universe.THEMES.get(t, {}))
        return targets
    return universe.all_codes()


def scan(
    theme_filter: list[str] | None = None,
    top_n: int = 20,
    data: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """全ユニバースをスキャンしてスコア順の候補DataFrameを返す

    Args:
        theme_filter: 対象テーマ名のリスト（Noneなら全テーマ）
        top_n: 返す最大件数
        data: 事前取得済みの {コード: 日足DataFrame}（指定時は再取得しない）
    """
    targets = _resolve_targets(theme_filter)
    if data is None:
        data = batch_fetch(list(targets.keys()))

    rows = []
    for code, df in data.items():
        if code not in targets:
            continue
        try:
            r = _evaluate(code, targets[code], df)
            if r:
                rows.append(r)
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    return (
        pd.DataFrame(rows)
        .sort_values("スコア", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )


def _overview_row(code: str, name: str, df: pd.DataFrame) -> dict | None:
    """1銘柄のテクニカル概況（指標＋レジーム＋戦略シグナル）をdictで返す"""
    df = indicators.calc_all(df)
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(latest["close"])
    rsi = float(latest["rsi"])
    adx = float(latest["adx"])
    is_jp = _is_jp(code)

    sig_a = int(strategy_alpha.signal(df).iloc[-1])
    sig_b = int(strategy_beta.signal(df).iloc[-1])
    sigs: list[str] = []
    if sig_a == 1:
        sigs.append("α買")
    elif sig_a == -1:
        sigs.append("α売")
    if sig_b == 1:
        sigs.append("β買")

    return {
        "コード": code,
        "銘柄名": name,
        "市場": "日本" if is_jp else "米国",
        "テーマ": " / ".join(universe.themes_of(code)),
        "終値": round(close, 2),
        "前日比%": round((close / float(prev["close"]) - 1) * 100, 2),
        "RSI": round(rsi, 0),
        "ADX": round(adx, 0),
        "レジーム": _regime(adx),
        "VWAP位置": "上" if close > float(latest["vwap"]) else "下",
        "シグナル": " / ".join(sigs) or "-",
    }


def overview(
    theme_filter: list[str] | None = None,
    data: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """ユニバース全銘柄のテクニカル概況テーブルを返す（スクリーナー相当）

    候補かどうかに関わらず全銘柄を返す。コードは市場→コード順にソート。

    Args:
        theme_filter: 対象テーマ名のリスト（Noneなら全テーマ）
        data: 事前取得済みの {コード: 日足DataFrame}（指定時は再取得しない）
    """
    targets = _resolve_targets(theme_filter)
    if data is None:
        data = batch_fetch(list(targets.keys()))

    rows = []
    for code, df in data.items():
        if code not in targets:
            continue
        try:
            r = _overview_row(code, targets[code], df)
            if r:
                rows.append(r)
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out["_jp"] = out["市場"].map({"日本": 0, "米国": 1})
    return (
        out.sort_values(["_jp", "コード"]).drop(columns="_jp").reset_index(drop=True)
    )
