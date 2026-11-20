"""Write the text of a payment reminder for an overdue, unpaid invoice.

The reminder is a DRAFT. A human approves or rejects it in the n8n
workflow, and an approved reminder is only written to an outbox file.
Nothing is emailed.

The invoices in this project are bills we received from vendors, so the
reminder is an internal note to our own (made-up) accounts payable team:
"this bill is overdue, please arrange payment".
"""
from datetime import date

COMPANY_SIGNATURE = (
    "Kind regards,\n"
    "Invoice Assistant (draft for human review)\n"
    "Fernhill Trading Co, a made-up company used for this demo"
)


def days_between(earlier_iso, later_iso):
    """Whole days from one ISO date (YYYY-MM-DD) to another."""
    return (date.fromisoformat(later_iso) - date.fromisoformat(earlier_iso)).days


def outstanding_amount(total, amount_paid):
    """What is still owed, rounded to 2 decimal places."""
    return round(float(total) - float(amount_paid or 0), 2)


def draft_reminder(fields, payment_status, amount_paid, today):
    """Return the reminder text.

    fields: extracted invoice fields (vendor, invoice_number, invoice_date,
            due_date, currency, total)
    payment_status: "unpaid" or "partial" (from the mock accounting API)
    amount_paid: number already paid
    today: ISO date string used to count the days overdue
    """
    currency = fields.get("currency") or ""
    total = fields["total"]
    owed = outstanding_amount(total, amount_paid)
    days_late = days_between(fields["due_date"], today)
    day_word = "day" if days_late == 1 else "days"

    lines = [
        f"Subject: Payment reminder - invoice {fields['invoice_number']} "
        f"from {fields['vendor']}",
        "",
        "Hello Accounts Payable team,",
        "",
        f"This is a friendly reminder that invoice {fields['invoice_number']} "
        f"from {fields['vendor']} was due on {fields['due_date']} and is now "
        f"{days_late} {day_word} overdue.",
        "",
        f"Invoice total: {currency} {total:,.2f}",
    ]
    if payment_status == "partial":
        lines.append(f"Already paid: {currency} {float(amount_paid):,.2f}")
    lines += [
        f"Still to pay: {currency} {owed:,.2f}",
        "",
        "Could you please arrange payment, or let us know if it has already "
        "been settled? Thank you for your help.",
        "",
        COMPANY_SIGNATURE,
    ]
    return "\n".join(lines)
