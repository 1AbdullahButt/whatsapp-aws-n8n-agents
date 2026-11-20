"""Human review of reminder drafts, from the Windows command line.

    .venv\\Scripts\\python scripts\\review.py list
    .venv\\Scripts\\python scripts\\review.py show 3
    .venv\\Scripts\\python scripts\\review.py approve 3
    .venv\\Scripts\\python scripts\\review.py reject 3

approve / reject call the draft's n8n resume URL. That wakes up the paused
n8n execution (the "Wait for human approval" node), and n8n then records
the decision through the extractor API. An approved reminder is written to
outbox/approved_reminders.jsonl. Nothing is emailed.
"""
import sys
from urllib.parse import urlsplit, urlunsplit

import httpx

API_URL = "http://localhost:8101"
N8N_URL = "http://localhost:5690"


def host_resume_url(resume_url, n8n_url=N8N_URL):
    """Point a resume URL at n8n as seen from this computer.

    n8n builds the URL from WEBHOOK_URL (http://localhost:5690/ in
    docker-compose.yml), so this normally changes nothing. If n8n ever used
    an internal name such as http://n8n:5678, we swap in the host address
    and keep the path and query (the query may carry a signature).
    """
    original = urlsplit(resume_url)
    target = urlsplit(n8n_url)
    return urlunsplit((target.scheme, target.netloc, original.path, original.query, ""))


def get_draft(draft_id):
    response = httpx.get(f"{API_URL}/drafts/{draft_id}", timeout=10)
    if response.status_code == 404:
        sys.exit(f"No draft with id {draft_id}")
    response.raise_for_status()
    return response.json()


def list_drafts(status="pending"):
    response = httpx.get(f"{API_URL}/drafts", params={"status": status}, timeout=10)
    response.raise_for_status()
    return response.json()


def send_decision(draft_id, decision):
    """Resume the n8n execution for this draft with "approve" or "reject"."""
    draft = get_draft(draft_id)
    if draft["status"] != "pending":
        sys.exit(f"Draft {draft_id} is already {draft['status']}")
    url = host_resume_url(draft["resume_url"])
    response = httpx.post(url, json={"decision": decision}, timeout=30)
    response.raise_for_status()
    return response.status_code


def print_list():
    drafts = list_drafts("pending")
    if not drafts:
        print("No pending drafts.")
        return
    print(f"{'id':>3}  {'file':<28} {'invoice':<15} {'payment':<8} {'due':<10}  flags")
    for d in drafts:
        inv = d["invoice"]
        flags = ", ".join(d["flags"]) or "-"
        print(f"{d['id']:>3}  {d['file_id']:<28} {inv['invoice_number']:<15} "
              f"{d['payment_status']:<8} {inv['due_date']:<10}  {flags}")


def main(args):
    if not args or args[0] not in ("list", "show", "approve", "reject"):
        sys.exit(__doc__)
    command = args[0]
    if command == "list":
        print_list()
        return
    if len(args) != 2 or not args[1].isdigit():
        sys.exit(f"Usage: review.py {command} ID")
    draft_id = int(args[1])
    if command == "show":
        draft = get_draft(draft_id)
        print(f"Draft {draft_id} ({draft['status']}), flags: {', '.join(draft['flags']) or '-'}\n")
        print(draft["reminder_text"])
        return
    status = send_decision(draft_id, command)
    print(f"Sent '{command}' for draft {draft_id} to n8n (HTTP {status}).")


if __name__ == "__main__":
    main(sys.argv[1:])
