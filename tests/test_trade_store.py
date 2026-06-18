"""
tests/test_trade_store.py
trade_store / journal のCSVバックエンドと値正規化のテスト（ネットワーク不要）

実行: python tests/test_trade_store.py  または  pytest tests/test_trade_store.py
"""
import os
import sys
import tempfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Supabaseを使わないことを保証
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_KEY", None)
os.environ.pop("SUPABASE_SERVICE_KEY", None)

from modules import trade_store  # noqa: E402


def test_clean_value():
    assert trade_store._clean_value("entry", "") is None
    assert trade_store._clean_value("entry", np.nan) is None
    assert trade_store._clean_value("entry", None) is None
    assert trade_store._clean_value("entry", "1.5") == 1.5
    assert trade_store._clean_value("shares", 10) == 10.0
    assert trade_store._clean_value("date_close", "") is None
    assert trade_store._clean_value("date_open", "2026-06-17") == "2026-06-17"
    assert trade_store._clean_value("note", "メモ") == "メモ"
    assert trade_store._clean_value("code", 7011) == "7011"
    print("test_clean_value OK")


def test_to_records_drops_idless():
    df = pd.DataFrame([
        {"id": "a1", "code": "7011", "entry": 100, "date_close": ""},
        {"id": "", "code": "9999", "entry": 50},     # id無し→除外
    ])
    recs = trade_store._to_records(df)
    assert len(recs) == 1
    r = recs[0]
    assert r["id"] == "a1"
    assert r["entry"] == 100.0
    assert r["date_close"] is None       # 空文字→None
    assert r["code"] == "7011"
    print("test_to_records_drops_idless OK")


def test_using_supabase_false_by_default():
    assert trade_store.using_supabase() is False
    assert "CSV" in trade_store.backend_name()
    print("test_using_supabase_false_by_default OK")


def test_journal_csv_roundtrip(tmp_path=None):
    """journal の add→close→stats がCSV保存先で正しく動くこと"""
    import importlib
    tmpdir = tempfile.mkdtemp()
    csv = os.path.join(tmpdir, "trades.csv")
    trade_store.TRADES_CSV = csv  # 保存先を一時ファイルへ

    from modules import journal
    importlib.reload(journal)  # TRADES_CSV束縛を更新
    journal.TRADES_CSV = csv

    tid = journal.add_trade("7011", "三菱重工業", "日本", "トレンド押し目",
                            entry=1000, sl=960, tp=1120, shares=10, risk_yen=400)
    df = journal.load_trades()
    assert len(df) == 1 and df.iloc[0]["status"] == "保有中"

    # 利確（+1.5R相当: exit=tp）
    journal.close_trade(tid, exit_price=1120)
    s = journal.stats()
    assert s["n_closed"] == 1
    assert s["wins"] == 1
    assert abs(s["expectancy_r"] - 3.0) < 0.01  # (1120-1000)/(1000-960)=3.0R
    print("test_journal_csv_roundtrip OK")


class _FakeQuery:
    """Supabase client の table().select()/upsert()/delete() を模した最小スタブ"""
    def __init__(self, store, op=None, payload=None):
        self.store = store
        self.op = op
        self.payload = payload
        self._eq = None

    def select(self, *_a, **_k):
        return _FakeQuery(self.store, "select")

    def order(self, *_a, **_k):
        return self

    def upsert(self, records):
        return _FakeQuery(self.store, "upsert", records)

    def delete(self):
        return _FakeQuery(self.store, "delete")

    def eq(self, col, val):
        self._eq = (col, val)
        return self

    def execute(self):
        if self.op == "select":
            return type("R", (), {"data": list(self.store.values())})()
        if self.op == "upsert":
            for rec in self.payload:
                self.store[rec["id"]] = rec
            return type("R", (), {"data": self.payload})()
        if self.op == "delete":
            self.store.pop(self._eq[1], None)
            return type("R", (), {"data": []})()
        return type("R", (), {"data": []})()


class _FakeClient:
    def __init__(self):
        self.store = {}

    def table(self, _name):
        return _FakeQuery(self.store)


def test_supabase_backend_with_fake_client():
    """SUPABASE設定時に upsert＋不要行delete でテーブルが同期されること"""
    fake = _FakeClient()
    trade_store._client = fake
    os.environ["SUPABASE_URL"] = "https://example.supabase.co"
    os.environ["SUPABASE_KEY"] = "fake-service-key"
    try:
        assert trade_store.using_supabase() is True

        # 2件書き込み
        df = pd.DataFrame([
            {"id": "a1", "code": "7011", "entry": 1000, "status": "保有中", "date_close": ""},
            {"id": "b2", "code": "2914", "entry": 4000, "status": "決済済み", "date_close": "2026-06-17"},
        ])
        trade_store.write_all(df)
        got = trade_store.read_all()
        assert set(got["id"]) == {"a1", "b2"}, got["id"].tolist()
        # 空文字date_closeはNoneとして保存される
        assert fake.store["a1"]["date_close"] is None

        # 1件だけのdfで上書き → b2が削除されること
        df2 = pd.DataFrame([{"id": "a1", "code": "7011", "entry": 1000, "status": "保有中"}])
        trade_store.write_all(df2)
        got2 = trade_store.read_all()
        assert set(got2["id"]) == {"a1"}, got2["id"].tolist()
        print("test_supabase_backend_with_fake_client OK")
    finally:
        trade_store._client = None
        os.environ.pop("SUPABASE_URL", None)
        os.environ.pop("SUPABASE_KEY", None)


if __name__ == "__main__":
    test_clean_value()
    test_to_records_drops_idless()
    test_using_supabase_false_by_default()
    test_journal_csv_roundtrip()
    test_supabase_backend_with_fake_client()
    print("\nALL trade_store tests passed ✅")
