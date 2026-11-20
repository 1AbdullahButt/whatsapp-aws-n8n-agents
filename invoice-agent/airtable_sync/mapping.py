"""Turn the workflow's local records into Airtable rows.

Field names match docs/AIRTABLE_SCHEMA.md exactly. Empty values are left
out, because Airtable rejects None for date and number fields.
"""

INVOICES = "Invoices"
DRAFTS = "Reminder Drafts"
ERRORS = "Error Log"

# The fields each table must have (checked read-only before any write).
EXPECTED_FIELDS = {
    INVOICES: {"File": "singleLineText", "Vendor": "singleLineText",
               "Invoice number": "singleLineText", "Invoice date": "date",
               "Due date": "date", "Currency": "singleLineText", "Subtotal": "number",
               "Tax": "number", "Total": "number", "Flags": "multilineText",
               "Outcome": "singleSelect", "Payment status": "singleLineText",
               "Processed at": "singleLineText"},
    DRAFTS: {"Draft id": "singleLineText", "File": "singleLineText",
             "Vendor": "singleLineText", "Invoice number": "singleLineText",
             "Amount due": "number", "Reminder text": "multilineText",
             "Status": "singleSelect", "Created at": "singleLineText",
             "Decided at": "singleLineText"},
    ERRORS: {"Received at": "singleLineText", "Workflow": "singleLineText",
             "Node": "singleLineText", "Execution id": "singleLineText",
             "Message": "multilineText"},
}
KEY_FIELDS = {INVOICES: "File", DRAFTS: "Draft id", ERRORS: "Received at"}


def schema_problems(actual):
    """List what is missing or has the wrong type. Empty list = schema is fine."""
    problems = []
    for table, fields in EXPECTED_FIELDS.items():
        if table not in actual:
            problems.append(f"missing table {table!r}")
            continue
        for name, kind in fields.items():
            if name not in actual[table]:
                problems.append(f"{table}: missing field {name!r}")
            elif actual[table][name] != kind:
                problems.append(f"{table}: {name!r} is {actual[table][name]}, expected {kind}")
    return problems


def drop_empty(row):
    return {k: v for k, v in row.items() if v not in (None, "", [])}


def payment_from_detail(detail):
    """'payment paid, due 2026-11-02' -> 'paid'."""
    if detail.startswith("payment "):
        return detail.split(",")[0].split(" ", 1)[1]
    return None


def outcome_label(outcome, draft):
    """One of the Outcome options in the schema."""
    if draft is not None:
        return "draft_created"
    status = outcome["status"]
    if status in ("duplicate", "needs_review"):
        return status
    if payment_from_detail(outcome.get("detail", "")) == "paid":
        return "paid"
    return "not_overdue"   # unpaid or part paid, but not past the due date yet


def invoice_row(file_id, extraction, outcome, draft):
    fields = extraction["fields"]
    if draft is not None:
        payment = draft["payment_status"]
        processed_at = draft["created_at"]
    else:
        payment = payment_from_detail(outcome.get("detail", ""))
        processed_at = outcome.get("recorded_at")
    return drop_empty({
        "File": file_id,
        "Vendor": fields.get("vendor"),
        "Invoice number": fields.get("invoice_number"),
        "Invoice date": fields.get("invoice_date"),
        "Due date": fields.get("due_date"),
        "Currency": fields.get("currency"),
        "Subtotal": fields.get("subtotal"),
        "Tax": fields.get("tax"),
        "Total": fields.get("total"),
        "Flags": ", ".join(extraction["flags"]),
        "Outcome": outcome_label(outcome, draft),
        "Payment status": payment,
        "Processed at": processed_at,
    })


def draft_row(draft):
    invoice = draft["invoice"]
    total = invoice.get("total") or 0
    return drop_empty({
        "Draft id": f"draft-{draft['id']}",
        "File": draft["file_id"],
        "Vendor": invoice.get("vendor"),
        "Invoice number": invoice.get("invoice_number"),
        "Amount due": round(total - draft["amount_paid"], 2),
        "Reminder text": draft["reminder_text"],
        "Status": draft["status"],
        "Created at": draft["created_at"],
        "Decided at": draft.get("decided_at"),
    })


def error_row(error):
    return drop_empty({
        "Received at": error["received_at"],
        "Workflow": error.get("workflow"),
        "Node": error.get("node"),
        "Execution id": str(error.get("execution_id") or ""),
        "Message": error.get("message"),
    })
