"""Spot invoices we have already seen.

Duplicate key = normalised vendor + invoice number + total (2 decimal places).

Normalising the vendor means "Acme Supplies Ltd." and "ACME SUPPLIES LTD"
give the same key: lowercase, punctuation removed, company suffixes such
as Ltd / LLC / Inc dropped.

Seen keys are kept in a small SQLite file (by default data/duplicates.db).
"""
import re
import sqlite3
from pathlib import Path

COMPANY_SUFFIXES = {
    "ltd", "limited", "llc", "inc", "incorporated", "co", "corp",
    "corporation", "plc", "gmbh", "sarl", "pvt", "private", "llp",
}


def normalise_vendor(name):
    """'Acme Supplies Ltd.' -> 'acme supplies'."""
    text = name.lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)      # punctuation becomes a space
    words = [w for w in text.split() if w not in COMPANY_SUFFIXES]
    return " ".join(words)


def normalise_invoice_number(number):
    """Uppercase and remove spaces, so 'inv-01 ' == 'INV-01'."""
    return re.sub(r"\s+", "", str(number)).upper()


def duplicate_key(vendor, invoice_number, total):
    """Build the key, or None if any part is missing.

    We do not build a key from partial data: two invoices that are both
    missing a total are not proof of a duplicate.
    """
    if not vendor or not invoice_number or total is None:
        return None
    return f"{normalise_vendor(vendor)}|{normalise_invoice_number(invoice_number)}|{float(total):.2f}"


class DuplicateChecker:
    """Remember invoice keys in SQLite and report repeats."""

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_table()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _create_table(self):
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS seen_invoices ("
                " dup_key TEXT PRIMARY KEY,"
                " file_id TEXT NOT NULL)"
            )

    def find(self, key):
        """Return the file id first stored under this key, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT file_id FROM seen_invoices WHERE dup_key = ?", (key,)
            ).fetchone()
        return row[0] if row else None

    def remember(self, key, file_id):
        """Store the key. If it is already there, keep the first file id."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO seen_invoices (dup_key, file_id) VALUES (?, ?)",
                (key, file_id),
            )

    def clear(self):
        """Forget every stored key. Used by the demo reset."""
        with self._connect() as conn:
            conn.execute("DELETE FROM seen_invoices")

    def check(self, fields, file_id):
        """Check one invoice and remember it.

        fields needs vendor, invoice_number and total.
        Returns the original file id if this is a duplicate, else None.
        Checking the same file id twice is not called a duplicate.
        """
        key = duplicate_key(fields.get("vendor"), fields.get("invoice_number"), fields.get("total"))
        if key is None:
            return None
        original = self.find(key)
        if original is not None and original != file_id:
            return original
        self.remember(key, file_id)
        return None
