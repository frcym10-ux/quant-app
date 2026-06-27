"""
modules/holdings_store.py
保有銘柄（ポートフォリオ）の保存先を抽象化するストレージ層

- SUPABASE_URL と SUPABASE_KEY が設定されていれば Supabase の quant_holdings テーブル
- なければローカルCSV（data/portfolio.csv）

各銘柄に hold_type（'スイング' / 'ガチホ'）を持たせ、画面から編集・CSV取込できる。
証券会社のCSV（楽天証券など・日本語見出し・cp932/utf-8）からの取込にも対応する。
"""
from __future__ import annotations

import io
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TABLE = "quant_holdings"
PORTFOLIO_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "portfolio.csv")

HOLD_COLUMNS = ["code", "name", "shares", "avg_cost", "hold_type", "note"]
HOLD_TYPES = ["スイング", "ガチホ"]
DEFAULT_HOLD_TYPE = "スイング"

_NUMERIC = {"shares", "avg_cost"}

# 証券会社CSVの見出し→標準列名のゆらぎ吸収（小文字・空白除去で照合）
_HEADER_SYNONYMS = {
    "code": ["銘柄コード", "コード", "証券コード", "ティッカー", "code", "ticker", "symbol", "銘柄"],
    "name": ["銘柄名", "名称", "name", "銘柄名称"],
    "shares": ["保有数量", "数量", "株数", "保有株数", "保有口数", "shares", "quantity", "qty", "口数"],
    "avg_cost": ["平均取得価額", "取得単価", "平均取得単価", "取得価額", "平均取得",
                 "取得平均", "avg_cost", "cost", "average_cost", "買付単価"],
}

_client = None


# ========== 保存先判定（trade_storeと同じ規約） ==========

def _supabase_config() -> tuple[str, str] | None:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = (os.getenv("SUPABASE_KEY", "").strip()
           or os.getenv("SUPABASE_SERVICE_KEY", "").strip())
    return (url, key) if url and key else None


def using_supabase() -> bool:
    return _supabase_config() is not None


def backend_name() -> str:
    return "Supabase（クラウド永続化）" if using_supabase() else "ローカルCSV"


def _get_client(url: str, key: str):
    global _client
    if _client is None:
        from supabase import create_client
        _client = create_client(url, key)
    return _client


# ========== 値の正規化 ==========

def _to_number(value) -> float | None:
    """'1,234株' のような表記から数値を取り出す。失敗時はNone"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if s == "":
        return None
    # 数字・小数点・マイナス以外を除去（カンマ・通貨記号・単位を落とす）
    cleaned = "".join(ch for ch in s if ch.isdigit() or ch in ".-")
    try:
        return float(cleaned) if cleaned not in ("", "-", ".") else None
    except ValueError:
        return None


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """標準列・型に整える"""
    for c in HOLD_COLUMNS:
        if c not in df.columns:
            df[c] = None
    df = df[HOLD_COLUMNS].copy()
    df["code"] = df["code"].astype(str).str.strip().str.upper()
    df = df[df["code"].notna() & (df["code"] != "") & (df["code"] != "NAN")]
    for c in _NUMERIC:
        df[c] = df[c].map(_to_number)
    df["hold_type"] = df["hold_type"].apply(
        lambda v: v if v in HOLD_TYPES else DEFAULT_HOLD_TYPE
    )
    df["name"] = df["name"].fillna("").astype(str)
    df["note"] = df["note"].fillna("").astype(str)
    return df.reset_index(drop=True)


# ========== CSV取込 ==========

def parse_broker_csv(data: bytes) -> pd.DataFrame:
    """証券会社のCSV（bytes）を読み、標準列のDataFrameに変換する

    文字コードは utf-8-sig → cp932 → utf-8 の順に試す。
    見出しのゆらぎを吸収して code/name/shares/avg_cost を抽出する。
    """
    raw = None
    for enc in ("utf-8-sig", "cp932", "utf-8"):
        try:
            raw = pd.read_csv(io.BytesIO(data), encoding=enc, dtype=str)
            break
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    if raw is None or raw.empty:
        return pd.DataFrame(columns=HOLD_COLUMNS)

    # 見出しの正規化（空白除去）してマッピング
    norm_cols = {str(c).strip(): c for c in raw.columns}
    mapping: dict[str, str] = {}
    for std, syns in _HEADER_SYNONYMS.items():
        for header, original in norm_cols.items():
            if header in syns or header.lower() in [s.lower() for s in syns]:
                mapping[std] = original
                break

    out = pd.DataFrame()
    for std in ("code", "name", "shares", "avg_cost"):
        out[std] = raw[mapping[std]] if std in mapping else None
    out["hold_type"] = DEFAULT_HOLD_TYPE
    out["note"] = ""
    return _normalize_df(out)


# ========== CSVバックエンド ==========

def _csv_read() -> pd.DataFrame:
    if not os.path.exists(PORTFOLIO_CSV):
        return pd.DataFrame(columns=HOLD_COLUMNS)
    df = pd.read_csv(PORTFOLIO_CSV, dtype={"code": str})
    return _normalize_df(df)


def _csv_write(df: pd.DataFrame) -> None:
    os.makedirs(os.path.dirname(PORTFOLIO_CSV), exist_ok=True)
    _normalize_df(df).to_csv(PORTFOLIO_CSV, index=False, encoding="utf-8-sig")


# ========== Supabaseバックエンド ==========

def _records(df: pd.DataFrame) -> list[dict]:
    df = _normalize_df(df)
    recs = []
    for _, row in df.iterrows():
        recs.append({
            "code": str(row["code"]),
            "name": str(row["name"]) or None,
            "shares": row["shares"] if pd.notna(row["shares"]) else None,
            "avg_cost": row["avg_cost"] if pd.notna(row["avg_cost"]) else None,
            "hold_type": row["hold_type"],
            "note": str(row["note"]) or None,
        })
    return recs


def _sb_read(url: str, key: str) -> pd.DataFrame:
    client = _get_client(url, key)
    res = client.table(TABLE).select("*").execute()
    df = pd.DataFrame(res.data or [])
    return _normalize_df(df)


def _sb_write(url: str, key: str, df: pd.DataFrame) -> None:
    client = _get_client(url, key)
    recs = _records(df)
    desired = {r["code"] for r in recs}
    if recs:
        client.table(TABLE).upsert(recs).execute()
    existing = client.table(TABLE).select("code").execute().data or []
    for r in existing:
        code = str(r.get("code"))
        if code not in desired:
            client.table(TABLE).delete().eq("code", code).execute()


# ========== 公開API ==========

def read_all() -> pd.DataFrame:
    """全保有銘柄をDataFrameで返す（保存先は自動判定。失敗時はCSVへフォールバック）"""
    cfg = _supabase_config()
    if cfg:
        try:
            return _sb_read(*cfg)
        except Exception as e:
            print(f"Supabase保有銘柄の読み込み失敗、CSVにフォールバック: {e}")
    return _csv_read()


def write_all(df: pd.DataFrame) -> None:
    """全保有銘柄を保存する（保存先は自動判定。Supabase失敗時はCSVへ）"""
    cfg = _supabase_config()
    if cfg:
        try:
            _sb_write(*cfg, df)
            return
        except Exception as e:
            print(f"Supabase保有銘柄の保存失敗、CSVにフォールバック: {e}")
    _csv_write(df)
