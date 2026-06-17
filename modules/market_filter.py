"""
modules/market_filter.py
全体相場のレジーム（順風／逆風）を判定する市場フィルター

長期インデックス（日経225・S&P500）が200日移動平均線の上にあるかで、
「リスクオン（順張りロングが報われやすい）」か「リスクオフ（逆風）」かを判定する。
ロング偏重のスイングでは、全体相場が下落基調のときにエントリーを控えるだけで
成績の安定性が大きく改善する（"don't fight the tape"）。

判定:
  🟢 順風   : 指数 > 200日線 かつ 指数 > 50日線（短期も長期も上）
  🟡 中立   : 指数 > 200日線 だが 50日線割れ（短期調整中）
  🔴 逆風   : 指数 < 200日線（長期下落基調 → 新規ロングは慎重に）
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 市場区分 -> (yfinanceシンボル, 表示名)
INDICES: dict[str, tuple[str, str]] = {
    "日本": ("^N225", "日経225"),
    "米国": ("^GSPC", "S&P500"),
}

SMA_LONG = 200   # 長期トレンドの基準
SMA_MID = 50     # 短期トレンドの基準


def _fetch_close(symbol: str, period: str = "2y") -> pd.Series | None:
    """指数の終値シリーズを取得する（失敗時はNone）"""
    try:
        import yfinance as yf
        raw = yf.download(symbol, period=period, auto_adjust=True, progress=False)
        if raw is None or raw.empty:
            return None
        close = raw["Close"]
        if hasattr(close, "columns"):  # MultiIndex列なら1列目
            close = close.iloc[:, 0]
        return close.dropna()
    except Exception:
        return None


def _status_from_close(close: pd.Series) -> dict | None:
    """終値シリーズから市場ステータスdictを組み立てる"""
    if close is None or len(close) < SMA_MID + 5:
        return None
    last = float(close.iloc[-1])
    sma_mid = float(close.rolling(SMA_MID).mean().iloc[-1])
    # 200日分なければ取得できた範囲の最長SMAで代替する
    long_window = SMA_LONG if len(close) >= SMA_LONG else len(close)
    sma_long = float(close.rolling(long_window).mean().iloc[-1])

    above_long = last >= sma_long
    above_mid = last >= sma_mid

    if above_long and above_mid:
        light, trend = "🟢", "順風（リスクオン）"
        comment = "指数は短期・長期の移動平均線の上。新規ロングが報われやすい環境です。"
    elif above_long and not above_mid:
        light, trend = "🟡", "中立（短期調整中）"
        comment = "長期は上昇基調だが短期は調整中。エントリーは厳選し、株数も控えめに。"
    else:
        light, trend = "🔴", "逆風（リスクオフ）"
        comment = "指数が200日線を割れた下落基調。新規ロングは見送りか、ごく小さく。"

    return {
        "light": light,
        "trend": trend,
        "comment": comment,
        "close": round(last, 2),
        "sma_mid": round(sma_mid, 2),
        "sma_long": round(sma_long, 2),
        "above_mid": above_mid,
        "above_long": above_long,
        "sma_long_window": long_window,
    }


def market_status() -> dict[str, dict]:
    """各市場（日本・米国）の相場ステータスを返す

    Returns:
        {"日本": {light, trend, comment, close, sma_mid, sma_long, ...}, "米国": {...}}
        取得失敗した市場はキーを欠く（呼び出し側は .get で扱うこと）。
    """
    out: dict[str, dict] = {}
    for market, (symbol, name) in INDICES.items():
        status = _status_from_close(_fetch_close(symbol))
        if status is not None:
            status["name"] = name
            status["symbol"] = symbol
            out[market] = status
    return out


def light_of(market: str, status: dict[str, dict] | None) -> str:
    """市場区分（日本/米国）の信号（🟢🟡🔴）を返す。不明なら空文字"""
    if not status:
        return ""
    return (status.get(market) or {}).get("light", "")


def is_risk_off(market: str, status: dict[str, dict] | None) -> bool:
    """その市場が逆風（リスクオフ）かどうかを返す"""
    return light_of(market, status) == "🔴"
