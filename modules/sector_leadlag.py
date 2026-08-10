"""
modules/sector_leadlag.py
米セクター→日本ETF リードラグ判定（新規モジュール、既存ファイルは変更しない）

設計思想:
    前日の米国セクターの動きが、翌営業日の東京の同セクターに波及する
    （リードラグ・アノマリー）ことを使い、個別株の決算リスクを負わずに
    セクターETFでそれを取る。既存の market_filter.py は市場全体しか見ていないため、
    それを壊さずセクター粒度の判定をここに新設する。

重要な前提（過学習・後追いへの戒め）:
    リードラグは有名なアノマリーで、寄り付きで既に織り込まれ窓を開けることが多い。
    「米↑→翌日寄り成買い」は寄りのギャップを追う形になり、勝率は上がらない。
    このモジュールの価値は「勝率を上げる魔法」ではなく、
    ①個別決算リスクの回避 ②値がさ/かぶミニ問題の回避
    ③セクター選択を機械ルール化してその場の衝動を排除、にある。
    しきい値（LEADLAG_US_RETURN_THRESHOLD等）は全て仮値。
    必ず tools/backtest_leadlag.py で検証してから本採用すること。
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings
from modules import indicators

# 米セクター指標 -> 日本ETFコード のマッピング（指示書ステップ4-1の表に準拠）
# 513A（防衛・日本）は米ITA/XARとの対応が指示書に明記されているが、2026年2月上場と
# 短く実運用時の候補判定には使えてもバックテストでは十分な検証ができない点に注意。
# 466A・1625（ステップ2で追加）は指示書のマッピング表に対応する米指標が示されていないため、
# ここでは対象外とする。
MAPPING: dict[str, dict[str, str]] = {
    "2644": {"us_symbol": "^SOX", "us_fallback": "SOXX", "name": "GX半導体日本株ETF", "sector": "半導体(日本)"},
    "2243": {"us_symbol": "^SOX", "us_fallback": "SMH", "name": "GX半導体ETF", "sector": "半導体(米SOX円換算)"},
    "513A": {"us_symbol": "ITA", "us_fallback": "XAR", "name": "GX防衛テック日本株ETF", "sector": "防衛(日本)"},
    "1627": {"us_symbol": "XLU", "us_fallback": None, "name": "NF電力ガスETF", "sector": "電力・公益"},
}


def us_return(us_df: pd.DataFrame, as_of_idx: int | None = None) -> float | None:
    """米指標の前日比リターンを返す（直近2本の終値から計算）

    Args:
        us_df: date/close列を持つ米指標の日足DataFrame
        as_of_idx: 基準にする行番号（Noneなら最終行）
    """
    if len(us_df) < 2:
        return None
    idx = len(us_df) - 1 if as_of_idx is None else as_of_idx
    if idx < 1 or idx >= len(us_df):
        return None
    prev = float(us_df.iloc[idx - 1]["close"])
    cur = float(us_df.iloc[idx]["close"])
    if prev <= 0:
        return None
    return cur / prev - 1


def decide_entry(prev_close: float, open_: float) -> tuple[str, float]:
    """当日の寄りギャップから、エントリーのモードと価格を決める（指示書4-2）

    寄りギャップが大きい（既に跳ねすぎ）なら押し目待ち（指値）、
    そうでなければブレイク待ち（前日終値上抜けで逆指値）。
    """
    if prev_close <= 0:
        return "ブレイク待ち", prev_close
    gap = open_ / prev_close - 1
    if gap >= settings.LEADLAG_GAP_THRESHOLD:
        return "押し目待ち", (prev_close + open_) / 2
    return "ブレイク待ち", prev_close


def scan_candidates(
    us_data: dict[str, pd.DataFrame], jp_data: dict[str, pd.DataFrame]
) -> list[dict]:
    """前日の米国セクター指標と本日の日本ETF気配から、当日の候補一覧を返す（実運用向け）

    Args:
        us_data: {米シンボル: 日足DataFrame}（最終行が直近の米国終値）
        jp_data: {日本ETFコード: 日足DataFrame}（最終行のopenが本日の日本ETF寄値）
    """
    out: list[dict] = []
    for code, m in MAPPING.items():
        us_df = us_data.get(m["us_symbol"])
        jp_df = jp_data.get(code)
        if us_df is None or jp_df is None or jp_df.empty:
            continue
        ret = us_return(us_df)
        if ret is None or ret < settings.LEADLAG_US_RETURN_THRESHOLD:
            continue
        latest = jp_df.iloc[-1]
        prev_close = float(jp_df.iloc[-2]["close"]) if len(jp_df) >= 2 else float(latest["close"])
        mode, entry = decide_entry(prev_close, float(latest["open"]))
        out.append({
            "コード": code,
            "銘柄名": m["name"],
            "セクター": m["sector"],
            "米指標": m["us_symbol"],
            "米前日比%": round(ret * 100, 2),
            "モード": mode,
            "想定エントリー": round(entry, 2),
            "前日終値": round(prev_close, 2),
            "本日寄値": round(float(latest["open"]), 2),
        })
    return out


def backtest_pair(us_df: pd.DataFrame, jp_df: pd.DataFrame, code: str, name: str) -> list[dict]:
    """1ペア（米指標×日本ETF）のヒストリカル検証（イベントドリブン）

    modules/backtest.py と同じ設計方針（先読み回避・SL優先・summarize()と互換のtrade形式）。
    コスト（LEADLAG_ROUNDTRIP_COST_PCT）はRから直接控除して返す。

    Returns:
        各トレードの dict のリスト（entry_date/exit_date/entry/exit/r/reason/hold + mode/us_return）
    """
    jp = indicators.calc_all(jp_df).reset_index(drop=True)
    us = us_df.sort_values("date").reset_index(drop=True)
    n = len(jp)
    if n < 40 or len(us) < 40:
        return []

    us_dates = us["date"].to_numpy()
    us_close = us["close"].to_numpy()

    trades: list[dict] = []
    i = 1
    while i < n - 1:
        jp_date = np.datetime64(jp.at[i, "date"])
        pos = int(np.searchsorted(us_dates, jp_date, side="left")) - 1
        if pos < 1:
            i += 1
            continue
        prev_us, cur_us = float(us_close[pos - 1]), float(us_close[pos])
        if prev_us <= 0:
            i += 1
            continue
        ret = cur_us / prev_us - 1
        if ret < settings.LEADLAG_US_RETURN_THRESHOLD:
            i += 1
            continue

        prev_close = float(jp.at[i - 1, "close"])
        open_ = float(jp.at[i, "open"])
        mode, entry = decide_entry(prev_close, open_)
        if entry <= 0:
            i += 1
            continue

        entry_idx = i
        lo0, hi0 = float(jp.at[i, "low"]), float(jp.at[i, "high"])
        filled = (lo0 <= entry) if mode == "押し目待ち" else (hi0 >= entry)
        if not filled:
            i += 1
            continue

        atr = float(jp.at[i, "atr"])
        if atr <= 0:
            i += 1
            continue
        sl = entry - settings.LEADLAG_SL_ATR_MULT * atr
        tp = entry + settings.LEADLAG_TP_ATR_MULT * atr
        if entry <= sl:
            i += 1
            continue

        exit_idx = exit_price = reason = None
        for j in range(entry_idx, min(entry_idx + settings.LEADLAG_MAX_HOLD_DAYS, n)):
            lo, hi = float(jp.at[j, "low"]), float(jp.at[j, "high"])
            if lo <= sl:
                exit_idx, exit_price, reason = j, sl, "SL"
                break
            if hi >= tp:
                exit_idx, exit_price, reason = j, tp, "TP"
                break
        if exit_idx is None:
            exit_idx = min(entry_idx + settings.LEADLAG_MAX_HOLD_DAYS, n - 1)
            exit_price, reason = float(jp.at[exit_idx, "close"]), "TIME"

        raw_r = (exit_price - entry) / (entry - sl)
        cost_r = (entry * settings.LEADLAG_ROUNDTRIP_COST_PCT) / (entry - sl)
        trades.append({
            "code": code,
            "name": name,
            "entry_date": jp.at[entry_idx, "date"],
            "exit_date": jp.at[exit_idx, "date"],
            "entry": round(entry, 2),
            "exit": round(exit_price, 2),
            "r": round(raw_r - cost_r, 3),
            "reason": reason,
            "hold": int(exit_idx - entry_idx),
            "mode": mode,
            "us_return": round(ret, 4),
        })
        i = exit_idx + 1
    return trades
