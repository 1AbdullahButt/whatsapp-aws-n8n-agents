"""B3 Airtable sync, with a fake client (no network, no API calls)."""
import json
import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "scripts"))

from airtable_sync import client as client_module           # noqa: E402
from airtable_sync import mapping                           # noqa: E402
from airtable_sync.client import AirtableClient, FakeAirtableClient, batches   # noqa: E402
from extractor.review_queue import ReviewQueue              # noqa: E402
import sync_airtable                                        # noqa: E402

INVOICE_DIR = PROJECT_DIR / "synthetic" / "invoices"
GOOD_SCHEMA = {table: dict(fields) for table, fields in mapping.EXPECTED_FIELDS.items()}


def make_data_dir(tmp_path):
    """A small copy of what one n8n run leaves behind."""
    data = tmp_path / "data"
    data.mkdir()
    outcomes = [
        {"file_id": "inv_01_classic_usd.pdf", "status": "no_reminder",
         "detail": "payment paid, due 2026-11-02", "recorded_at": "2026-11-20T17:57:28+00:00"},
        {"file_id": "inv_06_twocol_usd.pdf", "status": "no_reminder",
         "detail": "payment partial, due 2026-12-07", "recorded_at": "2026-11-20T17:57:40+00:00"},
        {"file_id": "inv_09_resent_copy.pdf", "status": "duplicate",
         "detail": "same invoice as inv_01_classic_usd.pdf", "recorded_at": "2026-11-20T17:57:45+00:00"},
        {"file_id": "inv_12_image_only.pdf", "status": "needs_review",
         "detail": "no_text_layer", "recorded_at": "2026-11-20T17:57:50+00:00"},
    ]
    (data / "outcomes.jsonl").write_text("\n".join(json.dumps(o) for o in outcomes), encoding="utf-8")
    (data / "errors.jsonl").write_text(json.dumps({
        "workflow": "Invoice intake", "node": "Extract fields", "message": "not found",
        "execution_id": 98, "received_at": "2026-11-20T17:58:40+00:00"}), encoding="utf-8")
    queue = ReviewQueue(data / "review.db")
    draft = queue.add("inv_02_twocol_eur.pdf",
                      {"vendor": "Kestrel Office Goods GmbH", "invoice_number": "KOG-77812",
                       "total": 906.42}, ["low_confidence_due_date"], "unpaid", 100.0,
                      "Subject: Payment reminder", "http://localhost:5690/webhook-waiting/1")
    queue.decide(draft["id"], "approve")
    return data


def test_batches_of_ten():
    assert [len(b) for b in batches(list(range(25)))] == [10, 10, 5]


def test_schema_check():
    assert mapping.schema_problems(GOOD_SCHEMA) == []
    broken = {t: dict(f) for t, f in GOOD_SCHEMA.items()}
    del broken[mapping.ERRORS]
    broken[mapping.INVOICES]["Total"] = "singleLineText"
    del broken[mapping.DRAFTS]["Status"]
    problems = mapping.schema_problems(broken)
    assert "missing table 'Error Log'" in problems
    assert "Invoices: 'Total' is singleLineText, expected number" in problems
    assert "Reminder Drafts: missing field 'Status'" in problems


def test_outcome_labels():
    assert mapping.outcome_label({"status": "no_reminder", "detail": "payment paid, due x"}, None) == "paid"
    assert mapping.outcome_label({"status": "no_reminder", "detail": "payment unpaid, due x"}, None) == "not_overdue"
    assert mapping.outcome_label({"status": "duplicate"}, None) == "duplicate"
    assert mapping.outcome_label({"status": "needs_review"}, None) == "needs_review"
    assert mapping.outcome_label(None, {"payment_status": "unpaid"}) == "draft_created"


def test_build_rows(tmp_path):
    rows = sync_airtable.build_rows(make_data_dir(tmp_path), INVOICE_DIR)
    invoices = {r["File"]: r for r in rows[mapping.INVOICES]}
    assert len(invoices) == 5
    assert invoices["inv_01_classic_usd.pdf"]["Outcome"] == "paid"
    assert invoices["inv_01_classic_usd.pdf"]["Invoice number"] == "INV-2026-0141"
    assert invoices["inv_01_classic_usd.pdf"]["Due date"] == "2026-11-02"
    assert invoices["inv_06_twocol_usd.pdf"]["Outcome"] == "not_overdue"
    assert invoices["inv_06_twocol_usd.pdf"]["Payment status"] == "partial"
    assert invoices["inv_02_twocol_eur.pdf"]["Outcome"] == "draft_created"
    # The image-only PDF has no fields: they are left out, not sent as None.
    image_only = invoices["inv_12_image_only.pdf"]
    assert "Total" not in image_only and "Due date" not in image_only
    assert image_only["Flags"].startswith("no_text_layer")

    [draft] = rows[mapping.DRAFTS]
    assert draft["Draft id"] == "draft-1"
    assert draft["Status"] == "approved"
    assert draft["Amount due"] == 806.42
    [error] = rows[mapping.ERRORS]
    assert error["Execution id"] == "98"


def test_sync_twice_does_not_duplicate_and_counts_calls(tmp_path):
    rows = sync_airtable.build_rows(make_data_dir(tmp_path), INVOICE_DIR)
    fake = FakeAirtableClient(schema=GOOD_SCHEMA)
    first = sync_airtable.sync(fake, rows)
    assert first[mapping.INVOICES] == (5, 0)
    assert fake.calls == 4   # 1 schema read + 1 batch per table
    second = sync_airtable.sync(fake, rows)
    assert second[mapping.INVOICES] == (0, 5)
    assert len(fake.tables[mapping.INVOICES]) == 5


def test_sync_stops_before_writing_if_schema_is_wrong(tmp_path):
    rows = sync_airtable.build_rows(make_data_dir(tmp_path), INVOICE_DIR)
    fake = FakeAirtableClient(schema={mapping.INVOICES: {}})
    with pytest.raises(SystemExit):
        sync_airtable.sync(fake, rows)
    assert fake.tables == {}


def test_dry_run_makes_no_client(tmp_path, monkeypatch, capsys):
    def no_client(*args, **kwargs):
        raise AssertionError("dry run must not create a client")
    monkeypatch.setattr(sync_airtable, "AirtableClient", no_client)
    data = make_data_dir(tmp_path)
    assert sync_airtable.main(["--dry-run", "--data-dir", str(data), "--pdf-dir", str(INVOICE_DIR)]) == 0
    assert "Invoices: 5 rows" in capsys.readouterr().out


class FakeResponse:
    def __init__(self, status, body):
        self.status_code = status
        self.is_error = status >= 400
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


def test_real_client_sends_upsert_batches(monkeypatch):
    sent = []

    def fake_request(method, url, headers, timeout, json=None):
        sent.append((method, url, json))
        return FakeResponse(200, {"createdRecords": ["r"] * len(json["records"]), "updatedRecords": []})

    monkeypatch.setattr(client_module.httpx, "request", fake_request)
    monkeypatch.setattr(client_module, "PAUSE_SECONDS", 0)
    client = AirtableClient("pat-test", "appTEST")
    rows = [{"File": f"f{i}"} for i in range(12)]
    assert client.upsert("Invoices", rows, "File") == (12, 0)
    assert client.calls == 2
    method, url, body = sent[0]
    assert method == "PATCH" and url.endswith("/appTEST/Invoices")
    assert body["performUpsert"] == {"fieldsToMergeOn": ["File"]}
    assert len(body["records"]) == 10


def test_real_client_raises_on_error(monkeypatch):
    monkeypatch.setattr(client_module.httpx, "request",
                        lambda *a, **k: FakeResponse(422, {"error": {"type": "UNKNOWN_FIELD_NAME"}}))
    with pytest.raises(RuntimeError, match="UNKNOWN_FIELD_NAME"):
        AirtableClient("pat-test", "appTEST").upsert("Invoices", [{"File": "x"}], "File")
