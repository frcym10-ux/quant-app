"""
tools/backtest_screener.py
週次スクリーナー6プリセットのヒストリカル検証CLI

使い方:
    python tools/backtest_screener.py          # 全6プリセットを2年で検証
    python tools/backtest_screener.py ⑥ 3y    # プリセット⑥だけを3年で検証
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules import screener, screener_backtest  # noqa: E402


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
    args = sys.argv[1:]
    valid_ids = list(screener.PRESET_NAMES.keys())
    keys = [a for a in args if a in valid_ids] or valid_ids
    period = next((a for a in args if a not in valid_ids), "2y")

    results = screener_backtest.backtest_all_presets(period=period, presets=keys)
    for pid in keys:
        per_symbol, overall = results[pid]
        print(f"\n===== {screener.PRESET_NAMES[pid]}（期間 {period}） =====")
        print(_fmt_overall(overall))
        if not per_symbol.empty:
            print("\n  銘柄別（累計R上位10）:")
            print(per_symbol.head(10).to_string(index=False))

    print(
        "\n注: Rは1トレードあたりのリスク倍率（損切り=-1R）。この検証は財務指標を遡って"
        "取得できないためチャート・テクニカル条件のみの有効性を測ったものです"
        "（ROE・PER・配当・経常利益成長率の条件は毎回「未取得」扱いで素通りしています）。"
        "エントリーはシグナル翌営業日の始値と仮定した簡略化モデルです。"
    )


if __name__ == "__main__":
    main()
