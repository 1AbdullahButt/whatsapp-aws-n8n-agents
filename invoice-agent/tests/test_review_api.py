"""B2 endpoints of the extractor API, with TestClient and temporary folders."""
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from extractor.api import app
from helpers import INVOICE_DIR


@pytest.fixture
def folders(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    shutil.copy(INVOICE_DIR / "inv_01_classic_usd.pdf", inbox)
    shutil.copy(INVOICE_DIR / "inv_11_malformed.pdf", inbox)
    (inbox / "notes.txt").write_text("not a pdf")
    monkeypatch.setenv("INBOX_DIR", str(inbox))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTBOX_DIR", str(tmp_path / "outbox"))
    return tmp_path


@pytest.fixture
def client(folders):
    return TestClient(app)


DRAFT = {
    "file_id": "inv_02_twocol_eur.pdf",
    "fields": {
        "vendor": "Kestrel Office Goods GmbH",
        "invoice_number": "KOG-77812",
        "invoice_date": "2026-10-03",
        "due_date": "2026-11-02",
        "currency": "EUR",
        "total": 906.42,
    },
    "flags": ["low_confidence_due_date"],
    "payment_status": "unpaid",
    "amount_paid": 0.0,
    "resume_url": "http://localhost:5690/webhook-waiting/41",
    "today": "2026-11-20",
}


def outbox_lines(folders):
    path = folders / "outbox" / "approved_reminders.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_inbox_lists_only_pdfs(client):
    assert client.get("/inbox").json() == ["inv_01_classic_usd.pdf", "inv_11_malformed.pdf"]


def test_extract_says_whether_to_stop(client):
    good = client.post("/extract", json={"path": "inv_01_classic_usd.pdf"}).json()
    assert good["stop_for_review"] is False
    assert good["blocking_flags"] == []
    bad = client.post("/extract", json={"path": "inv_11_malformed.pdf"}).json()
    assert bad["stop_for_review"] is True
    assert "missing_total" in bad["blocking_flags"]


def test_create_and_list_drafts(client):
    created = client.post("/drafts", json=DRAFT).json()
    assert created["id"] == 1
    assert created["status"] == "pending"
    assert "18 days overdue" in created["reminder_text"]
    assert created["resume_url"] == DRAFT["resume_url"]
    assert [d["id"] for d in client.get("/drafts", params={"status": "pending"}).json()] == [1]
    assert client.get("/drafts", params={"status": "approved"}).json() == []
    assert client.get("/drafts/1").json()["file_id"] == "inv_02_twocol_eur.pdf"
    assert client.get("/drafts/2").status_code == 404


def test_draft_needs_due_date_and_total(client):
    body = dict(DRAFT, fields=dict(DRAFT["fields"], due_date=None))
    assert client.post("/drafts", json=body).status_code == 400


def test_draft_only_for_unpaid_or_partial(client):
    assert client.post("/drafts", json=dict(DRAFT, payment_status="paid")).status_code == 422


def test_approve_writes_outbox_but_sends_nothing(client, folders):
    client.post("/drafts", json=DRAFT)
    response = client.post("/drafts/1/decision", json={"decision": "approve"})
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    lines = outbox_lines(folders)
    assert len(lines) == 1
    assert lines[0]["draft_id"] == 1
    assert lines[0]["invoice_number"] == "KOG-77812"
    assert lines[0]["sent"] is False


def test_reject_does_not_write_outbox(client, folders):
    client.post("/drafts", json=DRAFT)
    assert client.post("/drafts/1/decision", json={"decision": "reject"}).json()["status"] == "rejected"
    assert outbox_lines(folders) == []


def test_second_decision_is_refused(client):
    client.post("/drafts", json=DRAFT)
    client.post("/drafts/1/decision", json={"decision": "reject"})
    assert client.post("/drafts/1/decision", json={"decision": "approve"}).status_code == 409


def test_bad_decision_and_unknown_draft(client):
    client.post("/drafts", json=DRAFT)
    assert client.post("/drafts/1/decision", json={"decision": "maybe"}).status_code == 422
    assert client.post("/drafts/9/decision", json={"decision": "approve"}).status_code == 404


def test_outcomes_round_trip(client):
    client.post("/outcomes", json={"file_id": "inv_09.pdf", "status": "duplicate", "detail": "same as inv_01"})
    outcomes = client.get("/outcomes").json()
    assert len(outcomes) == 1
    assert outcomes[0]["status"] == "duplicate"
    assert "recorded_at" in outcomes[0]


def test_demo_reset_is_off_by_default(client, monkeypatch):
    monkeypatch.delenv("DEMO_RESET_ENABLED", raising=False)
    assert client.post("/demo/reset").status_code == 403


def test_demo_reset_empties_queue_and_logs(client, folders, monkeypatch):
    monkeypatch.setenv("DEMO_RESET_ENABLED", "true")
    client.post("/drafts", json=DRAFT)
    client.post("/drafts/1/decision", json={"decision": "approve"})
    client.post("/outcomes", json={"file_id": "x.pdf", "status": "duplicate"})
    first = {"file_id": "a.pdf", "vendor": "Acme", "invoice_number": "A-1", "total": 5.0}
    client.post("/check-duplicate", json=first)

    assert client.post("/demo/reset").json() == {"reset": True}
    assert client.get("/drafts").json() == []
    assert client.get("/outcomes").json() == []
    assert outbox_lines(folders) == []
    # The duplicate key was forgotten, so a second file is not a duplicate.
    again = dict(first, file_id="b.pdf")
    assert client.post("/check-duplicate", json=again).json()["duplicate"] is False
    # Ids start again at 1.
    assert client.post("/drafts", json=DRAFT).json()["id"] == 1


def test_errors_are_logged_and_alert_file_written(client, folders):
    report = {"workflow": "Invoice intake", "node": "Extract fields",
              "message": "404 - File not found in inbox", "execution_id": "17"}
    assert client.post("/errors", json=report).status_code == 200
    errors_file = folders / "data" / "errors.jsonl"
    saved = json.loads(errors_file.read_text(encoding="utf-8").splitlines()[0])
    assert saved["node"] == "Extract fields"
    assert saved["execution_id"] == "17"
    alert = (folders / "data" / "ALERT_LATEST.txt").read_text(encoding="utf-8")
    assert "Invoice intake" in alert
    assert "File not found in inbox" in alert
