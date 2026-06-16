"""
modules/notifier.py
スイング候補・保有銘柄サインを自分宛メールで通知する（Gmail SMTP）

環境変数（GitHub Actionsのシークレット or ローカル.env で設定）:
    SMTP_USER : 送信元Gmailアドレス
    SMTP_PASS : Gmailの「アプリパスワード」（通常のログインパスワードではない）
    NOTIFY_TO : 宛先（省略時は SMTP_USER 自身に送る）
これらが未設定なら通知はスキップされる（レポート生成には影響しない）。

通知は「候補が出た日 or 保有銘柄にサインが出た日」のみ送る。
保有銘柄サインは自分宛メールにのみ含め、公開レポートには出さない。
"""
from __future__ import annotations

import os
import smtplib
import sys
from email.mime.text import MIMEText

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules import explain

REPORT_URL = os.getenv("REPORT_URL", "https://swing-report.vercel.app")


def _build_html(candidates, holdings_signals) -> str:
    """通知メール本文（HTML）を組み立てる"""
    parts = ["<div style='font-family:sans-serif;font-size:14px;color:#222'>"]

    parts.append(f"<h2>🛰️ 本日のスイング候補（{len(candidates)}件）</h2>")
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

    if holdings_signals:
        parts.append(f"<h2>🔔 保有銘柄のサイン（{len(holdings_signals)}件）</h2>")
        for s in holdings_signals:
            pl = f"（含み損益 {s['含み損益%']:+.0f}%）" if s.get("含み損益%") is not None else ""
            color = "#c0392b" if s["サイン"] == "売り検討" else "#1565c0"
            parts.append(
                f"<div style='border-left:4px solid {color};padding:6px 10px;margin:6px 0'>"
                f"{s['絵文字']} <b>{s['コード']} {s['銘柄名']} — {s['サイン']}</b>{pl}　"
                f"終値 {s['終値']:,}（{s['前日比%']:+.2f}%）<br><small>{s['解説']}</small></div>"
            )

    parts.append(
        f"<p style='margin-top:16px'>📱 全候補リスト: <a href='{REPORT_URL}'>{REPORT_URL}</a></p>"
        "<p style='color:#999;font-size:12px'>※ 参考情報であり売買の推奨ではありません。"
        "最終判断はご自身の調査で行ってください。</p></div>"
    )
    return "".join(parts)


def send_if_needed(scan_df, holdings_df) -> bool:
    """候補または保有サインがあればメールを送る。送ったらTrueを返す

    Args:
        scan_df: swing_scanner.scan() の結果DataFrame
        holdings_df: holdings_monitor.scan_holdings() の結果DataFrame
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
    holdings_signals = holdings_df.to_dict("records") if holdings_df is not None and not holdings_df.empty else []

    if not candidates and not holdings_signals:
        print("メール通知: 候補・保有サインともになしのため送信せず")
        return False

    to = os.getenv("NOTIFY_TO", user).strip() or user
    import datetime as dt
    jst = dt.timezone(dt.timedelta(hours=9))
    today = dt.datetime.now(jst).strftime("%Y-%m-%d")
    subject = f"【スイング】候補{len(candidates)}件・保有サイン{len(holdings_signals)}件（{today}）"

    msg = MIMEText(_build_html(candidates, holdings_signals), "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user, pw)
        server.sendmail(user, [to], msg.as_string())
    print(f"メール通知: 送信完了 -> {to}（候補{len(candidates)}・保有{len(holdings_signals)}）")
    return True
