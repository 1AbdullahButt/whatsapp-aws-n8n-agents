"""Unit tests for validation rules and date parsing."""
from extractor.fields import FieldResult, parse_date
from extractor.validate import due_before_invoice_date, totals_mismatch, validate

ITEMS = [{"amount": 100.00}, {"amount": 50.25}]


def test_totals_match_exactly():
    assert totals_mismatch(ITEMS, tax=15.03, total=165.28) is False


def test_totals_within_tolerance():
    assert totals_mismatch(ITEMS, tax=15.03, total=165.29) is False   # off by 0.01


def test_totals_outside_tolerance():
    assert totals_mismatch(ITEMS, tax=15.03, total=165.30) is True    # off by 0.02


def test_totals_not_checked_when_parts_missing():
    assert totals_mismatch([], tax=1.0, total=2.0) is False
    assert totals_mismatch(ITEMS, tax=None, total=2.0) is False
    assert totals_mismatch(ITEMS, tax=1.0, total=None) is False


def test_due_before_invoice_date():
    assert due_before_invoice_date("2026-10-03", "2026-10-01") is True
    assert due_before_invoice_date("2026-10-03", "2026-11-02") is False
    assert due_before_invoice_date("2026-10-03", None) is False


def full_results(**overrides):
    """A complete, consistent set of field results for validate()."""
    results = {
        "vendor": FieldResult("Example Vendor Ltd", 1.0, "label"),
        "invoice_number": FieldResult("EX-1", 1.0, "label"),
        "invoice_date": FieldResult("2026-10-03", 1.0, "label"),
        "due_date": FieldResult("2026-11-02", 1.0, "label"),
        "currency": FieldResult("USD", 1.0, "label"),
        "line_items": FieldResult(ITEMS, 1.0, "label"),
        "subtotal": FieldResult(150.25, 1.0, "label"),
        "tax": FieldResult(15.03, 1.0, "label"),
        "total": FieldResult(165.28, 1.0, "label"),
    }
    results.update(overrides)
    return results


def test_clean_results_have_no_flags():
    check = validate(full_results())
    assert check.flags == []
    assert check.needs_review is False


def test_validate_flags_totals_mismatch():
    check = validate(full_results(total=FieldResult(200.00, 1.0, "label")))
    assert check.flags == ["totals_mismatch"]
    assert check.needs_review is True


def test_validate_flags_due_before_invoice_date():
    check = validate(full_results(due_date=FieldResult("2026-09-01", 1.0, "label")))
    assert "due_before_invoice_date" in check.flags


def test_validate_flags_missing_and_low_confidence():
    check = validate(full_results(
        vendor=FieldResult(),
        currency=FieldResult("USD", 0.6, "fallback"),
    ))
    assert check.flags == ["missing_vendor", "low_confidence_currency"]


def test_validate_no_text_layer():
    check = validate(full_results(), has_text_layer=False)
    assert check.flags == ["no_text_layer"]


def test_parse_date_formats():
    assert parse_date("2026-10-03") == ("2026-10-03", False)
    assert parse_date("3 Oct 2026") == ("2026-10-03", False)
    assert parse_date("28/10/2026") == ("2026-10-28", False)   # 28 > 12: dd/mm
    assert parse_date("10/28/2026") == ("2026-10-28", False)   # 28 > 12: mm/dd
    assert parse_date("03/10/2026") == ("2026-10-03", True)    # ambiguous, assume dd/mm
    assert parse_date("31/02/2026") == (None, False)           # not a real date
