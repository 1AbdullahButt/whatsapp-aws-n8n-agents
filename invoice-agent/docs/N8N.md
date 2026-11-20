# n8n workflow (milestone B2)

Everything runs on this computer in Docker. n8n calls two small local
Python services. No credentials are stored in n8n, nothing is emailed, and
the accounting data is a **MOCK** with fake records.

## What runs

`invoice-agent/docker-compose.yml`, compose project name `invoice-agent`:

| Service | Host address | What it is |
|---|---|---|
| `api` | http://localhost:8101 | extractor API + review queue (Python, `Dockerfile`) |
| `mock-accounting` | http://localhost:8102 | **MOCK** payment status, fake data |
| `n8n` | http://localhost:5690 | n8n `2.48.7` (pinned), volume `invoice_agent_n8n_data` |

Ports are bound to `127.0.0.1` only. Inside Docker the services call each
other by name (`http://api:8101`, `http://mock-accounting:8102`).

Folders mounted into `api`: `inbox/` (read-only), `data/` and `outbox/`.
`n8n/workflows/` is mounted read-only into n8n at `/workflows` for import.

n8n settings that matter (all in `docker-compose.yml`):
- `N8N_ENCRYPTION_KEY` comes from `invoice-agent/.env` (gitignored).
- Telemetry, version checks, personalisation, templates and banners are off.
- `WEBHOOK_URL=http://localhost:5690/` so resume URLs work from Windows.
- `REMINDER_TODAY=2026-11-20` makes "overdue" deterministic for the demo.
- `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`, because the workflow reads
  `$env.REMINDER_TODAY` and n8n 2.x blocks `$env` by default.

## The workflows

**Invoice intake** (`n8n/workflows/invoice_intake.json`, id `InvoiceIntake001`)

```
Webhook POST /webhook/invoice {"filename"}   (answers at once)
  -> Extract fields          POST api /extract {"path": filename}
  -> Check duplicate         POST api /check-duplicate
  -> Is duplicate?   yes -> Record duplicate      (POST api /outcomes)
  -> Needs review?   yes -> Record needs review   (POST api /outcomes)
  -> Get payment status (MOCK)   GET mock-accounting /invoices/{n}/payment-status
  -> Unpaid and overdue?  (unpaid/partial AND due_date < REMINDER_TODAY)
        no  -> Record no reminder  (POST api /outcomes)
        yes -> Create reminder draft  POST api /drafts (resume_url = $execution.resumeUrl)
               -> Wait for human approval (resumes on a POST to the resume URL)
               -> Record decision  POST api /drafts/{id}/decision
```

"Needs review?" uses `stop_for_review` from `/extract`: true when there
is a blocking flag (`missing_*`, `no_text_layer`, `totals_mismatch`,
`due_before_invoice_date`). Low-confidence flags do not stop the
workflow; they go with the draft to the human approver.

**Invoice errors** (`n8n/workflows/invoice_errors.json`, id
`InvoiceErrors001`): Error Trigger -> POST api `/errors` with workflow
name, node, message and execution id. The API appends to
`data/errors.jsonl` and overwrites `data/ALERT_LATEST.txt`. The intake
workflow points at it with `settings.errorWorkflow`.

## Start

```
cd invoice-agent
copy .env.example .env      # first time only, then put a random N8N_ENCRYPTION_KEY in .env
docker compose up -d --build
powershell -ExecutionPolicy Bypass -File scripts\n8n_setup.ps1
```

`n8n_setup.ps1` imports both workflows (`n8n import:workflow --separate
--input=/workflows`), publishes the intake workflow
(`n8n publish:workflow --id=InvoiceIntake001`; n8n 2.x replaced
`update:workflow --active=true` with this) and restarts n8n. Running it
again is safe: import overwrites by id.

## Open the n8n UI (human step)

Open http://localhost:5690. The first visit asks you to create an owner
account. This account is **local to this n8n container** (stored in the
`invoice_agent_n8n_data` volume); it is not an n8n cloud account. Pick any
email and password. The workflows run without this step.

## Run the invoices

```
.venv\Scripts\python scripts\run_inbox.py                 # copies the 12 PDFs to inbox\ and sends them
.venv\Scripts\python scripts\run_inbox.py inv_02_twocol_eur.pdf
```

## Review drafts

```
.venv\Scripts\python scripts\review.py list
.venv\Scripts\python scripts\review.py show 1
.venv\Scripts\python scripts\review.py approve 1
.venv\Scripts\python scripts\review.py reject 2
```

`approve` / `reject` POST `{"decision": ...}` to the draft's resume URL,
which wakes the paused n8n execution. Approved reminders are appended to
`outbox/approved_reminders.jsonl` with `"sent": false`. **Nothing is
emailed.**

## Force an error

```
.venv\Scripts\python scripts\run_inbox.py does_not_exist.pdf
type data\ALERT_LATEST.txt
```

`/extract` answers 404, the HTTP node fails, and n8n runs "Invoice errors".

## End-to-end check

```
.venv\Scripts\python scripts\e2e_n8n.py
```

It first calls `POST /demo/reset` (only enabled because
`DEMO_RESET_ENABLED=true` is set for `api` in `docker-compose.yml`), which
empties the review queue, the duplicate keys and the log files in `data\`
and `outbox\`. The reset runs inside the container on purpose: deleting
`review.db` from Windows made the next SQLite open in the container fail.
Then it sends all 12
invoices, checks drafts/duplicates/needs-review, approves one draft,
rejects one, forces an error, and prints PASS/FAIL per check. It is not
part of `pytest`.

## Export after editing in the UI

```
powershell -ExecutionPolicy Bypass -File scripts\n8n_export.ps1
```

Exports both workflows and runs `scripts\sanitize_workflow.py`, which
keeps only id, name, nodes, connections and settings, drops
`meta.instanceId`, pinData and any `credentials`, and refuses to save if
any of those words remain.

## Stop

```
docker compose down        # keeps the invoice_agent_n8n_data volume
```

Do not add `-v` unless you want to wipe this n8n (owner account,
executions). Never touch other n8n volumes on this machine.
