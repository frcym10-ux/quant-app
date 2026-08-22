"""
tests/test_jquants_fundamentals.py
ステップ7（J-Quants財務データ・決算発表予定日連携）のテスト
合成データ＋モッククライアントのみ・ネットワーク不要。

実行: python tests/test_jquants_fundamentals.py  または  pytest tests/test_jquants_fundamentals.py
"""
import datetime as dt
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules import earnings, jquants_fundamentals  # noqa: E402


class _FakeClient:
    """jquantsapi.ClientV2 の代わりに固定DataFrameを返す偽クライアント"""

    def __init__(self, fin_summary_df=None, earnings_date_df=None):
        self._fin_summary_df = fin_summary_df if fin_summary_df is not None else pd.DataFrame()
        self._earnings_date_df = earnings_date_df if earnings_date_df is not None else pd.DataFrame()

    def get_fin_summary(self, code=""):
        return self._fin_summary_df

    def get_fin_earnings_date(self, code=""):
        return self._earnings_date_df


def _with_fake_client(monkeypatch, client):
    """_get_client() が毎回同じ偽クライアントを返すように差し替える"""
    monkeypatch.setattr(jquants_fundamentals, "_get_client", lambda: client)


def _fin_summary_rows():
    """2期分の決算サマリ（前年同期比+20%の経常利益成長・ROE12%・予想EPS100円）"""
    return pd.DataFrame([
        {"DiscDate": "2025-05-10", "Code": "7203", "CurPerType": "FY",
         "OdP": 100_000_000, "ROE": 0.10, "FEPS": 90.0,
         "DivAnn": 40.0, "FDivAnn": 45.0},
        {"DiscDate": "2026-05-10", "Code": "7203", "CurPerType": "FY",
         "OdP": 120_000_000, "ROE": 0.12, "FEPS": 100.0,
         "DivAnn": 45.0, "FDivAnn": 50.0},
    ])


def test_fetch_fundamentals_jquants_full(monkeypatch):
    _with_fake_client(monkeypatch, _FakeClient(fin_summary_df=_fin_summary_rows()))
    v = jquants_fundamentals.fetch_fundamentals_jquants("7203", price=2000.0)
    assert v["roe"] == 12.0                                    # 0.12 → 12.0%
    assert v["per"] == 20.0                                     # 2000 / FEPS100
    assert v["dividend_yield"] == 2.5                            # FDivAnn50 / 2000 * 100
    assert v["ordinary_income_growth"] == 20.0                   # (120-100)/100*100
    print("test_fetch_fundamentals_jquants_full OK", v)


def test_fetch_fundamentals_jquants_roe_already_percent(monkeypatch):
    """ROEが既に%表現（12.0）で返ってきても二重に100倍しない"""
    df = _fin_summary_rows()
    df.loc[df.index[-1], "ROE"] = 12.0  # 比率ではなく%表現
    _with_fake_client(monkeypatch, _FakeClient(fin_summary_df=df))
    v = jquants_fundamentals.fetch_fundamentals_jquants("7203", price=2000.0)
    assert v["roe"] == 12.0
    print("test_fetch_fundamentals_jquants_roe_already_percent OK")


def test_fetch_fundamentals_jquants_no_price_skips_per_and_yield(monkeypatch):
    _with_fake_client(monkeypatch, _FakeClient(fin_summary_df=_fin_summary_rows()))
    v = jquants_fundamentals.fetch_fundamentals_jquants("7203", price=None)
    assert v["per"] is None and v["dividend_yield"] is None
    assert v["roe"] == 12.0 and v["ordinary_income_growth"] == 20.0
    print("test_fetch_fundamentals_jquants_no_price_skips_per_and_yield OK")


def test_fetch_fundamentals_jquants_empty_returns_all_none(monkeypatch):
    _with_fake_client(monkeypatch, _FakeClient(fin_summary_df=pd.DataFrame()))
    v = jquants_fundamentals.fetch_fundamentals_jquants("0000", price=2000.0)
    assert v == {"roe": None, "dividend_yield": None, "per": None, "ordinary_income_growth": None}
    print("test_fetch_fundamentals_jquants_empty_returns_all_none OK")


def test_fetch_fundamentals_jquants_single_period_no_growth(monkeypatch):
    """前年同期データが無ければ経常利益変化率はNone（要確認扱いに委ねる）"""
    df = _fin_summary_rows().iloc[[-1]]
    _with_fake_client(monkeypatch, _FakeClient(fin_summary_df=df))
    v = jquants_fundamentals.fetch_fundamentals_jquants("7203", price=2000.0)
    assert v["ordinary_income_growth"] is None
    assert v["roe"] == 12.0
    print("test_fetch_fundamentals_jquants_single_period_no_growth OK")


def test_fetch_earnings_date_jquants(monkeypatch):
    df = pd.DataFrame([
        {"PubDate": "2026-05-01", "Code": "7203", "SchDate": "2026-08-05"},
        {"PubDate": "2026-07-01", "Code": "7203", "SchDate": "2026-08-24"},  # 直近の更新後予定日
    ])
    _with_fake_client(monkeypatch, _FakeClient(earnings_date_df=df))
    d = jquants_fundamentals.fetch_earnings_date_jquants("7203")
    assert d == dt.date(2026, 8, 24)
    print("test_fetch_earnings_date_jquants OK", d)


def test_fetch_earnings_date_jquants_undetermined(monkeypatch):
    """SchDateが空文字（未定）ならNone"""
    df = pd.DataFrame([{"PubDate": "2026-07-01", "Code": "7203", "SchDate": ""}])
    df["SchDate"] = pd.to_datetime(df["SchDate"], errors="coerce")
    _with_fake_client(monkeypatch, _FakeClient(earnings_date_df=df))
    d = jquants_fundamentals.fetch_earnings_date_jquants("7203")
    assert d is None
    print("test_fetch_earnings_date_jquants_undetermined OK")


def test_load_earnings_manual_priority_over_jquants(monkeypatch):
    """手動登録（EARNINGS_JSON）がある銘柄はJ-Quantsで上書きしない"""
    monkeypatch.setenv("EARNINGS_JSON", '{"7203": "2026-09-01"}')
    monkeypatch.setattr(
        "config.settings.JQUANTS_API_KEY", "dummy-key", raising=False)
    monkeypatch.setattr(
        jquants_fundamentals, "fetch_earnings_date_jquants",
        lambda code: dt.date(2026, 1, 1))  # 呼ばれたら分かるよう別の日付
    table = earnings.load_earnings(codes=["7203", "9432"])
    assert table["7203"] == dt.date(2026, 9, 1)   # 手動登録が優先
    assert table["9432"] == dt.date(2026, 1, 1)   # 未登録分はJ-Quantsで補完
    print("test_load_earnings_manual_priority_over_jquants OK", table)


def test_load_earnings_without_key_skips_jquants(monkeypatch):
    monkeypatch.delenv("EARNINGS_JSON", raising=False)
    monkeypatch.setattr(
        "config.settings.JQUANTS_API_KEY", "", raising=False)
    table = earnings.load_earnings(codes=["9999"])
    assert "9999" not in table
    print("test_load_earnings_without_key_skips_jquants OK")


if __name__ == "__main__":
    import types

    _UNSET = object()

    class _MonkeyPatch:
        """pytest不使用時の簡易monkeypatch代替（dotted-path形式と obj,name,value 形式の両対応）"""
        def __init__(self):
            self._restores = []

        def setattr(self, target, name, value=_UNSET, raising=True):
            if isinstance(target, str) and value is _UNSET:
                # monkeypatch.setattr("mod.attr", value) 形式（name引数が実際の値）
                mod_path, attr = target.rsplit(".", 1)
                mod = __import__(mod_path, fromlist=[attr])
                old = getattr(mod, attr, None)
                self._restores.append((mod, attr, old))
                setattr(mod, attr, name)
            else:
                old = getattr(target, name, None)
                self._restores.append((target, name, old))
                setattr(target, name, value)

        def setenv(self, key, value):
            old = os.environ.get(key)
            self._restores.append((os.environ, key, old))
            os.environ[key] = value

        def delenv(self, key, raising=False):
            old = os.environ.pop(key, None)
            self._restores.append((os.environ, key, old))

        def undo(self):
            for target, name, old in reversed(self._restores):
                if target is os.environ:
                    if old is None:
                        target.pop(name, None)
                    else:
                        target[name] = old
                else:
                    if old is None:
                        try:
                            delattr(target, name)
                        except AttributeError:
                            pass
                    else:
                        setattr(target, name, old)
            self._restores.clear()

    tests = [
        test_fetch_fundamentals_jquants_full,
        test_fetch_fundamentals_jquants_roe_already_percent,
        test_fetch_fundamentals_jquants_no_price_skips_per_and_yield,
        test_fetch_fundamentals_jquants_empty_returns_all_none,
        test_fetch_fundamentals_jquants_single_period_no_growth,
        test_fetch_earnings_date_jquants,
        test_fetch_earnings_date_jquants_undetermined,
        test_load_earnings_manual_priority_over_jquants,
        test_load_earnings_without_key_skips_jquants,
    ]
    for t in tests:
        mp = _MonkeyPatch()
        try:
            t(mp)
        finally:
            mp.undo()
    print("\nALL jquants_fundamentals tests passed ✅")
