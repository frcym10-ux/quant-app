# スマホで全機能を使う：Streamlit Community Cloud デプロイ手順

このアプリ（Streamlit）をクラウドで動かし、**スマホのブラウザから全機能**（チャート・
スクリーニング・スイングスキャン・バックテスト等）を使うための手順です。
**完全無料**。閲覧を自分のメールだけに限定し、さらにアプリ内パスワードで二重に保護します。

> 静的レポート（`swing-report.vercel.app`）は今までどおり「朝夕の見るだけダイジェスト」として併用できます。
> こちらのStreamlit版は「対話的に全機能を使う本体」です。

---

## 全体像（セキュリティ二層）

1. **Community Cloudの閲覧者制限**：アプリを限定公開にし、招待したメール（=あなたのGoogle/GitHub）だけがログイン可能。
   Google/GitHubログインなので、**そのアカウントにパスキーを設定していればパスキーでログイン**できます。
2. **アプリ内パスワードゲート**（任意）：`APP_PASSWORD` を設定すると、ログイン後にもう一段パスワードを要求（多層防御）。

---

## 手順

### 1. 事前準備
- GitHubアカウント（このリポジトリ `frcym10-ux/quant-app` の所有者でOK）
- 無料の Streamlit アカウント

### 2. Streamlit Community Cloud にデプロイ
1. https://share.streamlit.io/ にGitHubでサインイン
2. **「Create app」→「Deploy a public app from GitHub」**
3. 設定：
   - Repository: `frcym10-ux/quant-app`
   - Branch: `master`
   - **Main file path: `app.py`**
4. **「Advanced settings」→「Secrets」** に、`/.streamlit/secrets.toml.example` を参考に必要な値を貼り付け（次節）
5. **Deploy** を押す（数分でビルド完了）

### 3. Secrets（秘密情報）の設定
`.streamlit/secrets.toml.example` の中身をベースに、Advanced settings の Secrets 欄へ貼り付けます。
root階層のキーは自動で環境変数になり、`config/settings.py` の `os.getenv` がそのまま読み取ります。

最低限おすすめ：
```toml
APP_PASSWORD = "好きなパスワード"          # アプリ内ゲート（任意だが推奨）
ACCOUNT_CAPITAL = "1000000"
SWING_CAPITAL = "3000000"
HOLDINGS_JSON = '[{"code":"7011","name":"三菱重工業","avg_cost":1500}]'  # 保有銘柄（任意）
# JQUANTS_REFRESH_TOKEN = "JQT-..."        # 日本株をJ-Quantsで取りたい場合のみ
```
> J-Quantsキーが無くても、日本株は yfinance（`XXXX.T`）経由で取得できるため主要機能は動きます。

### 4. 閲覧者を自分のメールに限定（重要）
1. デプロイ後、アプリ管理画面の **「Settings」→「Sharing」**
2. **「Who can view this app」を限定公開**にし、自分のメール（Googleアカウント等）を許可リストに追加
3. これで、招待した人以外はログインできません。スマホでは初回にGoogleログイン（パスキー可）→（設定していれば）アプリ内パスワード、で全機能が使えます。

### 5. スマホでの使い方
1. デプロイされたURL（`https://<your-app>.streamlit.app`）をスマホで開く
2. Google/GitHubでログイン（パスキー対応）
3. `APP_PASSWORD` を設定していれば入力
4. 左上のメニュー（≡）から各画面へ。**ホーム画面に追加**しておくとアプリのように使えます

---

## 注意点・既知の制約

- **トレード記録（ジャーナル）の永続化**：Community Cloudのファイルシステムは一時的で、再起動・再デプロイで
  `data/trades.csv` が消えます。下記のSupabase設定を行えば**クラウドに永続化され消えません**（未設定ならローカルCSVのまま）。
- **APIレート/スリープ**：無料枠はしばらくアクセスが無いとスリープし、次回起動に数十秒かかります。
- **秘密情報**：`secrets.toml` と `.env`、`portfolio.csv` は `.gitignore` 済み。GitHubには絶対に上げないでください。

---

## トレード記録をクラウドに永続化（Supabase・無料）

Supabaseプロジェクト **`quant-app`（東京リージョン）** と `quant_trades` テーブルは作成済みです。
あとは **service_role キー**をsecretsに入れるだけで、ジャーナルがクラウド保存に切り替わります。

1. https://supabase.com/dashboard/project/imbrldrsohzpppdmrmcv の **Project Settings → API** を開く
2. **`service_role`** のキー（`eyJ...` の長い文字列）をコピー
   - ⚠️ service_role はDB全権限を持つため、**Streamlitのsecrets（サーバー側）にのみ**置き、GitHubやブラウザには絶対に出さない
3. Streamlitアプリの Secrets に追記：
   ```toml
   SUPABASE_URL = "https://imbrldrsohzpppdmrmcv.supabase.co"
   SUPABASE_KEY = "（コピーしたservice_roleキー）"
   ```
4. 保存するとアプリが自動でSupabaseを使い始めます（目標ダッシュボード画面に「保存先: Supabase」と表示）。

> `quant_trades` は RLS 有効・公開ポリシー無しで、service_role キーからのみ読み書きできます。
> SUPABASE_URL/KEY を設定しなければ、これまでどおりローカルCSV（`data/trades.csv`）に保存します。

### 保有銘柄テーブル（quant_holdings）

保有銘柄（ポートフォリオ）もSupabaseに永続化できます。`quant_holdings` テーブルが必要です。
**まだ作成されていない場合**は、Supabaseダッシュボード → **SQL Editor** に以下を貼って一度だけ実行してください
（テーブルが無い間は自動でローカルCSV `data/portfolio.csv` に保存されます）：

```sql
create table if not exists public.quant_holdings (
  code text primary key,
  name text,
  shares numeric,
  avg_cost numeric,
  hold_type text not null default 'スイング',
  note text,
  updated_at timestamptz not null default now()
);
alter table public.quant_holdings enable row level security;
```

作成後、`SUPABASE_URL` / `SUPABASE_KEY` が設定されていれば、ポートフォリオ画面の取り込み・編集が
クラウドに保存されます（区分「スイング／ガチホ」もここに記録）。

## ローカル開発はそのまま
`APP_PASSWORD` を設定しなければパスワードゲートは無効（no-op）なので、これまでどおり：
```bash
streamlit run app.py
```
で動きます。
