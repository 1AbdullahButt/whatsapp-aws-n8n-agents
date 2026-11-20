"""Copy the workflow's results to Airtable (milestone B3).

    .venv\\Scripts\\python scripts\\sync_airtable.py --dry-run   build the rows, print counts, no calls
    .venv\\Scripts\\python scripts\\sync_airtable.py             check the schema, then upsert

Reads what the n8n run left behind:
    data/outcomes.jsonl   files that stopped early (paid, not overdue, duplicate, needs review)
    data/review.db        reminder drafts and their approve/reject status
    data/errors.jsonl     failures reported by the error workflow
and re-runs the (local, free) extractor on each PDF in inbox/ for the field values.

Rows are upserted on a key field, so running this twice does not create duplicates.
The number of Airtable API calls is printed at the end (free plan: 1,000 per month).
"""
import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR.parent))   # for shared/

from shared.config import load_env, require              # noqa: E402
from airtable_sync import mapping                        # noqa: E402
from airtable_sync.client import AirtableClient          # noqa: E402
from extractor.pipeline import extract_invoice           # noqa: E402
from extractor.records import read_jsonl                 # noqa: E402
from extractor.review_queue import ReviewQueue           # noqa: E402


def build_rows(data_dir, pdf_dir):
    """Return {table: [rows]} from the local workflow records."""
    outcomes = {o["file_id"]: o for o in read_jsonl(data_dir / "outcomes.jsonl")}
    drafts = ReviewQueue(data_dir / "review.db").list()
    drafts_by_file = {d["file_id"]: d for d in drafts}
    errors = read_jsonl(data_dir / "errors.jsonl")

    invoice_rows = []
    for file_id in sorted(set(outcomes) | set(drafts_by_file)):
        pdf = pdf_dir / file_id
        if not pdf.exists():
            print(f"skip {file_id}: not found in {pdf_dir}")
            continue
        extraction = extract_invoice(pdf, file_id)
        invoice_rows.append(mapping.invoice_row(
            file_id, extraction, outcomes.get(file_id), drafts_by_file.get(file_id)))

    return {
        mapping.INVOICES: invoice_rows,
        mapping.DRAFTS: [mapping.draft_row(d) for d in drafts],
        mapping.ERRORS: [mapping.error_row(e) for e in errors],
    }


def sync(client, rows):
    """Check the base schema (1 call), then upsert every table. Returns a summary dict."""
    problems = mapping.schema_problems(client.table_fields())
    if problems:
        raise SystemExit("Airtable base does not match docs/AIRTABLE_SCHEMA.md:\n  "
                         + "\n  ".join(problems))
    summary = {}
    for table, table_rows in rows.items():
        if table_rows:
            summary[table] = client.upsert(table, table_rows, mapping.KEY_FIELDS[table])
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Copy workflow results to Airtable")
    parser.add_argument("--dry-run", action="store_true", help="build rows only, no API calls")
    parser.add_argument("--data-dir", default=str(PROJECT_DIR / "data"))
    parser.add_argument("--pdf-dir", default=str(PROJECT_DIR / "inbox"))
    args = parser.parse_args(argv)

    rows = build_rows(Path(args.data_dir), Path(args.pdf_dir))
    for table, table_rows in rows.items():
        print(f"{table}: {len(table_rows)} rows")
    if args.dry_run:
        print("Dry run: no Airtable calls made.")
        return 0

    load_env(PROJECT_DIR / ".env")
    client = AirtableClient(require("AIRTABLE_TOKEN").strip(), require("AIRTABLE_BASE_ID").strip())
    for table, (created, updated) in sync(client, rows).items():
        print(f"{table}: {created} created, {updated} updated")
    print(f"Airtable API calls used this run: {client.calls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
