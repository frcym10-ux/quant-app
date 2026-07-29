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


def calc_shares(
    entry: float,
    sl: float,
    fx: float = 1.0,
    max_risk_yen: float | None = None,
    max_position_yen: float | None = None,
    available_cash: float | None = None,
) -> int:
    """スイング候補の購入株数を「3つの制約の最小値」で算出する（修正1・修正5）

    株数 = min(
        リスク上限から算出（1トレードの最大損失 MAX_RISK_YEN 以内に収める）,
        1銘柄への投資額上限（MAX_POSITION_YEN）から算出,
        利用可能資金（AVAILABLE_CASH）から算出,
    )
    いずれかの制約で0株になる場合は0を返す（＝現在の設定では購入不可）。

    Args:
        entry: エントリー価格（現地通貨建て）
        sl: 損切り価格（現地通貨建て）
        fx: 現地通貨→円の為替レート（日本株は1.0、米国株はUSD/JPY）
    Returns:
        購入株数（切り捨て・0以上の整数）
    """
    max_risk_yen = settings.MAX_RISK_YEN if max_risk_yen is None else max_risk_yen
    max_position_yen = settings.MAX_POSITION_YEN if max_position_yen is None else max_position_yen
    available_cash = settings.AVAILABLE_CASH if available_cash is None else available_cash

    per_share_risk_yen = (entry - sl) * fx  # 1株あたりの損失（円）
    price_yen = entry * fx                  # 1株あたりの投資額（円）
    if per_share_risk_yen <= 0 or price_yen <= 0:
        return 0

    shares_by_risk = math.floor(max_risk_yen / per_share_risk_yen)      # リスク上限
    shares_by_position = math.floor(max_position_yen / price_yen)       # 1銘柄投資額上限
    shares_by_cash = math.floor(available_cash / price_yen)             # 資金上限
    return int(max(min(shares_by_risk, shares_by_position, shares_by_cash), 0))
