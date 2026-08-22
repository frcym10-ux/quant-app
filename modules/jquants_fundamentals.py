"""
modules/jquants_fundamentals.py
J-Quants API から財務指標（ROE・配当利回り・PER・経常利益変化率）と
決算発表予定日を取得する（ステップ7：J-Quants連携）。

yfinanceは日本株の財務データが欠けやすく（特に経常利益変化率は非対応）、
J-Quants APIキーが設定されていればこちらを優先して精度を上げる。
未設定・取得失敗時は None を返し、呼び出し側（screener.fetch_fundamentals /
earnings.load_earnings）で yfinance・手動登録にフォールバックする。
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings

_client = None  # プロセス内で使い回す（呼び出しのたびに認証しない）


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = settings.JQUANTS_API_KEY
    if not api_key or "ここに" in api_key:
        raise RuntimeError("J-Quants APIキー未設定")
    from jquantsapi import ClientV2
    _client = ClientV2(api_key=api_key)
    return _client


def _to_pct(value) -> float | None:
    """比率(0.12)・%(12.0)どちらの表現で返ってきても%表示に正規化する"""
    if value is None or pd.isna(value):
        return None
    v = float(value)
    return round(v * 100, 1) if abs(v) <= 1.0 else round(v, 1)


def fetch_fundamentals_jquants(code: str, price: float | None = None) -> dict:
    """J-Quants /fins/summary から財務指標を取得する（ベストエフォート）

    Args:
        code: 銘柄コード
        price: PER・配当利回りの算出に使う現在値（省略時はこの2項目は算出しない）
    Returns:
        {"roe": float|None, "dividend_yield": float|None, "per": float|None,
         "ordinary_income_growth": float|None}
    """
    result = {"roe": None, "dividend_yield": None, "per": None, "ordinary_income_growth": None}
    try:
        client = _get_client()
        df = client.get_fin_summary(code=code)
        if df is None or df.empty:
            return result
        df = df.sort_values("DiscDate").reset_index(drop=True)
        latest = df.iloc[-1]

        result["roe"] = _to_pct(latest["ROE"])

        if price:
            div = latest["FDivAnn"]
            if div is None or pd.isna(div):
                div = latest["DivAnn"]
            if div is not None and not pd.isna(div) and float(price) > 0:
                result["dividend_yield"] = round(float(div) / float(price) * 100, 2)

            feps = latest["FEPS"]  # 今期予想EPS（通期）→ 予想PER
            if feps is not None and not pd.isna(feps) and float(feps) != 0:
                result["per"] = round(float(price) / float(feps), 1)

        # 経常利益変化率 = 同じ期間区分（Q1/Q2/…/FY）の前年同期との比較
        cur_type = latest["CurPerType"]
        cur_odp = latest["OdP"]
        if pd.notna(cur_type) and cur_odp is not None and pd.notna(cur_odp):
            same_type = df[df["CurPerType"] == cur_type]
            if len(same_type) >= 2:
                prior_odp = same_type.iloc[-2]["OdP"]
                if prior_odp is not None and pd.notna(prior_odp) and float(prior_odp) != 0:
                    result["ordinary_income_growth"] = round(
                        (float(cur_odp) - float(prior_odp)) / abs(float(prior_odp)) * 100, 1
                    )
    except Exception:
        pass
    return result


def fetch_earnings_date_jquants(code: str) -> dt.date | None:
    """J-Quants /fins/earnings-date から直近有効な決算発表予定日を取得する（ベストエフォート）"""
    try:
        client = _get_client()
        df = client.get_fin_earnings_date(code=code)
        if df is None or df.empty:
            return None
        df = df.sort_values("PubDate").reset_index(drop=True)
        sch = df.iloc[-1]["SchDate"]
        if sch is None or pd.isna(sch):
            return None
        return pd.Timestamp(sch).date()
    except Exception:
        return None
