"""
tests/test_notifier.py
notifier（本日のアクションメール）のテスト（ネットワーク不要・送信なし）

実行: python tests/test_notifier.py  または  pytest tests/test_notifier.py
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.pop("SMTP_USER", None)
os.environ.pop("SMTP_PASS", None)

from modules import notifier  # noqa: E402


def _holdings_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"コード": "7011", "銘柄名": "三菱重工業", "市場": "日本", "区分": "スイング",
         "現在値": 2500.0, "前日比%": 1.2, "含み損益%": 19.0, "含み損益円": 40000,
         "推奨利確指値": 2600.0, "損切りライン": 2350.0,
         "判定": "🔺 利確検討", "理由": "買われすぎ／上値抵抗に到達。"},
        {"コード": "2914", "銘柄名": "JT", "市場": "日本", "区分": "スイング",
         "現在値": 4000.0, "前日比%": -0.5, "含み損益%": 2.0, "含み損益円": 8000,
         "推奨利確指値": 4300.0, "損切りライン": 3800.0,
         "判定": "🟢 継続（保有）", "理由": "保有継続でOK。"},
        {"コード": "VOO", "銘柄名": "S&P500", "市場": "米国", "区分": "ガチホ",
         "現在値": 600.0, "前日比%": 0.3, "含み損益%": 50.0, "含み損益円": 300000,
         "推奨利確指値": None, "損切りライン": None,
         "判定": "⚠️ 長期トレンド転換の兆し", "理由": "中期の平均線を割り込み。"},
    ])


def test_pick_actionable():
    """継続以外（利確・損切り・⚠️）だけが抽出されること"""
    out = notifier.pick_actionable(_holdings_df())
    assert set(out["コード"]) == {"7011", "VOO"}, out["コード"].tolist()
    print("test_pick_actionable OK")


def test_build_html_contains_action_lines():
    """メールHTMLに利確指値・損切りラインが含まれること"""
    actions = notifier.pick_actionable(_holdings_df()).to_dict("records")
    cand = [{
        "コード": "6526", "銘柄名": "ソシオネクスト", "市場": "日本", "テーマ": "AI・半導体",
        "種別": "候補", "セットアップ": "平均回帰リバウンド", "スコア": 70,
        "終値": 3000.0, "前日比%": -2.0, "RSI": 28, "ADX": 15, "ATR%": 3.5,
        "SL": 2800.0, "TP": 3300.0, "株数目安": 100, "リスク額": 20000, "投資額": 300000,
        "根拠": "テスト",
    }]
    html = notifier._build_html(cand, actions)
    assert "保有銘柄のアクション（2件）" in html
    assert "2,600" in html and "2,350" in html          # 利確指値・損切りライン
    assert "利確検討" in html and "⚠️" in html
    assert "6526 ソシオネクスト" in html                  # 新規候補
    assert "2914" not in html                            # 継続はメールに含めない
    print("test_build_html_contains_action_lines OK")


def test_send_skipped_without_smtp():
    """SMTP未設定なら送信せずFalse"""
    assert notifier.send_if_needed(pd.DataFrame(), _holdings_df()) is False
    print("test_send_skipped_without_smtp OK")


if __name__ == "__main__":
    test_pick_actionable()
    test_build_html_contains_action_lines()
    test_send_skipped_without_smtp()
    print("\nALL notifier tests passed ✅")
