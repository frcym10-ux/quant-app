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
from modules import data_fetcher, holdings_store, indicators, swing_scanner

PORTFOLIO_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "portfolio.csv")


def load_holdings() -> list[dict]:
    """保有銘柄リストを返す

    優先順位: ストア（Supabase or portfolio.csv）→ なければ HOLDINGS_JSON 環境変数。
    GitHub Actions ではストアが空（CSV非同梱・Supabase未設定）のため HOLDINGS_JSON を使う。
    """
    df = holdings_store.read_all()
    if df is not None and not df.empty:
        return df.to_dict("records")
    env = os.getenv("HOLDINGS_JSON", "").strip()
    if env:
        try:
            return json.loads(env)
        except Exception:
            pass
    return []


def _to_float(value) -> float | None:
    """数値化（失敗時None）"""
    try:
        if value is None or value == "" or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def analyze_holding(h: dict) -> dict | None:
    """1銘柄の保有分析（現在地・含み損益・推奨利確指値・損切りライン・判定）を返す

    hold_type が 'スイング' のときは具体的な利確指値・損切りラインと売買判定を、
    'ガチホ' のときは長期トレンドの健全性のみを返す。
    """
    code = str(h.get("code", "")).strip().upper()
    if not code:
        return None
    name = h.get("name") or code
    hold_type = h.get("hold_type") if h.get("hold_type") in ("スイング", "ガチホ") else "スイング"
    avg_cost = _to_float(h.get("avg_cost"))
    shares = _to_float(h.get("shares"))

    df = data_fetcher.get_cached_or_fetch(code, 250)
    df = indicators.calc_all(df)
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(latest["close"])
    atr = float(latest["atr"])
    rsi = float(latest["rsi"])
    adx = float(latest["adx"])
    plus_di = float(latest["plus_di"])
    minus_di = float(latest["minus_di"])
    bb_upper = float(latest["bb_upper"])
    ema_long = float(latest["ema_long"])
    is_jp = data_fetcher.is_jp_code(code)

    pl_pct = (close / avg_cost - 1) * 100 if avg_cost else None
    pl_yen = None
    if avg_cost and shares:
        fx = 1.0 if is_jp else swing_scanner.get_usdjpy()
        pl_yen = round((close - avg_cost) * shares * fx, 0)
    change_pct = (close / float(prev["close"]) - 1) * 100

    # --- 損切りライン（ATRトレーリング＝シャンデリア and 直近スイング安値の高い方） ---
    recent_high22 = float(df["high"].tail(22).max())
    recent_low10 = float(df["low"].tail(10).min())
    chandelier = recent_high22 - 3 * atr
    stop = max(chandelier, recent_low10)
    if stop >= close:  # 直近で急騰し損切りが価格を上回る場合は安値ベースに退避
        stop = recent_low10 if recent_low10 < close else close - 2 * atr

    # --- 利確の指値目安（上値抵抗＝BB上限と直近20日高値の高い方。既に上抜けなら+3ATR） ---
    target = max(bb_upper, float(df["high"].tail(20).max()))
    if target <= close:
        target = close + 3 * atr

    downtrend = close < ema_long and adx >= settings.ADX_TREND_THRESHOLD and minus_di > plus_di

    sell_limit = stop_line = None
    if hold_type == "ガチホ":
        if downtrend:
            action = "⚠️ 長期トレンド転換の兆し"
            reason = "中期の平均線を割り込み下げ方向。ガチホでも一部利確やナンピンの是非を再点検。"
        else:
            action = "✅ 継続"
            reason = "長期保有として大きな崩れはありません。"
    else:  # スイング
        sell_limit = round(target, 2)
        stop_line = round(stop, 2)
        cur = "円" if is_jp else "ドル"
        if close <= stop or downtrend:
            action = "🔻 損切り検討"
            reason = (
                f"価格が損切りライン（{stop_line:,.2f}{cur}）付近〜下抜け、または下げトレンド入り。"
                "ルール通りの撤退を検討。"
            )
        elif rsi >= settings.RSI_OVERBOUGHT or close >= bb_upper or close >= target:
            action = "🔺 利確検討"
            reason = (
                f"買われすぎ／上値抵抗に到達。{sell_limit:,.2f}{cur} 付近での利確（指値）を検討。"
            )
        else:
            action = "🟢 継続（保有）"
            reason = (
                f"保有継続でOK。利確の指値目安 {sell_limit:,.2f}{cur} ／ "
                f"損切りライン {stop_line:,.2f}{cur} を置いておく。"
            )

    return {
        "コード": code,
        "銘柄名": name,
        "市場": "日本" if is_jp else "米国",
        "区分": hold_type,
        "現在値": round(close, 2),
        "前日比%": round(change_pct, 2),
        "保有数": int(shares) if shares else None,
        "平均取得": round(avg_cost, 2) if avg_cost else None,
        "含み損益%": round(pl_pct, 1) if pl_pct is not None else None,
        "含み損益円": pl_yen,
        "RSI": round(rsi, 0),
        "ADX": round(adx, 0),
        "推奨利確指値": sell_limit,
        "損切りライン": stop_line,
        "判定": action,
        "理由": reason,
    }


def analyze(holdings: list[dict] | None = None) -> pd.DataFrame:
    """全保有銘柄を分析してDataFrameで返す（区分=スイング/ガチホ別の売買判断つき）"""
    if holdings is None:
        holdings = load_holdings()
    rows = []
    for h in holdings:
        try:
            r = analyze_holding(h)
            if r:
                rows.append(r)
        except Exception:
            continue  # 取得失敗銘柄はスキップ
    return pd.DataFrame(rows)


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
