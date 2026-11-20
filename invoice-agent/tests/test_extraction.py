"""Extraction on the synthetic PDFs, checked against synthetic/expected.json."""
import pytest

from extractor.fields import FIELD_NAMES
from helpers import EXPECTED, extracted

# Invoices whose every field is readable from the text layer.
CLEAN_FILES = [name for name, entry in EXPECTED.items()
               if entry["layout"] not in ("malformed", "image")]

CASES = [(file_name, field) for file_name in CLEAN_FILES for field in FIELD_NAMES]


def test_answer_key_has_twelve_invoices():
    assert len(EXPECTED) == 12


@pytest.mark.parametrize("file_name,field", CASES)
def test_field_matches_expected(file_name, field):
    got = extracted(file_name)["fields"][field]
    want = EXPECTED[file_name]["fields"][field]
    if field in ("subtotal", "tax", "total"):
        assert got == pytest.approx(want, abs=0.005)
    elif field == "line_items":
        assert len(got) == len(want)
        for g, w in zip(got, want):
            assert g["description"] == w["description"]
            assert g["qty"] == w["qty"]
            assert g["unit_price"] == pytest.approx(w["unit_price"], abs=0.005)
            assert g["amount"] == pytest.approx(w["amount"], abs=0.005)
    else:
        assert got == want


@pytest.mark.parametrize("file_name", CLEAN_FILES)
def test_expected_flags_are_raised(file_name):
    flags = extracted(file_name)["flags"]
    for flag in EXPECTED[file_name]["expected_flags"]:
        assert flag in flags


@pytest.mark.parametrize("file_name", CLEAN_FILES)
def test_clean_invoices_add_up(file_name):
    assert "totals_mismatch" not in extracted(file_name)["flags"]


def test_missing_due_date_is_flagged_not_invented():
    result = extracted("inv_10_no_due_date.pdf")
    assert result["fields"]["due_date"] is None
    assert result["confidences"]["due_date"] == 0.0
    assert "missing_due_date" in result["flags"]
    assert result["needs_review"] is True


def test_malformed_invoice_needs_review_and_total_is_not_guessed():
    result = extracted("inv_11_malformed.pdf")
    assert result["needs_review"] is True
    assert result["fields"]["total"] is None
    assert result["fields"]["subtotal"] is None
    assert result["fields"]["tax"] is None
    assert "missing_total" in result["flags"]
    # The truncated "Toner cartrid" row must not become a line item.
    descriptions = [item["description"] for item in result["fields"]["line_items"]]
    assert not any(d.startswith("Toner") for d in descriptions)


def test_image_only_pdf_is_flagged_no_text_layer():
    result = extracted("inv_12_image_only.pdf")
    assert result["flags"] == ["no_text_layer"]
    assert result["needs_review"] is True
    for field in FIELD_NAMES:
        assert result["fields"][field] in (None, [])
        assert result["confidences"][field] == 0.0


def test_ambiguous_date_gets_low_confidence():
    # 03/10/2026 could be 3 Oct or 10 Mar: read as dd/mm, flagged.
    result = extracted("inv_02_twocol_eur.pdf")
    assert result["fields"]["invoice_date"] == "2026-10-03"
    assert result["confidences"]["invoice_date"] == 0.6
    assert "low_confidence_invoice_date" in result["flags"]
