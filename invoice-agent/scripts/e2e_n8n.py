"""End-to-end check against the LIVE Docker stack (n8n + extractor API + MOCK accounting).

Needs:  docker compose up -d --build   and   scripts\\n8n_setup.ps1
Run:    .venv\\Scripts\\python scripts\\e2e_n8n.py

Not part of `pytest` (it lives in scripts\\, and pytest only collects tests\\).

WARNING: it starts from a clean slate. It calls POST /demo/reset, which
empties the review queue and duplicate keys and blanks data\\outcomes.jsonl,
data\\errors.jsonl and outbox\\approved_reminders.jsonl. All of them are
local demo output for synthetic invoices.
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

import httpx

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import review       # noqa: E402  (scripts/review.py)
import run_inbox    # noqa: E402  (scripts/run_inbox.py)
from extractor.validate import blocking_flags   # noqa: E402

DATA_DIR = PROJECT_DIR / "data"
OUTBOX_FILE = PROJECT_DIR / "outbox" / "approved_reminders.jsonl"
ERRORS_FILE = DATA_DIR / "errors.jsonl"
EXPECTED = json.loads((PROJECT_DIR / "synthetic" / "expected.json").read_text(encoding="utf-8"))
PAYMENTS = json.loads((PROJECT_DIR / "mock_accounting" / "data.json").read_text(encoding="utf-8"))["invoices"]
TODAY = "2026-11-20"   # must match REMINDER_TODAY in docker-compose.yml

RESULTS = []   # (name, passed)


def check(name, passed, detail=""):
    RESULTS.append((name, passed))
    line = f"{'PASS' if passed else 'FAIL'}  {name}"
    if detail:
        line += f"  [{detail}]"
    print(line)


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def wait_until(condition, timeout_seconds=30):
    """Call condition() every second until it returns something truthy."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = condition()
        if result:
            return result
        time.sleep(1)
    return condition()


def expected_drafts():
    """Files that should get a reminder draft, worked out from the answer key.

    Draft = not a duplicate, no blocking flag, mock status unpaid or
    partial, and due date before TODAY.
    """
    names = []
    for name, info in sorted(EXPECTED.items()):
        fields = info["fields"]
        payment = PAYMENTS.get(fields["invoice_number"], {})
        if info["duplicate_of"] or blocking_flags(info["expected_flags"]):
            continue
        if payment.get("status") in ("unpaid", "partial") and fields["due_date"] < TODAY:
            names.append(name)
    return names


def reset_local_output():
    """Ask the API to empty the queue and logs (done inside the container).

    Deleting the SQLite files from Windows instead broke the next SQLite
    open inside the container on Docker Desktop.
    """
    response = httpx.post("http://localhost:8101/demo/reset", timeout=10)
    response.raise_for_status()


def stack_is_up():
    try:
        api = httpx.get("http://localhost:8101/health", timeout=5).status_code == 200
        mock = httpx.get("http://localhost:8102/health", timeout=5).status_code == 200
        n8n = httpx.get("http://localhost:5690/healthz", timeout=5).status_code == 200
    except httpx.HTTPError:
        return False
    return api and mock and n8n


def draft_status(draft_id):
    return review.get_draft(draft_id)["status"]


def main():
    if date.today().isoformat() != TODAY:
        print(f"note: real date is {date.today()}, the workflow uses REMINDER_TODAY={TODAY}")
    check("stack is up (api 8101, mock 8102, n8n 5690)", stack_is_up())
    if not RESULTS[-1][1]:
        return 1

    reset_local_output()
    want = expected_drafts()
    print(f"expected drafts (unpaid/partial, due before {TODAY}, no blocking flag): {want}")

    # 1. All 12 synthetic invoices through the workflow
    filenames = run_inbox.copy_synthetic_to_inbox()
    run_inbox.send_all(filenames)
    results = run_inbox.wait_for_results(filenames)
    for name in filenames:
        print(f"      {name:<28} {results.get(name, 'NO RESULT')}")
    check("all 12 invoices got an outcome or a draft", all(n in results for n in filenames),
          f"{sum(n in results for n in filenames)}/12")

    drafts = review.list_drafts("pending")
    drafted = sorted(d["file_id"] for d in drafts)
    check("drafts created for exactly the unpaid + overdue invoices", drafted == want, f"got {drafted}")

    outcomes = {o["file_id"]: o for o in httpx.get("http://localhost:8101/outcomes", timeout=10).json()}
    dup = outcomes.get("inv_09_resent_copy.pdf", {})
    check("resent copy inv_09 stopped as duplicate, not drafted",
          dup.get("status") == "duplicate" and "inv_09_resent_copy.pdf" not in drafted, dup.get("detail", ""))
    for name in ("inv_11_malformed.pdf", "inv_12_image_only.pdf"):
        outcome = outcomes.get(name, {})
        check(f"{name} stopped as needs_review", outcome.get("status") == "needs_review",
              outcome.get("detail", ""))

    if len(drafts) < 2:
        check("need at least 2 drafts for approve/reject checks", False)
        return 1

    # 2. Approve one draft, reject another, through the n8n resume URL
    approve_id, reject_id = drafts[0]["id"], drafts[1]["id"]
    review.send_decision(approve_id, "approve")
    status = wait_until(lambda: draft_status(approve_id) != "pending" and draft_status(approve_id))
    in_outbox = wait_until(lambda: [r for r in read_jsonl(OUTBOX_FILE) if r["draft_id"] == approve_id])
    check(f"approve draft {approve_id} via n8n -> approved and in outbox (sent=false)",
          status == "approved" and bool(in_outbox) and in_outbox[0]["sent"] is False,
          f"status={status}, outbox lines={len(read_jsonl(OUTBOX_FILE))}")

    review.send_decision(reject_id, "reject")
    status = wait_until(lambda: draft_status(reject_id) != "pending" and draft_status(reject_id))
    not_in_outbox = all(r["draft_id"] != reject_id for r in read_jsonl(OUTBOX_FILE))
    check(f"reject draft {reject_id} via n8n -> rejected and not in outbox",
          status == "rejected" and not_in_outbox, f"status={status}")

    earlier_errors = read_jsonl(ERRORS_FILE)
    check("no workflow errors during the normal run", earlier_errors == [],
          f"{len(earlier_errors)} error(s): {[e.get('node') for e in earlier_errors]}")

    # 3. Force a failure: a file that is not in the inbox makes /extract return 404
    run_inbox.send_file("does_not_exist.pdf")
    errors = wait_until(lambda: read_jsonl(ERRORS_FILE)[len(earlier_errors):], timeout_seconds=45)
    last = errors[-1] if errors else {}
    check("forced failure reached the error workflow -> data/errors.jsonl",
          last.get("workflow") == "Invoice intake" and last.get("node") == "Extract fields"
          and bool(last.get("message")),
          f"node={last.get('node')}, message={last.get('message')}")
    check("data/ALERT_LATEST.txt written", (DATA_DIR / "ALERT_LATEST.txt").exists())

    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
