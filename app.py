"""
app.py
クオンツ投資分析アプリ - エントリーポイント
"""
import streamlit as st

st.set_page_config(
    page_title="クオンツ投資分析",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 クオンツ投資分析アプリ")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🔍 銘柄スクリーニング")
    st.markdown(
        "テクニカル指標とレジーム判定で銘柄をフィルタリング。"
        "RSI・ADX・ボリンジャーバンド・ケルトナーチャネルの条件を組み合わせて候補銘柄を抽出します。"
    )
    if st.button("スクリーニングへ →", use_container_width=True):
        st.switch_page("pages/1_screener.py")

with col2:
    st.markdown("### 📊 テクニカル分析チャート")
    st.markdown(
        "銘柄コードを入力して詳細なテクニカルチャートを表示。"
        "BB・ケルトナーチャネル・MACD・RSI・ADXと戦略シグナルを一覧表示します。"
    )
    if st.button("チャートへ →", use_container_width=True):
        st.switch_page("pages/2_chart.py")

gcol1, gcol2 = st.columns(2)
with gcol1:
    st.markdown("### 🛰️ スイング候補 自動スキャン")
    st.markdown(
        "テーマ別ユニバース約70銘柄（日米）を一括分析し、"
        "エントリー候補と監視銘柄をスコア順に提示。朝夕の銘柄選定はここから。"
    )
    if st.button("スイング候補スキャンへ →", use_container_width=True, type="primary"):
        st.switch_page("pages/5_swing_scan.py")
with gcol2:
    st.markdown("### 🎯 目標ダッシュボード")
    st.markdown(
        "年内+100万円に向けた進捗・必要ペース・実現可能性をひと目で。"
        "トレードを記録すると勝率・期待値が自動集計されます。"
    )
    if st.button("目標ダッシュボードへ →", use_container_width=True):
        st.switch_page("pages/6_goal.py")

st.markdown("---")
col_a, col_b = st.columns(2)

with col_a:
    st.markdown("### 🎯 戦略シグナル")
    st.markdown(
        "銘柄ごとの戦略α/βシグナル履歴を表示。"
        "発生日・種別・エントリー価格・SL/TP・推奨株数を一覧できます。"
    )
    if st.button("戦略シグナルへ →", use_container_width=True):
        st.switch_page("pages/3_strategy.py")

with col_b:
    st.markdown("### 💼 ポートフォリオ概況")
    st.markdown(
        "保有銘柄の現在値・損益と、各銘柄の現在のレジーム（レンジ/トレンド）を一覧表示します。"
    )
    if st.button("ポートフォリオへ →", use_container_width=True):
        st.switch_page("pages/4_portfolio.py")

col_c, _col_d = st.columns(2)
with col_c:
    st.markdown("### 🧪 戦略バックテスト")
    st.markdown(
        "戦略α/βを過去データで検証。勝率・期待値（R）・プロフィットファクター・"
        "最大ドローダウンを銘柄別に算出し、戦略に優位性があるかを裏付けます。"
    )
    if st.button("バックテストへ →", use_container_width=True):
        st.switch_page("pages/7_backtest.py")

st.markdown("---")
st.markdown("### 実装戦略")

col3, col4 = st.columns(2)

with col3:
    st.info(
        "**戦略α：VWAP+BB+RSI モメンタム反転**\n\n"
        "- VWAPを上回る強気環境での押し目買い\n"
        "- ボリンジャーバンド下限 OR RSI < 25 でエントリー\n"
        "- イントラデイ〜短期スイング向け"
    )

with col4:
    st.info(
        "**戦略β：Keltner+ADX 自己適応型平均回帰**\n\n"
        "- ADX < 20（レンジ相場）のみ許可\n"
        "- ケルトナーチャネル下限タッチでエントリー\n"
        "- RSI強気ダイバージェンスで確認"
    )

st.markdown("---")
st.caption("⚠️ このアプリは投資判断の参考情報提供を目的としており、売買の推奨ではありません。")
