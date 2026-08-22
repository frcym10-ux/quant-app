"""
modules/screener_backtest.py
週次スクリーナー（6プリセット）のヒストリカル検証（ステップ8）

modules/backtest.py と同じイベントドリブン・エンジン（backtest_symbol/summarize）を再利用し、
シグナル生成だけを screener.py の実運用ロジック（各プリセットの評価関数＋チャート3点チェック）で
過去の各時点を再評価する形で作る。screener.py 側のロジックを変更・複製しないため、
実運用とバックテストでスクリーニング条件が食い違う心配がない。

制約（実運用との違い・簡略化。11月の実績照合時に念頭に置くこと）:
  1. 財務指標（ROE・PER・配当利回り・経常利益変化率）はその時点に遡って取得できないため、
     バックテストでは常に未取得（fund={}）として扱う＝ファンダ条件は毎回「要確認」扱いで
     素通りする。つまりこの検証は各プリセットの「チャート・テクニカル条件」の有効性のみを
     測るものであり、⑤GC×高配当・⑥週足中期のファンダ部分の有効性は評価できていない。
  2. エントリーは modules/backtest.py と同じ「シグナルが出た翌営業日の始値」で約定した
     と仮定する（実際の指値・ブレイク水準へのタッチを待つシミュレーションはしない簡略化）。
  3. 週足プリセット（⑤⑥）は実運用と同じ週次カデンスで判定する（毎営業日ではなくWEEKLY_STRIDE
     営業日おき）。日足プリセット（①②③④）は毎営業日判定する。
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings
from modules import backtest, chart_filter, indicators, order_calc, screener

# 75日MA・26週MA（≒130営業日）・52週高値（252営業日）すべてに十分な履歴を確保する
MIN_LOOKBACK = 260
WEEKLY_STRIDE = 5  # 週足プリセットは約5営業日（1週間）おきに判定する


def preset_signal(preset_id: str, df: pd.DataFrame) -> pd.Series:
    """指定プリセットの過去シグナルを返す（1=その日成立、翌営業日始値でエントリーする想定）

    Args:
        preset_id: "①"〜"⑥"
        df: date/open/high/low/close/volume を持つ日足DataFrame（十分な履歴が必要）
    """
    df = df.reset_index(drop=True)
    df_ind = indicators.calc_all(df)
    evaluator = screener.PRESET_EVAL[preset_id]
    timeframe = screener.PRESET_TIMEFRAME[preset_id]
    n = len(df_ind)
    sig = pd.Series(0, index=df_ind.index)
    if n <= MIN_LOOKBACK:
        return sig

    stride = WEEKLY_STRIDE if timeframe == "weekly" else 1
    for i in range(MIN_LOOKBACK, n, stride):
        window = df_ind.iloc[: i + 1]
        common_ok, _ = screener.passes_common_prereq(window, settings.AVAILABLE_CASH)
        if not common_ok:
            continue
        specific, _, _ = evaluator(window, {})  # fund={} → ファンダ条件は常に「未取得」で素通り
        checks = {"共通前提": common_ok, **specific}
        if not screener._finalize(checks)["pass"]:
            continue
        if timeframe == "weekly":
            chart_ok, _ = chart_filter.chart_check_weekly(window)
        else:
            chart_ok, _ = chart_filter.chart_check_daily(window)
        if chart_ok:
            sig.iloc[i] = 1
    return sig


def _sl_tp_mult(preset_id: str) -> tuple[float, float]:
    """プリセットの時間軸に応じたSL/TPのATR倍率（order_calc.pyの定数と揃える）"""
    if screener.PRESET_TIMEFRAME[preset_id] == "weekly":
        return order_calc.WEEKLY_SL_ATR_MULT, order_calc.WEEKLY_TP_ATR_MULT
    return order_calc.DAILY_SL_ATR_MULT, order_calc.DAILY_TP_ATR_MULT


def backtest_preset(
    preset_id: str,
    data: dict[str, pd.DataFrame],
    names: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """1プリセットをユニバース全銘柄で検証し、銘柄別成績と全体集計を返す"""
    names = names or {}
    sl_mult, tp_mult = _sl_tp_mult(preset_id)
    strategy = backtest.Strategy(
        preset_id, screener.PRESET_NAMES[preset_id], lambda d: preset_signal(preset_id, d)
    )

    all_trades: list[dict] = []
    rows = []
    for code, df in data.items():
        try:
            trades = backtest.backtest_symbol(df, strategy, sl_mult=sl_mult, tp_mult=tp_mult)
        except Exception:
            continue
        all_trades.extend(trades)
        s = backtest.summarize(trades)
        if s["n_trades"] == 0:
            continue
        rows.append({
            "コード": code,
            "銘柄名": names.get(code, code),
            "トレード数": s["n_trades"],
            "勝率": round(s["win_rate"] * 100, 1),
            "期待値R": round(s["expectancy_r"], 3),
            "PF": round(s["profit_factor"], 2) if s["profit_factor"] != float("inf") else 99.0,
            "最大DD_R": round(s["max_drawdown_r"], 2),
            "累計R": round(s["total_r"], 2),
        })

    overall = backtest.summarize(all_trades)
    overall["strategy"] = screener.PRESET_NAMES[preset_id]
    overall["by_year"] = backtest.summarize_by_year(all_trades)
    per_symbol = (
        pd.DataFrame(rows).sort_values("累計R", ascending=False).reset_index(drop=True)
        if rows else pd.DataFrame()
    )
    return per_symbol, overall


def backtest_all_presets(
    data: dict[str, pd.DataFrame] | None = None,
    period: str = "2y",
    presets: list[str] | None = None,
    names: dict[str, str] | None = None,
) -> dict[str, tuple[pd.DataFrame, dict]]:
    """複数プリセット（省略時は全6つ）をユニバース全銘柄で検証する

    Returns:
        {プリセットID: (銘柄別成績DataFrame, 全体集計dict)}
    """
    if data is None:
        from modules import swing_scanner, universe
        names = names or universe.all_codes()
        data = swing_scanner.batch_fetch(list(names.keys()), period=period)
    elif names is None:
        from modules import universe
        names = universe.all_codes()

    presets = presets or list(screener.PRESET_NAMES.keys())
    return {pid: backtest_preset(pid, data, names) for pid in presets}
