"""Glue: PDF in, fields + confidences + flags out.

Used by the API and by scripts/accuracy_report.py so both run the exact
same steps.
"""
from extractor.fields import FIELD_NAMES, FieldResult, extract_fields
from extractor.pdf_text import read_pdf
from extractor.validate import validate


def empty_results():
    """Every field as 'not found'. Used when the PDF has no text layer."""
    results = {name: FieldResult() for name in FIELD_NAMES}
    results["line_items"] = FieldResult(value=[])
    return results


def extract_invoice(source, file_id):
    """Extract and validate one PDF.

    source is a file path or a binary file object.
    Returns a plain dict that can be sent as JSON.
    """
    pdf = read_pdf(source)
    if pdf.has_text_layer:
        results = extract_fields(pdf)
    else:
        results = empty_results()
    check = validate(results, has_text_layer=pdf.has_text_layer)
    return {
        "file_id": file_id,
        "fields": {name: r.value for name, r in results.items()},
        "confidences": {name: r.confidence for name, r in results.items()},
        "flags": check.flags,
        "needs_review": check.needs_review,
    }
