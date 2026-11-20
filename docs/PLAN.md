# Plan

Written 20 Nov 2026. Portfolio projects, not production systems. Synthetic data only.

## Goal

Two projects that show, with real tests, the skills clients keep asking for:
WhatsApp Cloud API agents, AWS serverless (Lambda, DynamoDB, S3, SQS, CloudWatch),
queues and retries, document extraction, n8n, Airtable, and RAG with a vector database.
Total cost must stay at $0. See `COST_CHECKLIST.md`.

## Free-tier findings that shaped the plan (checked 20 Nov 2026)

| Topic | Finding | Effect |
|---|---|---|
| AWS Textract / Transcribe | Paid plan only for new accounts | Not used. Extraction and transcription are local. |
| AWS Free plan | $100 credits (+ up to $100 from activities), 6 months, cannot bill; account is suspended at the end unless upgraded | Never upgrade. Finish A4 and B4 inside 6 months. |
| WhatsApp service messages | Since 1 Oct 2026: first 1,000 per number per month free, then charged (not delivered if no payment method). Utility templates in the window are charged. | No payment method on the WABA. Template path simulated in tests only. |
| Airtable Free | 1,000 records per base, 1,000 API calls per workspace per month | Fake client in tests, batched writes, call counter. |
| Tunnels | Cloudflare quick tunnel: free, no account, random URL | Used for A2/A3. |
| Gemini free tier | Cut several times, unstable | Optional LLM step off by default, may be skipped. |

## Project A: tenant-desk

A tenant messages a WhatsApp number (text or voice note). The desk opens one
ticket, replies with the ticket number, flags urgent issues, and hands over to
a human when staff take over.

```
WhatsApp -> Meta Cloud API -> webhook (FastAPI locally / Lambda function URL on AWS)
  1. GET  /webhook  verify-token challenge
  2. POST /webhook  check X-Hub-Signature-256 (HMAC-SHA256 of raw body with app secret), 401 if bad
  3. dedupe on WhatsApp message id (unique key in storage, survives restarts)
  4. voice note: download media via Graph API, store file, transcribe (faster-whisper)
  5. classify with keyword rules (category + urgency)
  6. open a ticket, or append to the tenant's open ticket
  7. reply: inside 24h window = free-form text; outside = template (simulated)
  8. ticket in "human" mode: store the message, send nothing
```

Main pieces: `signature.py`, `parser.py`, `classifier.py`, `service.py` (the steps
above, no framework code), `repository.py` interface with SQLite and DynamoDB
versions, `whatsapp_client.py` (real + fake), `transcriber.py` (real + fake),
`window.py`, `staff_cli.py`.

AWS leg (A4): Lambda function URL checks the signature and puts the event on SQS,
returns 200 quickly. A worker Lambda reads SQS, dedupes in DynamoDB, creates the
ticket and replies. 3 failed tries move a message to a dead-letter queue. Voice
notes go to S3. Transcribe is paid-only, so the cloud worker marks the ticket
`transcription_pending` and a local script transcribes and writes back. Secrets
in SSM Parameter Store (standard tier). Logs kept 7 days. Infrastructure in SAM.

## Project B: invoice-agent

PDF invoices arrive. The workflow extracts fields, flags duplicates, checks
payment status against a mock API, drafts a reminder, and waits for a human to
approve. Nothing is sent.

```
PDF -> n8n workflow
  -> extractor API /extract          pdfplumber + rules -> fields, confidence, flags
  -> extractor API /check-duplicate  vendor + invoice number + total
  -> MOCK accounting API             fake payment status (clearly labelled mock)
  -> unpaid and overdue -> reminder draft -> review queue (status = pending)
  -> Wait node, resumed by approval webhook -> approved -> written to an outbox log, not emailed
  -> any failure -> Error Workflow -> error log + alert file
```

Fields: vendor, invoice number, date, due date, currency, line items, total, tax.
Missing or low-confidence fields are flagged, never guessed.
12 synthetic PDFs in 4 layouts, including one duplicate, one malformed, one with
no due date, one image-only.

n8n: fresh docker-compose, its own volume `invoice_agent_n8n_data`, port 5690
(LendLoop's old instance is not reused). Exported workflow JSON is checked for
credentials before commit.

AWS leg (B4): S3 upload -> S3 event -> SQS (+DLQ) -> Lambda running the same
pdfplumber extractor -> DynamoDB. No Textract.

B5 (optional): Postgres + pgvector in Docker, local MiniLM embeddings, about 8
synthetic policy docs, about 20 test questions, hit rate@3 reported as measured.

## Shared

`/shared/config.py` (reads `.env`, fails loudly on missing keys) and
`/shared/logging_setup.py`. One git repo at the root, one venv per project,
Python 3.12 (`py -3.12`), pytest.

## Milestones

| # | Done means |
|---|---|
| Phase 1 | Repo, .gitignore, CLAUDE.md, docs, shared exist; first commit; no secrets tracked. |
| A1 | pytest green: signature good/bad, duplicate delivery, restart-then-duplicate, handoff keeps messages and sends nothing, urgent routing, 24h window, voice path with fake transcriber. Repository tests run against SQLite and moto DynamoDB. |
| B1 | pytest green: extraction matches expected values on clean invoices, malformed and missing-due-date flagged, duplicate caught. Per-field accuracy printed. |
| A2 | Abdullah sends a WhatsApp text from his phone to the Meta test number and gets a ticket number back. Evidence: server log + screenshot. |
| B2 | `docker compose up`, PDFs processed end to end, draft waits for approval, forced failure triggers the error workflow. Workflow JSON committed. |
| A3 | Voice note from the phone becomes a transcribed ticket; staff take over; bot goes quiet; history shows later messages. |
| B3 | Records appear in the Airtable base; API calls used reported. |
| A4 | Budget alert confirmed, resources listed, Abdullah says yes, deploy, real message handled by Lambda, a poison message shown in the DLQ, logs captured, teardown, empty-resources check. |
| B4 | Same gates. PDF in S3 produces a record in DynamoDB. Teardown. |
| A5 | Pilot guide; one real person tries it; README records what happened. |
| B5 | Optional. Hit rate reported as measured. |
| End | `docs/PORTFOLIO_SUMMARY.md`. |

Order: Phase 1 -> A1 + B1 in parallel -> A2 -> B2 -> A3 -> B3 -> A4 -> B4 -> A5 -> B5.

## Risks

- Meta setup friction (token expiry every ~24h, tunnel URL changes on restart). A1 proves the logic with synthetic payloads first.
- AWS sign-up asking for a card. Stop and ask. Code stays "tested locally with moto, not deployed" if needed.
- The AWS 6-month clock starts at sign-up, so the account is created only after A3.
- faster-whisper accuracy on mixed Urdu/English is unknown. Report what is observed.
- Rule-based extraction is brittle on new layouts. Accuracy reported on the synthetic set only.
- A looping n8n workflow could burn Airtable's 1,000 calls. Manual triggers only.
- Usage limits: B5 and the optional LLM step are dropped first.
