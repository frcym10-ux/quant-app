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
from modules import auth, explain, swing_scanner, universe

st.set_page_config(page_title="スイング候補スキャン", page_icon="🛰️", layout="wide")
auth.require_auth()
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
        e = explain.explain_candidate(r.to_dict())
        with st.container(border=True):
            top1, top2 = st.columns([3, 1])
            with top1:
                st.markdown(f"### {r['コード']} {r['銘柄名']}　<small>（{r['市場']}・{r['テーマ']}）</small>",
                            unsafe_allow_html=True)
                st.markdown(f"**{e['headline']}**　{e['risk']}")
            with top2:
                st.metric("終値", f"{r['終値']:,}", f"{r['前日比%']:+.2f}%")

            st.markdown(f"📖 **なぜ候補か**：{e['why']}")

            a1, a2, a3 = st.columns(3)
            a1.success(f"**買う目安**\n\n{e['buy']}")
            a2.error(f"**撤退ライン（損切り）**\n\n{e['stop']}")
            a3.info(f"**利確の目安**\n\n{e['take']}")

            st.caption(f"💰 {e['invest']}")
            st.caption(e["edge"])
            bcol1, bcol2 = st.columns([1, 4])
            if bcol1.button("📝 記録に回す", key=f"rec_{r['コード']}_{r['市場']}"):
                st.session_state["journal_prefill"] = r.to_dict()
                st.switch_page("pages/6_goal.py")
            with bcol2.expander("✅ 買う前のチェックリスト"):
                for item in e["checklist"]:
                    st.markdown(f"- {item}")

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

with st.expander("ℹ️ 3つの買い場タイプとは？（やさしい説明）"):
    st.markdown(
        "- **押し目買い**：上がり続けている勢いの強い銘柄が、一息ついて少し下がったところを買う（順張り）\n"
        "- **逆張り（反発狙い）**：横ばい相場で下がりすぎた銘柄が、元の水準に戻る動きを狙って安値を拾う\n"
        "- **ブレイクアウト**：もみ合いを上に抜けて、出来高を伴って勢いがついた銘柄に乗る（順張り）\n\n"
        "いずれも、売買が活発で（流動性）、値動きが極端すぎない銘柄に自動で絞り込んでいます。"
        "各候補の「撤退ライン」「利確の目安」は、その銘柄の値動きの大きさ（ATR）から自動計算しています。"
    )
st.caption("⚠️ このアプリは投資判断の参考情報提供を目的としており、売買の推奨ではありません。最終判断はご自身の調査で行ってください。")
