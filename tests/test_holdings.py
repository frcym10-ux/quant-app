"""
tests/test_holdings.py
holdings_store（CSV取込）と holdings_monitor.analyze のテスト（ネットワーク不要）

実行: python tests/test_holdings.py  または  pytest tests/test_holdings.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_KEY", None)

from modules import holdings_monitor, holdings_store  # noqa: E402


def test_to_number():
    assert holdings_store._to_number("1,234株") == 1234.0
    assert holdings_store._to_number("¥2,100") == 2100.0
    assert holdings_store._to_number("12.5") == 12.5
    assert holdings_store._to_number("") is None
    assert holdings_store._to_number(None) is None
    print("test_to_number OK")


def test_parse_broker_csv_japanese_cp932():
    """楽天証券風の日本語見出し・cp932のCSVを取り込めること"""
    csv = "銘柄コード,銘柄名,保有数量,平均取得価額\n7011,三菱重工業,100,\"2,100\"\nVOO,バンガードS&P500,10,520\n"
    data = csv.encode("cp932")
    df = holdings_store.parse_broker_csv(data)
    assert list(df.columns) == holdings_store.HOLD_COLUMNS
    assert set(df["code"]) == {"7011", "VOO"}
    row = df[df["code"] == "7011"].iloc[0]
    assert row["shares"] == 100.0
    assert row["avg_cost"] == 2100.0
    assert row["hold_type"] == "スイング"  # 既定
    print("test_parse_broker_csv_japanese_cp932 OK")


def test_parse_broker_csv_english():
    csv = "code,name,shares,avg_cost\n6526,Socionext,50,3000\n"
    df = holdings_store.parse_broker_csv(csv.encode("utf-8"))
    assert df.iloc[0]["code"] == "6526" and df.iloc[0]["shares"] == 50.0
    print("test_parse_broker_csv_english OK")


def test_parse_rakuten_multisection():
    """楽天証券の実フォーマット（先頭に資産合計欄＋タブ区切り＋投資信託混在）を取り込めること"""
    lines = [
        "■資産合計欄",
        "\t時価評価額[円]\t前日比[円]",
        "資産合計\t14,294,498\t-123,723",
        "",
        "国内株式\t5,224,450\t-89,800",
        "",
        "■ 保有商品詳細 (すべて）",
        "",
        ("種別\t銘柄コード・ティッカー\t銘柄\t口座\t保有数量\t［単位］\t平均取得価額\t［単位］"
         "\t現在値\t［単位］\t現在値(更新日)\t(参考為替)\t前日比\t［単位］\t時価評価額[円]"
         "\t時価評価額[外貨]\t評価損益[円]\t評価損益[％]"),
        "国内株式\t7011\t三菱重工業\t特定\t100\t株\t2,100\t円\t2,500\t円\t2026/6/24\t-\t+50\t円\t250,000\t\t+40,000\t+19.04",
        "米国株式\tVOO\tバンガードS&P500\t特定\t10\t株\t520\tドル\t600\tドル\t2026/6/23\t155.00\t+5\tドル\t930,000\t6,000\t+124,000\t+15.38",
        "投資信託\tJP90C000H1T1\t楽天・全世界株式\t特定\t100000\t口\t12,000\t円\t13,000\t円\t2026/6/24\t-\t+10\t円\t1,300,000\t\t+100,000\t+8.33",
    ]
    data = "\n".join(lines).encode("cp932")
    df = holdings_store.parse_broker_csv(data)
    assert set(df["code"]) == {"7011", "VOO"}, df["code"].tolist()  # 投資信託は除外
    r = df[df["code"] == "7011"].iloc[0]
    assert r["name"] == "三菱重工業"
    assert r["shares"] == 100.0
    assert r["avg_cost"] == 2100.0
    voo = df[df["code"] == "VOO"].iloc[0]
    assert voo["avg_cost"] == 520.0
    print("test_parse_rakuten_multisection OK")


def _synthetic_df(trend: str) -> pd.DataFrame:
    """250本の合成日足を作る（trend: 'up' / 'down' / 'flat'）"""
    n = 250
    base = np.linspace(0, 1, n)
    if trend == "up":
        close = 1000 + base * 400
    elif trend == "down":
        close = 1400 - base * 400
    else:
        close = 1000 + np.sin(base * 20) * 20
    dates = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame({
        "date": dates, "open": close, "high": close + 8,
        "low": close - 8, "close": close, "volume": np.full(n, 1_000_000.0),
    })


def _patch_fetch(trend: str):
    holdings_monitor.data_fetcher.get_cached_or_fetch = lambda code, days: _synthetic_df(trend)
    holdings_monitor.swing_scanner.get_usdjpy = lambda: 150.0


def test_analyze_holding_swing_has_levels():
    """スイング銘柄は推奨利確指値・損切りライン・判定を返すこと"""
    _patch_fetch("flat")
    r = holdings_monitor.analyze_holding(
        {"code": "7011", "name": "三菱重工業", "shares": 100, "avg_cost": 1000, "hold_type": "スイング"})
    assert r is not None
    assert r["区分"] == "スイング"
    assert r["推奨利確指値"] is not None and r["損切りライン"] is not None
    assert r["損切りライン"] < r["現在値"]               # 損切りは現在値より下
    assert r["判定"] in {"🟢 継続（保有）", "🔺 利確検討", "🔻 損切り検討"}
    assert r["含み損益円"] is not None                   # shares*avg_costあり
    print("test_analyze_holding_swing_has_levels OK")


def test_analyze_holding_downtrend_is_stoploss():
    """下降トレンドのスイング銘柄は損切り検討になること"""
    _patch_fetch("down")
    r = holdings_monitor.analyze_holding(
        {"code": "7011", "name": "三菱重工業", "shares": 100, "avg_cost": 1400, "hold_type": "スイング"})
    assert r["判定"] == "🔻 損切り検討", r["判定"]
    print("test_analyze_holding_downtrend_is_stoploss OK")


def test_analyze_holding_gachi_no_levels():
    """ガチホ銘柄は利確指値・損切りラインを出さないこと"""
    _patch_fetch("up")
    r = holdings_monitor.analyze_holding(
        {"code": "VOO", "name": "S&P500", "shares": 10, "avg_cost": 400, "hold_type": "ガチホ"})
    assert r["区分"] == "ガチホ"
    assert r["推奨利確指値"] is None and r["損切りライン"] is None
    assert r["市場"] == "米国"
    print("test_analyze_holding_gachi_no_levels OK")


if __name__ == "__main__":
    test_to_number()
    test_parse_broker_csv_japanese_cp932()
    test_parse_broker_csv_english()
    test_parse_rakuten_multisection()
    test_analyze_holding_swing_has_levels()
    test_analyze_holding_downtrend_is_stoploss()
    test_analyze_holding_gachi_no_levels()
    print("\nALL holdings tests passed ✅")
