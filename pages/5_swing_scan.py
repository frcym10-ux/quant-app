"""
pages/5_swing_scan.py
スイング候補自動スキャン画面
"""
import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings
from modules import swing_scanner, universe

st.set_page_config(page_title="スイング候補スキャン", page_icon="🛰️", layout="wide")
st.title("🛰️ スイング候補 自動スキャン")
st.markdown(
    "テーマ別ユニバース（AI・半導体／量子／宇宙・防衛／生活インフラ）を一括分析し、"
    "**トレンド押し目・平均回帰リバウンド・ブレイクアウト**のセットアップが完成した銘柄と、"
    "あと一歩の**監視銘柄**をスコア順に表示します。"
)


@st.cache_data(ttl=1800, show_spinner="全ユニバースをスキャン中（1分前後かかります）...")
def run_scan(themes: tuple[str, ...], top_n: int) -> pd.DataFrame:
    return swing_scanner.scan(list(themes) if themes else None, top_n=top_n)


# ========== 条件 ==========
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    selected_themes = st.multiselect(
        "テーマ（未選択なら全テーマ）", list(universe.THEMES.keys()), default=[]
    )
with col2:
    top_n = st.number_input("最大表示件数", 5, 50, 25)
with col3:
    market_filter = st.selectbox("市場", ["すべて", "日本", "米国"])

if st.button("🛰️ スキャン実行", type="primary"):
    run_scan.clear()

df = run_scan(tuple(selected_themes), int(top_n))

if df.empty:
    st.warning("現在セットアップ条件を満たす銘柄はありません。")
    st.stop()

if market_filter != "すべて":
    df = df[df["市場"] == market_filter]

# ========== エントリー候補 ==========
cands = df[df["種別"] == "候補"]
watch = df[df["種別"] == "監視"]

st.markdown(f"### 🎯 エントリー候補（{len(cands)}件）")
if cands.empty:
    st.info("セットアップ完成銘柄はありません。監視リストを確認してください。")
else:
    for _, r in cands.iterrows():
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 2])
            with c1:
                st.markdown(f"**{r['コード']} {r['銘柄名']}**（{r['市場']}）")
                st.caption(f"{r['テーマ']}")
                st.markdown(f"📌 {r['セットアップ']} ｜ スコア **{r['スコア']:.0f}**")
            with c2:
                st.metric("終値", f"{r['終値']:,}", f"{r['前日比%']:+.2f}%")
                st.caption(f"RSI {r['RSI']:.0f} ／ ADX {r['ADX']:.0f} ／ ATR {r['ATR%']}%")
            with c3:
                st.markdown(f"SL: **{r['SL']:,}** ／ TP: **{r['TP']:,}**")
                if pd.notna(r["株数目安"]) and r["株数目安"]:
                    st.caption(
                        f"株数目安 {r['株数目安']:,}株"
                        f"（元手{settings.SWING_CAPITAL/10000:.0f}万円・リスク{settings.RISK_PERCENT:.0%}）"
                    )
            st.markdown(f"💡 {r['根拠']}")

# ========== 監視リスト ==========
st.markdown(f"### 👀 監視リスト（{len(watch)}件）")
if watch.empty:
    st.caption("監視銘柄はありません。")
else:
    st.dataframe(
        watch[["コード", "銘柄名", "市場", "テーマ", "セットアップ", "スコア",
               "終値", "前日比%", "RSI", "ADX", "根拠"]],
        use_container_width=True, hide_index=True,
    )

st.caption(
    "セットアップ定義 ― トレンド押し目: ADX≧25の上昇トレンドでEMA12へ押し ／ "
    "平均回帰: ADX<20でBB・Keltner下限タッチ＋RSI≦35 ／ "
    "ブレイクアウト: BB上限超え＋出来高1.5倍。"
    "流動性（売買代金）とボラティリティ（ATR1〜8%）でフィルター済み。"
)
st.caption("⚠️ このアプリは投資判断の参考情報提供を目的としており、売買の推奨ではありません。")
