"""
modules/strategy_beta.py
戦略β：ケルトナーチャネル+ADX 自己適応型平均回帰

レジーム判定（最優先）: ADX14 >= 20 ならシグナルをブロック
ロングエントリー（AND条件）:
  1. ADX < 20（レンジ相場）
  2. 終値 <= ケルトナーチャネル下限
  3. RSI <= 30 かつ 強気ダイバージェンス（価格安値更新 & RSI切り上がり）
エグジット: ケルトナーチャネル中央線（EMA20）回帰 or 反対バンド到達
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings

NAME = "戦略β（Keltner+ADX平均回帰）"

DIVERGENCE_LOOKBACK = 20  # ダイバージェンス判定の遡及期間（営業日）


def detect_bullish_divergence(df: pd.DataFrame, lookback: int = DIVERGENCE_LOOKBACK) -> pd.Series:
    """強気ダイバージェンスを検出する

    直近lookback期間内で価格が安値を更新したのに、RSIは前回安値時より切り上がっている状態。
    """
    low = df["low"]
    rsi = df["rsi"]
    result = pd.Series(False, index=df.index)
    for i in range(lookback, len(df)):
        window_low = low.iloc[i - lookback : i]
        prev_min_pos = window_low.idxmin()
        # 価格は安値更新、RSIは切り上がり
        if low.iloc[i] < window_low.min() and rsi.iloc[i] > rsi.loc[prev_min_pos]:
            result.iloc[i] = True
    return result


def signal(df: pd.DataFrame) -> pd.Series:
    """戦略βのシグナルを返す（1=ロング, 0=なし）

    入力: indicators.calc_all() 適用済みのDataFrame
    """
    in_range = df["adx"] < settings.ADX_RANGE_THRESHOLD
    touch_lower = df["close"] <= df["kc_lower"]
    oversold = df["rsi"] <= settings.RSI_OVERSOLD
    divergence = detect_bullish_divergence(df)

    sig = pd.Series(0, index=df.index, dtype=int)
    sig[in_range & touch_lower & oversold & divergence] = 1
    return sig


def exit_signal(df: pd.DataFrame) -> pd.Series:
    """戦略βのエグジットシグナルを返す（True=手仕舞い）

    ケルトナーチャネル中央線（EMA20）回帰 or 反対バンド（上限）到達。
    """
    return (df["close"] >= df["kc_mid"]) | (df["close"] >= df["kc_upper"])
