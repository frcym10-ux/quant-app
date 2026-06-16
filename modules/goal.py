"""
modules/goal.py
年内+100万円の目標を「進捗・必要ペース・実現可能性・ガードレール」で可視化する

ジャーナル（journal.py）の実績を使い、実績が少ないうちは仮定値（settings.ASSUMED_WIN_RATE,
REWARD_RISK）でペースを試算する。
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings
from modules import journal

MIN_TRADES_FOR_ACTUAL = 10  # この件数を超えたら実績の勝率・期待値を採用


def _parse(d: str) -> dt.date:
    return dt.date.fromisoformat(d)


def expectancy_per_trade_yen(st: dict) -> tuple[float, str]:
    """1トレードあたりの期待値（円）と、その根拠（実績/仮定）を返す"""
    risk_yen = settings.SWING_CAPITAL * settings.SWING_RISK_PERCENT
    if st["n_closed"] >= MIN_TRADES_FOR_ACTUAL and st["expectancy_yen"] is not None:
        return st["expectancy_yen"], f"実績（{st['n_closed']}トレード）"
    # 仮定: 期待R = 勝率×損益比 -(1-勝率)
    w = settings.ASSUMED_WIN_RATE
    b = settings.REWARD_RISK
    exp_r = w * b - (1 - w)
    return exp_r * risk_yen, f"仮定（勝率{w:.0%}・損益比{b:g}:1）"


def summary() -> dict:
    """目標ダッシュボード用の集計を返す"""
    st = journal.stats()
    today = dt.date.today()
    start = _parse(settings.GOAL_START)
    deadline = _parse(settings.GOAL_DEADLINE)

    goal = settings.GOAL_PROFIT
    realized = st["realized_pnl"]
    remaining = max(goal - realized, 0)
    progress = realized / goal if goal else 0

    days_left = max((deadline - today).days, 0)
    weeks_left = max(days_left / 7, 0.1)
    # 営業日換算（おおよそ平日のみ）
    trading_days_left = max(int(days_left * 5 / 7), 1)

    required_weekly = remaining / weeks_left if weeks_left else remaining
    required_monthly = required_weekly * 4.33

    exp_yen, exp_basis = expectancy_per_trade_yen(st)
    # 残り目標に必要なトレード数（期待値がプラスのときのみ算出可能）
    if exp_yen > 0:
        trades_needed = math.ceil(remaining / exp_yen)
        trades_per_week = trades_needed / weeks_left
    else:
        trades_needed = None
        trades_per_week = None

    # 月間ストップ判定
    month_pnl = journal.realized_pnl_in_month(today.year, today.month)
    stop_line = -settings.SWING_CAPITAL * settings.MONTHLY_STOP_PCT
    if month_pnl <= stop_line:
        guard = ("stop", f"今月の損失が停止ライン（{stop_line:,.0f}円）に到達。今月は新規エントリーを止めて見直しを。")
    elif month_pnl <= stop_line * 0.6:
        guard = ("warn", f"今月の損失が停止ラインの6割を超過。ペースを落として慎重に。")
    else:
        guard = ("ok", "資金は健全な範囲内です。")

    # 実現可能性の判定
    if exp_yen <= 0:
        feasibility = ("danger", "現在の想定では期待値がプラスになりません。手法の見直しが必要です。")
    elif trades_per_week is not None and trades_per_week > 4:
        feasibility = ("hard", f"必要ペースは週{trades_per_week:.1f}回。朝夕運用ではかなり挑戦的です。")
    elif trades_per_week is not None and trades_per_week > 2:
        feasibility = ("stretch", f"必要ペースは週{trades_per_week:.1f}回。集中すれば射程圏です。")
    else:
        feasibility = ("ok", f"必要ペースは週{trades_per_week:.1f}回。現実的な範囲です。")

    return {
        "goal": goal,
        "realized": realized,
        "remaining": remaining,
        "progress": progress,
        "days_left": days_left,
        "weeks_left": weeks_left,
        "trading_days_left": trading_days_left,
        "required_weekly": required_weekly,
        "required_monthly": required_monthly,
        "expectancy_yen": exp_yen,
        "expectancy_basis": exp_basis,
        "trades_needed": trades_needed,
        "trades_per_week": trades_per_week,
        "month_pnl": month_pnl,
        "stop_line": stop_line,
        "guard": guard,
        "feasibility": feasibility,
        "stats": st,
    }
