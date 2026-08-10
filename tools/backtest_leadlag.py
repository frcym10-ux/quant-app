"""
tools/backtest_leadlag.py
米セクター→日本ETF リードラグ戦略（modules/sector_leadlag.py）のヒストリカル検証CLI

指示書ステップ5: 期待値R>0 かつ PF>1.3（コスト控除後）を合格基準とし、
2015〜2023と2024年以降を分けて検証する（レジーム依存の点検）。

使い方:
    python tools/backtest_leadlag.py
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules import backtest, sector_leadlag  # noqa: E402

PERIODS = {
    "2015-2023": ("2015-01-01", "2023-12-31"),
    "2024以降": ("2024-01-01", None),
}


def _fetch(symbol: str, start: str, end: str | None) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False)
    if raw is None or raw.empty:
        raise RuntimeError(f"取得失敗: {symbol}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.droplevel(1)
    df = raw.reset_index().rename(columns={
        "Date": "date", "Open": "open", "High": "high",
        "Low": "low", "Close": "close", "Volume": "volume",
    })[["date", "open", "high", "low", "close", "volume"]]
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    return df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)


def _fmt(o: dict) -> str:
    if o["n_trades"] == 0:
        return "  トレードなし（シグナル未発生 or データ不足）"
    pf = "∞" if o["profit_factor"] == float("inf") else f"{o['profit_factor']:.2f}"
    return (
        f"  トレード数 {o['n_trades']}　勝率 {o['win_rate']*100:.1f}%　"
        f"期待値 {o['expectancy_r']:+.3f}R／回（コスト控除後）　PF {pf}\n"
        f"  最大ドローダウン {o['max_drawdown_r']:.1f}R　累計 {o['total_r']:+.1f}R"
    )


def main() -> None:
    for label, (start, end) in PERIODS.items():
        print(f"\n===== {label} =====")
        all_trades: list[dict] = []
        for code, m in sector_leadlag.MAPPING.items():
            try:
                us_df = _fetch(m["us_symbol"], start, end)
                jp_df = _fetch(f"{code}.T", start, end)
            except Exception as e:
                print(f"  {code}（{m['name']}）: データ取得失敗 - {e}")
                continue
            trades = sector_leadlag.backtest_pair(us_df, jp_df, code, m["name"])
            all_trades.extend(trades)
            s = backtest.summarize(trades)
            print(f"  {code}（{m['name']}）: ", _fmt(s).strip())
        overall = backtest.summarize(all_trades)
        print(f"\n  [{label} 全体]")
        print(_fmt(overall))

    print(
        "\n注: Rは1トレードあたりのリスク倍率（損切り=-1R）。コスト（往復"
        f"{sector_leadlag.settings.LEADLAG_ROUNDTRIP_COST_PCT:.1%}）控除後。"
        "期待値R>0かつPF>1.3が両期間で成立しなければ本採用しない。"
    )


if __name__ == "__main__":
    main()
