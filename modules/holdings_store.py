"""
modules/holdings_store.py
保有銘柄（ポートフォリオ）の保存先を抽象化するストレージ層

- SUPABASE_URL と SUPABASE_KEY が設定されていれば Supabase の quant_holdings テーブル
- なければローカルCSV（data/portfolio.csv）

各銘柄に hold_type（'スイング' / 'ガチホ'）を持たせ、画面から編集・CSV取込できる。
証券会社のCSV（楽天証券など・日本語見出し・cp932/utf-8）からの取込にも対応する。
"""
from __future__ import annotations

import csv
import io
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TABLE = "quant_holdings"
PORTFOLIO_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "portfolio.csv")

HOLD_COLUMNS = ["code", "name", "shares", "avg_cost", "hold_type", "note"]
HOLD_TYPES = ["スイング", "ガチホ"]
DEFAULT_HOLD_TYPE = "スイング"

_NUMERIC = {"shares", "avg_cost"}

# 証券会社CSVの見出し→標準列名のゆらぎ吸収（完全一致・大文字小文字無視で照合）
# 楽天証券「保有商品詳細」は「銘柄コード・ティッカー」「銘柄」等の独特な見出し。
_HEADER_SYNONYMS = {
    "code": ["銘柄コード・ティッカー", "銘柄コード", "コード", "証券コード", "ティッカー",
             "code", "ticker", "symbol"],
    "name": ["銘柄", "銘柄名", "名称", "name", "銘柄名称"],
    "shares": ["保有数量", "数量", "株数", "保有株数", "保有口数", "shares", "quantity", "qty", "口数"],
    "avg_cost": ["平均取得価額", "取得単価", "平均取得単価", "取得価額", "平均取得",
                 "取得平均", "avg_cost", "cost", "average_cost", "買付単価"],
}

# 取得対象とみなす銘柄コード（日本株4桁＋任意英字 / 米国ティッカー）。投資信託・現金等は除外。
_CODE_RE = re.compile(r"\d{3,4}[0-9A-Z]?|[A-Z]{1,5}")

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

def _map_header(cells: list[str]) -> dict[str, int]:
    """ヘッダー行のセル一覧から、標準列名→列インデックスの対応を返す（完全一致）"""
    norm = [str(c).strip().strip('"').strip() for c in cells]
    norm_l = [c.lower() for c in norm]
    mapping: dict[str, int] = {}
    for std, syns in _HEADER_SYNONYMS.items():
        syns_l = [s.lower() for s in syns]
        for idx, (cell, cell_l) in enumerate(zip(norm, norm_l)):
            if cell in syns or cell_l in syns_l:
                mapping[std] = idx
                break
    return mapping


def parse_broker_csv(data: bytes) -> pd.DataFrame:
    """証券会社のCSV（bytes）を読み、標準列のDataFrameに変換する

    楽天証券のように先頭に「資産合計欄」などの別セクションがあっても、
    保有明細のヘッダー行（保有数量・平均取得価額・銘柄コードを含む行）を自動検出して
    そこから読み取る。区切りはタブ/カンマを自動判定し、引用符内のカンマも正しく扱う。
    投資信託・現金など取得対象外のコードは除外する。
    """
    text = None
    for enc in ("utf-8-sig", "cp932", "utf-8"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return pd.DataFrame(columns=HOLD_COLUMNS)

    delimiter = "\t" if "\t" in text else ","
    reader = list(csv.reader(io.StringIO(text), delimiter=delimiter))

    # 明細ヘッダー行を探す（code/shares/avg_cost が揃う行）
    header_idx = None
    mapping: dict[str, int] = {}
    for i, cells in enumerate(reader):
        m = _map_header(cells)
        if {"code", "shares", "avg_cost"} <= set(m):
            header_idx, mapping = i, m
            break
    if header_idx is None:
        return pd.DataFrame(columns=HOLD_COLUMNS)

    max_idx = max(mapping.values())
    rows = []
    for cells in reader[header_idx + 1:]:
        if not any(str(c).strip() for c in cells):
            continue  # 空行・区切り行
        if len(cells) <= max_idx:
            continue  # 列数が足りない行（小計行など）
        rows.append({
            "code": cells[mapping["code"]].strip(),
            "name": cells[mapping["name"]].strip() if "name" in mapping else "",
            "shares": cells[mapping["shares"]],
            "avg_cost": cells[mapping["avg_cost"]],
            "hold_type": DEFAULT_HOLD_TYPE,
            "note": "",
        })
    if not rows:
        return pd.DataFrame(columns=HOLD_COLUMNS)

    df = _normalize_df(pd.DataFrame(rows))
    # 取得可能なコード（日本株/米国ティッカー）だけ残す＝投資信託・現金行を除外
    df = df[df["code"].map(lambda c: bool(_CODE_RE.fullmatch(str(c))))].reset_index(drop=True)
    return df


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
