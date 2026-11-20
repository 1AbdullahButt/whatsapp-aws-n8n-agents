"""Local HTTP API for the invoice extractor (port 8101).

Endpoints:
    GET  /health
    POST /extract           multipart upload (field "file"), or JSON {"path": "..."}
                            where the path must be inside INBOX_DIR
    POST /check-duplicate   JSON {"file_id", "vendor", "invoice_number", "total"}

Run from the invoice-agent folder:
    .venv\\Scripts\\python -m extractor.api
"""
import io
import sys
from pathlib import Path

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


def duplicate_checker():
    return DuplicateChecker(data_dir() / "duplicates.db")


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
        return extract_invoice(source, file_id)
    except Exception as error:   # pdfplumber raises several error types
        log.warning("Could not read %s: %s", file_id, type(error).__name__)
        raise HTTPException(status_code=422, detail="Could not read this PDF")


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
    original = duplicate_checker().check(body.model_dump(), body.file_id)
    return {"duplicate": original is not None, "original": original}


if __name__ == "__main__":
    import uvicorn
    port = int(optional("EXTRACTOR_PORT", "8101"))
    uvicorn.run(app, host="127.0.0.1", port=port)
