"""
tests/test_backtest.py
backtest モジュールのユニットテスト（合成データ・ネットワーク不要）

実行: python tests/test_backtest.py  または  pytest tests/test_backtest.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules import backtest


def _ohlc(closes, highs=None, lows=None):
    """終値リストから日足DataFrameを作る（high/low未指定なら終値±0）"""
    n = len(closes)
    dates = pd.bdate_range("2024-01-01", periods=n)
    closes = np.array(closes, dtype=float)
    highs = np.array(highs, dtype=float) if highs is not None else closes.copy()
    lows = np.array(lows, dtype=float) if lows is not None else closes.copy()
    return pd.DataFrame({
        "date": dates, "open": closes, "high": highs,
        "low": lows, "close": closes, "volume": np.full(n, 1_000_000.0),
    })


def test_summarize_basic():
    """summarize の勝率・PF・最大DDが正しいこと"""
    trades = [{"r": 1.5, "hold": 3}, {"r": -1.0, "hold": 2}, {"r": -1.0, "hold": 1}, {"r": 1.5, "hold": 4}]
    s = backtest.summarize(trades)
    assert s["n_trades"] == 4
    assert abs(s["win_rate"] - 0.5) < 1e-9
    # PF = 勝ち合計3.0 / 負け合計2.0 = 1.5
    assert abs(s["profit_factor"] - 1.5) < 1e-9
    # equity: 1.5, 0.5, -0.5, 1.0 → peak1.5, 谷-0.5 → 最大DD=2.0
    assert abs(s["max_drawdown_r"] - 2.0) < 1e-9
    assert abs(s["total_r"] - 1.0) < 1e-9
    print("test_summarize_basic OK")


def test_summarize_empty():
    s = backtest.summarize([])
    assert s["n_trades"] == 0 and s["total_r"] == 0.0
    print("test_summarize_empty OK")


def test_engine_tp_and_sl():
    """エンジンが TP / SL を正しく検出し、Rの符号が正しいこと"""
    # 注入シグナル戦略: index30で1（ロング）を出す（n>=40の内部ガードを満たす長さで）
    def fake_signal(df):
        s = pd.Series(0, index=df.index, dtype=int)
        s.iloc[30] = 1
        return s

    strat = backtest.Strategy("fake", "テスト戦略", fake_signal)

    # 終値は一定でも high/low にスプレッドを持たせ ATR>0 にする（仕掛け成立の前提）
    closes = [100.0] * 50
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    df = _ohlc(closes, highs, lows)
    df.loc[32, "high"] = 1000  # 確実にTP到達
    trades = backtest.backtest_symbol(df, strat, max_hold=10)
    assert len(trades) == 1, trades
    t = trades[0]
    assert t["reason"] == "TP", t
    assert t["r"] > 0, t
    print("test_engine_tp_and_sl OK (TP)")

    # 下落でSLヒット
    df2 = _ohlc(closes, highs, lows)
    df2.loc[32, "low"] = 1  # 確実にSL到達
    trades2 = backtest.backtest_symbol(df2, strat, max_hold=10)
    assert len(trades2) == 1
    assert trades2[0]["reason"] == "SL"
    assert abs(trades2[0]["r"] + 1.0) < 0.05, trades2  # 損切りは約-1R
    print("test_engine_tp_and_sl OK (SL)")


def test_no_lookahead_entry_next_open():
    """エントリーがシグナル足の翌足始値で行われること"""
    def fake_signal(df):
        s = pd.Series(0, index=df.index, dtype=int)
        s.iloc[30] = 1
        return s

    strat = backtest.Strategy("fake", "テスト", fake_signal)
    closes = [100.0] * 50
    df = _ohlc(closes, [c + 1 for c in closes], [c - 1 for c in closes])
    df.loc[31, "open"] = 105.0      # 翌足始値
    df.loc[32, "high"] = 100000.0   # TP到達させる
    trades = backtest.backtest_symbol(df, strat, max_hold=10)
    assert trades[0]["entry"] == 105.0, trades  # index31のopenで入っている
    print("test_no_lookahead_entry_next_open OK")


if __name__ == "__main__":
    test_summarize_basic()
    test_summarize_empty()
    test_engine_tp_and_sl()
    test_no_lookahead_entry_next_open()
    print("\nALL backtest tests passed ✅")
