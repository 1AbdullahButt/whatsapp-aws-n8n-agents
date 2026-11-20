"""Run the extractor on every synthetic PDF and compare with expected.json.

Prints:
  1. a per-field accuracy table (correct / total files)
  2. per-file flags, expected flags, and duplicate results

Run from the invoice-agent folder:
    .venv\\Scripts\\python scripts\\accuracy_report.py

"Correct" means the extracted value equals the true value in expected.json.
Where the true value is unknown (null, e.g. the garbled total on the
malformed invoice), extracting nothing counts as correct and extracting
anything counts as wrong. For the image-only PDF the true values are
known but nothing is extracted, so every field counts as wrong there.
"""
import json
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))   # so "extractor" imports when run as a script

from extractor.duplicates import DuplicateChecker      # noqa: E402
from extractor.fields import FIELD_NAMES               # noqa: E402
from extractor.pipeline import extract_invoice         # noqa: E402

INVOICE_DIR = PROJECT_DIR / "synthetic" / "invoices"
EXPECTED_FILE = PROJECT_DIR / "synthetic" / "expected.json"


def numbers_equal(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) < 0.005


def line_items_equal(got, want):
    if len(got) != len(want):
        return False
    for g, w in zip(got, want):
        if g["description"] != w["description"] or g["qty"] != w["qty"]:
            return False
        if not numbers_equal(g["unit_price"], w["unit_price"]):
            return False
        if not numbers_equal(g["amount"], w["amount"]):
            return False
    return True


def field_correct(name, got, want):
    """Compare one extracted field with its true value."""
    if name == "line_items":
        return line_items_equal(got or [], want or [])
    if name in ("subtotal", "tax", "total"):
        return numbers_equal(got, want)
    return got == want


def run():
    expected = json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))
    correct = {name: 0 for name in FIELD_NAMES}
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        checker = DuplicateChecker(Path(tmp) / "report.db")
        for file_name in sorted(expected):
            truth = expected[file_name]
            result = extract_invoice(INVOICE_DIR / file_name, file_name)
            wrong = []
            for name in FIELD_NAMES:
                if field_correct(name, result["fields"][name], truth["fields"][name]):
                    correct[name] += 1
                else:
                    wrong.append(name)
            duplicate_of = checker.check(result["fields"], file_name)
            rows.append((file_name, result, truth, wrong, duplicate_of))

    total_files = len(expected)
    print(f"Per-field accuracy on {total_files} synthetic PDFs")
    print(f"{'field':<16}{'correct/total':>14}")
    for name in FIELD_NAMES:
        print(f"{name:<16}{correct[name]:>8}/{total_files}")
    all_correct = sum(correct.values())
    print(f"{'ALL FIELDS':<16}{all_correct:>8}/{total_files * len(FIELD_NAMES)}")

    print()
    print("Per-file results")
    for file_name, result, truth, wrong, duplicate_of in rows:
        missing_expected = [f for f in truth["expected_flags"] if f not in result["flags"]]
        dup_ok = duplicate_of == truth["duplicate_of"]
        print(f"- {file_name}")
        print(f"    needs_review: {result['needs_review']}   flags: {result['flags'] or '-'}")
        print(f"    expected flags present: {'yes' if not missing_expected else 'NO, missing ' + str(missing_expected)}")
        print(f"    wrong fields: {wrong or '-'}")
        print(f"    duplicate_of: {duplicate_of}   ({'as expected' if dup_ok else 'NOT as expected'})")


if __name__ == "__main__":
    run()
