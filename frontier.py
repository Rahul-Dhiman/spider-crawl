"""Persistent URL frontier using SQLite with deduplication and depth tracking."""

import sqlite3
import threading
from typing import Optional, Tuple


class SQLiteFrontier:
    """Simple persistent priority frontier with depth and visited flags."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS queue (
                  url TEXT PRIMARY KEY,
                  depth INTEGER NOT NULL,
                  priority INTEGER NOT NULL DEFAULT 0,
                  enqueued_at REAL DEFAULT (strftime('%s','now')),
                  visited INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_prio ON queue(visited, priority, enqueued_at);")

    def put(self, url: str, depth: int, priority: int = 0) -> None:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO queue(url, depth, priority) VALUES(?,?,?)",
                (url, depth, priority),
            )

    def get(self) -> Optional[Tuple[str, int]]:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT url, depth FROM queue WHERE visited=0 ORDER BY priority DESC, enqueued_at ASC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            url, depth = row
            conn.execute("UPDATE queue SET visited=1 WHERE url=?", (url,))
            return url, depth

    def size(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM queue WHERE visited=0").fetchone()
            return int(row[0]) if row else 0

