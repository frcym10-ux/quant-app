"""
pages/7_backtest.py
戦略バックテスト画面（戦略α/βのヒストリカル検証）

戦略を過去データで検証し、勝率・期待値（Rマルチプル）・プロフィットファクター・
最大ドローダウンを銘柄別／全体で表示する。「勝率50%の仮定」を実績で裏付けるための画面。
"""
import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules import backtest

st.set_page_config(page_title="戦略バックテスト", page_icon="🧪", layout="wide")
st.title("🧪 戦略バックテスト")
st.markdown(
    "戦略α/βを過去データで検証します。**期待値R（1回あたりの平均リスク倍率）がプラスで、"
    "プロフィットファクター（PF）が1.3以上**なら、その戦略・銘柄には優位性の可能性があります。"
)


@st.cache_data(ttl=3600, show_spinner="過去データを取得して検証中（1〜2分かかります）...")
def run_bt(strategy_key: str, period: str) -> tuple[pd.DataFrame, dict]:
    return backtest.backtest_universe(strategy_key, period=period)


col1, col2 = st.columns([2, 1])
with col1:
    strat_key = st.radio(
        "戦略", list(backtest.STRATEGIES.keys()),
        format_func=lambda k: backtest.STRATEGIES[k].name, horizontal=True,
    )
with col2:
    period = st.selectbox("検証期間", ["1y", "2y", "3y", "5y"], index=1)

if st.button("🧪 バックテスト実行", type="primary"):
    run_bt.clear()

per_symbol, overall = run_bt(strat_key, period)

# ========== 全体成績 ==========
st.markdown(f"### 📊 全体成績：{overall.get('strategy', '')}")
if overall["n_trades"] == 0:
    st.warning("この期間ではシグナルが発生しませんでした。期間を延ばすか戦略を変えてください。")
    st.stop()

pf = overall["profit_factor"]
pf_disp = "∞" if pf == float("inf") else f"{pf:.2f}"
c1, c2, c3, c4 = st.columns(4)
c1.metric("トレード数", f"{overall['n_trades']}")
c2.metric("勝率", f"{overall['win_rate']*100:.1f}%")
c3.metric("期待値", f"{overall['expectancy_r']:+.3f} R/回")
c4.metric("プロフィットファクター", pf_disp)
c5, c6, c7 = st.columns(3)
c5.metric("最大ドローダウン", f"{overall['max_drawdown_r']:.1f} R")
c6.metric("累計損益", f"{overall['total_r']:+.1f} R")
c7.metric("平均保有日数", f"{overall['avg_hold']:.1f} 営業日")

# 総合判定
exp = overall["expectancy_r"]
if exp > 0 and (pf == float("inf") or pf >= 1.3):
    st.success("✅ この期間では優位性が見られます（期待値プラス・PF≥1.3）。ただし過去の結果は将来を保証しません。")
elif exp > 0:
    st.info("🟡 期待値はプラスですがPFは弱め。銘柄を絞る・フィルターを足すなどの改善余地があります。")
else:
    st.error("🔴 この期間では期待値がマイナス。この戦略を単独で使うのは推奨できません。")

# ========== 銘柄別 ==========
st.markdown("### 🏷️ 銘柄別成績（累計R順）")
st.caption("期待値Rがプラスの銘柄ほど、その戦略と相性が良い傾向。トレード数が少ない銘柄は参考程度に。")
st.dataframe(per_symbol, use_container_width=True, hide_index=True)

st.caption(
    "R = 1トレードあたりのリスク倍率（損切り=-1R、利確≈+1.5R）。"
    "エントリーは翌足始値、SL/TPはATRベース、最大保有20営業日のタイムストップで検証しています。"
)
st.caption("⚠️ バックテストは過去データに基づく参考情報であり、将来の成績や売買を保証・推奨するものではありません。")
