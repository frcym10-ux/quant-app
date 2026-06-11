"""
modules/risk_manager.py
ATRベースのリスク管理（ストップロス / テイクプロフィット / ポジションサイジング）

SL_long = エントリー価格 - (2 × ATR14)
TP_long = エントリー価格 + (3 × ATR14)
ポジションサイズ = (口座資金 × リスク率) / |エントリー価格 - SL価格|
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings


def calc_sl_tp(entry: float, atr: float, direction: int) -> tuple[float, float]:
    """ATRベースのストップロス・テイクプロフィット価格を計算して返す

    Args:
        entry: エントリー価格
        atr: ATR14の値
        direction: 1=ロング, -1=ショート
    Returns:
        (SL価格, TP価格)
    """
    sl_width = settings.ATR_SL_MULTIPLIER * atr
    tp_width = settings.ATR_TP_MULTIPLIER * atr
    if direction >= 0:
        return entry - sl_width, entry + tp_width
    return entry + sl_width, entry - tp_width


def calc_position_size(
    account: float = settings.ACCOUNT_CAPITAL,
    risk_pct: float = settings.RISK_PERCENT,
    entry: float = 0.0,
    sl: float = 0.0,
) -> float:
    """ATRポジションサイジングで購入株数を計算する（切り捨て）

    リスク金額 = 口座資金 × リスク率
    株数 = リスク金額 / |エントリー価格 - SL価格|
    """
    risk_amount = account * risk_pct
    per_share_risk = abs(entry - sl)
    if per_share_risk <= 0:
        return 0.0
    return float(math.floor(risk_amount / per_share_risk))
