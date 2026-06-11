# CLAUDE.md — クオンツ投資分析アプリ 開発指示書

## プロジェクト概要

個人投資家向けのクオンツ分析Webアプリ。
**銘柄スクリーニング（C）** と **テクニカル分析チャート（D）** を中核機能とする。
完全無料スタックで構築する。Streamlit + Python。

---

## 技術スタック（完全無料）

| 用途 | ライブラリ | 備考 |
|------|-----------|------|
| UI | Streamlit | `streamlit run app.py` で起動 |
| 日本株データ | jquants-api-client | J-Quants API（無料プラン） |
| 米国株データ | yfinance | 完全無料 |
| テクニカル指標 | pandas-ta | Ta-Libより導入が簡単 |
| 数値計算 | pandas / numpy / scipy | 標準 |
| グラフ | plotly | インタラクティブチャート |
| DB | SQLite (sqlite3) | ローカル保存、サーバー不要 |
| コード管理 | GitHub | リポジトリ: quant-app |

---

## ディレクトリ構成

```
quant-app/
├── app.py                   # Streamlitエントリーポイント
├── CLAUDE.md                # この指示書
├── README.md                # プロジェクト説明
├── requirements.txt         # 依存パッケージ
├── .gitignore               # 秘密情報・CSVを除外
├── .env.example             # 環境変数のサンプル（.envは.gitignoreで除外）
│
├── config/
│   └── settings.py          # パラメータ設定（APIキー読み込み等）
│
├── data/
│   ├── cache/               # APIレスポンスのキャッシュ（SQLite）
│   └── portfolio.csv        # ユーザー保有銘柄（.gitignoreで除外）
│
├── modules/
│   ├── data_fetcher.py      # J-Quants / yfinance データ取得
│   ├── indicators.py        # テクニカル指標計算
│   ├── screener.py          # 銘柄スクリーニングロジック
│   ├── strategy_alpha.py    # 戦略α：VWAP+BB+RSI
│   ├── strategy_beta.py     # 戦略β：Keltner+ADX
│   └── risk_manager.py      # ATRベースのリスク管理
│
└── pages/
    ├── 1_screener.py        # スクリーニング画面
    ├── 2_chart.py           # テクニカル分析チャート画面
    ├── 3_strategy.py        # 戦略シグナル確認画面
    └── 4_portfolio.py       # ポートフォリオ概況
```

---

## 実装する機能

### C. 銘柄スクリーニング（screener.py）

以下の条件でフィルタリングできること：

**基本フィルター**
- 市場（東証プライム / スタンダード / 米国ETF）
- セクター選択
- 時価総額レンジ
- 配当利回りレンジ

**テクニカルフィルター（レジーム判定付き）**
- ADX < 20 → レンジ相場（平均回帰戦略が有効）
- ADX >= 25 → トレンド相場（順張りが有効）
- RSI < 30 → 売られすぎ
- RSI > 70 → 買われすぎ
- ボリンジャーバンド下限タッチ
- ケルトナーチャネル下限タッチ
- VWAPより上 or 下

**スクリーニング結果の表示**
- 銘柄コード・銘柄名・現在値・RSI・ADX・レジーム判定
- 「詳細チャートを見る」ボタン（チャート画面へ遷移）

---

### D. テクニカル分析チャート（chart.py）

銘柄コードを入力（または一覧から選択）して以下を表示：

**メインチャート（Plotly）**
- ローソク足（OHLC）
- ボリンジャーバンド（期間20, 2σ）
- ケルトナーチャネル（EMA20, ATR10, 乗数2.0）
- VWAP（日次リセット）
- EMA12 / EMA26

**サブチャート1：MACD**
- MACDライン（EMA12 - EMA26）
- シグナルライン（EMA9）
- ヒストグラム（色付き）

**サブチャート2：RSI**
- RSI14
- 買われすぎ70ライン / 売られすぎ30ライン（赤・緑の水平線）

**サブチャート3：ADX**
- ADX14
- 20ライン（レンジ/トレンド判定境界）
- 25ライン（強いトレンド判定境界）

**シグナル表示**
- チャート上にエントリーシグナルを矢印で表示
  - 🔺 ロング（戦略α or β）
  - 🔻 ショート（戦略α）

---

## 実装する2つの戦略ロジック

### 戦略α：VWAP統合型 BB+RSIモメンタム反転

**パラメータ**
- RSI期間: 14, 売られすぎ閾値: 25, 買われすぎ閾値: 75
- ボリンジャーバンド: 期間20, 標準偏差乗数2.0

**ロングエントリー条件（AND条件）**
1. 終値 < ボリンジャーバンド下限 OR RSI < 25
2. 終値 > VWAP

**ショートエントリー条件（AND条件）**
1. 終値 > ボリンジャーバンド上限 OR RSI > 75
2. 終値 < VWAP

---

### 戦略β：ケルトナーチャネル+ADX 自己適応型平均回帰

**パラメータ**
- ケルトナーチャネル: EMA期間20, ATR期間10, ATR乗数2.0
- ADX: 期間14, レンジ判定閾値: 20

**レジーム判定（最優先）**
- ADX14 < 20 → 平均回帰ロジック許可
- ADX14 >= 20 → シグナルをブロック（何もしない）

**ロングエントリー条件（AND条件）**
1. ADX < 20（レンジ相場）
2. 終値 <= ケルトナーチャネル下限
3. RSI <= 30 かつ 強気ダイバージェンス（価格安値更新 & RSI切り上がり）

**エグジット条件**
- 利益確定: 価格がケルトナーチャネル中央線（EMA20）に回帰
- または反対バンド到達

---

## リスク管理（risk_manager.py）

ATRベースの動的ストップロス・テイクプロフィット：

```
SL_long = エントリー価格 - (2 × ATR14)
TP_long = エントリー価格 + (3 × ATR14)
```

ATRベースのポジションサイジング：
```
リスク金額 = 口座資金 × リスク率（デフォルト1%）
ポジションサイズ = リスク金額 / |エントリー価格 - SL価格|
```

---

## データ取得方針

### 日本株（J-Quants API）

```python
# .envに JQUANTS_REFRESH_TOKEN を設定すること
import jquantsapi

client = jquantsapi.Client(refresh_token=os.getenv("JQUANTS_REFRESH_TOKEN"))
df = client.get_price_range(code="7011", start_dt="2024-01-01", end_dt="2024-12-31")
```

**J-Quants無料プランの制約**
- ヒストリカルデータ: 直近12週分のみ（無料プラン）
- 有料プランなら過去データ取得可能

### 米国株・ETF（yfinance）

```python
import yfinance as yf
df = yf.download("VOO", start="2024-01-01", end="2024-12-31")
```

### APIキャッシュ（SQLite）

APIコール数を節約するため、取得データはSQLiteにキャッシュする。
同一銘柄・同一期間は当日中は再取得しない。

---

## ユーザーの主要保有銘柄（優先的にテスト対象）

| コード | 銘柄名 | 種別 | 戦略適合性 |
|--------|--------|------|-----------|
| 7011 | 三菱重工業 | 高ベータ・モメンタム | ADXフィルター必須、レジームスイッチング |
| 6526 | ソシオネクスト | 高ボラティリティ | 戦略α（極値での反転）、ATR広めのSL |
| 8267 | イオン | ディフェンシブ・内需 | 戦略β（純粋な平均回帰）が最適 |
| 2914 | JT | 高配当・バリュー | Keltner下限タッチで長期買い蓄積 |
| VOO | 米国ETF | インデックス | 週足MACDダイバージェンス戦略 |
| VYM | 米国ETF | 高配当ETF | 同上 |

---

## コーディング規約

- Python 3.10以上
- 型ヒント（type hints）を積極的に使う
- 関数には日本語docstringを書く
- エラーハンドリングは必ず実装する（API失敗時はキャッシュデータを返す）
- Streamlitの `st.cache_data` でデータ取得をキャッシュする
- 定数はすべて `config/settings.py` にまとめる

---

## 開発の進め方（優先順位）

1. **Phase 1**：データ取得モジュール（data_fetcher.py）の実装・動作確認
2. **Phase 2**：テクニカル指標計算（indicators.py）の実装
3. **Phase 3**：チャート画面（pages/2_chart.py）の実装
4. **Phase 4**：スクリーニング画面（pages/1_screener.py）の実装
5. **Phase 5**：戦略シグナル（strategy_alpha.py / strategy_beta.py）の実装
6. **Phase 6**：リスク管理モジュール（risk_manager.py）の実装

---

## 実行方法

```bash
# 依存関係のインストール
pip install -r requirements.txt

# .envファイルを作成（.env.exampleをコピーして編集）
cp .env.example .env

# アプリ起動
streamlit run app.py
```

---

## 注意事項

- `.env` ファイルは絶対にGitHubにpushしない（.gitignoreに記載済み）
- `data/portfolio.csv` もGitHubにpushしない
- J-Quants APIのリフレッシュトークンは `.env` で管理する
- このアプリは投資判断の参考情報提供を目的とし、売買の推奨ではない
