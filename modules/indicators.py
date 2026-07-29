"""
modules/indicators.py
テクニカル指標の一括計算（pandas/numpyによる自前実装）

計算する指標：
- MACD (12, 26, 9)
- RSI (14, Wilder平滑化)
- Bollinger Bands (20, 2.0)
- Keltner Channels (EMA20, ATR10, 乗数2.0)
- ATR (14, Wilder平滑化)
- ADX (14, Wilder平滑化)
- EMA (12, 26)
- VWAP（日足データのため期間先頭アンカーの近似計算）
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings


def _ema(s: pd.Series, period: int) -> pd.Series:
    """指数移動平均（EMA）を計算する"""
    return s.ewm(span=period, adjust=False).mean()


def _rma(s: pd.Series, period: int) -> pd.Series:
    """Wilder平滑化移動平均（RMA）を計算する。RSI/ATR/ADXで使用"""
    return s.ewm(alpha=1.0 / period, adjust=False).mean()


def _true_range(df: pd.DataFrame) -> pd.Series:
    """True Range を計算する"""
    prev_close = df["close"].shift(1)
    return pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def calc_rsi(close: pd.Series, period: int = settings.RSI_PERIOD) -> pd.Series:
    """RSI（Wilder方式）を計算する"""
    delta = close.diff()
    gain = _rma(delta.clip(lower=0), period)
    loss = _rma((-delta).clip(lower=0), period)
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def calc_atr(df: pd.DataFrame, period: int = settings.ATR_PERIOD) -> pd.Series:
    """ATR（Wilder方式）を計算する"""
    return _rma(_true_range(df), period)


def calc_adx(df: pd.DataFrame, period: int = settings.ADX_PERIOD) -> pd.DataFrame:
    """ADXと+DI/-DI（Wilder方式）を計算してDataFrameで返す"""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    atr = _rma(_true_range(df), period)
    plus_di = 100 * _rma(plus_dm, period) / atr
    minus_di = 100 * _rma(minus_dm, period) / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return pd.DataFrame({
        "adx": _rma(dx.fillna(0), period),
        "plus_di": plus_di,
        "minus_di": minus_di,
    })


def calc_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAPを計算する（日足のため期間先頭アンカーの累積近似）"""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].fillna(0)
    cum_vol = vol.cumsum().replace(0, np.nan)
    return (typical * vol).cumsum() / cum_vol


def calc_all(df: pd.DataFrame) -> pd.DataFrame:
    """全テクニカル指標を一括計算して列を追加したDataFrameを返す

    入力: date, open, high, low, close, volume 列を持つ日足DataFrame
    """
    df = df.copy().reset_index(drop=True)
    close = df["close"]

    # EMA
    df["ema_short"] = _ema(close, settings.EMA_SHORT)
    df["ema_long"] = _ema(close, settings.EMA_LONG)

    # SMA（中期トレンド判定・乖離率用。買いシグナルのハードフィルターで使用）
    df["sma_mid"] = close.rolling(settings.SMA_MID_PERIOD).mean()      # 25日線
    df["sma_trend"] = close.rolling(settings.SMA_TREND_PERIOD).mean()  # 75日線
    df["disparity_mid"] = (close / df["sma_mid"] - 1) * 100            # 25日線からの乖離%

    # MACD
    macd = _ema(close, settings.MACD_FAST) - _ema(close, settings.MACD_SLOW)
    df["macd"] = macd
    df["macd_signal"] = _ema(macd, settings.MACD_SIGNAL)
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # RSI
    df["rsi"] = calc_rsi(close)

    # Bollinger Bands
    mid = close.rolling(settings.BB_PERIOD).mean()
    std = close.rolling(settings.BB_PERIOD).std(ddof=0)
    df["bb_mid"] = mid
    df["bb_upper"] = mid + settings.BB_STDDEV * std
    df["bb_lower"] = mid - settings.BB_STDDEV * std

    # ATR（リスク管理用14期間）
    df["atr"] = calc_atr(df)

    # Keltner Channels（EMA20 ± ATR10 × 2.0）
    kc_mid = _ema(close, settings.KC_EMA_PERIOD)
    kc_atr = calc_atr(df, settings.KC_ATR_PERIOD)
    df["kc_mid"] = kc_mid
    df["kc_upper"] = kc_mid + settings.KC_MULTIPLIER * kc_atr
    df["kc_lower"] = kc_mid - settings.KC_MULTIPLIER * kc_atr

    # ADX（+DI/-DI付き）
    adx_df = calc_adx(df)
    df["adx"] = adx_df["adx"]
    df["plus_di"] = adx_df["plus_di"]
    df["minus_di"] = adx_df["minus_di"]

    # VWAP
    df["vwap"] = calc_vwap(df)

    return df
