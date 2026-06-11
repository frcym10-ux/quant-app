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
from modules import data_fetcher, indicators, strategy_alpha, strategy_beta

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
