# Airtable schema for B3 (base "Invoice Agent")

Free plan limits that matter (checked 20 Nov 2026): 1,000 records per base, 1,000 API calls per
workspace per month. A full demo run writes about 30 records in batches of 10 (about 5 calls).
Tests use a fake client and make zero calls.

Create the base with **Create -> Start from scratch**, name it `Invoice Agent`. Decline any trial.
Create the three tables below. Names must match exactly (case and spaces), because the code
writes to them by name. The **first field in each table is its primary field**: rename the
default "Name" field instead of adding a new one. Delete Airtable's default extra fields
("Notes", "Assignee", "Status", "Attachments") if it adds them.

## Table 1: `Invoices`

One row per processed PDF.

| Field | Type | Notes |
|---|---|---|
| `File` | Single line text | primary field, e.g. `inv_01_classic_usd.pdf` |
| `Vendor` | Single line text | |
| `Invoice number` | Single line text | |
| `Invoice date` | Date (ISO format) | |
| `Due date` | Date (ISO format) | empty if not found |
| `Currency` | Single line text | USD, EUR, GBP, PKR |
| `Subtotal` | Number, 2 decimals | |
| `Tax` | Number, 2 decimals | |
| `Total` | Number, 2 decimals | |
| `Flags` | Long text | comma-separated, e.g. `low_confidence_due_date` |
| `Outcome` | Single select | options: `draft_created`, `paid`, `not_overdue`, `duplicate`, `needs_review` |
| `Payment status` | Single line text | from the mock accounting API |
| `Processed at` | Single line text | UTC ISO time |

## Table 2: `Reminder Drafts`

One row per reminder draft waiting for, or after, a human decision. Nothing is ever emailed.

| Field | Type | Notes |
|---|---|---|
| `Draft id` | Single line text | primary field, e.g. `draft-3` |
| `File` | Single line text | |
| `Vendor` | Single line text | |
| `Invoice number` | Single line text | |
| `Amount due` | Number, 2 decimals | |
| `Reminder text` | Long text | |
| `Status` | Single select | options: `pending`, `approved`, `rejected` |
| `Created at` | Single line text | |
| `Decided at` | Single line text | empty while pending |

## Table 3: `Error Log`

One row per failure reported by the n8n error workflow.

| Field | Type | Notes |
|---|---|---|
| `Received at` | Single line text | primary field, UTC ISO time |
| `Workflow` | Single line text | |
| `Node` | Single line text | |
| `Execution id` | Single line text | |
| `Message` | Long text | |

## Token (Step 3 in `docs/HUMAN_STEPS.md`)

Personal access token named `invoice-agent`, scopes `data.records:read`, `data.records:write`,
`schema.bases:read`, access limited to the `Invoice Agent` base only. Put it and the base id in
`invoice-agent/.env` (`AIRTABLE_TOKEN=`, `AIRTABLE_BASE_ID=`). Never paste them in chat.

With `schema.bases:read`, Claude first checks (read-only) that the tables and fields above exist
and have the right types before writing any record.
