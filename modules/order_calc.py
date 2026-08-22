"""
modules/order_calc.py
指値・利確・損切り・建玉額の自動計算（指示書ステップ6-3）

合格銘柄ごとに、ATRベースで注文水準を自動算出する。オーナーはこの数値を見て
iSPEED（楽天証券アプリ）で手動発注する。注文入力は自動化しない方針。

  日足スイング（プリセット①②③④）: 損切り = Entry - 2×ATR / 利確 = Entry + 4×ATR（R:R 1:2）
  週足中期（プリセット⑤⑥）       : 損切り = Entry - 3×ATR / 利確 = Entry + 6×ATR（R:R 1:2）

株数は単元100株固定を基本とし、建玉額 = Entry × 100 を計算する。
建玉額が余力を超える値がさ銘柄は「かぶミニ扱い（成行のみ・逆指値/OCO不可）」と注記する。
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings

LOT_SIZE = 100  # 単元株数

# ===== ATR倍率（R:R はいずれも 1:2） =====
DAILY_SL_ATR_MULT = 2.0
DAILY_TP_ATR_MULT = 4.0
WEEKLY_SL_ATR_MULT = 3.0
WEEKLY_TP_ATR_MULT = 6.0

# ===== エントリー目安 =====
PULLBACK_ENTRY_PCT = 0.03  # 押し目型: 現在値から-3%付近を指値
BREAK_ENTRY_PCT = 0.01     # ブレイク型: 直近高値+1%を逆指値


def calc_order(
    price: float,
    atr: float,
    preset: str = "weekly",
    entry_style: str = "pullback",
    recent_high: float | None = None,
    available_cash: float | None = None,
    lot: int = LOT_SIZE,
) -> dict:
    """1銘柄の注文水準（指値・損切り・利確・建玉額）を算出して返す

    Args:
        price: 現在値
        atr: ATR(14)
        preset: "daily"（日足①〜④）または "weekly"（週足⑤⑥）。SL/TP幅が変わる
        entry_style: "pullback"（押し目・指値）または "break"（ブレイク・逆指値）
        recent_high: ブレイク型のときの直近高値（省略時は現在値を使用）
        available_cash: 利用可能資金（円）。省略時は settings.AVAILABLE_CASH
        lot: 単元株数（既定100）
    Returns:
        entry / stop / take / rr / shares / notional / kabumini / note を持つdict
    """
    available_cash = settings.AVAILABLE_CASH if available_cash is None else available_cash

    # --- エントリー指値の目安 ---
    if entry_style == "break":
        base = recent_high if recent_high else price
        entry = round(base * (1 + BREAK_ENTRY_PCT), 1)
    else:  # pullback
        entry = round(price * (1 - PULLBACK_ENTRY_PCT), 1)

    # --- SL / TP（プリセットで幅を切り替え。R:R は 1:2） ---
    if preset == "weekly":
        sl_mult, tp_mult = WEEKLY_SL_ATR_MULT, WEEKLY_TP_ATR_MULT
    else:
        sl_mult, tp_mult = DAILY_SL_ATR_MULT, DAILY_TP_ATR_MULT
    stop = round(entry - sl_mult * atr, 1)
    take = round(entry + tp_mult * atr, 1)

    risk = entry - stop
    reward = take - entry
    rr = round(reward / risk, 2) if risk > 0 else None

    # --- 建玉額と、かぶミニ（単元未満株）判定 ---
    notional = round(entry * lot, 0)   # 単元100株での建玉額
    kabumini = notional > available_cash
    if kabumini:
        # 100株で余力を超える値がさ銘柄は、かぶミニでしか買えない＝成行のみ
        max_kabu = int(math.floor(available_cash / entry)) if entry > 0 else 0
        note = (
            f"かぶミニ扱い（{lot}株={notional:,.0f}円 > 余力{available_cash:,.0f}円）。"
            f"かぶミニは成行のみ・逆指値/OCO不可。買えても最大 約{max_kabu}株。"
        )
    else:
        note = f"単元{lot}株で建玉 約{notional:,.0f}円（余力{available_cash:,.0f}円以内）"

    return {
        "entry": entry,
        "stop": stop,
        "take": take,
        "rr": rr,
        "shares": lot,
        "notional": notional,
        "kabumini": kabumini,
        "note": note,
    }
