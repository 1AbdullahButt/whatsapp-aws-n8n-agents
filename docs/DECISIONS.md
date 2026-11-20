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
15. **First WhatsApp test number banned; moved to a second app (21 Nov 2026).** The test number of "Property Support Bot" showed `status: BANNED` (and display name `DECLINED`) in the Graph API, so Meta delivered no real messages to the webhook. We created a new business portfolio ("Abdullah Demo Lab") and a new app ("Tenant Desk Demo 2") with its own test number, which is `CONNECTED`. A2 passed on the new app.
    - **Cause: not known.** The one thing we did that could look bad: Meta's dashboard "Test" webhook carries an old timestamp, so our bot treated it as outside the 24-hour window and tried a real **template** send. Meta rejected it (400) and nothing was delivered or charged. We doubt one rejected call caused the ban, but we cannot rule it out.
    - **Guard added (commit 0c6f537):** `WhatsAppClient.send_template` does nothing and logs "NOT sent" unless code passes `allow_templates=True`, and nothing does. Only plain-text replies inside the 24-hour window are ever sent for real.
    - **Also learned:** on the new app the WhatsApp Business Account was not subscribed to the app (`subscribed_apps` listed only Meta's internal app), so real messages were not delivered even though the dashboard Test worked. Subscribed with `POST /{WABA_ID}/subscribed_apps` after Abdullah's yes. Each app also has its own allowed-recipient list (error 131030 until the phone was added).
16. **Airtable sync is a Python script run after the n8n workflow, not an n8n Airtable node (B3).** The token stays in `invoice-agent/.env` and never enters n8n's credential store or the exported workflow JSON, and the sync is unit tested with a fake client. Writes are upserts on a key field, batched 10 per request, with a call counter (free plan: 1,000 calls per month). Trade-off: someone has to run the script; n8n does not trigger it. The Airtable MCP connector was not used; the schema was checked with one read-only Web API call instead.
