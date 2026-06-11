"""
modules/strategy_alpha.py
戦略α：VWAP統合型 BB+RSIモメンタム反転

ロングエントリー（AND条件）:
  1. 終値 < ボリンジャーバンド下限 OR RSI < 25
  2. 終値 > VWAP
ショートエントリー（AND条件）:
  1. 終値 > ボリンジャーバンド上限 OR RSI > 75
  2. 終値 < VWAP
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings

NAME = "戦略α（VWAP+BB+RSI反転）"


def signal(df: pd.DataFrame) -> pd.Series:
    """戦略αのシグナルを返す（1=ロング, -1=ショート, 0=なし）

    入力: indicators.calc_all() 適用済みのDataFrame
    """
    close = df["close"]
    long_cond = (
        ((close < df["bb_lower"]) | (df["rsi"] < settings.RSI_OS_STRICT))
        & (close > df["vwap"])
    )
    short_cond = (
        ((close > df["bb_upper"]) | (df["rsi"] > settings.RSI_OB_STRICT))
        & (close < df["vwap"])
    )
    sig = pd.Series(0, index=df.index, dtype=int)
    sig[long_cond] = 1
    sig[short_cond] = -1
    return sig
