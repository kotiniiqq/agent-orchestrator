"""Debates are kept in SQLite so the full record can be sent on request."""

import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .render import debate_markdown
from .transcript import Result


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS debates (
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     user_id INTEGER NOT NULL,
                     question TEXT NOT NULL,
                     result_json TEXT NOT NULL,
                     markdown TEXT NOT NULL,
                     created_at TEXT NOT NULL)"""
            )

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def save(self, user_id: int, r: Result) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO debates (user_id, question, result_json, markdown, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, r.question, json.dumps(asdict(r), ensure_ascii=False), debate_markdown(r), datetime.now(UTC).isoformat()),
            )
            return int(cur.lastrowid)

    def get(self, debate_id: int, user_id: int) -> tuple[str, str] | None:
        """The question and the Markdown record, only for the user who asked."""
        with self._conn() as c:
            row = c.execute("SELECT question, markdown FROM debates WHERE id = ? AND user_id = ?", (debate_id, user_id)).fetchone()
        return (row[0], row[1]) if row else None
