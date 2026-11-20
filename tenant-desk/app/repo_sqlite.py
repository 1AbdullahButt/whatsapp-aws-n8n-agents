"""SQLite version of the repository (used locally).

Dedupe: table seen_messages has wa_message_id as PRIMARY KEY (unique).
We use INSERT OR IGNORE: if the id is already there, nothing is inserted
and rowcount is 0. Because it is a file on disk, dedupe still works
after the server restarts.

Each method opens its own short connection. That keeps it safe when
FastAPI runs requests on different threads.
"""
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.repository import (Repository, StoredMessage, Ticket, check_direction,
                            check_mode, from_iso, ticket_number, to_iso)

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_messages (
    wa_message_id TEXT PRIMARY KEY,
    seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tickets (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT UNIQUE,
    phone TEXT NOT NULL,
    category TEXT NOT NULL,
    urgent INTEGER NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    text TEXT NOT NULL,
    at TEXT NOT NULL,
    wa_message_id TEXT UNIQUE,
    media_path TEXT
);
"""


class SqliteRepository(Repository):
    def __init__(self, db_path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _write(self, sql, params=()):
        """Run one INSERT/UPDATE, commit, and return the cursor."""
        with closing(self._connect()) as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor

    def _read(self, sql, params=()):
        with closing(self._connect()) as conn:
            return conn.execute(sql, params).fetchall()

    def mark_seen(self, wa_message_id):
        now = to_iso(datetime.now(timezone.utc))
        cursor = self._write(
            "INSERT OR IGNORE INTO seen_messages (wa_message_id, seen_at) VALUES (?, ?)",
            (wa_message_id, now),
        )
        return cursor.rowcount == 1

    def create_ticket(self, phone, category, urgent):
        created_at = datetime.now(timezone.utc).replace(microsecond=0)
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                "INSERT INTO tickets (phone, category, urgent, mode, status, created_at) "
                "VALUES (?, ?, ?, 'bot', 'open', ?)",
                (phone, category, int(urgent), to_iso(created_at)),
            )
            # The auto-increment number becomes the ticket id, e.g. 1 -> TD-0001.
            ticket_id = ticket_number(cursor.lastrowid)
            conn.execute("UPDATE tickets SET id = ? WHERE seq = ?", (ticket_id, cursor.lastrowid))
            conn.commit()
        return Ticket(ticket_id, phone, category, bool(urgent), "bot", "open", created_at)

    def get_ticket(self, ticket_id):
        rows = self._read("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return _row_to_ticket(rows[0]) if rows else None

    def get_open_ticket(self, phone):
        rows = self._read(
            "SELECT * FROM tickets WHERE phone = ? AND status = 'open' ORDER BY seq DESC LIMIT 1",
            (phone,),
        )
        return _row_to_ticket(rows[0]) if rows else None

    def set_mode(self, ticket_id, mode):
        check_mode(mode)
        self._write("UPDATE tickets SET mode = ? WHERE id = ?", (mode, ticket_id))

    def close_ticket(self, ticket_id):
        self._write("UPDATE tickets SET status = 'closed' WHERE id = ?", (ticket_id,))

    def mark_urgent(self, ticket_id):
        self._write("UPDATE tickets SET urgent = 1 WHERE id = ?", (ticket_id,))

    def add_message(self, ticket_id, direction, text, at, wa_message_id=None, media_path=None):
        check_direction(direction)
        self._write(
            "INSERT INTO messages (ticket_id, direction, text, at, wa_message_id, media_path) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ticket_id, direction, text, to_iso(at), wa_message_id, media_path),
        )

    def get_history(self, ticket_id):
        rows = self._read("SELECT * FROM messages WHERE ticket_id = ? ORDER BY seq", (ticket_id,))
        return [_row_to_message(row) for row in rows]

    def list_tickets(self):
        rows = self._read("SELECT * FROM tickets ORDER BY seq")
        return [_row_to_ticket(row) for row in rows]

    def last_inbound_time(self, phone):
        rows = self._read(
            "SELECT MAX(m.at) AS last_at FROM messages m "
            "JOIN tickets t ON t.id = m.ticket_id "
            "WHERE t.phone = ? AND m.direction = 'in'",
            (phone,),
        )
        last_at = rows[0]["last_at"]
        return from_iso(last_at) if last_at else None


def _row_to_ticket(row):
    return Ticket(
        id=row["id"],
        phone=row["phone"],
        category=row["category"],
        urgent=bool(row["urgent"]),
        mode=row["mode"],
        status=row["status"],
        created_at=from_iso(row["created_at"]),
    )


def _row_to_message(row):
    return StoredMessage(
        ticket_id=row["ticket_id"],
        direction=row["direction"],
        text=row["text"],
        at=from_iso(row["at"]),
        wa_message_id=row["wa_message_id"],
        media_path=row["media_path"],
    )
