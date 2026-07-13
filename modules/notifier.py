"""
modules/notifier.py
「本日のアクション」を自分宛メールで通知する（Gmail SMTP）

ユーザーは楽天証券で注文を出すだけでよいように、
  1. 保有銘柄のアクション（🔺利確検討＝推奨指値 / 🔻損切り検討＝撤退ライン）
  2. 新規エントリー候補（買い目安・株数・SL/TP）
を朝夕の自動実行時にメールで届ける。

環境変数（GitHub Actionsのシークレット or ローカル.env で設定）:
    SMTP_USER : 送信元Gmailアドレス
    SMTP_PASS : Gmailの「アプリパスワード」（通常のログインパスワードではない）
    NOTIFY_TO : 宛先（省略時は SMTP_USER 自身に送る）
これらが未設定なら通知はスキップされる（レポート生成には影響しない）。

通知は「アクションがある日」のみ送る。
保有銘柄の情報は自分宛メールにのみ含め、公開レポートには出さない。
"""
from __future__ import annotations

import os
import smtplib
import sys
from email.mime.text import MIMEText

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules import explain

REPORT_URL = os.getenv("REPORT_URL", "https://swing-report.vercel.app")

# 「継続」以外＝注文アクションが必要な判定
_ACTION_KEYWORDS = ("利確", "損切り", "⚠️")


def pick_actionable(holdings_df):
    """analyze() の結果から、注文アクションが必要な行だけを抜き出す"""
    if holdings_df is None or holdings_df.empty or "判定" not in holdings_df.columns:
        return holdings_df.iloc[0:0] if holdings_df is not None else None
    mask = holdings_df["判定"].astype(str).str.contains("|".join(_ACTION_KEYWORDS), na=False)
    return holdings_df[mask]


def _fmt_num(v, suffix="") -> str:
    """数値をカンマ区切りで整形（Noneや欠損は'—'）"""
    try:
        import pandas as pd
        if v is None or pd.isna(v):
            return "—"
    except Exception:
        if v is None:
            return "—"
    return f"{v:,}{suffix}"


def _holding_card(s: dict) -> str:
    """保有銘柄アクション1件のHTMLカード"""
    verdict = str(s.get("判定", ""))
    is_stop = "損切り" in verdict
    color = "#c0392b" if is_stop else "#1565c0"
    cur = "円" if s.get("市場") == "日本" else "ドル"
    pl = ""
    if s.get("含み損益%") is not None:
        try:
            pl = f"（含み損益 {float(s['含み損益%']):+.1f}%）"
        except (TypeError, ValueError):
            pl = ""
    lines = [
        f"<div style='border-left:4px solid {color};padding:6px 10px;margin:6px 0'>"
        f"<b>{s['コード']} {s['銘柄名']} — {verdict}</b>{pl}<br>"
        f"現在値 {_fmt_num(s.get('現在値'))}{cur}（{s.get('前日比%', 0):+.2f}%）"
    ]
    if s.get("推奨利確指値") is not None or s.get("損切りライン") is not None:
        lines.append(
            f"<br>🔵 利確の指値目安: <b>{_fmt_num(s.get('推奨利確指値'), cur)}</b>"
            f"　🔻 撤退（損切り）ライン: <b>{_fmt_num(s.get('損切りライン'), cur)}</b>"
        )
    if s.get("理由"):
        lines.append(f"<br><small>{s['理由']}</small>")
    lines.append("</div>")
    return "".join(lines)


def _build_html(candidates, holdings_actions) -> str:
    """通知メール本文（HTML）を組み立てる"""
    parts = ["<div style='font-family:sans-serif;font-size:14px;color:#222'>"]

    if holdings_actions:
        parts.append(f"<h2>🔔 保有銘柄のアクション（{len(holdings_actions)}件）</h2>")
        parts.extend(_holding_card(s) for s in holdings_actions)

    parts.append(f"<h2>🛰️ 新規エントリー候補（{len(candidates)}件）</h2>")
    if candidates:
        for r in candidates:
            e = explain.explain_candidate(r)
            parts.append(
                f"<div style='border:1px solid #ddd;border-radius:8px;padding:10px;margin:8px 0'>"
                f"<b>{r['コード']} {r['銘柄名']}</b>（{r['市場']}・{r['テーマ']}）<br>"
                f"<span style='color:#2a6'>{e['headline']}</span>　{e['risk']}<br>"
                f"<small>{e['why']}</small><br>"
                f"🟢 {e['buy']}<br>🔻 {e['stop']}<br>🔵 {e['take']}<br>"
                f"<small style='color:#666'>💰 {e['invest']}</small></div>"
            )
    else:
        parts.append("<p>本日エントリー候補はありません。</p>")

    parts.append(
        f"<p style='margin-top:16px'>📱 全候補リスト: <a href='{REPORT_URL}'>{REPORT_URL}</a></p>"
        "<p style='color:#999;font-size:12px'>※ 参考情報であり売買の推奨ではありません。"
        "最終判断はご自身の調査で行ってください。</p></div>"
    )
    return "".join(parts)


def send_if_needed(scan_df, holdings_df) -> bool:
    """アクション（候補 or 保有の利確/損切り）があればメールを送る。送ったらTrueを返す

    Args:
        scan_df: swing_scanner.scan() の結果DataFrame
        holdings_df: holdings_monitor.analyze() の結果DataFrame（全保有。要アクション行はここで抽出）
    """
    user = os.getenv("SMTP_USER", "").strip()
    pw = os.getenv("SMTP_PASS", "").strip()
    if not user or not pw:
        print("メール通知: SMTP_USER/SMTP_PASS 未設定のためスキップ")
        return False

    candidates = (
        scan_df[scan_df["種別"] == "候補"].to_dict("records")
        if scan_df is not None and not scan_df.empty else []
    )
    actionable = pick_actionable(holdings_df)
    holdings_actions = actionable.to_dict("records") if actionable is not None and not actionable.empty else []

    if not candidates and not holdings_actions:
        print("メール通知: 候補・保有アクションともになしのため送信せず")
        return False

    to = os.getenv("NOTIFY_TO", user).strip() or user
    import datetime as dt
    jst = dt.timezone(dt.timedelta(hours=9))
    today = dt.datetime.now(jst).strftime("%Y-%m-%d")
    subject = f"【本日のアクション】保有{len(holdings_actions)}件・新規候補{len(candidates)}件（{today}）"

    msg = MIMEText(_build_html(candidates, holdings_actions), "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user, pw)
        server.sendmail(user, [to], msg.as_string())
    print(f"メール通知: 送信完了 -> {to}（保有アクション{len(holdings_actions)}・候補{len(candidates)}）")
    return True
