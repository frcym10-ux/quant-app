"""
tests/test_sector_leadlag.py
sector_leadlag モジュールのユニットテスト（合成データ・ネットワーク不要）

実行: python tests/test_sector_leadlag.py  または  pytest tests/test_sector_leadlag.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules import sector_leadlag


def _ohlc(closes, opens=None, highs=None, lows=None, start="2024-01-01"):
    n = len(closes)
    dates = pd.bdate_range(start, periods=n)
    closes = np.array(closes, dtype=float)
    opens = np.array(opens, dtype=float) if opens is not None else closes.copy()
    highs = np.array(highs, dtype=float) if highs is not None else closes.copy()
    lows = np.array(lows, dtype=float) if lows is not None else closes.copy()
    return pd.DataFrame({
        "date": dates, "open": opens, "high": highs,
        "low": lows, "close": closes, "volume": np.full(n, 1_000_000.0),
    })


def test_decide_entry_gap_up_uses_pullback_limit():
    """寄りギャップが閾値以上なら押し目待ち＝前日終値と寄値の中間に指値"""
    mode, entry = sector_leadlag.decide_entry(prev_close=100.0, open_=104.0)  # +4%ギャップ
    assert mode == "押し目待ち"
    assert abs(entry - 102.0) < 1e-9
    print("test_decide_entry_gap_up_uses_pullback_limit OK")


def test_decide_entry_small_gap_uses_breakout_stop():
    """寄りギャップが小さければブレイク待ち＝前日終値で逆指値"""
    mode, entry = sector_leadlag.decide_entry(prev_close=100.0, open_=100.5)  # +0.5%
    assert mode == "ブレイク待ち"
    assert abs(entry - 100.0) < 1e-9
    print("test_decide_entry_small_gap_uses_breakout_stop OK")


def test_us_return():
    us_df = _ohlc([100, 100, 103])
    assert abs(sector_leadlag.us_return(us_df) - 0.03) < 1e-9
    assert sector_leadlag.us_return(_ohlc([100])) is None
    print("test_us_return OK")


def test_scan_candidates_filters_below_threshold():
    """米前日リターンが閾値未満のセクターは候補に出ないこと"""
    us_data = {
        "^SOX": _ohlc([100, 100, 103]),   # +3% -> 候補
        "ITA": _ohlc([100, 100, 100.5]),  # +0.5% -> 候補外
        "XLU": _ohlc([100, 100, 100.5]),
    }
    jp_data = {
        "2644": _ohlc([1000, 1000], opens=[1000, 1010]),
        "513A": _ohlc([500, 500], opens=[500, 501]),
        "1627": _ohlc([2000, 2000], opens=[2000, 2001]),
    }
    out = sector_leadlag.scan_candidates(us_data, jp_data)
    codes = {c["コード"] for c in out}
    assert codes == {"2644"}, out
    print("test_scan_candidates_filters_below_threshold OK")


def test_backtest_pair_breakout_tp():
    """ブレイク待ちで約定しTPに到達するケースでプラスRのトレードが記録されること"""
    n = 60
    us_closes = [100.0] * n
    us_closes[40] = 103.0  # +3%リターン発生（日付一致でJP側に拾わせる）
    us_df = _ohlc(us_closes, start="2024-01-01")

    jp_closes = [1000.0] * n
    # 通常日は毎日±5のレンジを持たせ、ATRが極端に小さくならないようにする
    jp_highs = [c + 5 for c in jp_closes]
    jp_lows = [c - 5 for c in jp_closes]
    jp_df = _ohlc(jp_closes, highs=jp_highs, lows=jp_lows, start="2024-01-01")
    # US側のシグナル発生日の翌営業日のJP足でブレイク（高値が前日終値を上抜けるが、TPには届かない）
    trigger_us_date = us_df.at[40, "date"]
    jp_idx = jp_df.index[jp_df["date"] > trigger_us_date][0]
    jp_df.loc[jp_idx, "high"] = 1002.0      # 前日終値1000を上抜けて約定（TP到達には届かない幅）
    jp_df.loc[jp_idx + 1, "high"] = 5000.0  # 翌日TPに到達

    trades = sector_leadlag.backtest_pair(us_df, jp_df, "2644", "テスト")
    assert len(trades) >= 1, trades
    t = trades[0]
    assert t["mode"] == "ブレイク待ち", t
    assert t["reason"] == "TP", t
    assert t["exit_date"] > t["entry_date"], t  # 翌日に決済されている
    assert t["r"] > 0, t
    print("test_backtest_pair_breakout_tp OK")


if __name__ == "__main__":
    test_decide_entry_gap_up_uses_pullback_limit()
    test_decide_entry_small_gap_uses_breakout_stop()
    test_us_return()
    test_scan_candidates_filters_below_threshold()
    test_backtest_pair_breakout_tp()
    print("\nALL sector_leadlag tests passed ✅")
