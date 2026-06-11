"""
config/settings.py
アプリ全体の設定・パラメータ定数
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ========== API設定 ==========
# J-Quants API v2 のAPIキー（旧v1リフレッシュトークンは廃止。変数名は.env互換のため両対応）
JQUANTS_API_KEY = os.getenv("JQUANTS_API_KEY", "") or os.getenv("JQUANTS_REFRESH_TOKEN", "")
JQUANTS_REFRESH_TOKEN = JQUANTS_API_KEY  # 後方互換

# ========== 口座設定 ==========
ACCOUNT_CAPITAL = float(os.getenv("ACCOUNT_CAPITAL", 1_000_000))  # 運用資金（円）
RISK_PERCENT = float(os.getenv("RISK_PERCENT", 0.01))              # 1トレードリスク率
SWING_CAPITAL = float(os.getenv("SWING_CAPITAL", 2_500_000))      # スイングトレード元手（円）

# ========== テクニカル指標パラメータ ==========
# MACD
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# RSI
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70       # 買われすぎ
RSI_OVERSOLD = 30         # 売られすぎ
RSI_OB_STRICT = 75        # 戦略α用（より厳しい閾値）
RSI_OS_STRICT = 25        # 戦略α用

# ボリンジャーバンド
BB_PERIOD = 20
BB_STDDEV = 2.0

# ケルトナーチャネル
KC_EMA_PERIOD = 20
KC_ATR_PERIOD = 10
KC_MULTIPLIER = 2.0

# ATR（リスク管理）
ATR_PERIOD = 14
ATR_SL_MULTIPLIER = 2.0   # ストップロス幅 = ATR × 2
ATR_TP_MULTIPLIER = 3.0   # テイクプロフィット幅 = ATR × 3

# ADX
ADX_PERIOD = 14
ADX_RANGE_THRESHOLD = 20  # 20未満 = レンジ相場（平均回帰が有効）
ADX_TREND_THRESHOLD = 25  # 25以上 = 強いトレンド相場

# VWAP（yfinanceではイントラデイデータが必要）
VWAP_RESET = "daily"

# EMA
EMA_SHORT = 12
EMA_LONG = 26

# ========== スクリーニング設定 ==========
# デフォルトの銘柄ユニバース（ユーザー保有銘柄）
MY_STOCKS_JP = [
    "2432", "2664", "2914", "3196", "4755", "6501",
    "6526", "7011", "7012", "8267", "9434",
]
MY_STOCKS_US = ["VOO", "VYM", "MRAM"]

# スクリーニング対象市場
MARKETS = ["東証プライム", "東証スタンダード", "米国ETF"]

# ========== チャート設定 ==========
CHART_PERIOD_OPTIONS = {
    "1ヶ月": 30,
    "3ヶ月": 90,
    "6ヶ月": 180,
    "1年": 365,
}
DEFAULT_CHART_PERIOD = "3ヶ月"

# ========== キャッシュ設定 ==========
CACHE_DB_PATH = "data/cache/market_data.db"
CACHE_EXPIRE_HOURS = 6  # 6時間でキャッシュ無効化
