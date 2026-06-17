"""
tests/test_market_filter.py
market_filter / swing_scanner の市場フィルター連携テスト（合成データ・ネットワーク不要）

実行: python tests/test_market_filter.py  または  pytest tests/test_market_filter.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules import market_filter, swing_scanner


def test_status_risk_on():
    """終値が両SMAの上 → 🟢 順風"""
    close = pd.Series(np.linspace(100, 300, 260))  # 一貫した上昇
    s = market_filter._status_from_close(close)
    assert s["light"] == "🟢", s
    assert s["above_long"] and s["above_mid"]
    print("test_status_risk_on OK")


def test_status_risk_off():
    """終値が200日線を割れ → 🔴 逆風"""
    close = pd.Series(np.linspace(300, 100, 260))  # 一貫した下落
    s = market_filter._status_from_close(close)
    assert s["light"] == "🔴", s
    assert not s["above_long"]
    print("test_status_risk_off OK")


def test_status_insufficient():
    """データ不足ならNone"""
    assert market_filter._status_from_close(pd.Series([1, 2, 3])) is None
    print("test_status_insufficient OK")


def test_apply_market_filter_demotes_long():
    """逆風(🔴)のとき候補→監視へ格下げ・減点されること"""
    ms = {"日本": {"light": "🔴", "trend": "逆風"}}
    r = {"市場": "日本", "種別": "候補", "スコア": 70, "根拠": "テスト根拠"}
    out = swing_scanner._apply_market_filter(r, ms)
    assert out["種別"] == "監視", out
    assert out["スコア"] == 58, out          # 70 - 12
    assert out["相場"] == "🔴"
    assert "逆風" in out["根拠"]
    print("test_apply_market_filter_demotes_long OK")


def test_apply_market_filter_keeps_on_risk_on():
    """順風(🟢)のときは格下げしないこと"""
    ms = {"米国": {"light": "🟢", "trend": "順風"}}
    r = {"市場": "米国", "種別": "候補", "スコア": 80, "根拠": "x"}
    out = swing_scanner._apply_market_filter(r, ms)
    assert out["種別"] == "候補"
    assert out["スコア"] == 80
    assert out["相場"] == "🟢"
    print("test_apply_market_filter_keeps_on_risk_on OK")


if __name__ == "__main__":
    test_status_risk_on()
    test_status_risk_off()
    test_status_insufficient()
    test_apply_market_filter_demotes_long()
    test_apply_market_filter_keeps_on_risk_on()
    print("\nALL market_filter tests passed ✅")
