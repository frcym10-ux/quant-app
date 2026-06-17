"""
pages/2_chart.py
テクニカル分析チャート画面（Plotly 4段構成）
"""
import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings
from modules import auth, data_fetcher, indicators, risk_manager, strategy_alpha, strategy_beta

st.set_page_config(page_title="テクニカル分析チャート", page_icon="📊", layout="wide")
auth.require_auth()
st.title("📊 テクニカル分析チャート")


@st.cache_data(ttl=3600, show_spinner="データ取得中...")
def load_data(code: str, days: int) -> pd.DataFrame:
    """データ取得＋指標計算（Streamlitキャッシュ付き）"""
    df = data_fetcher.get_cached_or_fetch(code, days)
    return indicators.calc_all(df)


# ========== 入力エリア ==========
default_code = st.session_state.get("selected_code", "VOO")
col1, col2 = st.columns([1, 2])
with col1:
    code = st.text_input("銘柄コード（例: 7011, VOO）", value=default_code)
with col2:
    period_label = st.radio(
        "期間", list(settings.CHART_PERIOD_OPTIONS.keys()),
        index=list(settings.CHART_PERIOD_OPTIONS.keys()).index(settings.DEFAULT_CHART_PERIOD),
        horizontal=True,
    )
days = settings.CHART_PERIOD_OPTIONS[period_label]

with st.expander("表示する指標", expanded=False):
    c1, c2, c3, c4, c5 = st.columns(5)
    show_bb = c1.checkbox("ボリンジャーバンド", value=True)
    show_kc = c2.checkbox("ケルトナーチャネル", value=True)
    show_vwap = c3.checkbox("VWAP", value=True)
    show_ema = c4.checkbox("EMA12/26", value=True)
    show_signals = c5.checkbox("戦略シグナル", value=True)

if not code.strip():
    st.info("銘柄コードを入力してください。")
    st.stop()

code = code.strip().upper()

try:
    df = load_data(code, days)
except Exception as e:
    st.error(f"データ取得に失敗しました: {e}")
    st.stop()

# ========== 4段チャート ==========
fig = make_subplots(
    rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
    row_heights=[0.5, 0.17, 0.17, 0.16],
    subplot_titles=(f"{code} 日足", "MACD (12,26,9)", "RSI (14)", "ADX (14)"),
)

# --- メイン: ローソク足 ---
fig.add_trace(go.Candlestick(
    x=df["date"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
    name="ローソク足", increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
), row=1, col=1)

if show_bb:
    fig.add_trace(go.Scatter(x=df["date"], y=df["bb_upper"], name="BB上限",
                             line=dict(color="rgba(100,149,237,0.6)", width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["date"], y=df["bb_lower"], name="BB下限",
                             line=dict(color="rgba(100,149,237,0.6)", width=1),
                             fill="tonexty", fillcolor="rgba(100,149,237,0.08)"), row=1, col=1)
if show_kc:
    fig.add_trace(go.Scatter(x=df["date"], y=df["kc_upper"], name="KC上限",
                             line=dict(color="rgba(255,165,0,0.7)", width=1, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["date"], y=df["kc_mid"], name="KC中央(EMA20)",
                             line=dict(color="rgba(255,165,0,0.9)", width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["date"], y=df["kc_lower"], name="KC下限",
                             line=dict(color="rgba(255,165,0,0.7)", width=1, dash="dot")), row=1, col=1)
if show_vwap:
    fig.add_trace(go.Scatter(x=df["date"], y=df["vwap"], name="VWAP",
                             line=dict(color="purple", width=1.5, dash="dash")), row=1, col=1)
if show_ema:
    fig.add_trace(go.Scatter(x=df["date"], y=df["ema_short"], name="EMA12",
                             line=dict(color="#2196f3", width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["date"], y=df["ema_long"], name="EMA26",
                             line=dict(color="#f44336", width=1)), row=1, col=1)

# --- 戦略シグナル矢印 ---
if show_signals:
    sig_a = strategy_alpha.signal(df)
    sig_b = strategy_beta.signal(df)
    longs = df[(sig_a == 1) | (sig_b == 1)]
    shorts = df[sig_a == -1]
    if not longs.empty:
        fig.add_trace(go.Scatter(
            x=longs["date"], y=longs["low"] * 0.99, mode="markers", name="ロングシグナル",
            marker=dict(symbol="triangle-up", size=12, color="#26a69a"),
        ), row=1, col=1)
    if not shorts.empty:
        fig.add_trace(go.Scatter(
            x=shorts["date"], y=shorts["high"] * 1.01, mode="markers", name="ショートシグナル",
            marker=dict(symbol="triangle-down", size=12, color="#ef5350"),
        ), row=1, col=1)

# --- サブ1: MACD ---
hist_colors = ["#26a69a" if v >= 0 else "#ef5350" for v in df["macd_hist"].fillna(0)]
fig.add_trace(go.Bar(x=df["date"], y=df["macd_hist"], name="MACDヒスト",
                     marker_color=hist_colors), row=2, col=1)
fig.add_trace(go.Scatter(x=df["date"], y=df["macd"], name="MACD",
                         line=dict(color="#2196f3", width=1.2)), row=2, col=1)
fig.add_trace(go.Scatter(x=df["date"], y=df["macd_signal"], name="Signal",
                         line=dict(color="#ff9800", width=1.2)), row=2, col=1)

# --- サブ2: RSI ---
fig.add_trace(go.Scatter(x=df["date"], y=df["rsi"], name="RSI14",
                         line=dict(color="#9c27b0", width=1.2)), row=3, col=1)
fig.add_hline(y=settings.RSI_OVERBOUGHT, line=dict(color="red", width=1, dash="dash"), row=3, col=1)
fig.add_hline(y=settings.RSI_OVERSOLD, line=dict(color="green", width=1, dash="dash"), row=3, col=1)

# --- サブ3: ADX ---
fig.add_trace(go.Scatter(x=df["date"], y=df["adx"], name="ADX14",
                         line=dict(color="#607d8b", width=1.2)), row=4, col=1)
fig.add_hline(y=settings.ADX_RANGE_THRESHOLD, line=dict(color="green", width=1, dash="dash"), row=4, col=1)
fig.add_hline(y=settings.ADX_TREND_THRESHOLD, line=dict(color="red", width=1, dash="dash"), row=4, col=1)

# 非営業日の隙間を除去
all_days = pd.date_range(df["date"].min(), df["date"].max())
missing = sorted(set(all_days.date) - set(df["date"].dt.date))
fig.update_xaxes(rangebreaks=[dict(values=[d.isoformat() for d in missing])])

fig.update_layout(
    height=900, xaxis_rangeslider_visible=False,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    margin=dict(t=80, b=40),
)
st.plotly_chart(fig, use_container_width=True)

# ========== 最新シグナル・リスク情報 ==========
latest = df.iloc[-1]
sig_a_now = strategy_alpha.signal(df).iloc[-1]
sig_b_now = strategy_beta.signal(df).iloc[-1]

m1, m2, m3, m4 = st.columns(4)
m1.metric("現在値", f"{latest['close']:,.2f}")
m2.metric("RSI14", f"{latest['rsi']:.1f}")
m3.metric("ADX14", f"{latest['adx']:.1f}")
regime = "レンジ" if latest["adx"] < settings.ADX_RANGE_THRESHOLD else (
    "トレンド" if latest["adx"] >= settings.ADX_TREND_THRESHOLD else "中立")
m4.metric("レジーム", regime)

if sig_a_now != 0 or sig_b_now == 1:
    direction = 1 if (sig_a_now == 1 or sig_b_now == 1) else -1
    sl, tp = risk_manager.calc_sl_tp(float(latest["close"]), float(latest["atr"]), direction)
    size = risk_manager.calc_position_size(entry=float(latest["close"]), sl=sl)
    label = "🔺 ロング" if direction == 1 else "🔻 ショート"
    src = "α" if sig_a_now != 0 else "β"
    st.success(
        f"**本日シグナル発生: {label}（戦略{src}）**  \n"
        f"エントリー想定: {latest['close']:,.2f} / SL: {sl:,.2f} / TP: {tp:,.2f} / "
        f"推奨株数: {size:,.0f}株（口座 {settings.ACCOUNT_CAPITAL:,.0f}・リスク {settings.RISK_PERCENT:.0%}）"
    )
else:
    st.info("本日のエントリーシグナルはありません。")

st.caption("⚠️ このアプリは投資判断の参考情報提供を目的としており、売買の推奨ではありません。")
