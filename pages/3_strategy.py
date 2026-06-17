"""
pages/3_strategy.py
戦略シグナル確認画面（シグナル履歴・SL/TP・ポジションサイズ）
"""
import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings
from modules import auth, data_fetcher, indicators, risk_manager, screener
from modules import strategy_alpha, strategy_beta

st.set_page_config(page_title="戦略シグナル", page_icon="🎯", layout="wide")
auth.require_auth()
st.title("🎯 戦略シグナル履歴")

# ========== 入力 ==========
all_codes = settings.MY_STOCKS_JP + settings.MY_STOCKS_US
col1, col2 = st.columns([2, 1])
with col1:
    code = st.selectbox(
        "銘柄を選択",
        all_codes,
        format_func=lambda c: f"{c} {screener.STOCK_NAMES.get(c, '')}",
    )
with col2:
    manual = st.text_input("または直接入力", value="")
if manual.strip():
    code = manual.strip().upper()

days = 120

try:
    with st.spinner("データ取得・シグナル計算中..."):
        df = data_fetcher.get_cached_or_fetch(code, days)
        df = indicators.calc_all(df)
except Exception as e:
    st.error(f"データ取得に失敗しました: {e}")
    st.stop()

sig_a = strategy_alpha.signal(df)
sig_b = strategy_beta.signal(df)

# ========== シグナル履歴テーブル ==========
rows = []
for name, sig in [(strategy_alpha.NAME, sig_a), (strategy_beta.NAME, sig_b)]:
    for i in sig[sig != 0].index:
        row = df.loc[i]
        direction = int(sig[i])
        entry = float(row["close"])
        atr = float(row["atr"])
        sl, tp = risk_manager.calc_sl_tp(entry, atr, direction)
        size = risk_manager.calc_position_size(entry=entry, sl=sl)
        rows.append({
            "発生日": row["date"].strftime("%Y-%m-%d"),
            "戦略": name,
            "種別": "🔺 ロング" if direction == 1 else "🔻 ショート",
            "エントリー価格": round(entry, 2),
            "SL価格": round(sl, 2),
            "TP価格": round(tp, 2),
            "推奨株数": int(size),
        })

st.markdown(f"### {code} {screener.STOCK_NAMES.get(code, '')} のシグナル履歴（直近{days}日）")

if rows:
    hist = pd.DataFrame(rows).sort_values("発生日", ascending=False).reset_index(drop=True)
    st.dataframe(hist, use_container_width=True, hide_index=True)
    st.caption(
        f"SL = エントリー − {settings.ATR_SL_MULTIPLIER}×ATR14 / "
        f"TP = エントリー + {settings.ATR_TP_MULTIPLIER}×ATR14 / "
        f"株数 = 口座資金 {settings.ACCOUNT_CAPITAL:,.0f} × リスク率 {settings.RISK_PERCENT:.0%} ÷ SL幅"
    )
else:
    st.info("この期間にシグナルは発生していません。")

# ========== 戦略βのエグジット状況 ==========
latest = df.iloc[-1]
exit_now = strategy_beta.exit_signal(df).iloc[-1]
st.markdown("### 現在の状態")
c1, c2, c3 = st.columns(3)
c1.metric("現在値", f"{latest['close']:,.2f}")
c2.metric("ADX（レジーム）", f"{latest['adx']:.1f}（{screener.get_regime(latest['adx'])}）")
c3.metric("戦略βエグジット条件", "✅ 到達" if exit_now else "未到達")

if st.button("📊 この銘柄のチャートを見る"):
    st.session_state["selected_code"] = code
    st.switch_page("pages/2_chart.py")

st.caption("⚠️ このアプリは投資判断の参考情報提供を目的としており、売買の推奨ではありません。")
