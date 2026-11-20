"""Find invoice fields in PDF text, one small function per field.

Every function returns a FieldResult with a value and a confidence:
    1.0  the value sat next to a label we expect (for example "Invoice No:")
    0.6  no label, but a fallback pattern found something that looks right
    0.0  not found (value is None; we never make a value up)

Dates are returned as ISO strings (YYYY-MM-DD). A date like 03/10/2026 is
ambiguous: it could be 3 October (dd/mm) or 10 March (mm/dd). We assume
dd/mm, because the synthetic vendors are mostly outside the US, and drop
the confidence to 0.6 so the invoice gets a human check. If one part is
above 12 the date is not ambiguous and keeps full confidence.

Text is read in pdfplumber "layout" mode, where two or more spaces in a
row separate columns. The regexes below treat 2+ spaces as a column gap.
"""
import re
from dataclasses import dataclass, asdict
from datetime import date

LABEL_CONFIDENCE = 1.0
FALLBACK_CONFIDENCE = 0.6
NOT_FOUND_CONFIDENCE = 0.0

KNOWN_CURRENCIES = ["USD", "EUR", "GBP", "PKR"]
CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "Rs": "PKR"}

# Pieces of regex reused below.
SEGMENT_START = r"(?:^[ \t]*|[ \t]{2,})"   # start of a line or of a column
LABEL_GAP = r"[ \t]*[:.#]?[ \t]*"           # optional colon/dot between label and value
CURRENCY_PREFIX = r"(?:(?:USD|EUR|GBP|PKR|Rs\.?|[$€£])[ \t]*)?"
AMOUNT = r"\d{1,3}(?:,\d{3})+\.\d{2}|\d+\.\d{2}"
DATE = (r"\d{4}-\d{2}-\d{2}"
        r"|\d{1,2}/\d{1,2}/\d{4}"
        r"|\d{1,2}[ -][A-Za-z]{3,9}[ -]\d{4}")

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Headings that are not a vendor name.
GENERIC_HEADINGS = {"invoice", "tax invoice", "receipt", "receipt / invoice", "bill"}


@dataclass
class FieldResult:
    value: object = None
    confidence: float = NOT_FOUND_CONFIDENCE
    source: str = "not_found"   # "label", "fallback" or "not_found"


@dataclass
class LineItem:
    description: str
    qty: int
    unit_price: float
    amount: float


def found_by_label(value):
    return FieldResult(value, LABEL_CONFIDENCE, "label")


def found_by_fallback(value):
    return FieldResult(value, FALLBACK_CONFIDENCE, "fallback")


def not_found():
    return FieldResult()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def find_after_label(text, labels, value_pattern):
    """Return the first value that follows one of the labels, or None.

    labels is a list of regex strings, longest first, so "Total Due" is
    tried before "Total".
    """
    for label in labels:
        pattern = SEGMENT_START + "(?:" + label + ")" + LABEL_GAP + "(" + value_pattern + ")"
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return None


def label_present(text, labels):
    """True if any label appears at the start of a line or column."""
    for label in labels:
        if re.search(SEGMENT_START + "(?:" + label + ")", text, re.IGNORECASE | re.MULTILINE):
            return True
    return False


def parse_amount(text):
    """Turn '1,234.50' into 1234.5. Return None if it is not a number."""
    if text is None:
        return None
    cleaned = text.replace(",", "").strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
        return None
    return round(float(cleaned), 2)


def parse_date(text):
    """Turn a date string into (iso_string, is_ambiguous).

    Returns (None, False) if the text is not a valid date.
    """
    text = text.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            year, month, day = (int(p) for p in text.split("-"))
            return date(year, month, day).isoformat(), False

        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", text):
            first, second, year = (int(p) for p in text.split("/"))
            if first > 12:          # must be dd/mm
                return date(year, second, first).isoformat(), False
            if second > 12:         # must be mm/dd
                return date(year, first, second).isoformat(), False
            # Both parts could be a month: assume dd/mm, mark ambiguous.
            return date(year, second, first).isoformat(), True

        match = re.fullmatch(r"(\d{1,2})[ -]([A-Za-z]{3,9})[ -](\d{4})", text)
        if match:
            month = MONTHS.get(match.group(2)[:3].lower())
            if month:
                return date(int(match.group(3)), month, int(match.group(1))).isoformat(), False
    except ValueError:
        # For example 31/02/2026: looks like a date but is not one.
        pass
    return None, False


def date_result(raw, found_with_label):
    """Build a FieldResult for a raw date string."""
    if raw is None:
        return not_found()
    iso, ambiguous = parse_date(raw)
    if iso is None:
        return not_found()
    if found_with_label and not ambiguous:
        return found_by_label(iso)
    result = found_by_fallback(iso)
    if found_with_label:
        result.source = "label_ambiguous_date"
    return result


def amount_field(text, labels):
    """Shared logic for subtotal, tax and total: label match only.

    There is no fallback for money. Picking "the biggest number on the
    page" would be a guess, and a wrong total is worse than a missing one.
    """
    raw = find_after_label(text, labels, CURRENCY_PREFIX + "(?:" + AMOUNT + ")")
    if raw is None:
        return not_found()
    number = re.search(AMOUNT, raw)
    return found_by_label(parse_amount(number.group(0)))


# ---------------------------------------------------------------------------
# One function per field
# ---------------------------------------------------------------------------

VENDOR_LABELS = [r"From", r"Supplier", r"Vendor", r"Merchant", r"Seller"]


def extract_vendor(pdf):
    """Vendor name: after a From/Supplier/Merchant label, else the letterhead."""
    for label in VENDOR_LABELS:
        pattern = SEGMENT_START + label + r"[ \t]*:[ \t]*(\S.*?)(?=[ \t]{2,}|[ \t]*$)"
        match = re.search(pattern, pdf.layout_text, re.IGNORECASE | re.MULTILINE)
        if match:
            return found_by_label(match.group(1).strip())

    # Fallback: the first line of plain text that is not a generic heading.
    # Plain text is used here because big letterhead fonts get extra
    # spaces in layout mode.
    for line in pdf.text.splitlines():
        line = line.strip()
        if line and line.lower() not in GENERIC_HEADINGS and re.search(r"[A-Za-z]{3}", line):
            return found_by_fallback(line)
    return not_found()


INVOICE_NUMBER_LABELS = [
    r"Invoice[ \t]*(?:No\.?|Number|#)",
    r"Inv\.?[ \t]*No\.?",
    r"Bill[ \t]*No\.?",
]
# Letters/digits with - or /, and at least one digit.
INVOICE_NUMBER_VALUE = r"[A-Z0-9][A-Z0-9/\-]*\d[A-Z0-9/\-]*"


def extract_invoice_number(pdf):
    raw = find_after_label(pdf.layout_text, INVOICE_NUMBER_LABELS, INVOICE_NUMBER_VALUE)
    if raw:
        return found_by_label(raw)
    # Fallback: something shaped like ABC-1234 or AB/2026/12.
    match = re.search(r"\b[A-Z]{2,4}[-/]\d[A-Z0-9/\-]*\b", pdf.layout_text)
    if match:
        return found_by_fallback(match.group(0))
    return not_found()


INVOICE_DATE_LABELS = [
    r"Invoice[ \t]+Date", r"Date[ \t]+of[ \t]+Issue", r"Issue[ \t]+Date",
    r"Dated", r"Issued", r"Date",
]


def extract_invoice_date(pdf):
    raw = find_after_label(pdf.layout_text, INVOICE_DATE_LABELS, DATE)
    if raw:
        return date_result(raw, found_with_label=True)
    # Fallback: the first date anywhere on the page.
    match = re.search(DATE, pdf.layout_text)
    return date_result(match.group(0) if match else None, found_with_label=False)


DUE_DATE_LABELS = [
    r"Due[ \t]+Date", r"Payment[ \t]+Due", r"Payable[ \t]+by", r"Due[ \t]+by", r"Due",
]


def extract_due_date(pdf):
    """Due date: label match only.

    No fallback, because "the second date on the page" could be anything
    (a delivery date, an order date) and a wrong due date is misleading.
    """
    raw = find_after_label(pdf.layout_text, DUE_DATE_LABELS, DATE)
    return date_result(raw, found_with_label=True)


def extract_currency(pdf):
    raw = find_after_label(pdf.layout_text, [r"Currency"], r"[A-Z]{3}")
    if raw and raw.upper() in KNOWN_CURRENCIES:
        return found_by_label(raw.upper())
    # Fallback: the first known currency code or symbol on the page.
    match = re.search(r"\b(" + "|".join(KNOWN_CURRENCIES) + r")\b", pdf.layout_text)
    if match:
        return found_by_fallback(match.group(1))
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in pdf.layout_text:
            return found_by_fallback(code)
    return not_found()


SUBTOTAL_LABELS = [r"Sub[ -]?total"]
TAX_RATE = r"(?:[ \t]*\(?\d+(?:\.\d+)?[ \t]*%\)?)?"
TAX_LABELS = [r"Sales[ \t]+Tax" + TAX_RATE, r"Tax" + TAX_RATE,
              r"VAT" + TAX_RATE, r"GST" + TAX_RATE]
TOTAL_LABELS = [r"Grand[ \t]+Total", r"Total[ \t]+Due", r"Amount[ \t]+Due", r"Total"]


def extract_subtotal(pdf):
    return amount_field(pdf.layout_text, SUBTOTAL_LABELS)


def extract_tax(pdf):
    return amount_field(pdf.layout_text, TAX_LABELS)


def extract_total(pdf):
    return amount_field(pdf.layout_text, TOTAL_LABELS)


# --- line items -------------------------------------------------------------

def find_column(header, words):
    """Index of the first header cell containing any of the words, else None."""
    for index, cell in enumerate(header):
        cell_text = (cell or "").lower()
        if any(word in cell_text for word in words):
            return index
    return None


def items_from_tables(tables):
    """Line items from a ruled table whose header names the columns."""
    for table in tables:
        if not table:
            continue
        header = table[0]
        desc_col = find_column(header, ["description", "item"])
        qty_col = find_column(header, ["qty", "quantity"])
        unit_col = find_column(header, ["unit", "price", "rate"])
        amount_col = find_column(header, ["amount", "line total"])
        if None in (desc_col, qty_col, unit_col, amount_col):
            continue
        items = []
        for row in table[1:]:
            item = make_line_item(row[desc_col], row[qty_col], row[unit_col], row[amount_col])
            if item:
                items.append(item)
        if items:
            return items
    return []


def make_line_item(description, qty, unit_price, amount):
    """Build a LineItem, or None if any part does not parse."""
    qty_text = (qty or "").strip()
    unit = parse_amount(unit_price)
    total = parse_amount(amount)
    if not description or not qty_text.isdigit() or unit is None or total is None:
        return None
    return LineItem(description.strip(), int(qty_text), unit, total)


TEXT_ROW = re.compile(
    r"^[ \t]*(\S.*?)[ \t]{2,}(\d+)[ \t]{2,}(" + AMOUNT + r")[ \t]{2,}(" + AMOUNT + r")[ \t]*$",
    re.MULTILINE,
)
RECEIPT_ROW = re.compile(
    r"^[ \t]*(\d+)[ \t]*x[ \t]+(\S.*?)[ \t]*\n[ \t]*@[ \t]*(" + AMOUNT + r")[ \t]*=[ \t]*(" + AMOUNT + r")",
    re.MULTILINE | re.IGNORECASE,
)
TEXT_HEADER = re.compile(r"Description.*Qty.*Amount", re.IGNORECASE)


def items_from_text_columns(layout_text):
    """Line items from an unruled table: a header line, then column rows."""
    header = TEXT_HEADER.search(layout_text)
    if not header:
        return []
    rows = TEXT_ROW.findall(layout_text[header.end():])
    items = [make_line_item(*row) for row in rows]
    return [item for item in items if item]


def items_from_receipt(layout_text):
    """Receipt rows: '12 x Notebook A5' then '@ 150.00 = 1,800.00'."""
    items = []
    for qty, description, unit, amount in RECEIPT_ROW.findall(layout_text):
        item = make_line_item(description, qty, unit, amount)
        if item:
            items.append(item)
    return items


def extract_line_items(pdf):
    """Line items as a list of dicts.

    1.0 when a header row (Description / Qty / Amount) was found, either
    as a ruled table or as a text header. 0.6 for receipt-style rows that
    only match a pattern. An empty list means none were found.
    """
    items = items_from_tables(pdf.tables)
    if items:
        return found_by_label([asdict(i) for i in items])
    items = items_from_text_columns(pdf.layout_text)
    if items:
        return found_by_label([asdict(i) for i in items])
    items = items_from_receipt(pdf.layout_text)
    if items:
        return found_by_fallback([asdict(i) for i in items])
    return FieldResult([], NOT_FOUND_CONFIDENCE, "not_found")


# ---------------------------------------------------------------------------

FIELD_EXTRACTORS = {
    "vendor": extract_vendor,
    "invoice_number": extract_invoice_number,
    "invoice_date": extract_invoice_date,
    "due_date": extract_due_date,
    "currency": extract_currency,
    "line_items": extract_line_items,
    "subtotal": extract_subtotal,
    "tax": extract_tax,
    "total": extract_total,
}

FIELD_NAMES = list(FIELD_EXTRACTORS)


def extract_fields(pdf):
    """Run every field extractor. Returns {field_name: FieldResult}."""
    return {name: extractor(pdf) for name, extractor in FIELD_EXTRACTORS.items()}
