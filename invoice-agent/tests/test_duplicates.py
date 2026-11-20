"""Duplicate detection tests."""
from extractor.duplicates import DuplicateChecker, duplicate_key, normalise_vendor
from helpers import extracted


def test_vendor_normalisation():
    assert normalise_vendor("Acme Supplies Ltd.") == normalise_vendor("ACME SUPPLIES LTD")
    assert normalise_vendor("Acme Supplies Ltd.") == "acme supplies"
    assert normalise_vendor("Shalimar Stationers (Pvt) Ltd") == "shalimar stationers"


def test_key_rounds_total_to_two_places():
    assert duplicate_key("Acme Ltd", "A-1", 10.004) == duplicate_key("ACME LTD.", "a-1", 10.0)


def test_no_key_when_a_part_is_missing():
    assert duplicate_key("Acme Ltd", "A-1", None) is None
    assert duplicate_key(None, "A-1", 10.0) is None


def test_checker_returns_original_file_id(tmp_path):
    checker = DuplicateChecker(tmp_path / "dup.db")
    first = {"vendor": "Acme Supplies Ltd.", "invoice_number": "A-100", "total": 99.5}
    again = {"vendor": "ACME SUPPLIES LTD", "invoice_number": "A-100", "total": 99.50}
    assert checker.check(first, "first.pdf") is None
    assert checker.check(again, "second.pdf") == "first.pdf"


def test_same_file_twice_is_not_a_duplicate(tmp_path):
    checker = DuplicateChecker(tmp_path / "dup.db")
    fields = {"vendor": "Acme Ltd", "invoice_number": "A-1", "total": 1.0}
    assert checker.check(fields, "a.pdf") is None
    assert checker.check(fields, "a.pdf") is None


def test_different_total_is_not_a_duplicate(tmp_path):
    checker = DuplicateChecker(tmp_path / "dup.db")
    checker.check({"vendor": "Acme Ltd", "invoice_number": "A-1", "total": 1.0}, "a.pdf")
    assert checker.check({"vendor": "Acme Ltd", "invoice_number": "A-1", "total": 2.0}, "b.pdf") is None


def test_store_survives_reopening(tmp_path):
    db = tmp_path / "dup.db"
    DuplicateChecker(db).check({"vendor": "Acme Ltd", "invoice_number": "A-1", "total": 1.0}, "a.pdf")
    assert DuplicateChecker(db).check({"vendor": "Acme", "invoice_number": "A-1", "total": 1.0}, "b.pdf") == "a.pdf"


def test_resent_synthetic_invoice_is_detected(tmp_path):
    checker = DuplicateChecker(tmp_path / "dup.db")
    original = extracted("inv_01_classic_usd.pdf")
    resent = extracted("inv_09_resent_copy.pdf")
    assert checker.check(original["fields"], original["file_id"]) is None
    assert checker.check(resent["fields"], resent["file_id"]) == "inv_01_classic_usd.pdf"
