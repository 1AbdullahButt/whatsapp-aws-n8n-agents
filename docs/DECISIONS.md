# Decisions

Each entry: what, why, date.

1. **Python 3.12 via `py -3.12`** (20 Nov 2026). Plain `python` on this machine is 3.10; the brief needs 3.11+.
2. **One venv per project** (`tenant-desk/.venv`, `invoice-agent/.venv`). Keeps dependencies separate; faster-whisper is heavy and B does not need it.
3. **Rules before LLM** for tenant classification. Free, explainable, testable. Optional LLM behind a flag only if a free tier is confirmed on the day.
4. **Local transcription (faster-whisper) and local extraction (pdfplumber)** everywhere, because Textract and Transcribe are Paid-plan only for new AWS accounts (checked 20 Nov 2026).
5. **AWS SAM over CDK.** One YAML template, no Node/TypeScript toolchain, easy to read line by line in an interview. `sam delete` is a single teardown command.
6. **Lambda function URL over API Gateway.** No extra service to pay for or configure; the brief asks for it.
7. **DynamoDB on-demand.** No capacity to tune; tiny demo traffic.
8. **SQS between webhook and worker.** Webhook returns 200 fast (Meta retries slow webhooks); retries and a dead-letter queue come for free from SQS.
9. **Idempotency in storage, not memory.** SQLite `UNIQUE` / DynamoDB conditional put on the WhatsApp message id, so duplicates are caught after a restart.
10. **moto for AWS tests.** Same repository tests run against SQLite and a fake DynamoDB, without an AWS account.
11. **Cloudflare quick tunnel over ngrok.** No account, no session cap. URL changes on restart, which is documented.
12. **Fresh n8n instance on port 5690 with its own volume.** The older LendLoop instance is not reused, so no old credentials leak into exported workflows. Exports are scanned for credential ids before commit.
13. **Mock accounting API built with FastAPI**, labelled as a mock in code, responses (`X-Mock: true` header) and README.
14. **MCP connectors.** Supabase: not used for now (pgvector runs in local Docker for B5, so no project creation that could reach a paid tier). Make: not used (n8n is the workflow tool being demonstrated). Airtable: may be used at B3 only to inspect the base schema, never to bulk-write. Each use will be noted here.
