"""
pages/4_portfolio.py
ポートフォリオ管理画面

- 証券会社CSVの取り込み（楽天証券など・列名/文字コード自動判定）
- 銘柄ごとに「スイング / ガチホ」を選択
- スイング銘柄は推奨利確指値・損切りライン・売買判定（継続/利確検討/損切り検討）を表示
- 手動更新ボタン
保有データは holdings_store 経由でSupabase（設定時）またはCSVに保存する。
"""
import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules import auth, holdings_monitor, holdings_store

st.set_page_config(page_title="ポートフォリオ管理", page_icon="💼", layout="wide")
auth.require_auth()
st.title("💼 ポートフォリオ管理")

top1, top2 = st.columns([3, 1])
top1.caption(f"📦 保有データの保存先: {holdings_store.backend_name()}")
if top2.button("🔄 最新に更新", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# ========== 取り込み・編集 ==========
with st.expander("📥 保有銘柄の取り込み・編集", expanded=False):
    st.markdown(
        "証券会社のCSV（楽天証券など）をアップロードして取り込めます。"
        "見出し（銘柄コード／保有数量／平均取得価額 等）と文字コードは自動判定します。"
    )
    up = st.file_uploader("保有銘柄CSVをアップロード", type=["csv"])
    if up is not None:
        try:
            parsed = holdings_store.parse_broker_csv(up.getvalue())
        except Exception as e:
            parsed = pd.DataFrame()
            st.error(f"CSVの解析に失敗しました: {e}")
        if parsed is None or parsed.empty:
            st.warning(
                "コード列を自動検出できませんでした。下の表に手入力するか、"
                "CSVの見出し行を教えてください（対応を追加します）。"
            )
        else:
            st.write("取り込みプレビュー：")
            st.dataframe(parsed, hide_index=True, use_container_width=True)
            mode = st.radio("取り込み方法", ["既存に追記／更新", "全置換"], horizontal=True)
            if st.button("この内容で保存", type="primary"):
                if mode == "全置換":
                    holdings_store.write_all(parsed)
                else:
                    cur = holdings_store.read_all()
                    merged = pd.concat([cur, parsed], ignore_index=True)
                    merged = merged.drop_duplicates("code", keep="last")
                    holdings_store.write_all(merged)
                st.cache_data.clear()
                st.success("保存しました。")
                st.rerun()

    st.markdown("**保有銘柄の編集**（区分でガチホ／スイングを選択。行の追加・削除も可）")
    current = holdings_store.read_all()
    edited = st.data_editor(
        current, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={
            "code": st.column_config.TextColumn("コード", required=True),
            "name": st.column_config.TextColumn("銘柄名"),
            "shares": st.column_config.NumberColumn("保有数", min_value=0.0, format="%g"),
            "avg_cost": st.column_config.NumberColumn("平均取得", min_value=0.0, format="%g"),
            "hold_type": st.column_config.SelectboxColumn(
                "区分", options=holdings_store.HOLD_TYPES, default=holdings_store.DEFAULT_HOLD_TYPE),
            "note": st.column_config.TextColumn("メモ"),
        },
        key="holdings_editor",
    )
    if st.button("💾 編集を保存"):
        holdings_store.write_all(edited)
        st.cache_data.clear()
        st.success("保存しました。")
        st.rerun()

# ========== 分析・売買判断 ==========
holdings = holdings_store.read_all()
if holdings is None or holdings.empty:
    st.info("保有銘柄がまだ登録されていません。上の「📥 保有銘柄の取り込み・編集」から登録してください。")
    st.stop()


@st.cache_data(ttl=1800, show_spinner="各銘柄の現在値と売買判断を計算中…")
def run_analysis(signature: str) -> pd.DataFrame:
    """保有銘柄を分析する（signatureはキャッシュ無効化用の保有内容ハッシュ）"""
    return holdings_monitor.analyze()


signature = "|".join(sorted(f"{r.code}:{r.hold_type}" for r in holdings.itertuples()))
res = run_analysis(signature)

if res.empty:
    st.warning("分析データを取得できませんでした。銘柄コードが正しいかご確認ください。")
    st.stop()

total_pl = pd.to_numeric(res["含み損益円"], errors="coerce").dropna().sum()
st.metric("合計 含み損益（円換算）", f"¥{total_pl:+,.0f}")

for kind, emoji in (("スイング", "🔁"), ("ガチホ", "💎")):
    sub = res[res["区分"] == kind]
    if sub.empty:
        continue
    st.subheader(f"{emoji} {kind}（{len(sub)}銘柄）")
    for _, r in sub.iterrows():
        cur = "円" if r["市場"] == "日本" else "ドル"
        pl_pct = f"{r['含み損益%']:+.1f}%" if pd.notna(r["含み損益%"]) else "—"
        pl_yen = f"{r['含み損益円']:+,.0f}円" if pd.notna(r["含み損益円"]) else ""
        with st.container(border=True):
            h1, h2 = st.columns([3, 1])
            h1.markdown(
                f"#### {r['コード']} {r['銘柄名']} <small>（{r['市場']}）</small>",
                unsafe_allow_html=True,
            )
            h1.markdown(f"**{r['判定']}**")
            h2.metric("現在値", f"{r['現在値']:,}", f"{r['前日比%']:+.2f}%")

            if kind == "スイング":
                a1, a2, a3 = st.columns(3)
                a1.info(f"**推奨利確の指値**\n\n{r['推奨利確指値']:,} {cur}")
                a2.error(f"**損切りライン**\n\n{r['損切りライン']:,} {cur}")
                a3.metric("含み損益", pl_pct, pl_yen)
            else:
                a1, a2 = st.columns(2)
                a1.metric("含み損益", pl_pct, pl_yen)
                a2.caption(f"RSI {r['RSI']:.0f} ／ ADX {r['ADX']:.0f}")
            st.caption(f"📖 {r['理由']}")

st.caption(
    "⚠️ 推奨利確の指値・損切りラインは、その銘柄の値動き（ATR）や上値抵抗・直近安値から"
    "自動計算した参考値です。売買を保証・推奨するものではありません。最終判断はご自身で。"
)
