"""
pages/1_screener.py
銘柄スクリーニング画面
"""
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings
from modules import screener

st.set_page_config(page_title="銘柄スクリーニング", page_icon="🔍", layout="wide")
st.title("🔍 銘柄スクリーニング")

# ========== サイドバー: 条件入力 ==========
st.sidebar.header("スクリーニング条件")

market = st.sidebar.selectbox("市場", ["すべて", "日本株", "米国ETF"])

st.sidebar.subheader("レジーム（ADX）")
regime_option = st.sidebar.radio(
    "レジームフィルター", ["指定なし", "レンジのみ（ADX<20）", "トレンドのみ（ADX≧25）"]
)
regime = {"指定なし": None, "レンジのみ（ADX<20）": "レンジ", "トレンドのみ（ADX≧25）": "トレンド"}[regime_option]

st.sidebar.subheader("RSI条件")
rsi_oversold = st.sidebar.checkbox(f"売られすぎ（RSI < {settings.RSI_OVERSOLD}）")
rsi_overbought = st.sidebar.checkbox(f"買われすぎ（RSI > {settings.RSI_OVERBOUGHT}）")

st.sidebar.subheader("バンド条件")
bb_lower = st.sidebar.checkbox("ボリンジャーバンド下限タッチ")
bb_upper = st.sidebar.checkbox("ボリンジャーバンド上限タッチ")
kc_lower = st.sidebar.checkbox("ケルトナーチャネル下限タッチ")

st.sidebar.subheader("VWAP条件")
vwap_option = st.sidebar.radio("VWAP位置", ["指定なし", "VWAPより上", "VWAPより下"])

extra = st.sidebar.text_input("追加銘柄（カンマ区切り 例: AAPL,8035）", value="")

# ========== ユニバース構築 ==========
universe: list[str] = []
if market in ("すべて", "日本株"):
    universe += settings.MY_STOCKS_JP
if market in ("すべて", "米国ETF"):
    universe += settings.MY_STOCKS_US
universe += [c.strip().upper() for c in extra.split(",") if c.strip()]

conditions = {
    "regime": regime,
    "rsi_oversold": rsi_oversold,
    "rsi_overbought": rsi_overbought,
    "bb_lower_touch": bb_lower,
    "bb_upper_touch": bb_upper,
    "kc_lower_touch": kc_lower,
    "above_vwap": vwap_option == "VWAPより上",
    "below_vwap": vwap_option == "VWAPより下",
}

st.markdown(f"対象ユニバース: **{len(universe)}銘柄**（保有銘柄＋追加入力）")

if st.button("🔍 スクリーニング実行", type="primary"):
    with st.spinner("各銘柄のデータを取得・分析中..."):
        result = screener.screen(universe, conditions)
    st.session_state["screen_result"] = result

result = st.session_state.get("screen_result")
if result is not None:
    if result.empty:
        st.warning("条件に合致する銘柄はありませんでした。")
    else:
        st.markdown(f"### 結果: {len(result)}銘柄")
        event = st.dataframe(
            result, use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row",
        )
        selected = event.selection.rows if event and event.selection else []
        if selected:
            code = result.iloc[selected[0]]["コード"]
            st.session_state["selected_code"] = code
            st.switch_page("pages/2_chart.py")
        st.caption("行を選択すると詳細チャート画面へ遷移します。")

st.caption("⚠️ このアプリは投資判断の参考情報提供を目的としており、売買の推奨ではありません。")
