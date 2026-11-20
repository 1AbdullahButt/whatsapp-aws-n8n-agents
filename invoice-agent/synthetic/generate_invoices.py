"""Generate 12 synthetic invoice PDFs and an expected.json answer key.

All companies, numbers and amounts are made up. Nothing here is a real invoice.

Run from the invoice-agent folder:
    .venv\\Scripts\\python synthetic\\generate_invoices.py

The output is deterministic: there is no randomness, and reportlab runs in
"invariant" mode so it does not stamp the current time into the PDF.

Four layouts are used so the extractor cannot rely on one template:
    classic   - "INVOICE" header, labelled fields, ruled table
    twocol    - supplier block on the left, invoice details on the right
    labelright - letterhead vendor name, "Inv No." style labels on the right,
                 plain text table without ruled lines
    receipt   - narrow till-receipt style, "2 x item @ price = amount" lines
"""
import io
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "invoices"
EXPECTED_FILE = HERE / "expected.json"

CENT = Decimal("0.01")


# ---------------------------------------------------------------------------
# Invoice data
# ---------------------------------------------------------------------------

def money(value):
    """Round a Decimal to 2 places the way an invoice would."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value):
    """Format a Decimal as 1,234.50."""
    return f"{value:,.2f}"


def make_invoice(file_name, layout, vendor, number, date_text, date_iso,
                 due_text, due_iso, currency, items, tax_rate, tax_label):
    """Build one invoice dict and work out subtotal, tax and total."""
    lines = []
    for description, qty, unit_price in items:
        unit = money(unit_price)
        lines.append({
            "description": description,
            "qty": qty,
            "unit_price": unit,
            "amount": money(unit * qty),
        })
    subtotal = money(sum(line["amount"] for line in lines))
    tax = money(subtotal * Decimal(tax_rate) / 100)
    return {
        "file": file_name,
        "layout": layout,
        "vendor": vendor,
        "invoice_number": number,
        "date_text": date_text,
        "invoice_date": date_iso,
        "due_text": due_text,
        "due_date": due_iso,
        "currency": currency,
        "line_items": lines,
        "tax_label": tax_label,
        "subtotal": subtotal,
        "tax": tax,
        "total": subtotal + tax,
    }


def build_invoices():
    """Return the list of invoices to draw, in file order."""
    inv = []
    inv.append(make_invoice(
        "inv_01_classic_usd.pdf", "classic", "Bluefinch Paper Supplies LLC",
        "INV-2026-0141", "2026-10-03", "2026-10-03", "2026-11-02", "2026-11-02",
        "USD",
        [("A4 copy paper (box)", 10, "24.50"),
         ("Heavy duty stapler", 2, "18.75"),
         ("Ballpoint pens (pack of 50)", 4, "12.20")],
        8, "Tax (8%)"))
    inv.append(make_invoice(
        "inv_02_twocol_eur.pdf", "twocol", "Kestrel Office Goods GmbH",
        "KOG-77812", "03/10/2026", "2026-10-03", "02/11/2026", "2026-11-02",
        "EUR",
        [("Ergonomic desk chair", 3, "189.00"),
         ("Monitor arm", 3, "64.90")],
        19, "VAT 19%"))
    inv.append(make_invoice(
        "inv_03_labelright_gbp.pdf", "labelright", "Harbourline Print Ltd",
        "HP/2026/0093", "3 Oct 2026", "2026-10-03", "2 Nov 2026", "2026-11-02",
        "GBP",
        [("Business cards (500)", 6, "35.00"),
         ("A2 posters", 20, "6.50"),
         ("Design proof", 1, "45.00")],
        20, "VAT (20%)"))
    inv.append(make_invoice(
        "inv_04_receipt_pkr.pdf", "receipt", "Shalimar Stationers (Pvt) Ltd",
        "SS-5521", "15 Oct 2026", "2026-10-15", "28/10/2026", "2026-10-28",
        "PKR",
        [("Notebook A5", 12, "150.00"),
         ("Gel pen blue", 24, "45.00"),
         ("Box file", 5, "320.00")],
        18, "GST 18%"))
    inv.append(make_invoice(
        "inv_05_classic_eur.pdf", "classic", "Vellum and Quill Supplies SARL",
        "VQ-2026-0207", "21/10/2026", "2026-10-21", "20/11/2026", "2026-11-20",
        "EUR",
        [("Fountain pen ink (set)", 8, "14.25"),
         ("Letter paper ream", 15, "9.80")],
        20, "Tax (20%)"))
    inv.append(make_invoice(
        "inv_06_twocol_usd.pdf", "twocol", "Copperleaf IT Services Inc",
        "CIT-3009", "7 Nov 2026", "2026-11-07", "7 Dec 2026", "2026-12-07",
        "USD",
        [("Laptop setup (hours)", 6, "85.00"),
         ("USB-C docking station", 2, "149.99"),
         ("Network cable 5m", 10, "7.45")],
        0, "Tax 0%"))
    inv.append(make_invoice(
        "inv_07_labelright_pkr.pdf", "labelright", "Margalla Packaging Co",
        "MP-0456", "2026-10-12", "2026-10-12", "2026-11-11", "2026-11-11",
        "PKR",
        [("Corrugated boxes (large)", 200, "85.00"),
         ("Packing tape roll", 40, "120.00")],
        17, "GST (17%)"))
    inv.append(make_invoice(
        "inv_08_receipt_gbp.pdf", "receipt", "Thistle Catering Supplies Ltd",
        "TCS-1180", "05/11/2026", "2026-11-05", "19/11/2026", "2026-11-19",
        "GBP",
        [("Paper cups (100)", 6, "4.80"),
         ("Napkins (500)", 3, "7.25"),
         ("Coffee beans 1kg", 2, "18.90")],
        20, "VAT 20%"))

    # 09: the same invoice as 01 sent again under a new file name.
    duplicate = dict(inv[0])
    duplicate["file"] = "inv_09_resent_copy.pdf"
    inv.append(duplicate)

    # 10: no due date anywhere on the page.
    inv.append(make_invoice(
        "inv_10_no_due_date.pdf", "twocol", "Larkspur Design Studio Ltd",
        "LDS-1102", "2026-11-01", "2026-11-01", None, None,
        "GBP",
        [("Logo refresh", 1, "650.00"),
         ("Brand guide pages", 12, "40.00")],
        20, "VAT 20%"))

    # 11: malformed. The table is cut off and the total is garbled.
    inv.append(make_invoice(
        "inv_11_malformed.pdf", "malformed", "Pinewood Janitorial Supplies LLC",
        "INV-2026-0388", "2026-10-20", "2026-10-20", "2026-11-19", "2026-11-19",
        "USD",
        [("Floor cleaner 5L", 4, "22.00"),
         ("Microfibre cloths (20)", 3, "15.50")],
        8, "Tax (8%)"))

    # 12: image only. The page is a picture of text, with no text layer.
    inv.append(make_invoice(
        "inv_12_image_only.pdf", "image", "Ostler Lane Hardware Ltd",
        "OLH-0712", "2026-10-28", "2026-10-28", "2026-11-27", "2026-11-27",
        "GBP",
        [("Hinge set", 10, "3.40"),
         ("Wood screws (box)", 5, "6.10")],
        20, "VAT 20%"))
    return inv


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def draw_ruled_table(c, left, top, col_x, rows, row_h=8 * mm):
    """Draw a table with full grid lines so pdfplumber can find it.

    col_x is the list of column boundaries (one more than the columns).
    The first row is the header.
    """
    c.setLineWidth(0.6)
    y = top
    for row_index, row in enumerate(rows):
        font = "Helvetica-Bold" if row_index == 0 else "Helvetica"
        c.setFont(font, 10)
        for col, text in enumerate(row):
            if col == 0:
                c.drawString(col_x[col] + 2 * mm, y - row_h + 2.6 * mm, text)
            else:
                c.drawRightString(col_x[col + 1] - 2 * mm, y - row_h + 2.6 * mm, text)
        y -= row_h
    # Horizontal lines
    for i in range(len(rows) + 1):
        line_y = top - i * row_h
        c.line(col_x[0], line_y, col_x[-1], line_y)
    # Vertical lines
    for x in col_x:
        c.line(x, top, x, top - len(rows) * row_h)
    return top - len(rows) * row_h


def item_rows(inv):
    """Table rows (header first) as strings."""
    rows = [["Description", "Qty", "Unit Price", "Amount"]]
    for line in inv["line_items"]:
        rows.append([line["description"], str(line["qty"]),
                     fmt(line["unit_price"]), fmt(line["amount"])])
    return rows


def draw_totals(c, label_x, value_x, y, pairs, size=10):
    """Draw label / right-aligned value pairs going down the page."""
    for label, value in pairs:
        c.setFont("Helvetica-Bold" if "Total" in label or "Due" in label else "Helvetica", size)
        c.drawString(label_x, y, label)
        c.drawRightString(value_x, y, value)
        y -= 6 * mm
    return y


# ---------------------------------------------------------------------------
# Layouts
# ---------------------------------------------------------------------------

def draw_classic(c, inv):
    """Layout 1: title, labelled fields down the left, ruled table."""
    width, height = A4
    c.setFont("Helvetica-Bold", 22)
    c.drawString(20 * mm, height - 25 * mm, "INVOICE")
    c.setFont("Helvetica", 10)
    y = height - 40 * mm
    fields = [
        ("From:", inv["vendor"]),
        ("Invoice No:", inv["invoice_number"]),
        ("Invoice Date:", inv["date_text"]),
    ]
    if inv["due_text"]:
        fields.append(("Due Date:", inv["due_text"]))
    fields.append(("Currency:", inv["currency"]))
    for label, value in fields:
        c.drawString(20 * mm, y, label)
        c.drawString(55 * mm, y, value)
        y -= 6 * mm
    c.drawString(20 * mm, y, "Bill To:")
    c.drawString(55 * mm, y, "Example Trading Co, 1 Sample Street")
    col_x = [20 * mm, 110 * mm, 130 * mm, 160 * mm, 190 * mm]
    bottom = draw_ruled_table(c, 20 * mm, y - 10 * mm, col_x, item_rows(inv))
    draw_totals(c, 130 * mm, 190 * mm, bottom - 10 * mm, [
        ("Subtotal:", fmt(inv["subtotal"])),
        (inv["tax_label"] + ":", fmt(inv["tax"])),
        ("Total:", f"{inv['currency']} {fmt(inv['total'])}"),
    ])


def draw_twocol(c, inv):
    """Layout 2: supplier on the left, invoice details on the right."""
    width, height = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, height - 22 * mm, "Tax Invoice")
    c.setFont("Helvetica", 10)
    left = [
        f"Supplier: {inv['vendor']}",
        "Unit 4, Fictional Business Park",
        "Sampletown",
    ]
    right = [
        f"Invoice Number: {inv['invoice_number']}",
        f"Date: {inv['date_text']}",
    ]
    if inv["due_text"]:
        right.append(f"Due Date: {inv['due_text']}")
    right.append(f"Currency: {inv['currency']}")
    y = height - 38 * mm
    for i in range(max(len(left), len(right))):
        if i < len(left):
            c.drawString(20 * mm, y, left[i])
        if i < len(right):
            c.drawString(120 * mm, y, right[i])
        y -= 6 * mm
    col_x = [20 * mm, 110 * mm, 130 * mm, 160 * mm, 190 * mm]
    bottom = draw_ruled_table(c, 20 * mm, y - 10 * mm, col_x, item_rows(inv))
    draw_totals(c, 130 * mm, 190 * mm, bottom - 10 * mm, [
        ("Subtotal", fmt(inv["subtotal"])),
        (inv["tax_label"], fmt(inv["tax"])),
        ("Amount Due", fmt(inv["total"])),
    ])


def draw_labelright(c, inv):
    """Layout 3: letterhead, short labels on the right, unruled table."""
    width, height = A4
    c.setFont("Helvetica-Bold", 20)
    c.drawString(20 * mm, height - 25 * mm, inv["vendor"])
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, height - 31 * mm, "22 Imaginary Quay, Nowhere Bay")
    c.setFont("Helvetica", 10)
    y = height - 48 * mm
    block = [f"Inv No. {inv['invoice_number']}", f"Dated {inv['date_text']}"]
    if inv["due_text"]:
        block.append(f"Payable by {inv['due_text']}")
    for text in block:
        c.drawRightString(190 * mm, y, text)
        y -= 6 * mm
    y -= 8 * mm
    # Plain table: no ruled lines, columns set by x position only.
    cols = [20 * mm, 120 * mm, 150 * mm, 190 * mm]
    c.setFont("Helvetica-Bold", 10)
    c.drawString(cols[0], y, "Description")
    c.drawRightString(cols[1], y, "Qty")
    c.drawRightString(cols[2], y, "Unit Price")
    c.drawRightString(cols[3], y, "Amount")
    c.setFont("Helvetica", 10)
    for line in inv["line_items"]:
        y -= 6 * mm
        c.drawString(cols[0], y, line["description"])
        c.drawRightString(cols[1], y, str(line["qty"]))
        c.drawRightString(cols[2], y, fmt(line["unit_price"]))
        c.drawRightString(cols[3], y, fmt(line["amount"]))
    cur = inv["currency"]
    draw_totals(c, 120 * mm, 190 * mm, y - 14 * mm, [
        ("Subtotal", f"{cur} {fmt(inv['subtotal'])}"),
        (inv["tax_label"], f"{cur} {fmt(inv['tax'])}"),
        ("Total Due", f"{cur} {fmt(inv['total'])}"),
    ])


RECEIPT_SIZE = (80 * mm, 200 * mm)


def draw_receipt(c, inv):
    """Layout 4: narrow receipt, everything stacked, compact lines."""
    width, height = RECEIPT_SIZE
    c.setFont("Courier-Bold", 10)
    c.drawCentredString(width / 2, height - 12 * mm, "RECEIPT / INVOICE")
    c.setFont("Courier", 7.5)
    y = height - 22 * mm
    header = [
        f"Merchant: {inv['vendor']}",
        f"Invoice #: {inv['invoice_number']}",
        f"Date: {inv['date_text']}",
    ]
    if inv["due_text"]:
        header.append(f"Due: {inv['due_text']}")
    header.append(f"Currency: {inv['currency']}")
    for text in header:
        c.drawString(4 * mm, y, text)
        y -= 4.5 * mm
    c.drawString(4 * mm, y, "-" * 40)
    for line in inv["line_items"]:
        y -= 4.5 * mm
        c.drawString(4 * mm, y, f"{line['qty']} x {line['description']}")
        y -= 4.5 * mm
        c.drawRightString(width - 4 * mm, y,
                          f"@ {fmt(line['unit_price'])} = {fmt(line['amount'])}")
    y -= 4.5 * mm
    c.drawString(4 * mm, y, "-" * 40)
    for label, value in [("SUBTOTAL", inv["subtotal"]),
                         (inv["tax_label"].upper(), inv["tax"]),
                         ("TOTAL", inv["total"])]:
        y -= 4.5 * mm
        c.drawString(4 * mm, y, label)
        c.drawRightString(width - 4 * mm, y, fmt(value))
    c.drawCentredString(width / 2, y - 10 * mm, "Thank you")


def draw_malformed(c, inv):
    """Malformed: like classic, but the table is cut off and the total garbled.

    There is no subtotal or tax line, and the total cannot be read.
    """
    width, height = A4
    c.setFont("Helvetica-Bold", 22)
    c.drawString(20 * mm, height - 25 * mm, "INVOICE")
    c.setFont("Helvetica", 10)
    y = height - 40 * mm
    for label, value in [("From:", inv["vendor"]),
                         ("Invoice No:", inv["invoice_number"]),
                         ("Invoice Date:", inv["date_text"]),
                         ("Due Date:", inv["due_text"]),
                         ("Currency:", inv["currency"])]:
        c.drawString(20 * mm, y, label)
        c.drawString(55 * mm, y, value)
        y -= 6 * mm
    col_x = [20 * mm, 110 * mm, 130 * mm, 160 * mm, 190 * mm]
    bottom = draw_ruled_table(c, 20 * mm, y - 10 * mm, col_x, item_rows(inv))
    # A third row that was cut off mid-print.
    c.drawString(22 * mm, bottom - 6 * mm, "Toner cartrid")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(130 * mm, bottom - 20 * mm, "Total:")
    c.drawRightString(190 * mm, bottom - 20 * mm, "USD ##.#?")


def image_font(size):
    """Pillow's built-in scalable font, so no font file is needed."""
    return ImageFont.load_default(size=size)


def draw_image_only(c, inv):
    """Image only: draw the invoice into a picture, then place the picture.

    The PDF has no text layer at all, like a scan without OCR.
    """
    img = Image.new("L", (1240, 1754), color=255)
    draw = ImageDraw.Draw(img)
    big, normal = image_font(48), image_font(26)
    draw.text((100, 100), "INVOICE", font=big, fill=0)
    lines = [
        f"From: {inv['vendor']}",
        f"Invoice No: {inv['invoice_number']}",
        f"Invoice Date: {inv['date_text']}",
        f"Due Date: {inv['due_text']}",
        f"Currency: {inv['currency']}",
        "",
        "Description            Qty   Unit Price   Amount",
    ]
    for line in inv["line_items"]:
        lines.append(f"{line['description']:<22} {line['qty']:>3}   "
                     f"{fmt(line['unit_price']):>10}   {fmt(line['amount']):>8}")
    lines += ["",
              f"Subtotal: {fmt(inv['subtotal'])}",
              f"{inv['tax_label']}: {fmt(inv['tax'])}",
              f"Total: {inv['currency']} {fmt(inv['total'])}"]
    y = 220
    for line in lines:
        draw.text((100, y), line, font=normal, fill=0)
        y += 44
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    width, height = A4
    c.drawImage(ImageReader(buffer), 0, 0, width=width, height=height)


DRAWERS = {
    "classic": draw_classic,
    "twocol": draw_twocol,
    "labelright": draw_labelright,
    "receipt": draw_receipt,
    "malformed": draw_malformed,
    "image": draw_image_only,
}


def write_pdf(inv):
    """Draw one invoice to synthetic/invoices/<file>."""
    page_size = RECEIPT_SIZE if inv["layout"] == "receipt" else A4
    path = OUT_DIR / inv["file"]
    # invariant=1 keeps dates and IDs fixed so reruns give the same file.
    c = canvas.Canvas(str(path), pagesize=page_size, invariant=1)
    c.setTitle(f"Synthetic invoice {inv['invoice_number']}")
    c.setAuthor("invoice-agent synthetic generator")
    DRAWERS[inv["layout"]](c, inv)
    c.showPage()
    c.save()


# ---------------------------------------------------------------------------
# Answer key
# ---------------------------------------------------------------------------

def expected_entry(inv, duplicate_of=None):
    """The true values a careful human would read from the page."""
    fields = {
        "vendor": inv["vendor"],
        "invoice_number": inv["invoice_number"],
        "invoice_date": inv["invoice_date"],
        "due_date": inv["due_date"],
        "currency": inv["currency"],
        "line_items": [
            {"description": l["description"], "qty": l["qty"],
             "unit_price": float(l["unit_price"]), "amount": float(l["amount"])}
            for l in inv["line_items"]
        ],
        "subtotal": float(inv["subtotal"]),
        "tax": float(inv["tax"]),
        "total": float(inv["total"]),
    }
    flags = []
    note = ""
    if inv["due_date"] is None:
        flags.append("missing_due_date")
    if inv["layout"] == "malformed":
        # Subtotal and tax were never printed, and the total is unreadable,
        # so the honest answer for these fields is "unknown".
        fields["subtotal"] = None
        fields["tax"] = None
        fields["total"] = None
        flags += ["missing_subtotal", "missing_tax", "missing_total"]
        note = "Table cut off after two rows; total printed as '##.#?'."
    if inv["layout"] == "image":
        flags.append("no_text_layer")
        note = "Rasterised page with no text layer. Values are what the picture shows."
    return {
        "layout": inv["layout"],
        "fields": fields,
        "expected_flags": flags,
        "duplicate_of": duplicate_of,
        "note": note,
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    invoices = build_invoices()
    expected = {}
    for inv in invoices:
        write_pdf(inv)
        dup = "inv_01_classic_usd.pdf" if inv["file"] == "inv_09_resent_copy.pdf" else None
        expected[inv["file"]] = expected_entry(inv, duplicate_of=dup)
    EXPECTED_FILE.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(invoices)} PDFs to {OUT_DIR}")
    print(f"Wrote answer key to {EXPECTED_FILE}")


if __name__ == "__main__":
    main()
