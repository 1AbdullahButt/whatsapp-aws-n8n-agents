"""Reminder text, the review queue and the blocking-flag rule."""
import pytest

from extractor.reminders import days_between, draft_reminder, outstanding_amount
from extractor.review_queue import AlreadyDecided, ReviewQueue
from extractor.validate import blocking_flags

FIELDS = {
    "vendor": "Kestrel Office Goods GmbH",
    "invoice_number": "KOG-77812",
    "invoice_date": "2026-10-03",
    "due_date": "2026-11-02",
    "currency": "EUR",
    "total": 906.42,
}


def test_days_between():
    assert days_between("2026-11-02", "2026-11-20") == 18
    assert days_between("2026-11-19", "2026-11-20") == 1


def test_outstanding_amount():
    assert outstanding_amount(462.0, 200.0) == 262.0
    assert outstanding_amount(906.42, 0) == 906.42
    assert outstanding_amount(906.42, None) == 906.42


def test_unpaid_reminder_text():
    text = draft_reminder(FIELDS, "unpaid", 0.0, "2026-11-20")
    assert text.startswith("Subject: Payment reminder - invoice KOG-77812 from Kestrel Office Goods GmbH")
    assert "was due on 2026-11-02 and is now 18 days overdue" in text
    assert "Invoice total: EUR 906.42" in text
    assert "Still to pay: EUR 906.42" in text
    assert "Already paid" not in text
    assert "please" in text.lower()
    assert "made-up company" in text


def test_partial_reminder_shows_amount_paid():
    fields = dict(FIELDS, total=462.0, currency="GBP")
    text = draft_reminder(fields, "partial", 200.0, "2026-11-20")
    assert "Already paid: GBP 200.00" in text
    assert "Still to pay: GBP 262.00" in text


def test_one_day_overdue_is_singular():
    fields = dict(FIELDS, due_date="2026-11-19")
    assert "1 day overdue" in draft_reminder(fields, "unpaid", 0, "2026-11-20")


def test_large_amounts_get_thousand_separators():
    fields = dict(FIELDS, total=25506.0, currency="PKR")
    assert "PKR 25,506.00" in draft_reminder(fields, "unpaid", 0, "2026-11-20")


def test_blocking_flags_ignore_low_confidence():
    flags = ["low_confidence_vendor", "missing_due_date", "no_text_layer", "totals_mismatch"]
    assert blocking_flags(flags) == ["missing_due_date", "no_text_layer", "totals_mismatch"]
    assert blocking_flags(["low_confidence_currency"]) == []
    assert blocking_flags([]) == []


# --- review queue --------------------------------------------------------------

@pytest.fixture
def queue(tmp_path):
    return ReviewQueue(tmp_path / "review.db")


def add_draft(queue, file_id="inv_02.pdf"):
    return queue.add(file_id, FIELDS, ["low_confidence_due_date"], "unpaid", 0.0,
                     "reminder text", "http://localhost:5690/webhook-waiting/7")


def test_new_draft_is_pending(queue):
    draft = add_draft(queue)
    assert draft["id"] == 1
    assert draft["status"] == "pending"
    assert draft["invoice"]["invoice_number"] == "KOG-77812"
    assert draft["flags"] == ["low_confidence_due_date"]
    assert draft["resume_url"].endswith("/webhook-waiting/7")
    assert draft["decided_at"] is None


def test_list_by_status(queue):
    add_draft(queue, "a.pdf")
    add_draft(queue, "b.pdf")
    queue.decide(1, "approve")
    assert [d["file_id"] for d in queue.list()] == ["a.pdf", "b.pdf"]
    assert [d["file_id"] for d in queue.list("pending")] == ["b.pdf"]
    assert [d["file_id"] for d in queue.list("approved")] == ["a.pdf"]


def test_decision_only_once(queue):
    add_draft(queue)
    assert queue.decide(1, "reject")["status"] == "rejected"
    with pytest.raises(AlreadyDecided):
        queue.decide(1, "approve")


def test_decide_unknown_id(queue):
    with pytest.raises(KeyError):
        queue.decide(99, "approve")
