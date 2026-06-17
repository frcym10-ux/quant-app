"""
modules/backtest.py
戦略α/βのヒストリカル検証（イベントドリブン・バックテスト）

各戦略のシグナル（indicators.calc_all 済みのDataFrameに対する1=ロング）を使い、
ATRベースのSL/TPで仕掛け→手仕舞いをシミュレートして、実績ベースの
勝率・期待値（Rマルチプル）・プロフィットファクター・最大ドローダウンを算出する。

設計上の注意（先読みバイアスの排除）:
  - シグナルは「その足の終値」で確定し、エントリーは「翌足の始値」で行う
  - SL/TPの当日内ヒット判定は、安全側（SL優先）で評価する
  - 1銘柄につき同時に1ポジションのみ（手仕舞い後に次のシグナルを取る）

Rマルチプル: r = (決済値 - エントリー) / (エントリー - SL)。通貨に依存しない。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings
from modules import indicators, risk_manager, strategy_alpha, strategy_beta

MAX_HOLD_DAYS = 20  # 最大保有営業日数（タイムストップ）


@dataclass
class Strategy:
    """バックテスト対象の戦略定義"""
    key: str
    name: str
    signal_fn: callable                 # (df) -> pd.Series（1=ロング）
    exit_fn: callable | None = None     # (df) -> pd.Series（True=手仕舞い）


STRATEGIES: dict[str, Strategy] = {
    "alpha": Strategy("alpha", strategy_alpha.NAME, lambda df: strategy_alpha.signal(df)),
    "beta": Strategy(
        "beta", strategy_beta.NAME,
        lambda df: strategy_beta.signal(df),
        lambda df: strategy_beta.exit_signal(df),
    ),
}


def backtest_symbol(
    df: pd.DataFrame,
    strategy: Strategy,
    *,
    sl_mult: float = settings.ATR_SL_MULTIPLIER,
    tp_mult: float = settings.ATR_TP_MULTIPLIER,
    max_hold: int = MAX_HOLD_DAYS,
) -> list[dict]:
    """1銘柄の日足に戦略を適用してトレード一覧を返す

    Args:
        df: date/open/high/low/close/volume を持つ日足DataFrame
        strategy: 対象戦略
    Returns:
        各トレードの dict（entry/exit/r/reason/hold/dates）のリスト
    """
    df = indicators.calc_all(df).reset_index(drop=True)
    n = len(df)
    if n < 40:
        return []
    sig = strategy.signal_fn(df).reset_index(drop=True)
    exits = strategy.exit_fn(df).reset_index(drop=True) if strategy.exit_fn else None

    trades: list[dict] = []
    i = 0
    while i < n - 1:
        if int(sig.iloc[i]) != 1:
            i += 1
            continue

        # エントリーは翌足の始値（先読み回避）。SLは当日終値のATRで設定
        entry_idx = i + 1
        entry = float(df.at[entry_idx, "open"])
        atr = float(df.at[i, "atr"])
        if atr <= 0 or entry <= 0:
            i += 1
            continue
        sl, tp = risk_manager.calc_sl_tp(entry, atr, 1)
        if entry <= sl:
            i += 1
            continue

        exit_idx = exit_price = reason = None
        for j in range(entry_idx, min(entry_idx + max_hold, n)):
            lo = float(df.at[j, "low"])
            hi = float(df.at[j, "high"])
            if lo <= sl:                      # 安全側: 損切り優先
                exit_idx, exit_price, reason = j, sl, "SL"
                break
            if hi >= tp:
                exit_idx, exit_price, reason = j, tp, "TP"
                break
            if exits is not None and bool(exits.iloc[j]):
                exit_idx, exit_price, reason = j, float(df.at[j, "close"]), "EXIT"
                break
        if exit_idx is None:                  # タイムストップ
            exit_idx = min(entry_idx + max_hold, n - 1)
            exit_price, reason = float(df.at[exit_idx, "close"]), "TIME"

        r = (exit_price - entry) / (entry - sl)
        trades.append({
            "entry_date": df.at[entry_idx, "date"],
            "exit_date": df.at[exit_idx, "date"],
            "entry": round(entry, 2),
            "exit": round(exit_price, 2),
            "r": round(r, 3),
            "reason": reason,
            "hold": int(exit_idx - entry_idx),
        })
        i = exit_idx + 1   # 手仕舞いの翌足から次のシグナルを探す
    return trades


def summarize(trades: list[dict]) -> dict:
    """トレード一覧から成績指標を集計する

    Returns:
        n_trades, win_rate, avg_r, expectancy_r, profit_factor,
        max_drawdown_r, avg_hold, gross_win_r, gross_loss_r
    """
    n = len(trades)
    if n == 0:
        return {
            "n_trades": 0, "win_rate": None, "avg_r": None, "expectancy_r": None,
            "profit_factor": None, "max_drawdown_r": None, "avg_hold": None,
            "total_r": 0.0,
        }
    rs = [t["r"] for t in trades]
    wins = [x for x in rs if x > 0]
    losses = [x for x in rs if x <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)

    # Rベースのエクイティカーブから最大ドローダウン
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in rs:
        equity += x
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    return {
        "n_trades": n,
        "win_rate": len(wins) / n,
        "avg_r": sum(rs) / n,
        "expectancy_r": sum(rs) / n,           # 1トレードあたり平均R = 期待値
        "profit_factor": profit_factor,
        "max_drawdown_r": max_dd,
        "avg_hold": sum(t["hold"] for t in trades) / n,
        "total_r": sum(rs),
        "gross_win_r": gross_win,
        "gross_loss_r": gross_loss,
    }


def backtest_universe(
    strategy_key: str = "alpha",
    data: dict[str, pd.DataFrame] | None = None,
    period: str = "2y",
    names: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """ユニバース全銘柄に戦略を適用し、銘柄別成績と全体集計を返す

    Args:
        strategy_key: "alpha" または "beta"
        data: 事前取得済みの {コード: 日足DataFrame}（Noneならswing_scannerで取得）
        period: dataがNoneのときの取得期間
        names: コード -> 銘柄名（表示用）
    Returns:
        (銘柄別成績DataFrame, 全体集計dict)
    """
    if strategy_key not in STRATEGIES:
        raise ValueError(f"未知の戦略: {strategy_key}")
    strategy = STRATEGIES[strategy_key]

    if data is None:
        from modules import swing_scanner, universe
        names = names or universe.all_codes()
        data = swing_scanner.batch_fetch(list(names.keys()), period=period)
    names = names or {}

    all_trades: list[dict] = []
    rows = []
    for code, df in data.items():
        try:
            trades = backtest_symbol(df, strategy)
        except Exception:
            continue
        all_trades.extend(trades)
        s = summarize(trades)
        if s["n_trades"] == 0:
            continue
        rows.append({
            "コード": code,
            "銘柄名": names.get(code, code),
            "トレード数": s["n_trades"],
            "勝率": round(s["win_rate"] * 100, 1),
            "期待値R": round(s["expectancy_r"], 3),
            "PF": round(s["profit_factor"], 2) if s["profit_factor"] != float("inf") else 99.0,
            "最大DD_R": round(s["max_drawdown_r"], 2),
            "累計R": round(s["total_r"], 2),
        })

    overall = summarize(all_trades)
    overall["strategy"] = strategy.name
    per_symbol = (
        pd.DataFrame(rows).sort_values("累計R", ascending=False).reset_index(drop=True)
        if rows else pd.DataFrame()
    )
    return per_symbol, overall
