"""Check extracted fields and list anything a human should look at.

Flags:
    no_text_layer             the PDF is a picture; nothing was extracted
    missing_<field>           the field was not found (value stays None)
    low_confidence_<field>    found, but with confidence below 0.7
    totals_mismatch           sum(line amounts) + tax differs from total by > 0.01
    due_before_invoice_date   the due date is earlier than the invoice date

needs_review is True whenever there is at least one flag.
This module never fills in a missing value.
"""
from dataclasses import dataclass, field

LOW_CONFIDENCE_THRESHOLD = 0.7
TOTALS_TOLERANCE = 0.01


@dataclass
class ValidationResult:
    flags: list = field(default_factory=list)

    @property
    def needs_review(self):
        return bool(self.flags)


def is_missing(value):
    """None or an empty list both count as missing."""
    return value is None or value == []


def missing_and_low_confidence_flags(results):
    """missing_<field> and low_confidence_<field> flags, in field order."""
    flags = []
    for name, result in results.items():
        if is_missing(result.value):
            flags.append(f"missing_{name}")
        elif result.confidence < LOW_CONFIDENCE_THRESHOLD:
            flags.append(f"low_confidence_{name}")
    return flags


def totals_mismatch(line_items, tax, total, tolerance=TOTALS_TOLERANCE):
    """True if sum(line amounts) + tax is more than `tolerance` away from total.

    Returns False when we cannot check (no line items, no tax or no total);
    those cases are already covered by missing_<field> flags.
    """
    if not line_items or tax is None or total is None:
        return False
    line_sum = sum(item["amount"] for item in line_items)
    # Round first so float noise such as 357.80000000000001 does not count.
    difference = round(line_sum + tax - total, 2)
    return abs(difference) > tolerance


def due_before_invoice_date(invoice_date, due_date):
    """True if both dates exist and the due date is earlier.

    ISO date strings (YYYY-MM-DD) sort the same way as the dates themselves.
    """
    if invoice_date is None or due_date is None:
        return False
    return due_date < invoice_date


def validate(results, has_text_layer=True):
    """Return a ValidationResult for {field_name: FieldResult}."""
    if not has_text_layer:
        # Nothing was read, so per-field flags would only repeat this one.
        return ValidationResult(flags=["no_text_layer"])

    flags = missing_and_low_confidence_flags(results)
    values = {name: result.value for name, result in results.items()}
    if totals_mismatch(values["line_items"], values["tax"], values["total"]):
        flags.append("totals_mismatch")
    if due_before_invoice_date(values["invoice_date"], values["due_date"]):
        flags.append("due_before_invoice_date")
    return ValidationResult(flags=flags)
