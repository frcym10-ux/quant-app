"""
tests/test_screener_backtest.py
ステップ8（週次スクリーナー6プリセットのヒストリカル検証）のテスト
合成データのみ・ネットワーク不要。

実行: python tests/test_screener_backtest.py  または  pytest tests/test_screener_backtest.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules import screener_backtest  # noqa: E402


def _df(closes, volumes=None, highs=None):
    """終値リストから日足DataFrameを作る（tests/test_step6.pyと同じ流儀）"""
    n = len(closes)
    closes = np.array(closes, dtype=float)
    highs = np.array(highs, dtype=float) if highs is not None else closes * 1.01
    lows = closes * 0.99
    volumes = np.array(volumes, dtype=float) if volumes is not None else np.full(n, 1_000_000.0)
    return pd.DataFrame({
        "date": pd.bdate_range("2022-01-01", periods=n),
        "open": closes, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    })


def _cyclic_pullback_df(cycles=3, up_len=250, pull_len=10):
    """長期上昇→浅い低出来高の押し目、を複数回繰り返す（週足チャート判定に合格する形を周期的に作る）"""
    closes, vols = [], []
    base = 1500.0
    for _ in range(cycles):
        up = list(np.linspace(base, base * 1.6, up_len))
        pull = list(np.linspace(base * 1.6, base * 1.6 * 0.93, pull_len))
        closes += up + pull
        vols += [1_000_000.0] * up_len + [400_000.0] * pull_len
        base = base * 1.6 * 0.93
    return _df(closes, volumes=vols)


def _downtrend(n=600):
    """一貫した下降トレンド（チャート判定は常に不合格すべき）"""
    return _df(list(np.linspace(3000, 500, n)))


def test_preset_signal_fires_on_healthy_cyclic_pattern():
    df = _cyclic_pullback_df()
    sig = screener_backtest.preset_signal("⑥", df)
    assert len(sig) == len(df)
    assert int(sig.sum()) >= 1, "健全な周期的押し目パターンでシグナルが一度も出ていない"
    print("test_preset_signal_fires_on_healthy_cyclic_pattern OK", int(sig.sum()))


def test_preset_signal_never_fires_on_downtrend():
    df = _downtrend()
    for pid in ["①", "②", "③", "④", "⑤", "⑥"]:
        sig = screener_backtest.preset_signal(pid, df)
        assert int(sig.sum()) == 0, f"下降トレンドでプリセット{pid}がシグナルを出した"
    print("test_preset_signal_never_fires_on_downtrend OK")


def test_preset_signal_short_history_returns_all_zero():
    """MIN_LOOKBACKに満たない履歴では判定せず全て0を返す（クラッシュしない）"""
    df = _df(list(np.linspace(2000, 2100, 50)))
    sig = screener_backtest.preset_signal("①", df)
    assert len(sig) == 50
    assert int(sig.sum()) == 0
    print("test_preset_signal_short_history_returns_all_zero OK")


def test_backtest_preset_integration():
    """preset_signal → modules.backtest のエンジンに正しく橋渡しされ、トレードが記録される"""
    data = {"9999": _cyclic_pullback_df()}
    per_symbol, overall = screener_backtest.backtest_preset(
        "⑥", data, names={"9999": "テスト銘柄"})
    assert overall["n_trades"] >= 1
    assert overall["strategy"] == "⑥週足中期"
    assert not per_symbol.empty
    assert per_symbol.iloc[0]["コード"] == "9999"
    print("test_backtest_preset_integration OK", overall)


def test_backtest_preset_no_signal_returns_empty():
    """一度もシグナルが出ない銘柄はトレード0件・空DataFrameで返る（例外にならない）"""
    data = {"8888": _downtrend()}
    per_symbol, overall = screener_backtest.backtest_preset("①", data)
    assert overall["n_trades"] == 0
    assert per_symbol.empty
    print("test_backtest_preset_no_signal_returns_empty OK")


def test_backtest_all_presets_with_injected_data():
    """swing_scanner/universeを呼ばず、渡したdataだけで全プリセットを検証できる"""
    data = {"9999": _cyclic_pullback_df(), "8888": _downtrend()}
    results = screener_backtest.backtest_all_presets(
        data=data, presets=["①", "⑥"], names={"9999": "テスト銘柄", "8888": "下降株"})
    assert set(results.keys()) == {"①", "⑥"}
    for pid, (per_symbol, overall) in results.items():
        assert "n_trades" in overall
        if not per_symbol.empty:
            assert "8888" not in set(per_symbol["コード"])  # 下降株はシグナルが出ないはず
    print("test_backtest_all_presets_with_injected_data OK")


def test_sl_tp_mult_matches_order_calc_constants():
    from modules import order_calc
    assert screener_backtest._sl_tp_mult("⑥") == (
        order_calc.WEEKLY_SL_ATR_MULT, order_calc.WEEKLY_TP_ATR_MULT)
    assert screener_backtest._sl_tp_mult("①") == (
        order_calc.DAILY_SL_ATR_MULT, order_calc.DAILY_TP_ATR_MULT)
    print("test_sl_tp_mult_matches_order_calc_constants OK")


if __name__ == "__main__":
    test_preset_signal_fires_on_healthy_cyclic_pattern()
    test_preset_signal_never_fires_on_downtrend()
    test_preset_signal_short_history_returns_all_zero()
    test_backtest_preset_integration()
    test_backtest_preset_no_signal_returns_empty()
    test_backtest_all_presets_with_injected_data()
    test_sl_tp_mult_matches_order_calc_constants()
    print("\nALL screener_backtest tests passed ✅")
