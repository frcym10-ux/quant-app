"""
pages/6_goal.py
目標ダッシュボード ＋ トレードジャーナル（年内+100万円の進捗管理）
"""
import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings
from modules import auth, goal, journal, swing_scanner, trade_store

st.set_page_config(page_title="目標ダッシュボード", page_icon="🎯", layout="wide")
auth.require_auth()
st.title("🎯 目標ダッシュボード")
st.caption(f"📦 トレード記録の保存先: {trade_store.backend_name()}")

s = goal.summary()

# ========== 進捗バー ==========
st.subheader(f"年内 +{settings.GOAL_PROFIT/10000:.0f}万円（元手 {settings.SWING_CAPITAL/10000:.0f}万円・1回リスク上限 {settings.MAX_RISK_YEN:,.0f}円）")
st.progress(min(max(s["progress"], 0), 1.0))
c1, c2, c3, c4 = st.columns(4)
c1.metric("実現損益", f"{s['realized']:+,.0f}円", f"{s['progress']*100:.1f}% 達成")
c2.metric("残り", f"{s['remaining']:,.0f}円")
c3.metric("残り日数", f"{s['days_left']}日", f"約{s['weeks_left']:.0f}週")
c4.metric("必要ペース", f"{s['required_weekly']:,.0f}円/週", f"月 約{s['required_monthly']:,.0f}円")

# ========== 実現可能性・ガードレール ==========
fkind, fmsg = s["feasibility"]
fbox = {"ok": st.success, "stretch": st.info, "hard": st.warning, "danger": st.error}[fkind]
needed = f"あと約{s['trades_needed']}トレード必要（週{s['trades_per_week']:.1f}回ペース）。" if s["trades_needed"] else ""
fbox(f"**実現可能性**：{fmsg} {needed}（期待値 約{s['expectancy_yen']:+,.0f}円/回・{s['expectancy_basis']}）")

gkind, gmsg = s["guard"]
gbox = {"ok": st.success, "warn": st.warning, "stop": st.error}[gkind]
gbox(f"**今月の損益**：{s['month_pnl']:+,.0f}円（停止ライン {s['stop_line']:,.0f}円）— {gmsg}")

# ========== ジャーナル実績 ==========
st.markdown("### 📈 これまでの成績")
stt = s["stats"]
if stt["n_closed"] == 0:
    st.caption("まだ決済済みトレードがありません。下のフォームから記録すると、勝率や期待値が自動集計されます。")
else:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("決済済み", f"{stt['n_closed']}件", f"勝ち{stt['wins']}・負け{stt['losses']}")
    m2.metric("勝率", f"{stt['win_rate']*100:.0f}%" if stt["win_rate"] is not None else "—")
    m3.metric("平均R", f"{stt['avg_r']:+.2f}" if stt["avg_r"] is not None else "—",
              help="1トレード平均の損益倍率。損切り=-1.0、利確=+1.5が目安")
    m4.metric("保有中リスク", f"{stt['open_risk_yen']:,.0f}円", f"{stt['n_open']}件保有中")

st.markdown("---")

# ========== トレード記録フォーム ==========
st.markdown("### ✏️ トレードを記録する")

# スイング画面の「記録」ボタンから渡された候補を初期値にする
pre = st.session_state.pop("journal_prefill", None)

with st.form("add_trade", clear_on_submit=True):
    cc1, cc2, cc3 = st.columns(3)
    code = cc1.text_input("コード", value=pre["コード"] if pre else "")
    name = cc2.text_input("銘柄名", value=pre["銘柄名"] if pre else "")
    market = cc3.selectbox("市場", ["日本", "米国"], index=0 if (not pre or pre["市場"] == "日本") else 1)
    cc4, cc5, cc6 = st.columns(3)
    entry = cc4.number_input("エントリー値", value=float(pre["終値"]) if pre else 0.0, format="%.2f")
    sl = cc5.number_input("損切り値(SL)", value=float(pre["SL"]) if pre else 0.0, format="%.2f")
    tp = cc6.number_input("利確値(TP)", value=float(pre["TP"]) if pre else 0.0, format="%.2f")
    cc7, cc8 = st.columns(2)
    shares = cc7.number_input("株数", value=int(pre["株数目安"]) if (pre and pre.get("株数目安")) else 0, step=1)
    setup = cc8.text_input("セットアップ／メモ", value=pre["セットアップ"] if pre else "")

    if st.form_submit_button("この内容で記録する", type="primary"):
        if code and entry > 0 and sl > 0:
            fx = 1.0 if market == "日本" else swing_scanner.get_usdjpy()
            risk_yen = round(shares * abs(entry - sl) * fx, 0)
            journal.add_trade(code.strip().upper(), name or code, market, setup,
                              entry, sl, tp, shares, risk_yen)
            st.success(f"{code} を記録しました（想定リスク {risk_yen:,.0f}円）。")
            st.rerun()
        else:
            st.error("コード・エントリー値・損切り値は必須です。")

# ========== 保有中ポジション ==========
trades = journal.load_trades()
open_pos = trades[trades["status"] == "保有中"]
if not open_pos.empty:
    st.markdown("### 📌 保有中のポジション")
    for _, t in open_pos.iterrows():
        with st.container(border=True):
            oc1, oc2 = st.columns([3, 2])
            oc1.markdown(
                f"**{t['code']} {t['name']}**（{t['market']}・{t['setup']}）　"
                f"建値 {float(t['entry']):,.2f} ｜ SL {float(t['sl']):,.2f} ｜ TP {float(t['tp']):,.2f} ｜ "
                f"{int(float(t['shares']))}株 ｜ リスク {float(t['risk_yen']):,.0f}円"
            )
            with oc2:
                with st.form(f"close_{t['id']}", clear_on_submit=True):
                    ex = st.number_input("決済値", value=float(t["entry"]), format="%.2f", key=f"ex_{t['id']}")
                    fc1, fc2 = st.columns(2)
                    if fc1.form_submit_button("決済する"):
                        journal.close_trade(str(t["id"]), ex)
                        st.rerun()
                    if fc2.form_submit_button("削除"):
                        journal.delete_trade(str(t["id"]))
                        st.rerun()

# ========== 決済履歴 ==========
closed = trades[trades["status"] == "決済済み"]
if not closed.empty:
    st.markdown("### 📜 決済履歴")
    view = closed[["date_close", "code", "name", "setup", "entry", "exit",
                   "r_multiple", "pnl_yen"]].copy()
    view.columns = ["決済日", "コード", "銘柄名", "セットアップ", "建値", "決済値", "R", "損益(円)"]
    view = view.sort_values("決済日", ascending=False)
    st.dataframe(
        view.style.map(
            lambda v: "color:#26a69a" if isinstance(v, (int, float)) and v > 0
            else ("color:#ef5350" if isinstance(v, (int, float)) and v < 0 else ""),
            subset=["R", "損益(円)"],
        ).format({"損益(円)": "{:+,.0f}", "R": "{:+.2f}"}),
        use_container_width=True, hide_index=True,
    )

st.caption("⚠️ このアプリは投資判断の参考情報提供を目的としており、売買の推奨ではありません。")
