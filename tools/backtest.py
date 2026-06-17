"""
tools/backtest.py
戦略α/βをユニバース全銘柄で過去検証し、成績をターミナルに出力するCLI

使い方:
    python tools/backtest.py            # α・β両方を2年で検証
    python tools/backtest.py alpha 3y   # 戦略αを3年で検証
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules import backtest  # noqa: E402


def _fmt_overall(o: dict) -> str:
    if o["n_trades"] == 0:
        return "  トレードなし（シグナル未発生）"
    pf = "∞" if o["profit_factor"] == float("inf") else f"{o['profit_factor']:.2f}"
    return (
        f"  トレード数 {o['n_trades']}　勝率 {o['win_rate']*100:.1f}%　"
        f"期待値 {o['expectancy_r']:+.3f}R／回　PF {pf}\n"
        f"  最大ドローダウン {o['max_drawdown_r']:.1f}R　"
        f"累計 {o['total_r']:+.1f}R　平均保有 {o['avg_hold']:.1f}営業日"
    )


def main() -> None:
    args = [a for a in sys.argv[1:]]
    keys = [a for a in args if a in backtest.STRATEGIES] or ["alpha", "beta"]
    period = next((a for a in args if a not in backtest.STRATEGIES), "2y")

    for key in keys:
        strat = backtest.STRATEGIES[key]
        print(f"\n===== {strat.name}（期間 {period}） =====")
        per_symbol, overall = backtest.backtest_universe(key, period=period)
        print(_fmt_overall(overall))
        if not per_symbol.empty:
            print("\n  銘柄別（累計R上位10）:")
            print(per_symbol.head(10).to_string(index=False))
    print(
        "\n注: Rは1トレードあたりのリスク倍率（損切り=-1R, 利確≈+1.5R）。"
        "期待値R>0かつPF>1.3、最大DDが許容範囲なら実運用の検討余地あり。"
    )


if __name__ == "__main__":
    main()
