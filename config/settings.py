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
ACCOUNT_CAPITAL = float(os.getenv("ACCOUNT_CAPITAL", 1_000_000))  # 保有資産の口座資金（円）
RISK_PERCENT = float(os.getenv("RISK_PERCENT", 0.01))              # 保有資産側の1トレードリスク率

# ========== スイングトレード設定 ==========
SWING_CAPITAL = float(os.getenv("SWING_CAPITAL", 3_000_000))       # スイング元手（円）
SWING_RISK_PERCENT = float(os.getenv("SWING_RISK_PERCENT", 0.02))  # スイング1トレードのリスク率（旧・参考値）

# ========== 資金・リスク上限（絶対額で一元管理）==========
# リスク上限 26,000円 の根拠：
# 依頼者の平均勝ち 52,461円 の半分に設定することで、
# リスクリワード 1:2 が成立する。
# 旧設定(60,000円＝元手300万×2%)では平均勝ちを上回っており、
# 構造的に「負けの方が大きい」状態だった。
MAX_RISK_YEN = float(os.getenv("MAX_RISK_YEN", 26_000))            # 1トレードの最大損失（円・絶対額）
MAX_POSITION_YEN = float(os.getenv("MAX_POSITION_YEN", 700_000))   # 1銘柄への最大投資額（円）
AVAILABLE_CASH = float(os.getenv("AVAILABLE_CASH", 1_650_000))     # 利用可能資金（円・手入力で更新）

# ========== 目標設定 ==========
GOAL_PROFIT = float(os.getenv("GOAL_PROFIT", 1_000_000))           # 目標利益（円）
GOAL_START = os.getenv("GOAL_START", "2026-06-16")                 # 目標開始日
GOAL_DEADLINE = os.getenv("GOAL_DEADLINE", "2026-12-31")           # 目標期限
MONTHLY_STOP_PCT = float(os.getenv("MONTHLY_STOP_PCT", 0.10))      # 月間ストップ（元手比・この損失で一旦停止）

# 期待値の事前見積り用（ジャーナルに実績が溜まるまでの仮定値）
ASSUMED_WIN_RATE = float(os.getenv("ASSUMED_WIN_RATE", 0.50))      # 仮定勝率
REWARD_RISK = 1.5  # 損益比（利確3ATR / 損切り2ATR = 1.5）。最低この勝率(=1/(1+1.5)=40%)で損益分岐

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
# 20以上25未満 = 中立（方向感が定まらない＝シグナルを出さない。修正4）

# ========== 買いシグナルのハードフィルター（修正2）==========
# 暴落途中の銘柄を「押し目」と誤検出しないための中期トレンド・過熱・流動性チェック。
# 下の条件に該当する銘柄は「候補」「監視」「α買」から必ず除外する（一覧には表示可）。
SMA_TREND_PERIOD = 75           # 中期トレンド判定の単純移動平均（終値がこれ未満なら除外）
SMA_MID_PERIOD = 25             # 25日移動平均（乖離率の基準）
RSI_BUY_MAX = 75                # RSIがこれを超えたら「過熱」で除外
RSI_BUY_MIN = 40                # RSIがこれ未満なら「下落継続中」で除外
MAX_DISPARITY_PCT = 12.0        # 25日移動平均からの上方乖離がこれを超えたら「伸びすぎ」で除外
MIN_TURNOVER_BUY_JP = 3_000_000_000  # 日本株: 20日平均売買代金 30億円未満は「流動性不足」で除外

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
