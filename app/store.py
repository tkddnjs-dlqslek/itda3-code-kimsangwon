# -*- coding: utf-8 -*-
"""재고 저장소 (SQLite). 기한 순 목록, 임박 상태, 수기 대 촬영 소요 시간 통계."""
from __future__ import annotations

import csv
import datetime
import io
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  barcode TEXT NOT NULL DEFAULT '',
  product_name TEXT NOT NULL DEFAULT '',
  year TEXT NOT NULL, month TEXT NOT NULL, day TEXT NOT NULL,
  final_date TEXT NOT NULL,
  confidence REAL,
  needs_review INTEGER NOT NULL DEFAULT 0,
  edited INTEGER NOT NULL DEFAULT 0,
  stage TEXT NOT NULL DEFAULT '',
  evidence TEXT NOT NULL DEFAULT '[]',
  mode TEXT NOT NULL DEFAULT 'scan',
  seconds REAL,
  second_shot INTEGER NOT NULL DEFAULT 0
)"""
CSV_COLS = ["id", "created_at", "barcode", "product_name", "final_date", "confidence",
            "needs_review", "edited", "second_shot", "stage", "mode", "seconds"]


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)   # FastAPI 스레드풀에서 같이 쓴다. 쓰기는 서버가 잠금으로 직렬화
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def final_date_of(year: str, month: str, day: str) -> str:
    return "NONE" if (year, month, day) == ("NONE", "NONE", "NONE") else f"{year}-{month}-{day}"


def status_of(final_date: str, today: datetime.date, imminent_days: int = 3):
    try:
        days = (datetime.date.fromisoformat(final_date) - today).days
    except ValueError:
        return None, "unknown"          # 부분 날짜나 NONE 은 기한 계산 불가
    return days, "expired" if days < 0 else ("imminent" if days <= imminent_days else "ok")


def add_item(conn, item: dict) -> int:
    cur = conn.execute(
        "INSERT INTO items (created_at, barcode, product_name, year, month, day, final_date, confidence,"
        " needs_review, edited, stage, evidence, mode, seconds, second_shot) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (datetime.datetime.now().isoformat(timespec="seconds"), item.get("barcode", ""),
         item.get("product_name", ""), item["year"], item["month"], item["day"],
         final_date_of(item["year"], item["month"], item["day"]), item.get("confidence"),
         int(bool(item.get("needs_review"))), int(bool(item.get("edited"))), item.get("stage", ""),
         json.dumps(item.get("evidence", []), ensure_ascii=False), item.get("mode", "scan"), item.get("seconds"),
         int(bool(item.get("second_shot")))))
    conn.commit()
    return cur.lastrowid


def list_items(conn, today: datetime.date) -> list[dict]:
    out = []
    for r in conn.execute("SELECT * FROM items"):
        d = dict(r)
        d["needs_review"], d["edited"], d["second_shot"] = bool(d["needs_review"]), bool(d["edited"]), bool(d["second_shot"])
        d["evidence"] = json.loads(d["evidence"])
        d["days_left"], d["status"] = status_of(d["final_date"], today)
        out.append(d)
    return sorted(out, key=lambda d: (d["days_left"] is None, d["days_left"] or 0, d["id"]))


def stats(conn) -> dict:
    modes = {m: {"n": n, "avg_seconds": round(avg, 2)} for m, n, avg in conn.execute(
        "SELECT mode, COUNT(*), AVG(seconds) FROM items WHERE seconds IS NOT NULL GROUP BY mode")}
    review, edit, second = conn.execute(
        "SELECT AVG(needs_review), AVG(edited), AVG(second_shot) FROM items WHERE mode = 'scan'").fetchone()
    return {"modes": modes,
            "review_rate": None if review is None else round(review, 4),
            "edit_rate": None if edit is None else round(edit, 4),
            "second_shot_rate": None if second is None else round(second, 4)}


def to_csv(conn) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLS)
    for r in conn.execute(f"SELECT {', '.join(CSV_COLS)} FROM items ORDER BY id"):
        w.writerow(list(r))
    return buf.getvalue()
