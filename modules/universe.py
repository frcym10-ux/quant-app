"""
modules/universe.py
スイングトレード候補スキャンの対象ユニバース（テーマ別・日米）

銘柄の追加・削除はこのファイルを編集するだけでよい。
日本株は4桁コード（内部で .T を付けて取得）、米国株はティッカーをそのまま書く。
"""
from __future__ import annotations

# テーマ名 -> {コード: 銘柄名}
THEMES: dict[str, dict[str, str]] = {
    "AI・半導体": {
        # 日本株
        "8035": "東京エレクトロン",
        "6857": "アドバンテスト",
        "6920": "レーザーテック",
        "6146": "ディスコ",
        "6723": "ルネサスエレクトロニクス",
        "7735": "SCREENホールディングス",
        "6526": "ソシオネクスト",
        "4062": "イビデン",
        "6963": "ローム",
        "6981": "村田製作所",
        "285A": "キオクシアホールディングス",
        "9984": "ソフトバンクグループ",
        "6701": "NEC",
        "6702": "富士通",
        "4307": "野村総合研究所",
        "3993": "PKSHA Technology",
        "4011": "ヘッドウォータース",
        # 米国株
        "NVDA": "NVIDIA",
        "AMD": "AMD",
        "AVGO": "Broadcom",
        "TSM": "TSMC (ADR)",
        "MU": "Micron",
        "MRVL": "Marvell",
        "ARM": "Arm Holdings",
        "QCOM": "Qualcomm",
        "PLTR": "Palantir",
        "VRT": "Vertiv",
        "SMCI": "Super Micro Computer",
    },
    "量子コンピュータ": {
        # 日本株（純粋な量子銘柄は少なく、大手IT/関連ベンダー中心）
        "3687": "フィックスターズ",
        "6701": "NEC",
        "6702": "富士通",
        "6501": "日立製作所",
        "9432": "NTT",
        # 米国株
        "IONQ": "IonQ",
        "RGTI": "Rigetti Computing",
        "QBTS": "D-Wave Quantum",
        "QUBT": "Quantum Computing Inc",
    },
    "宇宙・防衛": {
        # 日本株
        "7011": "三菱重工業",
        "7012": "川崎重工業",
        "7013": "IHI",
        "9348": "ispace",
        "186A": "アストロスケールHD",
        "290A": "Synspective",
        "9412": "スカパーJSAT",
        "7721": "東京計器",
        "6232": "ACSL",
        # 米国株
        "RKLB": "Rocket Lab",
        "LUNR": "Intuitive Machines",
        "ASTS": "AST SpaceMobile",
        "RDW": "Redwire",
        "PL": "Planet Labs",
        "KTOS": "Kratos Defense",
        "LMT": "Lockheed Martin",
    },
    "生活インフラ・ディフェンシブ": {
        # 日本株
        "2914": "JT",
        "9432": "NTT",
        "9433": "KDDI",
        "9434": "ソフトバンク",
        "9501": "東京電力HD",
        "9502": "中部電力",
        "9503": "関西電力",
        "9531": "東京ガス",
        "9532": "大阪ガス",
        "2802": "味の素",
        "8267": "イオン",
        "6370": "栗田工業",
        "9020": "JR東日本",
        # 米国株
        "KO": "Coca-Cola",
        "PG": "Procter & Gamble",
        "PEP": "PepsiCo",
        "WM": "Waste Management",
        "NEE": "NextEra Energy",
        "DUK": "Duke Energy",
        "O": "Realty Income",
        "VZ": "Verizon",
    },
}


def all_codes() -> dict[str, str]:
    """全テーマの銘柄をまとめて返す（コード -> 銘柄名、重複は除去）"""
    merged: dict[str, str] = {}
    for theme_map in THEMES.values():
        merged.update(theme_map)
    return merged


def themes_of(code: str) -> list[str]:
    """銘柄が属するテーマの一覧を返す"""
    return [t for t, m in THEMES.items() if code in m]
