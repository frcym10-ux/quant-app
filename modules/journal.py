"""
modules/journal.py
スイングトレードの記録（トレードジャーナル）

保存先は trade_store が自動判定（Supabase設定時はクラウド、なければ data/trades.csv）。
実現損益・勝率・期待値を集計し、目標管理（goal.py）に渡す。
損益は「Rマルチプル方式」で通貨に依存せず計算する:
    r = (決済値 - エントリー値) / (エントリー値 - 損切り値)   ← 価格単位の比なので円/ドル不問
    実現損益(円) = r × リスク額(円)
これにより、損切りに当たれば r≈-1（損失=リスク額）、利確(TP)に届けば r≈+1.5 となる。
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules import trade_store
from modules.trade_store import COLUMNS

TRADES_CSV = trade_store.TRADES_CSV  # 後方互換（CSV保存先パス）


def load_trades() -> pd.DataFrame:
    """トレード履歴をDataFrameで返す（保存先はSupabase/CSVを自動判定）"""
    df = trade_store.read_all()
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = None
    return df[COLUMNS]


def _save(df: pd.DataFrame) -> None:
    trade_store.write_all(df)


def add_trade(code: str, name: str, market: str, setup: str,
              entry: float, sl: float, tp: float, shares: float,
              risk_yen: float, date_open: str | None = None, note: str = "") -> str:
    """新しいトレード（保有中）を記録して採番したIDを返す"""
    df = load_trades()
    existing = set(df["id"].astype(str)) if not df.empty else set()
    new_id = dt.datetime.now().strftime("%Y%m%d%H%M%S%f")
    while new_id in existing:  # 念のため衝突回避
        new_id += "1"
    row = {
        "id": new_id,
        "date_open": date_open or dt.date.today().isoformat(),
        "code": code, "name": name, "market": market, "setup": setup,
        "entry": entry, "sl": sl, "tp": tp, "shares": shares, "risk_yen": risk_yen,
        "status": "保有中", "date_close": "", "exit": "", "pnl_yen": "",
        "r_multiple": "", "note": note,
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _save(df)
    return new_id


def close_trade(trade_id: str, exit_price: float, date_close: str | None = None) -> None:
    """保有中トレードを決済して実現損益・Rマルチプルを記録する"""
    df = load_trades()
    mask = df["id"].astype(str) == str(trade_id)
    if not mask.any():
        return
    # 保有中の同IDのみを対象にする（決済済みは再決済しない）
    mask = mask & (df["status"] == "保有中")
    if not mask.any():
        return
    i = df[mask].index[0]
    for col in ["date_close", "exit", "pnl_yen", "r_multiple"]:
        df[col] = df[col].astype(object)  # 空列のfloat64化による警告を回避
    entry = float(df.at[i, "entry"])
    sl = float(df.at[i, "sl"])
    risk_yen = float(df.at[i, "risk_yen"])
    denom = entry - sl
    r = (exit_price - entry) / denom if denom else 0.0
    df.at[i, "status"] = "決済済み"
    df.at[i, "date_close"] = date_close or dt.date.today().isoformat()
    df.at[i, "exit"] = exit_price
    df.at[i, "r_multiple"] = round(r, 3)
    df.at[i, "pnl_yen"] = round(r * risk_yen, 0)
    _save(df)


def delete_trade(trade_id: str) -> None:
    """トレード記録を削除する"""
    df = load_trades()
    df = df[df["id"].astype(str) != str(trade_id)]
    _save(df)


def stats() -> dict:
    """実現損益・勝率・期待値などを集計して返す"""
    df = load_trades()
    closed = df[df["status"] == "決済済み"].copy()
    open_df = df[df["status"] == "保有中"].copy()

    realized = pd.to_numeric(closed["pnl_yen"], errors="coerce").fillna(0)
    r_vals = pd.to_numeric(closed["r_multiple"], errors="coerce").fillna(0)
    n_closed = len(closed)
    wins = (r_vals > 0).sum()
    losses = (r_vals <= 0).sum()
    win_rate = wins / n_closed if n_closed else None
    avg_r = r_vals.mean() if n_closed else None
    expectancy_r = avg_r  # 1トレードあたり平均Rマルチプル
    avg_risk = pd.to_numeric(closed["risk_yen"], errors="coerce").fillna(0).mean() if n_closed else None
    expectancy_yen = expectancy_r * avg_risk if (expectancy_r is not None and avg_risk) else None

    open_risk = pd.to_numeric(open_df["risk_yen"], errors="coerce").fillna(0).sum()

    return {
        "realized_pnl": float(realized.sum()),
        "n_closed": int(n_closed),
        "n_open": int(len(open_df)),
        "wins": int(wins),
        "losses": int(losses),
        "win_rate": float(win_rate) if win_rate is not None else None,
        "avg_r": float(avg_r) if avg_r is not None else None,
        "expectancy_r": float(expectancy_r) if expectancy_r is not None else None,
        "expectancy_yen": float(expectancy_yen) if expectancy_yen is not None else None,
        "open_risk_yen": float(open_risk),
    }


def realized_pnl_in_month(year: int, month: int) -> float:
    """指定年月の実現損益（円）を返す（月間ストップ判定用）"""
    df = load_trades()
    closed = df[df["status"] == "決済済み"].copy()
    if closed.empty:
        return 0.0
    closed["dc"] = pd.to_datetime(closed["date_close"], errors="coerce")
    m = closed[(closed["dc"].dt.year == year) & (closed["dc"].dt.month == month)]
    return float(pd.to_numeric(m["pnl_yen"], errors="coerce").fillna(0).sum())
