# -*- coding: utf-8 -*-
"""
Минимальная аналитика на SQLite: кто пришёл, откуда (метка из ссылки
t.me/bot?start=метка) и чем пользуется. Тело/веса пользователей НЕ храним —
только user_id, даты, источник и тип действия.
"""

import sqlite3
import time
from contextlib import closing

_DB_PATH = "bot.db"


def init(path: str = "bot.db") -> None:
    global _DB_PATH
    _DB_PATH = path
    with closing(_connect()) as con, con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                source     TEXT,
                first_seen INTEGER NOT NULL,
                last_seen  INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                user_id INTEGER NOT NULL,
                kind    TEXT    NOT NULL,
                ts      INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
            """
        )


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(_DB_PATH, timeout=5)


def touch_user(user_id: int, source: str | None = None) -> None:
    """Новый юзер — создаём; старый — обновляем last_seen.
    Источник пишем только если его ещё не было (первое касание)."""
    now = int(time.time())
    with closing(_connect()) as con, con:
        con.execute(
            """
            INSERT INTO users (user_id, source, first_seen, last_seen) VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                last_seen = excluded.last_seen,
                source    = COALESCE(users.source, excluded.source)
            """,
            (user_id, source, now, now),
        )


def log_event(user_id: int, kind: str) -> None:
    with closing(_connect()) as con, con:
        con.execute("INSERT INTO events (user_id, kind, ts) VALUES (?, ?, ?)",
                    (user_id, kind, int(time.time())))


def stats(days: int = 7) -> dict:
    since = int(time.time()) - days * 86400
    with closing(_connect()) as con:
        total = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        new = con.execute("SELECT COUNT(*) FROM users WHERE first_seen >= ?", (since,)).fetchone()[0]
        active = con.execute("SELECT COUNT(*) FROM users WHERE last_seen >= ?", (since,)).fetchone()[0]
        sources = con.execute(
            "SELECT COALESCE(source, '—'), COUNT(*) FROM users WHERE first_seen >= ? "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 15",
            (since,),
        ).fetchall()
        events = con.execute(
            "SELECT kind, COUNT(*) FROM events WHERE ts >= ? GROUP BY 1 ORDER BY 2 DESC",
            (since,),
        ).fetchall()
    return {"total": total, "new": new, "active": active, "sources": sources, "events": events}
