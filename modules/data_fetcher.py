"""
modules/data_fetcher.py
J-Quants API（日本株）/ yfinance（米国株）からの日足データ取得とSQLiteキャッシュ
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sqlite3
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings

COLUMNS = ["date", "open", "high", "low", "close", "volume"]


def is_jp_code(code: str) -> bool:
    """銘柄コードが日本株（4桁数字、または4桁+市場区分1文字）かどうかを判定する"""
    return bool(re.fullmatch(r"\d{4}[0-9A-Z]?", code.strip()))


# ========== SQLiteキャッシュ ==========

def _get_conn() -> sqlite3.Connection:
    """キャッシュDBへの接続を返す（テーブルがなければ作成する）"""
    db_path = os.path.join(os.path.dirname(__file__), "..", settings.CACHE_DB_PATH)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS price_cache (
            code TEXT,
            date TEXT,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            fetched_at TEXT,
            PRIMARY KEY (code, date)
        )
        """
    )
    return conn


def _load_cache(code: str, days: int, ignore_expiry: bool = False) -> pd.DataFrame | None:
    """キャッシュから日足データを読み込む。有効期限切れ or データなしなら None を返す"""
    try:
        conn = _get_conn()
        df = pd.read_sql_query(
            "SELECT * FROM price_cache WHERE code = ? ORDER BY date", conn, params=(code,)
        )
        conn.close()
    except Exception:
        return None
    if df.empty:
        return None
    if not ignore_expiry:
        last_fetched = pd.to_datetime(df["fetched_at"].max())
        expire = dt.datetime.now() - dt.timedelta(hours=settings.CACHE_EXPIRE_HOURS)
        if last_fetched < expire:
            return None
    df["date"] = pd.to_datetime(df["date"])
    cutoff = pd.Timestamp(dt.date.today() - dt.timedelta(days=days))
    return df[df["date"] >= cutoff][COLUMNS].reset_index(drop=True)


def _save_cache(code: str, df: pd.DataFrame) -> None:
    """日足データをキャッシュに保存する（同一コード・日付は上書き）"""
    if df.empty:
        return
    try:
        conn = _get_conn()
        now = dt.datetime.now().isoformat()
        rows = [
            (code, row["date"].strftime("%Y-%m-%d"), row["open"], row["high"],
             row["low"], row["close"], row["volume"], now)
            for _, row in df.iterrows()
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO price_cache VALUES (?,?,?,?,?,?,?,?)", rows
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # キャッシュ保存失敗は致命的ではない


# ========== データ取得 ==========

def get_jp_stock(code: str, days: int) -> pd.DataFrame:
    """日本株の日足データを取得する

    最新データが取れる yfinance（東証ティッカー: XXXX.T）を優先し、
    失敗時は J-Quants API v2 にフォールバックする。
    （J-Quants無料プランは約12週間遅延のヒストリカルデータのみ提供）
    """
    try:
        return get_us_stock(f"{code}.T", days)
    except Exception:
        return _get_jp_stock_jquants(code, days)


def _get_jp_stock_jquants(code: str, days: int) -> pd.DataFrame:
    """J-Quants API v2 で日本株の日足データを取得する（フォールバック用）

    無料プランは直近約12週分が提供されない（遅延データ）。取得できた分を返す。
    """
    from jquantsapi import ClientV2

    api_key = settings.JQUANTS_API_KEY
    if not api_key or "ここに" in api_key:
        raise RuntimeError(
            "J-Quants APIキー未設定（.env の JQUANTS_REFRESH_TOKEN にAPIキーを記入してください）"
        )
    client = ClientV2(api_key=api_key)
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    raw = client.get_eq_bars_daily(
        code=code,
        from_yyyymmdd=start.strftime("%Y%m%d"),
        to_yyyymmdd=end.strftime("%Y%m%d"),
    )
    if raw is None or raw.empty:
        raise RuntimeError(f"J-Quants からデータを取得できませんでした: {code}")
    # 列名はAPIバージョンで揺れるため候補から解決する（調整後株価を優先）
    def find_col(*candidates: str) -> str:
        lower_map = {c.lower(): c for c in raw.columns}
        for cand in candidates:
            if cand.lower() in lower_map:
                return lower_map[cand.lower()]
        raise RuntimeError(f"J-Quants応答に想定列がありません: {candidates} / {list(raw.columns)}")

    df = pd.DataFrame({
        "date": pd.to_datetime(raw[find_col("Date")]),
        "open": raw[find_col("AdjustmentOpen", "AdjO", "Open", "O")],
        "high": raw[find_col("AdjustmentHigh", "AdjH", "High", "H")],
        "low": raw[find_col("AdjustmentLow", "AdjL", "Low", "L")],
        "close": raw[find_col("AdjustmentClose", "AdjC", "Close", "C")],
        "volume": raw[find_col("AdjustmentVolume", "AdjV", "Volume", "V")],
    })
    return df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)


def get_us_stock(ticker: str, days: int) -> pd.DataFrame:
    """yfinanceで米国株・ETFの日足データを取得する"""
    import yfinance as yf

    end = dt.date.today() + dt.timedelta(days=1)
    start = dt.date.today() - dt.timedelta(days=days)
    raw = yf.download(
        ticker, start=start.isoformat(), end=end.isoformat(),
        auto_adjust=True, progress=False,
    )
    if raw is None or raw.empty:
        raise RuntimeError(f"yfinance からデータを取得できませんでした: {ticker}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.droplevel(1)
    df = raw.reset_index().rename(columns={
        "Date": "date", "Open": "open", "High": "high",
        "Low": "low", "Close": "close", "Volume": "volume",
    })[COLUMNS]
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    return df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)


def get_cached_or_fetch(code: str, days: int) -> pd.DataFrame:
    """キャッシュがあれば返し、なければAPIから取得してキャッシュする

    API失敗時は期限切れキャッシュでもフォールバックとして返す。
    """
    code = code.strip().upper()
    cached = _load_cache(code, days)
    if cached is not None and not cached.empty:
        return cached
    try:
        if is_jp_code(code):
            df = get_jp_stock(code, days)
        else:
            df = get_us_stock(code, days)
        _save_cache(code, df)
        return df
    except Exception:
        stale = _load_cache(code, days, ignore_expiry=True)
        if stale is not None and not stale.empty:
            return stale
        raise
