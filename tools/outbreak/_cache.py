"""SQLite cache cho số liệu dịch bệnh — lưu LỊCH SỬ nhiều tuần (1 dòng / tuần).

DB auto-create runtime tại data/outbreak_cache.db (đã gitignore qua *.db).
"""

from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "outbreak_cache.db"


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS outbreak_history (
               disease     TEXT NOT NULL,
               year        INTEGER NOT NULL,
               week        INTEGER NOT NULL,
               data        TEXT NOT NULL,
               source_url  TEXT,
               fetched_at  TEXT NOT NULL,
               PRIMARY KEY (disease, year, week)
           )"""
    )
    return conn


def _row_to_record(row) -> dict:
    return {"data": json.loads(row[0]), "source_url": row[1], "fetched_at": row[2]}


def save_record(disease: str, data: dict) -> None:
    """Upsert 1 tuần vào lịch sử (key = disease + year + week)."""
    year, week = data.get("year"), data.get("week")
    if not year or not week:
        return
    fetched_at = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO outbreak_history "
            "(disease, year, week, data, source_url, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
            (disease, year, week, json.dumps(data, ensure_ascii=False),
             data.get("source_url", ""), fetched_at),
        )


def get_record(disease: str, year: int, week: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT data, source_url, fetched_at FROM outbreak_history "
            "WHERE disease = ? AND year = ? AND week = ?",
            (disease, year, week),
        ).fetchone()
    return _row_to_record(row) if row else None


def get_latest(disease: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT data, source_url, fetched_at FROM outbreak_history "
            "WHERE disease = ? ORDER BY year DESC, week DESC LIMIT 1",
            (disease,),
        ).fetchone()
    return _row_to_record(row) if row else None


def get_previous(disease: str, year: int, week: int) -> dict | None:
    """Tuần liền trước (year, week) lớn nhất nhưng < (year, week) đã cho."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT data, source_url, fetched_at FROM outbreak_history "
            "WHERE disease = ? AND (year < ? OR (year = ? AND week < ?)) "
            "ORDER BY year DESC, week DESC LIMIT 1",
            (disease, year, year, week),
        ).fetchone()
    return _row_to_record(row) if row else None


def has_week(disease: str, year: int, week: int) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM outbreak_history WHERE disease = ? AND year = ? AND week = ?",
            (disease, year, week),
        ).fetchone()
    return row is not None


def list_weeks(disease: str) -> list[tuple[int, int]]:
    """Danh sách (year, week) đang có, mới nhất trước."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT year, week FROM outbreak_history WHERE disease = ? "
            "ORDER BY year DESC, week DESC",
            (disease,),
        ).fetchall()
    return [(r[0], r[1]) for r in rows]


def latest_age_hours(disease: str) -> float:
    """Số giờ kể từ lần fetch gần nhất của BẤT KỲ tuần nào (để gate discovery)."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT MAX(fetched_at) FROM outbreak_history WHERE disease = ?",
            (disease,),
        ).fetchone()
    if not row or not row[0]:
        return float("inf")
    try:
        ts = datetime.fromisoformat(row[0])
    except (ValueError, TypeError):
        return float("inf")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
