"""
modules/chart_filter.py
チャート3点チェックの数値判定（指示書ステップ6-2）

オーナーが今まで目視でやっていた「チャートの形」の判断を、数値で自動判定する。
これによりスクショ→目視が不要になり、下降トレンド銘柄（参天製薬・住友電工・
清水建設のような形）を機械的に除外できる。

判定は3点＋現在値位置の計4条件。すべてTrueで「チャート合格」とする。
  ① トレンドの方向 : 移動平均が上向きか（is_ma_rising）
  ② 下げ方が急性か : 直近高値からの日数が短い＝急な押し（is_acute_pullback）
                     慢性的にダラダラ下げている銘柄を除外する
  ③ 出来高が細いか : 下落日の出来高が平均より少ない（is_low_volume_pullback）
                     投げ売り・パニック下げを除外する
  ④ 現在値が移動平均の上か（is_above_ma）

日足プリセット（①②③④）は75日移動平均、週足プリセット（⑤⑥）は26週移動平均を参照する。
しきい値（lookback / max_days / window）は上部にまとめ、11月に目視結果と突き合わせて調整する。
"""
from __future__ import annotations

import pandas as pd

# ===== しきい値（目視結果と突き合わせて調整する前提） =====
DAILY_MA_PERIOD = 75          # 日足プリセットの参照移動平均（日）
WEEKLY_MA_PERIOD = 26         # 週足プリセットの参照移動平均（週）
MA_RISING_LOOKBACK_DAILY = 20   # MAの上昇判定：何本前と比べるか（日足）
MA_RISING_LOOKBACK_WEEKLY = 4   # 同上（週足）
ACUTE_MAX_DAYS = 15           # 直近高値からこの日数以内なら「急性の押し」
ACUTE_HIGH_WINDOW = 60        # 直近高値を探す範囲（日）
LOW_VOLUME_WINDOW = 10        # 出来高チェックの直近日数
LOW_VOLUME_AVG_WINDOW = 60    # 出来高の平均を取る期間（日）


# ========== 4つの判定関数（合格=True） ==========

def is_ma_rising(ma_series: pd.Series, lookback: int = MA_RISING_LOOKBACK_DAILY) -> bool:
    """移動平均が上向きか（直近lookback本前より上昇しているか）を判定する"""
    ma = ma_series.dropna()
    if len(ma) <= lookback:
        return False
    return bool(ma.iloc[-1] > ma.iloc[-1 - lookback])


def is_acute_pullback(
    high_series: pd.Series,
    close_series: pd.Series,
    max_days: int = ACUTE_MAX_DAYS,
    high_window: int = ACUTE_HIGH_WINDOW,
) -> bool:
    """下げ方が「急性」か（直近高値をつけてからの日数がmax_days以内か）を判定する

    慢性的な下降トレンド（高値からずっと下げ続けている）を除外するための条件。
    """
    highs = high_series.tail(high_window)
    if highs.empty:
        return False
    recent_high_idx = highs.idxmax()
    days_since_high = len(close_series.loc[recent_high_idx:]) - 1
    return bool(days_since_high <= max_days)


def is_low_volume_pullback(
    close_series: pd.Series,
    volume_series: pd.Series,
    window: int = LOW_VOLUME_WINDOW,
    avg_window: int = LOW_VOLUME_AVG_WINDOW,
) -> bool:
    """下落中の出来高が細いか（下落日の平均出来高 < 全期間平均）を判定する

    投げ売り・パニック的な急落（出来高を伴う下げ）を除外するための条件。
    """
    recent_close = close_series.tail(window)
    recent_vol = volume_series.tail(window)
    down_days = recent_close.diff() < 0
    if not bool(down_days.any()):
        return True  # 直近に下落日がない＝押し目局面ではない。出来高条件は満たすとみなす
    down_vol = recent_vol[down_days].mean()
    avg_vol = volume_series.tail(avg_window).mean()
    if pd.isna(down_vol) or pd.isna(avg_vol) or avg_vol <= 0:
        return False
    return bool(down_vol < avg_vol)


def is_above_ma(close_series: pd.Series, ma_series: pd.Series) -> bool:
    """現在値が移動平均の上にあるかを判定する"""
    ma = ma_series.dropna()
    if ma.empty:
        return False
    return bool(close_series.iloc[-1] > ma.iloc[-1])


# ========== 週足リサンプリング ==========

def to_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """日足OHLCVを週足（金曜終い）にリサンプリングする

    入力: date, open, high, low, close, volume 列を持つ日足DataFrame
    """
    df = daily_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    w = (
        df.set_index("date")
        .resample("W-FRI")
        .agg({"open": "first", "high": "max", "low": "min",
              "close": "last", "volume": "sum"})
        .dropna(subset=["close"])
        .reset_index()
    )
    return w


# ========== 総合判定 ==========

def _check(close_s, high_s, vol_s, ma_s, ma_lookback) -> tuple[bool, dict]:
    """4条件を評価して (合格か, 内訳dict) を返す"""
    checks = {
        "MA上向き": is_ma_rising(ma_s, ma_lookback),
        "急性の押し": is_acute_pullback(high_s, close_s),
        "出来高細い": is_low_volume_pullback(close_s, vol_s),
        "MA上に位置": is_above_ma(close_s, ma_s),
    }
    return all(checks.values()), checks


def chart_check_daily(daily_df: pd.DataFrame, ma_period: int = DAILY_MA_PERIOD) -> tuple[bool, dict]:
    """日足プリセット（①②③④）向けのチャート判定（75日移動平均を使用）"""
    close_s = daily_df["close"]
    ma_s = close_s.rolling(ma_period).mean()
    return _check(close_s, daily_df["high"], daily_df["volume"], ma_s, MA_RISING_LOOKBACK_DAILY)


def chart_check_weekly(daily_df: pd.DataFrame, ma_period: int = WEEKLY_MA_PERIOD) -> tuple[bool, dict]:
    """週足プリセット（⑤⑥）向けのチャート判定（26週移動平均を使用）

    MA方向・MA上位置は週足ベース、押しの急性・出来高は日足ベースで見る。
    """
    weekly = to_weekly(daily_df)
    w_close = weekly["close"]
    w_ma = w_close.rolling(ma_period).mean()
    checks = {
        "26週MA上向き": is_ma_rising(w_ma, MA_RISING_LOOKBACK_WEEKLY),
        "急性の押し": is_acute_pullback(daily_df["high"], daily_df["close"]),
        "出来高細い": is_low_volume_pullback(daily_df["close"], daily_df["volume"]),
        "26週MA上に位置": is_above_ma(w_close, w_ma),
    }
    return all(checks.values()), checks
