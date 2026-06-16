"""
modules/holdings_monitor.py
保有銘柄に「売り時・買い増し」サインが出ていないかを判定する

データの出どころは2系統:
  - ローカルアプリ: data/portfolio.csv（code, name, shares, avg_cost）
  - GitHub Actions: 環境変数 HOLDINGS_JSON（[{code, name, avg_cost}, ...]）
        ※ portfolio.csv はリポジトリに含めないため、Actionsでは秘匿シークレットで渡す

サインはすべて平易な日本語で返す（投資判断の参考用、売買推奨ではない）。
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings
from modules import data_fetcher, indicators

PORTFOLIO_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "portfolio.csv")


def load_holdings() -> list[dict]:
    """保有銘柄リストを返す（HOLDINGS_JSON環境変数を優先、なければCSV）"""
    env = os.getenv("HOLDINGS_JSON", "").strip()
    if env:
        try:
            return json.loads(env)
        except Exception:
            pass
    if os.path.exists(PORTFOLIO_CSV):
        df = pd.read_csv(PORTFOLIO_CSV, dtype={"code": str})
        return df.to_dict("records")
    return []


def _judge(name: str, code: str, df: pd.DataFrame, avg_cost: float | None) -> dict | None:
    """1銘柄を判定して保有サインdictを返す（サインなしならNone）"""
    df = indicators.calc_all(df)
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(latest["close"])
    rsi = float(latest["rsi"])
    adx = float(latest["adx"])
    plus_di = float(latest["plus_di"])
    minus_di = float(latest["minus_di"])

    pl_pct = ((close / avg_cost) - 1) * 100 if avg_cost else None

    signal = None       # "売り検討" / "買い増し検討" / None
    emoji = ""
    reasons: list[str] = []

    # --- 売り検討サイン ---
    # 1. 下落トレンドへ転換
    if close < float(latest["ema_long"]) and adx >= settings.ADX_TREND_THRESHOLD and minus_di > plus_di:
        signal, emoji = "売り検討", "🔻"
        reasons.append("下落の方向感が強まっています（中期の平均線を割り込み、下げトレンド入りの兆し）。撤退ラインを意識")
    # 2. 短期的に買われすぎ（利益が乗っているなら一部利確）
    elif rsi >= settings.RSI_OVERBOUGHT:
        signal, emoji = "売り検討", "🔺"
        msg = "短期的に買われすぎの水準です。"
        if pl_pct is not None and pl_pct > 0:
            msg += f"含み益（約{pl_pct:+.0f}%）が乗っているなら一部利確も検討。"
        else:
            msg += "過熱感があるので戻り売りに注意。"
        reasons.append(msg)
    # 3. レンジ上限まで戻った（平均回帰の利確）
    elif adx < settings.ADX_RANGE_THRESHOLD and close >= float(latest["kc_upper"]):
        signal, emoji = "売り検討", "🔺"
        reasons.append("横ばい相場の上限まで戻りました。反落しやすい位置なので利確を検討")

    # --- 買い増し検討サイン ---
    if signal is None and adx < settings.ADX_RANGE_THRESHOLD:
        if (close <= float(latest["kc_lower"]) or close <= float(latest["bb_lower"])) and rsi <= settings.RSI_OVERSOLD:
            signal, emoji = "買い増し検討", "🟢"
            msg = "下がりすぎの水準まで来ました（反発が出やすい位置）。"
            if pl_pct is not None and pl_pct < 0:
                msg += f"含み損（約{pl_pct:+.0f}%）の銘柄なら平均取得単価を下げる買い増しの候補。"
            reasons.append(msg + "ただし下落トレンド中でないか要確認")

    if signal is None:
        return None

    change_pct = (close / float(prev["close"]) - 1) * 100
    return {
        "コード": code,
        "銘柄名": name,
        "サイン": signal,
        "絵文字": emoji,
        "終値": round(close, 2),
        "前日比%": round(change_pct, 2),
        "含み損益%": round(pl_pct, 1) if pl_pct is not None else None,
        "解説": " ".join(reasons),
    }


def scan_holdings() -> pd.DataFrame:
    """全保有銘柄を判定し、サインの出た銘柄のDataFrameを返す"""
    rows = []
    for h in load_holdings():
        code = str(h.get("code", "")).strip().upper()
        if not code:
            continue
        name = h.get("name", code)
        avg_cost = h.get("avg_cost")
        try:
            avg_cost = float(avg_cost) if avg_cost not in (None, "", "nan") else None
        except (TypeError, ValueError):
            avg_cost = None
        try:
            df = data_fetcher.get_cached_or_fetch(code, 180)
            r = _judge(name, code, df, avg_cost)
            if r:
                rows.append(r)
        except Exception:
            continue  # 取得失敗銘柄はスキップ
    return pd.DataFrame(rows)
