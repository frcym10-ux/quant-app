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
