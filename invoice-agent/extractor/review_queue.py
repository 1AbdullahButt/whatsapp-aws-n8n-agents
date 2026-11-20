"""Review queue: reminder drafts waiting for a human decision.

Stored in a small SQLite file (by default data/review.db). Each draft
keeps the n8n "resume URL": calling it wakes up the paused n8n execution
with the human's decision.

Status goes pending -> approved or pending -> rejected. A decision can
only be made once.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

STATUSES = ("pending", "approved", "rejected")
DECISIONS = {"approve": "approved", "reject": "rejected"}


class AlreadyDecided(Exception):
    """The draft is not pending any more."""


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ReviewQueue:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_table()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_table(self):
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS drafts ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " file_id TEXT NOT NULL,"
                " invoice_json TEXT NOT NULL,"
                " flags_json TEXT NOT NULL,"
                " payment_status TEXT NOT NULL,"
                " amount_paid REAL NOT NULL,"
                " reminder_text TEXT NOT NULL,"
                " resume_url TEXT NOT NULL,"
                " status TEXT NOT NULL,"
                " created_at TEXT NOT NULL,"
                " decided_at TEXT)"
            )

    def add(self, file_id, invoice, flags, payment_status, amount_paid, reminder_text, resume_url):
        """Store a new pending draft and return it as a dict."""
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO drafts (file_id, invoice_json, flags_json, payment_status,"
                " amount_paid, reminder_text, resume_url, status, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (file_id, json.dumps(invoice), json.dumps(flags), payment_status,
                 amount_paid, reminder_text, resume_url, now_iso()),
            )
            draft_id = cursor.lastrowid
        return self.get(draft_id)

    def get(self, draft_id):
        """Return one draft as a dict, or None if there is no such id."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        return row_to_dict(row) if row else None

    def list(self, status=None):
        """All drafts, oldest first, optionally only one status."""
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM drafts WHERE status = ? ORDER BY id", (status,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM drafts ORDER BY id").fetchall()
        return [row_to_dict(row) for row in rows]

    def decide(self, draft_id, decision):
        """Record "approve" or "reject". Returns the updated draft.

        Raises KeyError for an unknown id and AlreadyDecided if the draft
        is no longer pending.
        """
        draft = self.get(draft_id)
        if draft is None:
            raise KeyError(draft_id)
        if draft["status"] != "pending":
            raise AlreadyDecided(draft["status"])
        with self._connect() as conn:
            conn.execute(
                "UPDATE drafts SET status = ?, decided_at = ? WHERE id = ?",
                (DECISIONS[decision], now_iso(), draft_id),
            )
        return self.get(draft_id)


    def clear(self):
        """Delete every draft and restart ids at 1. Used by the demo reset."""
        with self._connect() as conn:
            conn.execute("DELETE FROM drafts")
            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'drafts'")


def row_to_dict(row):
    """SQLite row -> plain dict, with the JSON columns decoded."""
    draft = dict(row)
    draft["invoice"] = json.loads(draft.pop("invoice_json"))
    draft["flags"] = json.loads(draft.pop("flags_json"))
    return draft
