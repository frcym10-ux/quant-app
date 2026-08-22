"""
modules/earnings.py
決算発表予定日の手動チェック支援（指示書ステップ6-6）

無料で決算発表予定日を確実に自動取得する手段がないため（J-Quants無料枠は12週遅れ・
予定日エンドポイントは翌営業日分のみ等）、ここでは「手動で登録した予定日」を読み込み、
±14営業日以内なら警告する、という半自動の仕組みにする。

登録元（どちらでも可・両方あればJSONを優先）:
  1. 環境変数 EARNINGS_JSON … {"6702": "2026-07-30", "9432": "2026-08-05", ...}
  2. CSVファイル data/earnings.csv … ヘッダ code,next_earnings（1行1銘柄）

登録が無い銘柄は「決算日未登録（要手動確認）」を返す（オーナーの最重要ルール＝決算跨ぎ回避
を、登録忘れで見落とさないよう、未登録はサイレントにせず明示する）。
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

EARNINGS_CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "earnings.csv")
DEFAULT_WITHIN_DAYS = 14  # この営業日数以内なら「決算接近」


def _parse_date(s: str) -> dt.date | None:
    """YYYY-MM-DD 文字列を date に変換する（失敗時 None）"""
    try:
        return dt.date.fromisoformat(str(s).strip())
    except Exception:
        return None


def load_earnings() -> dict[str, dt.date]:
    """登録済みの決算予定日を {コード: date} で返す（EARNINGS_JSON→CSVの順で読む）"""
    table: dict[str, dt.date] = {}

    raw = os.getenv("EARNINGS_JSON", "").strip()
    if raw:
        try:
            for code, ds in json.loads(raw).items():
                d = _parse_date(ds)
                if d:
                    table[str(code)] = d
        except Exception:
            pass

    if os.path.exists(EARNINGS_CSV_PATH):
        try:
            with open(EARNINGS_CSV_PATH, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    code = str(row.get("code", "")).strip()
                    d = _parse_date(row.get("next_earnings", ""))
                    if code and d and code not in table:  # JSON優先
                        table[code] = d
        except Exception:
            pass

    return table


def business_days_until(target: dt.date, ref: dt.date | None = None) -> int:
    """ref から target までの営業日数（平日ベース）。過去ならマイナス"""
    ref = ref or dt.date.today()
    return int(np.busday_count(ref, target))


def earnings_flag(
    code: str,
    ref: dt.date | None = None,
    within_days: int = DEFAULT_WITHIN_DAYS,
    table: dict[str, dt.date] | None = None,
) -> tuple[str, dt.date | None]:
    """決算接近の警告文と予定日を返す

    Returns:
        (表示文字列, 予定日 or None)
        - 登録あり＆今後within_days営業日以内 → ("⚠️決算接近(±14営業日: YYYY-MM-DD)", date)
        - 登録あり＆範囲外            → ("決算 YYYY-MM-DD", date)
        - 登録なし                    → ("決算日未登録（要手動確認）", None)
    """
    table = load_earnings() if table is None else table
    d = table.get(str(code))
    if d is None:
        return "決算日未登録（要手動確認）", None
    n = business_days_until(d, ref)
    if 0 <= n <= within_days:
        return f"⚠️決算接近(±{within_days}営業日: {d.isoformat()})", d
    return f"決算 {d.isoformat()}", d
