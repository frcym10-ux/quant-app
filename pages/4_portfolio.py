"""
pages/4_portfolio.py
ポートフォリオ概況画面（保有銘柄の損益・レジーム一覧）
"""
import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules import data_fetcher, indicators, screener

st.set_page_config(page_title="ポートフォリオ概況", page_icon="💼", layout="wide")
st.title("💼 ポートフォリオ概況")

PORTFOLIO_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "portfolio.csv")

if not os.path.exists(PORTFOLIO_CSV):
    st.warning(
        "`data/portfolio.csv` が見つかりません。以下の形式で作成してください：\n\n"
        "```csv\ncode,name,shares,avg_cost\n7011,三菱重工業,100,2100\nVOO,Vanguard S&P500 ETF,10,520\n```"
    )
    st.stop()

try:
    pf = pd.read_csv(PORTFOLIO_CSV, dtype={"code": str})
except Exception as e:
    st.error(f"portfolio.csv の読み込みに失敗しました: {e}")
    st.stop()

usd_jpy = st.sidebar.number_input("為替レート（USD/JPY、米国株の円換算用）", value=150.0, step=0.5)

rows = []
total_value_jpy = 0.0
total_pl_jpy = 0.0

with st.spinner("各銘柄の現在値を取得中..."):
    for _, h in pf.iterrows():
        code = str(h["code"]).strip().upper()
        is_jp = data_fetcher.is_jp_code(code)
        try:
            df = data_fetcher.get_cached_or_fetch(code, 84 if is_jp else 120)
            df = indicators.calc_all(df)
            latest = df.iloc[-1]
            price = float(latest["close"])
            shares = float(h["shares"])
            avg_cost = float(h["avg_cost"])
            value = price * shares
            pl = (price - avg_cost) * shares
            pl_pct = (price / avg_cost - 1) * 100 if avg_cost else 0.0
            rate = 1.0 if is_jp else usd_jpy
            total_value_jpy += value * rate
            total_pl_jpy += pl * rate
            rows.append({
                "コード": code,
                "銘柄名": h.get("name", screener.STOCK_NAMES.get(code, code)),
                "保有数": int(shares),
                "取得単価": round(avg_cost, 2),
                "現在値": round(price, 2),
                "評価額": round(value, 0),
                "損益": round(pl, 0),
                "損益率(%)": round(pl_pct, 2),
                "ADX": round(float(latest["adx"]), 1),
                "レジーム": screener.get_regime(latest["adx"]),
                "RSI": round(float(latest["rsi"]), 1),
            })
        except Exception as e:
            rows.append({
                "コード": code, "銘柄名": h.get("name", code),
                "保有数": int(h["shares"]), "取得単価": h["avg_cost"],
                "現在値": None, "評価額": None, "損益": None, "損益率(%)": None,
                "ADX": None, "レジーム": f"取得失敗: {e}", "RSI": None,
            })

c1, c2 = st.columns(2)
c1.metric("評価額合計（円換算）", f"¥{total_value_jpy:,.0f}")
c2.metric("評価損益合計（円換算）", f"¥{total_pl_jpy:+,.0f}")

result = pd.DataFrame(rows)
st.dataframe(
    result.style.map(
        lambda v: "color: #26a69a" if isinstance(v, (int, float)) and v > 0
        else ("color: #ef5350" if isinstance(v, (int, float)) and v < 0 else ""),
        subset=["損益", "損益率(%)"],
    ).format(precision=2, thousands=",", na_rep="-"),
    use_container_width=True, hide_index=True,
)

st.markdown(
    "**レジーム別の戦略ガイドライン**  \n"
    "- レンジ（ADX<20）: 平均回帰戦略（戦略β）が有効。Keltner下限での押し目買い候補  \n"
    "- トレンド（ADX≧25）: 順張りが有効。逆張りエントリーはブロック  \n"
    "- 中立: 様子見、またはポジション縮小を検討"
)
st.caption("⚠️ このアプリは投資判断の参考情報提供を目的としており、売買の推奨ではありません。")
