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


def _fmt_by_year(by_year: dict) -> str:
    """年別のトレード成績を1行ずつ整形する（直近の相場でエッジが劣化していないか確認用）"""
    if not by_year:
        return ""
    lines = ["\n  年別（直近の相場でエッジが落ちていないか確認）:"]
    for year, s in by_year.items():
        pf = "∞" if s["profit_factor"] == float("inf") else f"{s['profit_factor']:.2f}"
        lines.append(
            f"    {year}: {s['n_trades']:>3}件　勝率{s['win_rate']*100:5.1f}%　"
            f"期待値{s['expectancy_r']:+.3f}R　PF{pf}"
        )
    return "\n".join(lines)


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
        print(_fmt_by_year(overall.get("by_year", {})))
        if not per_symbol.empty:
            print("\n  銘柄別（累計R上位10）:")
            print(per_symbol.head(10).to_string(index=False))

    print(
        "\n注: Rは1トレードあたりのリスク倍率（損切り=-1R）。この検証は財務指標を遡って"
        "取得できないためチャート・テクニカル条件のみの有効性を測ったものです"
        "（ROE・PER・配当・経常利益成長率の条件は毎回「未取得」扱いで素通りしています）。"
        "エントリーはシグナル翌営業日の始値と仮定した簡略化モデルです。"
        "\n複数年の平均は『良い年と悪い年を均した数字』なので、年別の直近1〜2年が"
        "全体平均より弱くなっていないか（アルゴ取引の高速化・地政学リスク等で"
        "相場の性質が変わっていないか）も必ず確認すること。"
    )


if __name__ == "__main__":
    main()
