# クオンツ投資分析アプリ

個人投資家向けの定量分析Webアプリ。日本株（J-Quants API）と米国株・ETF（yfinance）を対象に、
テクニカルスクリーニング・4段チャート・戦略シグナル・ポートフォリオ管理を完全無料スタックで提供する。

## 機能

| 画面 | 内容 |
|------|------|
| 🔍 スクリーニング | RSI / ADX / BB / Keltner / VWAP 条件＋レジーム判定で銘柄抽出 |
| 📊 チャート | ローソク足＋BB＋Keltner＋VWAP＋EMA、MACD / RSI / ADX の4段Plotlyチャート、シグナル矢印 |
| 🎯 戦略シグナル | 戦略α/βのシグナル履歴・SL/TP・ATRポジションサイジング |
| 💼 ポートフォリオ | 保有銘柄の損益・現在レジーム一覧 |
| 🛰️ スイング候補スキャン | テーマ別ユニバース（AI・半導体／量子／宇宙・防衛／生活インフラ、日米約70銘柄）を自動分析し、エントリー候補と監視銘柄をスコア順に提示 |
| 🧪 戦略バックテスト | 戦略α/βを過去データで検証し、勝率・期待値（Rマルチプル）・プロフィットファクター・最大ドローダウンを銘柄別／全体で算出 |

## 市場フィルター（相場に逆らわない）

`modules/market_filter.py` が日経225・S&P500の200日線を見て全体相場を判定する。
指数が200日線を割れた「逆風（リスクオフ）」局面では、スイング候補スキャンが新規ロング候補を
自動で「監視」に格下げ・減点する。ロング偏重の運用で成績の安定性を高めるための仕組み。
スマホ用レポートの先頭にも 🟢🟡🔴 の相場バナーを表示する。

## バックテスト（CLI）

```bash
python tools/backtest.py            # α・βを2年で検証
python tools/backtest.py alpha 3y   # 戦略αを3年で検証
```

期待値R>0 かつ プロフィットファクター>1.3 が、その戦略・銘柄に優位性がある目安。
ユニットテストは `python tests/test_backtest.py` / `python tests/test_market_filter.py` で実行（ネットワーク不要）。

## スマホ用レポート

`python -X utf8 tools/publish_report.py` でスイング候補のみの静的HTML（`swing-report/index.html`）を生成。
ポートフォリオ・APIキーは含まれない。`tools/setup_schedule.ps1` で平日7:00/16:30の自動生成を登録でき、
一度 `vercel login` すれば `tools/publish.bat` がVercelへ自動公開する。
銘柄ユニバースの追加・削除は `modules/universe.py` を編集する。

## 実装戦略

- **戦略α**: VWAP統合型 BB+RSIモメンタム反転（ロング/ショート）
- **戦略β**: ケルトナーチャネル+ADX 自己適応型平均回帰（ADX<20のレンジ相場のみ、RSI強気ダイバージェンス確認）

## セットアップ

```bash
pip install -r requirements.txt

# .env を作成して J-Quants リフレッシュトークンを設定
copy .env.example .env   # Windowsの場合

streamlit run app.py
```

J-Quantsトークンは https://jpx-jquants.com/ の無料会員登録で取得できる（無料プランは日足直近12週分）。

## 補足

- テクニカル指標は `modules/indicators.py` で pandas/numpy により自前計算
  （pandas-ta 0.3.x はPyPIから削除済み、0.4.x はPython 3.12+が必要なため不使用）
- 取得データは SQLite（`data/cache/market_data.db`）に6時間キャッシュ
- `data/portfolio.csv` に保有銘柄（code,name,shares,avg_cost）を記載するとポートフォリオ画面に反映される

⚠️ このアプリは投資判断の参考情報提供を目的としており、売買の推奨ではありません。
