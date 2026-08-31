"""SQLite persistence for Prominence playtime tracking.

One process (the tracker daemon) writes; the Discord bot and in-game command
handler read. A single connection guarded by a lock keeps it thread- and
asyncio-executor-safe. Totals survive restarts; per-session AFK state does not
(it lives in the tracker's memory and resets cleanly on restart).
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS playtime (
    name           TEXT PRIMARY KEY,
    active_seconds REAL    NOT NULL DEFAULT 0,
    afk_seconds    REAL    NOT NULL DEFAULT 0,
    first_seen     INTEGER,
    last_seen      INTEGER
);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def add_time(self, name: str, active: float = 0.0, afk: float = 0.0,
                 now: int | None = None) -> None:
        now = now or int(time.time())
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO playtime (name, active_seconds, afk_seconds, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    active_seconds = active_seconds + excluded.active_seconds,
                    afk_seconds    = afk_seconds    + excluded.afk_seconds,
                    last_seen      = excluded.last_seen
                """,
                (name, active, afk, now, now),
            )
            self._conn.commit()

    def touch_seen(self, name: str, now: int | None = None) -> None:
        """Ensure a row exists (first join) without crediting time."""
        self.add_time(name, 0.0, 0.0, now)

    def get(self, name: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM playtime WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
        return dict(row) if row else None

    def leaderboard(self, limit: int = 10) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM playtime ORDER BY active_seconds DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def all_names(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT name FROM playtime").fetchall()
        return [r["name"] for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def fmt_hours(seconds: float) -> str:
    """Human 'Xh Ym' from a seconds count."""
    total_min = int(seconds // 60)
    h, m = divmod(total_min, 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"
