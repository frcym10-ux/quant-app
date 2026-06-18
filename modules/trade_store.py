"""
modules/trade_store.py
トレード記録（ジャーナル）の保存先を抽象化するストレージ層

- SUPABASE_URL と SUPABASE_KEY（service role キー）が設定されていれば Supabase に保存
  （Streamlit Community Cloud のように再デプロイでファイルが消える環境でも記録が残る）
- 未設定ならローカルCSV（data/trades.csv）に保存（従来どおり・オフライン可）

journal.py はこのモジュール経由でのみ読み書きするため、保存先の違いを意識しなくてよい。
Supabaseテーブルは RLS 有効・公開ポリシー無しで、service key（サーバー側のsecretsのみ）から
アクセスする想定。
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TABLE = "quant_trades"
TRADES_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "trades.csv")

COLUMNS = [
    "id", "date_open", "code", "name", "market", "setup",
    "entry", "sl", "tp", "shares", "risk_yen",
    "status", "date_close", "exit", "pnl_yen", "r_multiple", "note",
]

# 型変換のための列分類
_NUMERIC_COLS = {"entry", "sl", "tp", "shares", "risk_yen", "exit", "pnl_yen", "r_multiple"}
_DATE_COLS = {"date_open", "date_close"}

_client = None  # Supabaseクライアントのキャッシュ


# ========== 保存先の判定 ==========

def _supabase_config() -> tuple[str, str] | None:
    """SUPABASE_URL / SUPABASE_KEY が揃っていれば (url, key) を返す。なければNone"""
    url = os.getenv("SUPABASE_URL", "").strip()
    key = (os.getenv("SUPABASE_KEY", "").strip()
           or os.getenv("SUPABASE_SERVICE_KEY", "").strip())
    return (url, key) if url and key else None


def using_supabase() -> bool:
    """現在Supabaseを保存先に使うかどうか"""
    return _supabase_config() is not None


def backend_name() -> str:
    """保存先の表示名を返す（UI表示用）"""
    return "Supabase（クラウド永続化）" if using_supabase() else "ローカルCSV"


def _get_client(url: str, key: str):
    """Supabaseクライアントを取得（初回のみ生成してキャッシュ）"""
    global _client
    if _client is None:
        from supabase import create_client
        _client = create_client(url, key)
    return _client


# ========== 値の正規化 ==========

def _clean_value(col: str, value):
    """DataFrameの1セルを、保存先に適した型へ正規化する

    空文字・NaN・None は None に統一。数値列はfloat、日付列はISO文字列、その他は文字列。
    """
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    if pd.isna(value):
        return None

    if col in _NUMERIC_COLS:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if col in _DATE_COLS:
        # YYYY-MM-DD のISO文字列へ
        s = str(value).strip()
        return s or None
    return str(value)


def _to_records(df: pd.DataFrame) -> list[dict]:
    """DataFrameをSupabase upsert用のレコード（型正規化済み）に変換する"""
    records = []
    for _, row in df.iterrows():
        rec = {c: _clean_value(c, row.get(c)) for c in COLUMNS}
        if rec.get("id"):  # idが無い行は無視（不正データ防止）
            rec["id"] = str(rec["id"])
            records.append(rec)
    return records


# ========== CSVバックエンド ==========

def _csv_read() -> pd.DataFrame:
    if not os.path.exists(TRADES_CSV):
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(TRADES_CSV, dtype={"code": str, "id": str})
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = None
    return df[COLUMNS]


def _csv_write(df: pd.DataFrame) -> None:
    os.makedirs(os.path.dirname(TRADES_CSV), exist_ok=True)
    df.to_csv(TRADES_CSV, index=False, encoding="utf-8-sig")


# ========== Supabaseバックエンド ==========

def _sb_read(url: str, key: str) -> pd.DataFrame:
    client = _get_client(url, key)
    res = client.table(TABLE).select("*").order("date_open").execute()
    rows = res.data or []
    df = pd.DataFrame(rows)
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = None
    df = df[COLUMNS]
    if not df.empty:
        df["code"] = df["code"].astype(str)
        df["id"] = df["id"].astype(str)
    return df.reset_index(drop=True)


def _sb_write(url: str, key: str, df: pd.DataFrame) -> None:
    """desired状態（df）にテーブルを同期する（upsert＋不要行のdelete）"""
    client = _get_client(url, key)
    records = _to_records(df)
    desired_ids = {r["id"] for r in records}

    if records:
        client.table(TABLE).upsert(records).execute()

    existing = client.table(TABLE).select("id").execute().data or []
    for r in existing:
        rid = str(r.get("id"))
        if rid not in desired_ids:
            client.table(TABLE).delete().eq("id", rid).execute()


# ========== 公開API ==========

def read_all() -> pd.DataFrame:
    """全トレードをDataFrameで返す（保存先は自動判定）"""
    cfg = _supabase_config()
    if cfg:
        try:
            return _sb_read(*cfg)
        except Exception as e:
            print(f"Supabase読み込み失敗、CSVにフォールバック: {e}")
    return _csv_read()


def write_all(df: pd.DataFrame) -> None:
    """全トレードを保存する（保存先は自動判定）"""
    cfg = _supabase_config()
    if cfg:
        _sb_write(*cfg, df)
        return
    _csv_write(df)
