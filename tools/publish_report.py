"""
tools/publish_report.py
スイング候補スキャンを実行し、スマホ閲覧用の静的HTMLレポートを生成する

ポートフォリオ・口座情報・APIキーは一切含めない（候補銘柄リストのみ）。
生成先: public/index.html
使い方:
    python tools/publish_report.py            # HTML生成のみ
    python tools/publish_report.py --deploy   # 生成後に Vercel CLI でデプロイ
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules import swing_scanner  # noqa: E402

PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "..", "swing-report")

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, 'Hiragino Sans', 'Noto Sans JP', sans-serif;
       background: #0e1117; color: #e6e6e6; padding: 16px; max-width: 640px; margin: 0 auto; }
h1 { font-size: 1.3rem; margin-bottom: 4px; }
h2 { font-size: 1.05rem; margin: 20px 0 8px; border-left: 4px solid #4a9eff; padding-left: 8px; }
.ts { color: #888; font-size: .8rem; margin-bottom: 12px; }
.card { background: #1a1f2b; border-radius: 10px; padding: 12px 14px; margin-bottom: 10px;
        border: 1px solid #2a3142; }
.card.watch { opacity: .85; border-style: dashed; }
.head { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 4px; }
.name { font-weight: 700; font-size: 1.0rem; }
.mkt { font-size: .72rem; color: #aaa; background: #2a3142; border-radius: 4px; padding: 1px 6px; }
.score { font-weight: 700; color: #4a9eff; }
.setup { display: inline-block; font-size: .78rem; margin: 6px 0; padding: 2px 8px;
         border-radius: 999px; background: #24426b; color: #bcd9ff; }
.nums { font-size: .85rem; color: #ccc; margin: 4px 0; }
.nums b { color: #fff; }
.up { color: #26a69a; } .down { color: #ef5350; }
.sl { color: #ef5350; } .tp { color: #26a69a; }
.reason { font-size: .8rem; color: #9ab; margin-top: 6px; line-height: 1.5; }
.theme { font-size: .72rem; color: #777; }
.empty { color: #888; padding: 12px; }
footer { color: #666; font-size: .72rem; margin-top: 24px; line-height: 1.6; }
"""


def render(df) -> str:
    """スキャン結果DataFrameをモバイル向けHTMLにレンダリングする"""
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = [
        "<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<meta name='robots' content='noindex'>",
        "<title>スイング候補スキャン</title>",
        f"<style>{CSS}</style></head><body>",
        "<h1>🛰️ スイング候補スキャン</h1>",
        f"<p class='ts'>更新: {now}（日足ベース・朝夕更新）</p>",
    ]

    def card(r, watch=False) -> str:
        cls = "card watch" if watch else "card"
        chg = float(r["前日比%"])
        chg_cls = "up" if chg >= 0 else "down"
        import pandas as pd
        has_shares = pd.notna(r["株数目安"]) and r["株数目安"]
        shares = f" ／ 株数目安 <b>{int(r['株数目安']):,}</b>株" if has_shares else ""
        return (
            f"<div class='{cls}'>"
            f"<div class='head'><span class='name'>{r['コード']} {r['銘柄名']}</span>"
            f"<span class='mkt'>{r['市場']}</span>"
            f"<span class='score'>スコア {r['スコア']:.0f}</span></div>"
            f"<div class='theme'>{r['テーマ']}</div>"
            f"<span class='setup'>{r['セットアップ']}</span>"
            f"<div class='nums'>終値 <b>{r['終値']:,}</b> "
            f"<span class='{chg_cls}'>{chg:+.2f}%</span>"
            f" ／ RSI {r['RSI']:.0f} ／ ADX {r['ADX']:.0f} ／ ATR {r['ATR%']}%</div>"
            f"<div class='nums'>SL <b class='sl'>{r['SL']:,}</b> ／ "
            f"TP <b class='tp'>{r['TP']:,}</b>{shares}</div>"
            f"<div class='reason'>💡 {r['根拠']}</div></div>"
        )

    if df.empty:
        parts.append("<p class='empty'>現在条件を満たす銘柄はありません。</p>")
    else:
        cands = df[df["種別"] == "候補"]
        watch = df[df["種別"] == "監視"]
        parts.append(f"<h2>🎯 エントリー候補（{len(cands)}件）</h2>")
        if cands.empty:
            parts.append("<p class='empty'>セットアップ完成銘柄なし。監視リストを確認。</p>")
        parts.extend(card(r) for _, r in cands.iterrows())
        parts.append(f"<h2>👀 監視リスト（{len(watch)}件）</h2>")
        if watch.empty:
            parts.append("<p class='empty'>監視銘柄なし。</p>")
        parts.extend(card(r, watch=True) for _, r in watch.iterrows())

    parts.append(
        "<footer>セットアップ: トレンド押し目（ADX≧25でEMA12へ押し）／ "
        "平均回帰（ADX&lt;20でBB・Keltner下限＋RSI≦35）／ "
        "ブレイクアウト（BB上限超え＋出来高1.5倍）。"
        "流動性・ボラティリティでフィルター済み。SL=終値−2×ATR、TP=終値＋3×ATR。<br>"
        "⚠️ 本レポートは参考情報であり売買の推奨ではありません。</footer>"
        "</body></html>"
    )
    return "".join(parts)


def main() -> None:
    df = swing_scanner.scan(top_n=30)
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    out = os.path.join(PUBLIC_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(df))
    print(f"レポート生成: {out}（候補 {len(df)}件）")

    if "--deploy" in sys.argv:
        # 一度 `vercel login` 済みであれば自動デプロイできる
        ret = subprocess.run(
            ["vercel", "deploy", "--prod", "--yes", "--cwd", PUBLIC_DIR],
            capture_output=True, text=True, shell=True,
        )
        print(ret.stdout or ret.stderr)


if __name__ == "__main__":
    main()
