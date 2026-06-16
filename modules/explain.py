"""
modules/explain.py
テクニカル指標・セットアップを「専門家でなくても分かる日本語」に翻訳する

スイング候補カード・公開レポート・保有銘柄サイン・通知メールで共通利用する。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings


# ========== リスクの大きさ（値動きの激しさ） ==========

def risk_level(atr_pct: float) -> tuple[str, str]:
    """ATR%（1日の平均的な値幅）から値動きの激しさを表すラベルと絵文字を返す"""
    if atr_pct < 2.0:
        return "穏やか", "🟢"
    if atr_pct < 4.0:
        return "普通", "🟡"
    return "激しい（要注意）", "🔴"


# ========== セットアップの平易な説明 ==========

# セットアップ種別 -> （ひとことの買い場タイプ, やさしい説明）
_SETUP_PLAIN: dict[str, tuple[str, str]] = {
    "トレンド押し目": (
        "上昇の波に乗った銘柄の押し目買い",
        "上がり続けている勢いの強い銘柄が、一息ついて少しだけ下がったところです。"
        "上昇トレンドが続く前提で、安く買えるタイミングを狙う「押し目買い」の形です。",
    ),
    "トレンド押し目（待ち）": (
        "上昇銘柄・もう少し下がるのを待つ",
        "勢いは強いのですが、まだ少し高い位置にあります。"
        "あと少し下がって買い頃になるのを待つ「監視」段階です。",
    ),
    "平均回帰リバウンド": (
        "下がりすぎからの反発（逆張り）",
        "横ばいの相場で、いつもの値動きの範囲を超えて下がりすぎたところです。"
        "ゴムのように元の水準へ戻りやすい（反発しやすい）と見て、安値を拾う「逆張り」の形です。",
    ),
    "平均回帰（待ち）": (
        "反発狙い・下限タッチを待つ",
        "下がってきていますが、反発を狙う水準まであと少しです。"
        "もう一段下げて買い頃になるのを待つ「監視」段階です。",
    ),
    "ブレイクアウト": (
        "もみ合いを上抜けた勢いに乗る（順張り）",
        "長くもみ合っていた銘柄が、出来高（売買の活発さ）を伴って上に飛び出したところです。"
        "そのまま勢いが続くと見て乗っていく「順張り」の形です。",
    ),
}


def setup_plain(setup_name: str) -> tuple[str, str]:
    """セットアップ名から（買い場タイプ, やさしい説明）を返す"""
    return _SETUP_PLAIN.get(setup_name, (setup_name, ""))


# ========== RSI / ADX の体温計コメント ==========

def rsi_comment(rsi: float) -> str:
    """RSI（買われすぎ・売られすぎの体温計）をやさしい言葉にする"""
    if rsi >= 70:
        return f"RSI {rsi:.0f}：買われすぎ気味（短期的には過熱）"
    if rsi >= 55:
        return f"RSI {rsi:.0f}：やや強気"
    if rsi >= 45:
        return f"RSI {rsi:.0f}：中立（過熱感なし）"
    if rsi >= 30:
        return f"RSI {rsi:.0f}：やや弱気（押している）"
    return f"RSI {rsi:.0f}：売られすぎ気味（反発が出やすい水準）"


def adx_comment(adx: float) -> str:
    """ADX（トレンドの強さ）をやさしい言葉にする"""
    if adx >= 25:
        return f"ADX {adx:.0f}：はっきりした方向感あり（トレンド相場）"
    if adx >= 20:
        return f"ADX {adx:.0f}：方向感が出始め"
    return f"ADX {adx:.0f}：方向感は弱い（横ばい・レンジ相場）"


# ========== 候補の総合解説（行動プラン込み） ==========

def explain_candidate(row: dict) -> dict:
    """スイング候補1件を、やさしい解説＋具体的な行動プランに変換する

    Args:
        row: swing_scanner.scan() が返す1行（dict化したもの）
    Returns:
        headline, why, buy, stop, take, risk, invest, checklist, one_liner を持つdict
    """
    is_jp = row["市場"] == "日本"
    cur = "円" if is_jp else "ドル"
    price = float(row["終値"])
    sl = float(row["SL"])
    tp = float(row["TP"])
    atr_pct = float(row["ATR%"])
    is_watch = row.get("種別") == "監視"

    setup_type, setup_desc = setup_plain(row["セットアップ"])
    risk_lbl, risk_emoji = risk_level(atr_pct)

    loss_pct = (sl / price - 1) * 100   # 損切りまでの下落率（マイナス）
    gain_pct = (tp / price - 1) * 100   # 利確までの上昇率（プラス）

    # --- 買い目安 ---
    if is_watch:
        buy = f"まだ買い頃ではありません。現在 {price:,.2f}{cur}。下の「撤退ライン」付近まで下げたら検討。"
    else:
        buy = f"現在値 {price:,.2f}{cur} 付近が目安（成行か、これより少し安い指値）。"

    # --- 損切り・利確 ---
    stop = f"{sl:,.2f}{cur}（今より約 {loss_pct:.1f}%）まで下がったら撤退（損切り）"
    take = f"{tp:,.2f}{cur}（今より約 +{gain_pct:.1f}%）まで上がったら利確を検討"

    # --- 投資金額・想定リスク ---
    risk_yen = settings.SWING_CAPITAL * settings.RISK_PERCENT
    shares = row.get("株数目安")
    if is_jp and shares:
        invest_amount = price * int(shares)
        invest = (
            f"目安 {int(shares):,}株（約 {invest_amount:,.0f}円）。"
            f"もし撤退ラインに当たっても損失が約 {risk_yen:,.0f}円 に収まるよう株数を調整しています。"
        )
    else:
        invest = (
            f"1回の損失を投資元手の {settings.RISK_PERCENT:.0%}（約 {risk_yen:,.0f}円）に抑えるなら、"
            f"買付額 ＝ {risk_yen:,.0f}円 ÷ {abs(loss_pct):.1f}% ≒ {risk_yen/ (abs(loss_pct)/100):,.0f}円 が上限の目安。"
        )

    # --- なぜ候補か（指標のやさしい要約） ---
    why = setup_desc + " " + rsi_comment(float(row["RSI"])) + " ／ " + adx_comment(float(row["ADX"]))

    # --- 買う前チェックリスト ---
    checklist = [
        f"撤退ライン（{sl:,.2f}{cur}）を必ず決めてから買う",
        "直近に決算発表が控えていないか（決算前後は値動きが荒れやすい）",
        f"この銘柄に最近の悪いニュースが出ていないか（{row['コード']} {row['銘柄名']}）",
        "日経平均やS&P500など全体相場が急落していないか",
        "1つの銘柄やテーマに資金を集中させすぎていないか",
    ]
    if atr_pct >= 4.0:
        checklist.insert(1, "値動きが激しい銘柄です。株数を控えめにすることも検討")

    one_liner = f"{risk_emoji} {setup_type}｜{cur=='円' and '日本株' or '米国株'}"

    return {
        "headline": setup_type,
        "why": why,
        "buy": buy,
        "stop": stop,
        "take": take,
        "risk": f"{risk_emoji} 値動き：{risk_lbl}（1日あたり平均 約{atr_pct:.1f}%動く）",
        "invest": invest,
        "checklist": checklist,
        "one_liner": one_liner,
    }
