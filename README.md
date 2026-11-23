# whatsapp-aws-n8n-agents

Two portfolio projects in Python 3.12: a WhatsApp maintenance desk built on the WhatsApp Cloud API
and FastAPI, and an invoice-processing workflow built on n8n and FastAPI. Both have an AWS leg
(AWS Lambda, SQS with a dead-letter queue, DynamoDB, S3, SSM Parameter Store, deployed with AWS
SAM). All data is synthetic, and everything runs on free tiers.

One-page overview: [docs/PORTFOLIO_SUMMARY.md](docs/PORTFOLIO_SUMMARY.md).

## tenant-desk

A tenant sends a WhatsApp text or voice note about a repair. The desk checks the webhook
signature, ignores repeat deliveries, transcribes voice notes with local faster-whisper, sorts the
message into a category with keyword rules, flags urgent cases, opens or updates a ticket and
replies with the ticket number. Staff can take over a conversation and hand it back.
Details: [tenant-desk/README.md](tenant-desk/README.md), AWS leg: [tenant-desk/aws/README.md](tenant-desk/aws/README.md).

## invoice-agent

Reads synthetic invoice PDFs with pdfplumber, extracts the key fields with a confidence score,
flags anything a person should check and catches invoices sent twice. An n8n workflow checks
payment status against a mock accounting API, drafts a reminder for overdue invoices and waits for
a person to approve it. Results can be synced to Airtable. Nothing is emailed.
Details: [invoice-agent/README.md](invoice-agent/README.md), AWS leg: [invoice-agent/aws/README.md](invoice-agent/aws/README.md).

## What was tested, on what, and what was not

| Tested | On |
|---|---|
| Unit tests: tenant-desk 81, invoice-agent 193, all passing | Local, no network or accounts needed (fakes and moto) |
| Text and voice-note messages, ticket replies, staff takeover | A WhatsApp Cloud API test number and one phone |
| Invoice workflow end to end, 11/11 checks | n8n 2.48.7 in Docker |
| Sync of results | A free Airtable base |
| Field extraction: 99/108 fields correct | The 12 synthetic PDFs, locally and on AWS |
| Webhook -> SQS -> worker -> DynamoDB, and S3 -> SQS -> extractor -> DynamoDB, including a message forced into the dead-letter queue | AWS in ap-southeast-2 (Sydney), one day |

Not proven, or known gaps:

- A failed WhatsApp reply is not resent, because dedupe runs before the reply.
- Only WARNING and ERROR log lines reach CloudWatch.
- Voice notes are transcribed on a PC, not on AWS (AWS Transcribe is not on the Free plan).
- A transcript only changes the ticket category when it was `other`.
- "Water on the floor" is not marked urgent.
- The n8n UI has not been clicked through by a person; the workflow was run through its webhooks.
- No real users, no load testing, no pilot yet (A5), no RAG part yet (B5).

## AWS

Both stacks were deployed in ap-southeast-2 (Sydney) for the demo on 21-22 November 2026 and then
deleted. Nothing is running now. Screenshots, with account and phone numbers blurred:

- [tenant-desk/docs/screenshots/a4-aws-sydney/](tenant-desk/docs/screenshots/a4-aws-sydney/)
- [invoice-agent/docs/screenshots/b4-aws-sydney/](invoice-agent/docs/screenshots/b4-aws-sydney/)

## Data

All tenants, phone numbers, companies and invoices in this repo are made up. The only real
messages were sent from the author's own phone to a WhatsApp test number.

## Run the tests

```
cd tenant-desk   && py -3.12 -m venv .venv && .venv\Scripts\pip install -r requirements.txt && .venv\Scripts\python -m pytest -q
cd invoice-agent && py -3.12 -m venv .venv && .venv\Scripts\pip install -r requirements.txt && .venv\Scripts\python -m pytest -q
```

Secrets are read from a `.env` file in each project (see `.env.example`); the tests do not need one.
