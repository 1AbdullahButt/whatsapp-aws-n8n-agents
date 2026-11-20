"""Read text and tables out of a PDF with pdfplumber.

No OCR is done here. If a PDF has no text layer (for example a scan or a
picture of an invoice), we say so with has_text_layer=False instead of
trying to guess what the picture says.
"""
from dataclasses import dataclass, field

import pdfplumber

# Fewer real characters than this across all pages counts as "no text layer".
MIN_TEXT_CHARS = 10


@dataclass
class PdfText:
    """Everything the field extractors need from one PDF."""
    text: str = ""            # plain reading-order text
    layout_text: str = ""     # text with spacing kept, so columns stay apart
    tables: list = field(default_factory=list)   # list of tables, each a list of rows
    page_count: int = 0
    has_text_layer: bool = False


def read_pdf(source):
    """Open a PDF (a path or a binary file object) and pull out its text.

    pdfplumber accepts both a file path and a file-like object, so the API
    can pass uploaded bytes without saving them to disk first.
    """
    result = PdfText()
    plain_pages, layout_pages = [], []
    with pdfplumber.open(source) as pdf:
        result.page_count = len(pdf.pages)
        for page in pdf.pages:
            plain_pages.append(page.extract_text() or "")
            layout_pages.append(page.extract_text(layout=True) or "")
            result.tables.extend(page.extract_tables())
    result.text = "\n".join(plain_pages)
    result.layout_text = "\n".join(layout_pages)
    result.has_text_layer = count_visible_chars(result.text) >= MIN_TEXT_CHARS
    return result


def count_visible_chars(text):
    """Count characters that are not spaces or newlines."""
    return sum(1 for ch in text if not ch.isspace())
