"""Shared test helpers: paths, the answer key, and cached extraction."""
import json
from functools import lru_cache
from pathlib import Path

from extractor.pipeline import extract_invoice

PROJECT_DIR = Path(__file__).resolve().parents[1]
INVOICE_DIR = PROJECT_DIR / "synthetic" / "invoices"
EXPECTED = json.loads((PROJECT_DIR / "synthetic" / "expected.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def extracted(file_name):
    """Extract a synthetic PDF once and reuse the result across tests."""
    return extract_invoice(INVOICE_DIR / file_name, file_name)
