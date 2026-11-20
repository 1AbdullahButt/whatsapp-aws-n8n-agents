"""MOCK accounting API (QuickBooks-style), port 8102.

THIS IS A MOCK. It does not talk to QuickBooks or any real accounting
system. It serves fake payment records from mock_accounting/data.json for
the synthetic invoices this project generates, so the workflow can be
built and tested without an accounting account.

Every response, including errors, carries the header "X-Mock: true", and
every payment-status body includes "mock": true.

Endpoints:
    GET /health
    GET /invoices/{invoice_number}/payment-status

Run from the invoice-agent folder:
    .venv\\Scripts\\python -m mock_accounting.api
"""
import json
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

PROJECT_DIR = Path(__file__).resolve().parents[1]
PORTFOLIO_DIR = PROJECT_DIR.parent
if str(PORTFOLIO_DIR) not in sys.path:
    sys.path.insert(0, str(PORTFOLIO_DIR))

from shared.config import load_env, optional   # noqa: E402

DATA_FILE = Path(__file__).resolve().parent / "data.json"

load_env(PROJECT_DIR / ".env")

app = FastAPI(title="MOCK accounting API (fake data)")


@app.middleware("http")
async def add_mock_header(request: Request, call_next):
    """Label every response as mock, so nobody mistakes it for real data."""
    response = await call_next(request)
    response.headers["X-Mock"] = "true"
    return response


def load_payments():
    """Read the fake payment records from data.json."""
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))["invoices"]


@app.get("/health")
def health():
    return {"status": "ok", "mock": True}


# ":path" lets invoice numbers contain "/" (for example HP/2026/0093).
@app.get("/invoices/{invoice_number:path}/payment-status")
def payment_status(invoice_number: str):
    record = load_payments().get(invoice_number)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown invoice number (mock data)")
    return {
        "invoice_number": invoice_number,
        "status": record["status"],
        "amount_paid": record["amount_paid"],
        "mock": True,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(optional("MOCK_ACCOUNTING_PORT", "8102"))
    uvicorn.run(app, host="127.0.0.1", port=port)
