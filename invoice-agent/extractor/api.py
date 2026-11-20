"""Local HTTP API for the invoice extractor (port 8101).

Endpoints:
    GET  /health
    POST /extract           multipart upload (field "file"), or JSON {"path": "..."}
                            where the path must be inside INBOX_DIR
    POST /check-duplicate   JSON {"file_id", "vendor", "invoice_number", "total"}

Added for the n8n workflow (milestone B2):
    GET  /inbox                     PDF file names in INBOX_DIR
    POST /drafts                    store a reminder draft (status pending)
    GET  /drafts?status=pending     list drafts
    GET  /drafts/{id}               one draft
    POST /drafts/{id}/decision      {"decision": "approve" | "reject"}
                                    approve -> outbox/approved_reminders.jsonl (NOT sent)
    POST /outcomes, GET /outcomes   what the workflow decided for each file
    POST /errors                    called by the n8n error workflow
    POST /demo/reset                empty queue + logs (only if DEMO_RESET_ENABLED=true)

Run from the invoice-agent folder:
    .venv\\Scripts\\python -m extractor.api
"""
import io
import sys
import threading
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

PROJECT_DIR = Path(__file__).resolve().parents[1]
PORTFOLIO_DIR = PROJECT_DIR.parent
# Make the repo-level `shared` package importable when run with -m.
if str(PORTFOLIO_DIR) not in sys.path:
    sys.path.insert(0, str(PORTFOLIO_DIR))

from shared.config import load_env, optional        # noqa: E402
from shared.logging_setup import get_logger         # noqa: E402

from extractor.duplicates import DuplicateChecker  # noqa: E402
from extractor.pipeline import extract_invoice     # noqa: E402
from extractor.records import alert_text, append_jsonl, read_jsonl   # noqa: E402
from extractor.reminders import draft_reminder     # noqa: E402
from extractor.review_queue import AlreadyDecided, ReviewQueue, now_iso   # noqa: E402
from extractor.validate import blocking_flags      # noqa: E402

load_env(PROJECT_DIR / ".env")
log = get_logger("invoice-agent.extractor")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024   # 10 MB is plenty for an invoice

app = FastAPI(title="invoice-agent extractor (local)")


def project_path(setting, default):
    """Read a folder setting. Relative paths are relative to invoice-agent/."""
    path = Path(optional(setting, default))
    if not path.is_absolute():
        path = PROJECT_DIR / path
    return path.resolve()


def inbox_dir():
    """Folder that JSON {"path": ...} requests may read from."""
    return project_path("INBOX_DIR", "inbox")


def data_dir():
    """Folder for the duplicate-check SQLite file."""
    return project_path("DATA_DIR", "data")


def outbox_dir():
    """Folder for approved reminders. They are written here, never sent."""
    return project_path("OUTBOX_DIR", "outbox")


# FastAPI runs normal (non-async) endpoints in several threads at once.
# Only one of them may touch the SQLite files and log files at a time.
# Without this, the e2e run once failed with "unable to open database file":
# SQLite's own file locking is not reliable on a Docker Desktop bind mount
# of a Windows folder (data/ is one).
storage_lock = threading.Lock()


def duplicate_checker():
    return DuplicateChecker(data_dir() / "duplicates.db")


def review_queue():
    return ReviewQueue(data_dir() / "review.db")


def safe_inbox_path(raw_path):
    """Resolve a path and refuse anything outside the inbox folder.

    Relative paths are taken as relative to the inbox. resolve() removes
    any "..", so "../secret.pdf" ends up outside and is refused.
    """
    inbox = inbox_dir()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = inbox / candidate
    candidate = candidate.resolve()
    if not candidate.is_relative_to(inbox):
        raise HTTPException(status_code=403, detail="Path is outside the inbox folder")
    if candidate.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only .pdf files are accepted")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="File not found in inbox")
    return candidate


def looks_like_pdf(data):
    return data.startswith(b"%PDF")


def run_extraction(source, file_id):
    """Call the pipeline and turn a broken PDF into a 422, not a 500."""
    try:
        result = extract_invoice(source, file_id)
    except Exception as error:   # pdfplumber raises several error types
        log.warning("Could not read %s: %s", file_id, type(error).__name__)
        raise HTTPException(status_code=422, detail="Could not read this PDF")
    # The n8n workflow stops on these; low-confidence flags go on to a human.
    result["blocking_flags"] = blocking_flags(result["flags"])
    result["stop_for_review"] = bool(result["blocking_flags"])
    return result


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/extract")
async def extract(request: Request):
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(status_code=400, detail='Send the PDF in a form field named "file"')
        data = await upload.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File too large")
        if not looks_like_pdf(data):
            raise HTTPException(status_code=400, detail="That file is not a PDF")
        file_id = Path(upload.filename or "upload.pdf").name
        log.info("Extracting upload %s", file_id)
        return run_extraction(io.BytesIO(data), file_id)

    if content_type.startswith("application/json"):
        body = await request.json()
        if not isinstance(body, dict) or not body.get("path"):
            raise HTTPException(status_code=400, detail='JSON body needs a "path"')
        path = safe_inbox_path(body["path"])
        log.info("Extracting inbox file %s", path.name)
        return run_extraction(path, path.name)

    raise HTTPException(status_code=415, detail="Use multipart/form-data or application/json")


class DuplicateRequest(BaseModel):
    file_id: str
    vendor: str | None = None
    invoice_number: str | None = None
    total: float | None = None


@app.post("/check-duplicate")
def check_duplicate(body: DuplicateRequest):
    with storage_lock:
        original = duplicate_checker().check(body.model_dump(), body.file_id)
    return {"duplicate": original is not None, "original": original}


# --- B2: inbox, review queue, outcomes, errors ---------------------------------

@app.get("/inbox")
def list_inbox():
    """PDF file names waiting in the inbox folder, sorted by name."""
    folder = inbox_dir()
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")


class DraftRequest(BaseModel):
    file_id: str
    fields: dict
    flags: list[str] = []
    payment_status: Literal["unpaid", "partial"]
    amount_paid: float = 0.0
    resume_url: str
    today: str | None = None   # ISO date; the workflow sends REMINDER_TODAY


@app.post("/drafts")
def create_draft(body: DraftRequest):
    """Build the reminder text and store the draft as pending."""
    for name in ("vendor", "invoice_number", "due_date", "total"):
        if body.fields.get(name) is None:
            raise HTTPException(status_code=400, detail=f"fields.{name} is required")
    today = body.today or date.today().isoformat()
    text = draft_reminder(body.fields, body.payment_status, body.amount_paid, today)
    with storage_lock:
        draft = review_queue().add(
            body.file_id, body.fields, body.flags, body.payment_status,
            body.amount_paid, text, body.resume_url,
        )
    log.info("Draft %s created for %s", draft["id"], body.file_id)
    return draft


@app.get("/drafts")
def list_drafts(status: str | None = None):
    with storage_lock:
        return review_queue().list(status)


@app.get("/drafts/{draft_id}")
def get_draft(draft_id: int):
    with storage_lock:
        draft = review_queue().get(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="No such draft")
    return draft


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]


@app.post("/drafts/{draft_id}/decision")
def decide_draft(draft_id: int, body: DecisionRequest):
    """Record the human decision. Approved reminders go to the outbox file.

    The outbox is a log file only: nothing is emailed or sent.
    """
    with storage_lock:
        try:
            draft = review_queue().decide(draft_id, body.decision)
        except KeyError:
            raise HTTPException(status_code=404, detail="No such draft")
        except AlreadyDecided as error:
            raise HTTPException(status_code=409, detail=f"Draft is already {error}")
        if draft["status"] == "approved":
            append_jsonl(outbox_dir() / "approved_reminders.jsonl", {
                "draft_id": draft["id"],
                "file_id": draft["file_id"],
                "invoice_number": draft["invoice"]["invoice_number"],
                "vendor": draft["invoice"]["vendor"],
                "reminder_text": draft["reminder_text"],
                "approved_at": draft["decided_at"],
                "sent": False,
            })
    log.info("Draft %s %s", draft_id, draft["status"])
    return draft


class OutcomeRequest(BaseModel):
    file_id: str
    status: str            # duplicate, needs_review, no_reminder
    detail: str = ""


@app.post("/outcomes")
def record_outcome(body: OutcomeRequest):
    """The workflow reports here when it stops early for a file."""
    record = body.model_dump()
    record["recorded_at"] = now_iso()
    with storage_lock:
        append_jsonl(data_dir() / "outcomes.jsonl", record)
    return record


@app.get("/outcomes")
def list_outcomes():
    with storage_lock:
        return read_jsonl(data_dir() / "outcomes.jsonl")


class ErrorReport(BaseModel):
    workflow: str | None = None
    node: str | None = None
    message: str | None = None
    execution_id: str | None = None


@app.post("/errors")
def record_error(body: ErrorReport):
    """Called by the n8n error workflow. Logs the error and writes an alert file."""
    error = body.model_dump()
    error["received_at"] = now_iso()
    with storage_lock:
        append_jsonl(data_dir() / "errors.jsonl", error)
        (data_dir() / "ALERT_LATEST.txt").write_text(alert_text(error), encoding="utf-8")
    log.warning("Workflow error from %s at node %s", error["workflow"], error["node"])
    return error


@app.post("/demo/reset")
def demo_reset():
    """Empty the review queue, duplicate keys and log files (for scripts/e2e_n8n.py).

    Only works when DEMO_RESET_ENABLED=true (set in docker-compose.yml).
    The reset happens here, inside the API, and not by deleting files from
    Windows: deleting review.db from the host while the container had used
    it made the next SQLite open fail ("unable to open database file").
    """
    if optional("DEMO_RESET_ENABLED", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="Demo reset is turned off")
    with storage_lock:
        review_queue().clear()
        duplicate_checker().clear()
        for path in (data_dir() / "outcomes.jsonl", data_dir() / "errors.jsonl",
                     outbox_dir() / "approved_reminders.jsonl"):
            if path.exists():
                path.write_text("", encoding="utf-8")
        (data_dir() / "ALERT_LATEST.txt").unlink(missing_ok=True)
    log.info("Demo reset done")
    return {"reset": True}


if __name__ == "__main__":
    import uvicorn
    port = int(optional("EXTRACTOR_PORT", "8101"))
    uvicorn.run(app, host="127.0.0.1", port=port)
