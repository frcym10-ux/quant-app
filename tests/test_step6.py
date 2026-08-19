"""
tests/test_step6.py
ステップ6（週次スクリーナー・チャート数値判定・注文計算）のテスト
合成データのみ・ネットワーク不要。

実行: python tests/test_step6.py  または  pytest tests/test_step6.py
"""
import datetime as dt
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules import chart_filter, earnings, order_calc, screener  # noqa: E402


def _df(closes, volumes=None, highs=None):
    """終値リストから日足DataFrameを作る"""
    n = len(closes)
    closes = np.array(closes, dtype=float)
    highs = np.array(highs, dtype=float) if highs is not None else closes * 1.01
    lows = closes * 0.99
    volumes = np.array(volumes, dtype=float) if volumes is not None else np.full(n, 1_000_000.0)
    return pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=n),
        "open": closes, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    })


def _healthy_uptrend():
    """長期上昇→直近だけ小さく出来高細く押した銘柄（チャート合格すべき）"""
    up = list(np.linspace(2000, 3000, 292))
    pull = list(np.linspace(3000, 2900, 8))          # 直近8日だけ小反落
    closes = up + pull
    vol = [1_000_000.0] * 292 + [400_000.0] * 8      # 押し目は出来高細い
    return _df(closes, volumes=vol)


def _downtrend():
    """一貫した下降トレンド（参天・住友電工・清水建設型＝チャート不合格すべき）"""
    return _df(list(np.linspace(3000, 2000, 300)))


# ========== chart_filter ==========

def test_chart_reject_downtrend():
    ok, detail = chart_filter.chart_check_weekly(_downtrend())
    assert ok is False, detail
    assert detail["26週MA上向き"] is False
    assert detail["26週MA上に位置"] is False
    print("test_chart_reject_downtrend OK", detail)


def test_chart_accept_healthy():
    ok, detail = chart_filter.chart_check_weekly(_healthy_uptrend())
    assert ok is True, detail
    print("test_chart_accept_healthy OK", detail)


def test_chart_daily_functions():
    df = _healthy_uptrend()
    ma = df["close"].rolling(75).mean()
    assert chart_filter.is_ma_rising(ma) is True
    assert chart_filter.is_above_ma(df["close"], ma) is True
    assert chart_filter.is_acute_pullback(df["high"], df["close"]) is True
    assert chart_filter.is_low_volume_pullback(df["close"], df["volume"]) is True
    print("test_chart_daily_functions OK")


# ========== order_calc ==========

def test_order_weekly_rr_and_levels():
    o = order_calc.calc_order(2000.0, 50.0, preset="weekly", entry_style="pullback",
                              available_cash=1_650_000)
    assert o["entry"] == 1940.0                       # 2000×(1-0.03)
    assert o["stop"] == 1940.0 - 3 * 50               # -3ATR
    assert o["take"] == 1940.0 + 6 * 50               # +6ATR
    assert o["rr"] == 2.0                             # R:R 1:2
    assert o["shares"] == 100 and o["kabumini"] is False
    assert o["notional"] == 194000.0
    print("test_order_weekly_rr_and_levels OK")


def test_order_kabumini_flag():
    # 値がさ（10万円/株）→ 単元100株=1000万で余力165万を超える → かぶミニ
    o = order_calc.calc_order(100_000.0, 2000.0, preset="weekly", available_cash=1_650_000)
    assert o["kabumini"] is True
    assert "かぶミニ" in o["note"]
    print("test_order_kabumini_flag OK")


# ========== screener（プリセット⑥） ==========

def _preset6_price():
    """株価帯内・流動性十分・上昇トレンドから直近だけ約-8%の浅い押し目

    52週高値から-8%（押し目ゾーン-20〜-5%内）で、週足チャートも合格する形。
    """
    up = list(np.linspace(1500, 3000, 290))              # 長期の力強い上昇
    pull = list(np.linspace(3000, 2800, 10))             # 直近10日だけ約-6.7%の浅い押し
    closes = up + pull
    vol = [1_000_000.0] * 290 + [400_000.0] * 10         # 押し目は出来高細い・代金は5億超
    return _df(closes, volumes=vol)


def test_common_prereq_rejects_out_of_band():
    hi = _df(list(np.linspace(8000, 9000, 60)))       # 株価帯外（>5000）
    ok, reasons = screener.passes_common_prereq(hi, available_cash=1_650_000)
    assert ok is False and any("対象帯" in r for r in reasons)
    print("test_common_prereq_rejects_out_of_band OK")


def test_preset6_pass_with_good_fundamentals():
    v = screener.passes_preset6(_preset6_price(),
                                {"roe": 12.0, "dividend_yield": 3.0, "per": 15.0},
                                available_cash=1_650_000)
    assert v["pass"] is True and v["flags"] == [], v
    assert -20 <= v["drop_pct"] <= -5
    print("test_preset6_pass_with_good_fundamentals OK", v["drop_pct"])


def test_preset6_fail_on_per():
    v = screener.passes_preset6(_preset6_price(),
                                {"roe": 12.0, "dividend_yield": 3.0, "per": 25.0},
                                available_cash=1_650_000)
    assert v["pass"] is False
    print("test_preset6_fail_on_per OK")


def test_preset6_missing_fundamentals_flagged_not_failed():
    v = screener.passes_preset6(_preset6_price(),
                                {"roe": None, "dividend_yield": None, "per": None},
                                available_cash=1_650_000)
    assert v["pass"] is True                          # 未取得は不合格にしない
    assert len(v["flags"]) >= 3                        # 要確認フラグが立つ
    print("test_preset6_missing_fundamentals_flagged_not_failed OK")


def test_screen_preset6_end_to_end():
    price_data = {"9999": _preset6_price(), "8888": _downtrend()}
    fmap = {
        "9999": {"roe": 12.0, "dividend_yield": 3.0, "per": 15.0, "name": "テスト優良"},
        "8888": {"roe": 12.0, "dividend_yield": 3.0, "per": 15.0, "name": "下降株"},
    }
    out = screener.screen_preset6(["9999", "8888"], available_cash=1_650_000,
                                  price_data=price_data, fundamentals_map=fmap)
    # 9999は合格、8888はチャート不合格で除外される
    assert list(out["コード"]) == ["9999"], out
    assert out.iloc[0]["RR"] == 2.0
    print("test_screen_preset6_end_to_end OK")


# ========== 他プリセット①〜⑤の固有条件 ==========

def _passed(checks):
    """_finalize と同じ判定（False が無ければ合格）"""
    return all(v is not False for v in checks.values())


def test_preset1_pushback():
    df = pd.DataFrame({"close": [1000, 1000], "rsi": [38, 38],
                       "sma25": [1030, 1030], "sma75": [980, 980],
                       "high": [1000, 1000], "volume": [1, 1]})
    checks, memo, rh = screener._preset1(df, {})
    assert _passed(checks) and rh is None, checks
    # 乖離が浅すぎる（-0.5%）と不合格
    df2 = df.assign(sma25=[1005, 1005])
    assert screener._preset1(df2, {})[0]["25日乖離 -5〜-1%"] is False
    print("test_preset1_pushback OK", memo)


def test_preset2_breakout():
    df = pd.DataFrame({"close": [990, 1000], "volume": [100, 200], "rsi": [60, 60],
                       "sma25": [985, 985], "high": [995, 1000]})
    checks, memo, rh = screener._preset2(df, {})
    assert _passed(checks), checks
    assert checks["売買代金 前日比≥1.5倍"] is True and rh == 1000.0
    print("test_preset2_breakout OK", memo)


def test_preset3_ordinary_growth_flagged():
    df = pd.DataFrame({"close": [1000, 1000], "rsi": [38, 38]})
    checks, memo, rh = screener._preset3(
        df, {"roe": 12.0, "ordinary_income_growth": None, "per": 15.0})
    # 経常利益変化率が未取得（None）でも不合格にはせず要確認
    assert checks["経常利益変化率≥+5%"] is None
    assert _passed(checks) is True
    print("test_preset3_ordinary_growth_flagged OK")


def test_preset4_bollinger():
    df = pd.DataFrame({"close": [940, 940], "rsi": [30, 30],
                       "bb_lower": [950, 950], "bb_mid": [1000, 1000],
                       "sma75": [900, 900]})
    checks, memo, rh = screener._preset4(df, {})
    assert _passed(checks) and checks["BB -2σ〜-3σ到達"] is True
    # -3σより下（過剰）なら到達=False
    df2 = df.assign(close=[900, 900])
    assert screener._preset4(df2, {})[0]["BB -2σ〜-3σ到達"] is False
    print("test_preset4_bollinger OK")


def test_preset5_golden_cross():
    gc_df = pd.DataFrame({"close": [100.0] * 29 + [200.0]})
    flat_df = pd.DataFrame({"close": [100.0] * 30})
    fund = {"dividend_yield": 4.0, "roe": 10.0}
    assert screener._preset5(gc_df, fund)[0]["GC(5日/25日)"] is True
    assert screener._preset5(flat_df, fund)[0]["GC(5日/25日)"] is False
    print("test_preset5_golden_cross OK")


def test_screen_all_presets_runs_and_marks_dup():
    price_data = {"9999": _preset6_price(), "8888": _downtrend()}
    fmap = {
        "9999": {"roe": 12.0, "dividend_yield": 3.0, "per": 15.0,
                 "ordinary_income_growth": 8.0, "name": "優良テスト"},
        "8888": {"roe": 12.0, "dividend_yield": 3.0, "per": 15.0,
                 "ordinary_income_growth": 8.0, "name": "下降株"},
    }
    out = screener.screen_all_presets(["9999", "8888"], available_cash=1_650_000,
                                      price_data=price_data, fundamentals_map=fmap)
    assert "重複" in out.columns
    assert (out["プリセット"] == "⑥週足中期").any()          # ⑥で拾える
    assert "8888" not in set(out["コード"])                  # 下降株はチャートで全除外
    print("test_screen_all_presets_runs_and_marks_dup OK", list(out["プリセット"]))


# ========== 決算日フィルタ（6-6）＆ 今週の候補レンダリング（6-4） ==========

def test_earnings_flag():
    ref = dt.date(2026, 8, 19)
    tbl = {"6702": dt.date(2026, 8, 24), "9432": dt.date(2026, 10, 1)}
    near, _ = earnings.earnings_flag("6702", ref=ref, table=tbl)
    far, _ = earnings.earnings_flag("9432", ref=ref, table=tbl)
    none, d = earnings.earnings_flag("1234", ref=ref, table=tbl)
    assert near.startswith("⚠️決算接近") and not far.startswith("⚠️")
    assert "未登録" in none and d is None
    print("test_earnings_flag OK")


def test_weekly_panel_render():
    spec = importlib.util.spec_from_file_location(
        "pubrep", os.path.join(os.path.dirname(__file__), "..", "tools", "publish_report.py"))
    pr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pr)
    wk = pd.DataFrame([{
        "コード": "2914", "銘柄名": "JT", "プリセット": "⑥週足中期", "重複": "★重複",
        "現在値": 4000, "指標メモ": "52週高値から-8.0%", "チャート合格": "✅",
        "指値": 3880, "損切り": 3730, "利確": 4180, "RR": 2.0, "建玉額": 388000,
        "かぶミニ": "", "要確認": "-", "ROE%": 12, "配当利回り%": 3, "PER": 15,
    }])
    tbl = {"2914": dt.date(2026, 8, 24)}
    html = pr._weekly_panel(wk, tbl)
    for s in ["今週の候補", "⑥週足中期", "★重複", "推奨指値", "JT"]:
        assert s in html, s
    # weekly=None のときは今週タブを出さない
    assert "data-tab='weekly'" not in pr.render(pd.DataFrame(), pd.DataFrame())
    print("test_weekly_panel_render OK")


if __name__ == "__main__":
    test_chart_reject_downtrend()
    test_chart_accept_healthy()
    test_chart_daily_functions()
    test_order_weekly_rr_and_levels()
    test_order_kabumini_flag()
    test_common_prereq_rejects_out_of_band()
    test_preset6_pass_with_good_fundamentals()
    test_preset6_fail_on_per()
    test_preset6_missing_fundamentals_flagged_not_failed()
    test_screen_preset6_end_to_end()
    test_preset1_pushback()
    test_preset2_breakout()
    test_preset3_ordinary_growth_flagged()
    test_preset4_bollinger()
    test_preset5_golden_cross()
    test_screen_all_presets_runs_and_marks_dup()
    test_earnings_flag()
    test_weekly_panel_render()
    print("\nALL step6 tests passed ✅")
