"""
tools/publish_report.py
スイング候補スキャンを実行し、スマホ閲覧用の静的HTMLレポートを生成する

スマホでもアプリの主要機能を確認できるよう、3つのタブで構成する:
  1. スイング候補スキャン（エントリー候補・監視リスト）
  2. テクニカル一覧（全ユニバースのRSI/ADX/レジーム/VWAP/戦略シグナル＝スクリーナー相当）
  3. 戦略シグナル（戦略α/βが現在発生している銘柄）

ポートフォリオ・口座情報・APIキー・目標額は一切含めない（市場データのみ）。
生成先: swing-report/index.html
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
from modules import holdings_monitor, market_filter, notifier, swing_scanner, universe  # noqa: E402

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
.setup { display: inline-block; font-size: .85rem; font-weight: 700; margin: 6px 0; padding: 3px 10px;
         border-radius: 999px; background: #24426b; color: #bcd9ff; }
.nums { font-size: .85rem; color: #ccc; margin: 4px 0; }
.nums b { color: #fff; }
.up { color: #26a69a; } .down { color: #ef5350; }
.why { font-size: .85rem; color: #cdd6e0; margin: 8px 0; line-height: 1.6; }
.actions { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; margin: 10px 0; }
.act { border-radius: 8px; padding: 8px; font-size: .78rem; line-height: 1.4; }
.act .lbl { display: block; font-weight: 700; font-size: .72rem; margin-bottom: 3px; }
.act.buy { background: #14301f; border: 1px solid #1f6b3f; }
.act.buy .lbl { color: #4cd791; }
.act.stop { background: #341818; border: 1px solid #7a2a2a; }
.act.stop .lbl { color: #ff7676; }
.act.take { background: #1a2740; border: 1px solid #2a4a7a; }
.act.take .lbl { color: #7fb4ff; }
.invest { font-size: .78rem; color: #9ab; margin-top: 6px; line-height: 1.5; }
.theme { font-size: .72rem; color: #777; }
.empty { color: #888; padding: 12px; }

/* ===== 市場フィルター（相場の信号） ===== */
.market { display: flex; gap: 8px; margin-bottom: 12px; }
.mkt-card { flex: 1; background: #1a1f2b; border: 1px solid #2a3142; border-radius: 10px;
            padding: 9px 11px; }
.mkt-card .mname { font-size: .75rem; color: #9ab; }
.mkt-card .mlight { font-size: .95rem; font-weight: 700; margin: 2px 0; }
.mkt-card .mcomment { font-size: .72rem; color: #aab; line-height: 1.5; }
.mkt-card.off { border-color: #7a2a2a; }
.mkt-card.warn { border-color: #7a6a2a; }
.mkt-card.on { border-color: #1f6b3f; }
footer { color: #666; font-size: .72rem; margin-top: 24px; line-height: 1.6; }

/* ===== タブ ===== */
.tabs { display: flex; gap: 6px; position: sticky; top: 0; z-index: 10;
        background: #0e1117; padding: 8px 0; margin-bottom: 8px; }
.tab { flex: 1; text-align: center; padding: 9px 4px; font-size: .82rem; font-weight: 700;
       color: #9ab; background: #1a1f2b; border: 1px solid #2a3142; border-radius: 8px; cursor: pointer; }
.tab.active { color: #fff; background: #24426b; border-color: #4a9eff; }
.panel { display: none; }
.panel.active { display: block; }
.hint { font-size: .78rem; color: #8aa; margin-bottom: 10px; line-height: 1.6; }

/* ===== テクニカル一覧（コンパクト行） ===== */
.subhead { font-size: .8rem; color: #9ab; margin: 14px 0 6px; font-weight: 700; }
.row { display: grid; grid-template-columns: 1fr auto; gap: 4px 10px; align-items: baseline;
       background: #1a1f2b; border: 1px solid #2a3142; border-radius: 8px;
       padding: 9px 11px; margin-bottom: 7px; }
.row .rname { font-weight: 700; font-size: .92rem; }
.row .rcode { color: #889; font-size: .72rem; margin-right: 5px; }
.row .rprice { text-align: right; font-size: .9rem; }
.row .rmetrics { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 6px; margin-top: 3px; }
.pill { font-size: .72rem; padding: 1px 7px; border-radius: 999px; background: #2a3142; color: #cdd6e0; }
.pill.range { background: #24426b; color: #bcd9ff; }
.pill.trend { background: #14301f; color: #4cd791; }
.pill.neutral { background: #3a3320; color: #d9c97f; }
.pill.os { background: #14301f; color: #4cd791; }
.pill.ob { background: #341818; color: #ff7676; }
.pill.sig { background: #3a2440; color: #e6a8ff; font-weight: 700; }
"""

REPORT_URL_NOTE = (
    "Streamlitアプリ（フル機能）はPCで <code>streamlit run app.py</code>。"
    "このページはスマホ用の閲覧専用ダイジェストです。"
)


def _esc(s: object) -> str:
    """HTML特殊文字をエスケープする"""
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _candidate_card(r, watch=False) -> str:
    """スイング候補1件をカードHTMLにする"""
    from modules import explain
    e = explain.explain_candidate(r.to_dict())
    cls = "card watch" if watch else "card"
    chg = float(r["前日比%"])
    chg_cls = "up" if chg >= 0 else "down"
    return (
        f"<div class='{cls}'>"
        f"<div class='head'><span class='name'>{_esc(r['コード'])} {_esc(r['銘柄名'])}</span>"
        f"<span class='mkt'>{_esc(r['市場'])}</span>"
        f"<span class='score'>スコア {r['スコア']:.0f}</span></div>"
        f"<div class='theme'>{_esc(r['テーマ'])}</div>"
        f"<span class='setup'>{_esc(e['headline'])}</span>"
        f"<div class='nums'>終値 <b>{r['終値']:,}</b> "
        f"<span class='{chg_cls}'>{chg:+.2f}%</span> ／ {_esc(e['risk'])}</div>"
        f"<div class='why'>📖 {_esc(e['why'])}</div>"
        f"<div class='actions'>"
        f"<div class='act buy'><span class='lbl'>買う目安</span>{_esc(e['buy'])}</div>"
        f"<div class='act stop'><span class='lbl'>撤退（損切り）</span>{_esc(e['stop'])}</div>"
        f"<div class='act take'><span class='lbl'>利確の目安</span>{_esc(e['take'])}</div>"
        f"</div>"
        f"<div class='invest'>💰 {_esc(e['invest'])}</div>"
        f"<div class='invest'>{_esc(e['edge'])}</div></div>"
    )


def _scan_panel(df) -> str:
    """タブ1: スイング候補スキャン"""
    parts = [
        "<div class='hint'>テーマ別ユニバース（日米約70銘柄）を日足で一括分析し、"
        "セットアップが完成した「候補」と、あと一歩の「監視」を提示します。</div>",
    ]
    if df.empty:
        parts.append("<p class='empty'>現在条件を満たす銘柄はありません。</p>")
        return "".join(parts)
    cands = df[df["種別"] == "候補"]
    watch = df[df["種別"] == "監視"]
    parts.append(f"<h2>🎯 エントリー候補（{len(cands)}件）</h2>")
    if cands.empty:
        parts.append("<p class='empty'>セットアップ完成銘柄なし。監視リストを確認。</p>")
    parts.extend(_candidate_card(r) for _, r in cands.iterrows())
    parts.append(f"<h2>👀 監視リスト（{len(watch)}件）</h2>")
    if watch.empty:
        parts.append("<p class='empty'>監視銘柄なし。</p>")
    parts.extend(_candidate_card(r, watch=True) for _, r in watch.iterrows())
    return "".join(parts)


def _regime_pill(regime: str) -> str:
    cls = {"レンジ": "range", "トレンド": "trend"}.get(regime, "neutral")
    return f"<span class='pill {cls}'>{_esc(regime)}</span>"


def _rsi_pill(rsi: float) -> str:
    if rsi <= 30:
        return f"<span class='pill os'>RSI {rsi:.0f} 売られすぎ</span>"
    if rsi >= 70:
        return f"<span class='pill ob'>RSI {rsi:.0f} 買われすぎ</span>"
    return f"<span class='pill'>RSI {rsi:.0f}</span>"


def _overview_row_html(r) -> str:
    """テクニカル一覧の1行HTML"""
    chg = float(r["前日比%"])
    chg_cls = "up" if chg >= 0 else "down"
    sig = "" if r["シグナル"] == "-" else f"<span class='pill sig'>{_esc(r['シグナル'])}</span>"
    return (
        "<div class='row'>"
        f"<div><span class='rcode'>{_esc(r['コード'])}</span>"
        f"<span class='rname'>{_esc(r['銘柄名'])}</span></div>"
        f"<div class='rprice'>{r['終値']:,} "
        f"<span class='{chg_cls}'>{chg:+.2f}%</span></div>"
        "<div class='rmetrics'>"
        f"{_regime_pill(r['レジーム'])}"
        f"<span class='pill'>ADX {r['ADX']:.0f}</span>"
        f"{_rsi_pill(float(r['RSI']))}"
        f"<span class='pill'>VWAP{_esc(r['VWAP位置'])}</span>"
        f"{sig}"
        "</div></div>"
    )


def _tech_panel(ov) -> str:
    """タブ2: テクニカル一覧（スクリーナー相当）"""
    parts = [
        "<div class='hint'>全ユニバースのRSI・ADX・レジーム判定・VWAP位置・戦略シグナルの一覧です。"
        "レジームは ADX&lt;20＝レンジ（逆張り有効）／ADX≥25＝トレンド（順張り有効）。</div>",
    ]
    if ov.empty:
        parts.append("<p class='empty'>データを取得できませんでした。</p>")
        return "".join(parts)
    for mkt, label in (("日本", "🇯🇵 日本株"), ("米国", "🇺🇸 米国株")):
        sub = ov[ov["市場"] == mkt]
        if sub.empty:
            continue
        parts.append(f"<div class='subhead'>{label}（{len(sub)}銘柄）</div>")
        parts.extend(_overview_row_html(r) for _, r in sub.iterrows())
    return "".join(parts)


def _signal_panel(ov) -> str:
    """タブ3: 戦略シグナル（α/βが現在発生している銘柄）"""
    parts = [
        "<div class='hint'>本日時点で戦略シグナルが点灯している銘柄です。"
        "α買=VWAP上での押し目反転／α売=VWAP下での戻り売り／β買=レンジ下限の平均回帰。</div>",
    ]
    if ov.empty:
        parts.append("<p class='empty'>データを取得できませんでした。</p>")
        return "".join(parts)
    hits = ov[ov["シグナル"] != "-"]
    if hits.empty:
        parts.append("<p class='empty'>現在、戦略シグナルが点灯している銘柄はありません。</p>")
        return "".join(parts)
    parts.append(f"<h2>🎯 点灯中シグナル（{len(hits)}件）</h2>")
    parts.extend(_overview_row_html(r) for _, r in hits.iterrows())
    parts.append(
        "<div class='hint'>具体的なエントリー価格・損切り・利確・株数は、上の「スイング候補」タブ"
        "またはPCのStreamlitアプリ（戦略シグナル画面）で確認できます。</div>"
    )
    return "".join(parts)


def _market_banner(ms) -> str:
    """全体相場（日経225・S&P500）の信号バナーを描画する"""
    if not ms:
        return ""
    cls_map = {"🟢": "on", "🟡": "warn", "🔴": "off"}
    cards = []
    for market in ("日本", "米国"):
        info = ms.get(market)
        if not info:
            continue
        cls = cls_map.get(info["light"], "")
        cards.append(
            f"<div class='mkt-card {cls}'>"
            f"<div class='mname'>{_esc(info.get('name', market))}</div>"
            f"<div class='mlight'>{info['light']} {_esc(info['trend'])}</div>"
            f"<div class='mcomment'>{_esc(info['comment'])}</div></div>"
        )
    if not cards:
        return ""
    return "<div class='market'>" + "".join(cards) + "</div>"


def render(df, ov, ms=None) -> str:
    """スキャン結果と概況をモバイル向けタブHTMLにレンダリングする"""
    jst = dt.timezone(dt.timedelta(hours=9))
    now = dt.datetime.now(jst).strftime("%Y-%m-%d %H:%M")
    parts = [
        "<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<meta name='robots' content='noindex'>",
        "<title>クオンツ投資ダイジェスト</title>",
        f"<style>{CSS}</style></head><body>",
        "<h1>📈 クオンツ投資ダイジェスト</h1>",
        f"<p class='ts'>更新: {now}（日足ベース・平日朝夕更新）</p>",
        _market_banner(ms),
        "<div class='tabs'>",
        "<div class='tab active' data-tab='scan'>🛰️ 候補</div>",
        "<div class='tab' data-tab='tech'>📊 一覧</div>",
        "<div class='tab' data-tab='signal'>🎯 シグナル</div>",
        "</div>",
        f"<div class='panel active' id='scan'>{_scan_panel(df)}</div>",
        f"<div class='panel' id='tech'>{_tech_panel(ov)}</div>",
        f"<div class='panel' id='signal'>{_signal_panel(ov)}</div>",
    ]
    parts.append(
        "<footer>「買う目安・撤退ライン・利確の目安」は、その銘柄の値動きの大きさから自動計算した参考値です。"
        "買う前に各カードの内容を確認し、撤退ライン（損切り）を必ず決めてからエントリーしてください。<br>"
        f"{REPORT_URL_NOTE}<br>"
        "⚠️ 本レポートは参考情報であり売買の推奨ではありません。最終判断はご自身の調査で。</footer>"
    )
    parts.append(
        "<script>"
        "document.querySelectorAll('.tab').forEach(function(t){"
        "t.addEventListener('click',function(){"
        "document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active');});"
        "document.querySelectorAll('.panel').forEach(function(x){x.classList.remove('active');});"
        "t.classList.add('active');"
        "document.getElementById(t.dataset.tab).classList.add('active');"
        "window.scrollTo(0,0);});});"
        "</script>"
    )
    parts.append("</body></html>")
    return "".join(parts)


def main() -> None:
    # API取得は1回だけ行い、各タブで使い回す（二重ダウンロード回避）
    data = swing_scanner.batch_fetch(list(universe.all_codes().keys()))
    try:
        ms = market_filter.market_status()
    except Exception as e:
        print(f"市場フィルター取得失敗（レポートは継続）: {e}")
        ms = {}
    df = swing_scanner.scan(top_n=30, data=data, market_status=ms)
    ov = swing_scanner.overview(data=data)

    os.makedirs(PUBLIC_DIR, exist_ok=True)
    out = os.path.join(PUBLIC_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(df, ov, ms))
    print(f"レポート生成: {out}（候補 {len(df)}件 / 一覧 {len(ov)}銘柄）")

    # 保有銘柄の売買アクション判定と自分宛メール通知（公開レポートには含めない）
    try:
        holdings = holdings_monitor.analyze()
        notifier.send_if_needed(df, holdings)
    except Exception as e:
        print(f"通知処理でエラー（レポート生成は成功）: {e}")

    if "--deploy" in sys.argv:
        # 一度 `vercel login` 済みであれば自動デプロイできる
        ret = subprocess.run(
            ["vercel", "deploy", "--prod", "--yes", "--cwd", PUBLIC_DIR],
            capture_output=True, text=True, shell=True,
        )
        print(ret.stdout or ret.stderr)


if __name__ == "__main__":
    main()
