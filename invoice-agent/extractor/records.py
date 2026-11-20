"""Small append-only log files (one JSON object per line).

Used for:
    outbox/approved_reminders.jsonl   approved reminders (NOT sent anywhere)
    data/outcomes.jsonl               what the workflow decided per invoice
    data/errors.jsonl                 failures reported by the n8n error workflow
"""
import json
from pathlib import Path


def append_jsonl(path, record):
    """Add one record as a line of JSON at the end of the file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record) + "\n")


def read_jsonl(path):
    """All records in the file, oldest first. A missing file means none."""
    path = Path(path)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def alert_text(error):
    """Plain text for data/ALERT_LATEST.txt, so a person can read it quickly."""
    return (
        "INVOICE WORKFLOW ERROR\n"
        f"time:         {error['received_at']}\n"
        f"workflow:     {error.get('workflow')}\n"
        f"node:         {error.get('node')}\n"
        f"execution id: {error.get('execution_id')}\n"
        f"message:      {error.get('message')}\n"
    )
