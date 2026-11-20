"""Send the synthetic invoices through the n8n workflow.

    .venv\\Scripts\\python scripts\\run_inbox.py              copy the 12 PDFs to inbox\\ and send all
    .venv\\Scripts\\python scripts\\run_inbox.py inv_02_twocol_eur.pdf   send one file

Each file name is POSTed to http://localhost:5690/webhook/invoice. The
webhook answers at once (the workflow keeps running, and may pause for
approval), so afterwards we ask the extractor API what happened to each
file and print it.
"""
import shutil
import sys
import time
from pathlib import Path

import httpx

PROJECT_DIR = Path(__file__).resolve().parents[1]
SYNTHETIC_DIR = PROJECT_DIR / "synthetic" / "invoices"
INBOX_DIR = PROJECT_DIR / "inbox"

WEBHOOK_URL = "http://localhost:5690/webhook/invoice"
API_URL = "http://localhost:8101"
SECONDS_BETWEEN_FILES = 0.5   # keeps inv_01 well ahead of its resent copy inv_09


def copy_synthetic_to_inbox():
    """Copy the synthetic PDFs into inbox\\ (the api container sees it read-only)."""
    INBOX_DIR.mkdir(exist_ok=True)
    names = []
    for pdf in sorted(SYNTHETIC_DIR.glob("*.pdf")):
        shutil.copy(pdf, INBOX_DIR / pdf.name)
        names.append(pdf.name)
    return names


def send_file(filename):
    """POST one file name to the n8n webhook. Returns the HTTP status code."""
    response = httpx.post(WEBHOOK_URL, json={"filename": filename}, timeout=30)
    return response.status_code


def current_results():
    """{file_id: outcome text} from the API's outcomes and drafts."""
    results = {}
    for outcome in httpx.get(f"{API_URL}/outcomes", timeout=10).json():
        results[outcome["file_id"]] = f"{outcome['status']} ({outcome['detail']})"
    for draft in httpx.get(f"{API_URL}/drafts", timeout=10).json():
        results[draft["file_id"]] = f"draft {draft['id']} {draft['status']}"
    return results


def wait_for_results(filenames, timeout_seconds=90):
    """Poll the API until every file has an outcome or a draft."""
    deadline = time.time() + timeout_seconds
    results = current_results()
    while time.time() < deadline:
        results = current_results()
        if all(name in results for name in filenames):
            break
        time.sleep(1)
    return results


def send_all(filenames):
    for name in filenames:
        status = send_file(name)
        print(f"sent {name:<28} webhook HTTP {status}")
        time.sleep(SECONDS_BETWEEN_FILES)


def main(args):
    filenames = args if args else copy_synthetic_to_inbox()
    send_all(filenames)
    print("\nWaiting for the workflow to finish each file ...")
    results = wait_for_results(filenames)
    print()
    for name in filenames:
        print(f"{name:<28} {results.get(name, 'no result yet (check n8n executions)')}")


if __name__ == "__main__":
    main(sys.argv[1:])
