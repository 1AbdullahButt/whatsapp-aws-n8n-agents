"""API tests with FastAPI's TestClient (no real server, no network)."""
import pytest
from fastapi.testclient import TestClient

from extractor.api import app as extractor_app
from helpers import INVOICE_DIR
from mock_accounting.api import app as mock_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    # The synthetic invoices folder acts as the inbox; duplicates go to tmp.
    monkeypatch.setenv("INBOX_DIR", str(INVOICE_DIR))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return TestClient(extractor_app)


@pytest.fixture
def mock_client():
    return TestClient(mock_app)


# --- extractor ---------------------------------------------------------------

def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_extract_upload(client):
    pdf_bytes = (INVOICE_DIR / "inv_01_classic_usd.pdf").read_bytes()
    response = client.post("/extract", files={"file": ("inv_01_classic_usd.pdf", pdf_bytes, "application/pdf")})
    assert response.status_code == 200
    body = response.json()
    assert body["fields"]["invoice_number"] == "INV-2026-0141"
    assert body["fields"]["total"] == pytest.approx(357.80)
    assert body["confidences"]["total"] == 1.0
    assert body["flags"] == []
    assert body["needs_review"] is False


def test_extract_upload_rejects_non_pdf(client):
    response = client.post("/extract", files={"file": ("notes.pdf", b"hello", "application/pdf")})
    assert response.status_code == 400


def test_extract_path_inside_inbox(client):
    response = client.post("/extract", json={"path": "inv_10_no_due_date.pdf"})
    assert response.status_code == 200
    body = response.json()
    assert body["fields"]["due_date"] is None
    assert "missing_due_date" in body["flags"]
    assert body["needs_review"] is True


def test_extract_path_outside_inbox_is_refused(client):
    response = client.post("/extract", json={"path": "../expected.json"})
    assert response.status_code == 403
    response = client.post("/extract", json={"path": "../../conftest.py"})
    assert response.status_code == 403


def test_extract_image_only_via_api(client):
    body = client.post("/extract", json={"path": "inv_12_image_only.pdf"}).json()
    assert body["flags"] == ["no_text_layer"]


def test_check_duplicate(client):
    first = {"file_id": "a.pdf", "vendor": "Acme Supplies Ltd.", "invoice_number": "A-100", "total": 99.5}
    again = {"file_id": "b.pdf", "vendor": "ACME SUPPLIES LTD", "invoice_number": "A-100", "total": 99.5}
    assert client.post("/check-duplicate", json=first).json() == {"duplicate": False, "original": None}
    assert client.post("/check-duplicate", json=again).json() == {"duplicate": True, "original": "a.pdf"}


# --- mock accounting -----------------------------------------------------------

def test_mock_payment_status(mock_client):
    response = mock_client.get("/invoices/INV-2026-0141/payment-status")
    assert response.status_code == 200
    assert response.headers["X-Mock"] == "true"
    body = response.json()
    assert body["status"] == "paid"
    assert body["amount_paid"] == pytest.approx(357.80)
    assert body["mock"] is True


def test_mock_invoice_number_with_slashes(mock_client):
    body = mock_client.get("/invoices/HP/2026/0093/payment-status").json()
    assert body["status"] == "partial"


def test_mock_unknown_invoice_is_404_and_still_marked_mock(mock_client):
    response = mock_client.get("/invoices/NOPE-1/payment-status")
    assert response.status_code == 404
    assert response.headers["X-Mock"] == "true"


def test_mock_health_header(mock_client):
    assert mock_client.get("/health").headers["X-Mock"] == "true"
