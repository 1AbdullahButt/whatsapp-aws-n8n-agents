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
12. **Fresh n8n instance on port 5690 with its own volume.** An earlier n8n instance is not reused, so no old credentials leak into exported workflows. Exports are scanned for credential ids before commit.
13. **Mock accounting API built with FastAPI**, labelled as a mock in code, responses (`X-Mock: true` header) and README.
14. **MCP connectors.** Supabase: not used for now (pgvector runs in local Docker for B5, so no project creation that could reach a paid tier). Make: not used (n8n is the workflow tool being demonstrated). Airtable: may be used at B3 only to inspect the base schema, never to bulk-write. Each use will be noted here.
15. **First WhatsApp test number restricted by Meta; moved to a second app (21 Nov 2026).** A2 and all later runs used the second app's test number.
16. **Airtable sync is a Python script run after the n8n workflow, not an n8n Airtable node (B3).** The token stays in `invoice-agent/.env` and never enters n8n's credential store or the exported workflow JSON, and the sync is unit tested with a fake client. Writes are upserts on a key field, batched 10 per request, with a call counter (free plan: 1,000 calls per month). Trade-off: someone has to run the script; n8n does not trigger it. The Airtable MCP connector was not used; the schema was checked with one read-only Web API call instead.
17. **AWS region ap-southeast-2 (Sydney), not us-east-1 (21 Nov 2026).** The new account is a member of an AWS Organization whose service control policy denies CloudFormation, Lambda, DynamoDB, SQS and SSM outside ap-southeast-2 (explicit deny in us-east-1 and us-west-2). Found with read-only checks after the first deploy attempt failed; the Organization and its policies were not touched. Lesson: run a read-only call per service in the target region before planning a deploy, and read "explicit deny" in an error as a policy, not a missing permission.
18. **`SSMParameterWithSlashPrefixReadPolicy` for `/tenant-desk/*` (21 Nov 2026).** SAM's `SSMParameterReadPolicy` adds a `/` itself, so the deployed policy said `parameter//tenant-desk/*` and the Lambdas got AccessDenied. moto does not check IAM, so only real AWS showed it. A test now fails if the old policy name comes back.
19. **Secrets re-read every 5 minutes (22 Nov 2026).** The temporary WhatsApp token from the Meta dashboard stopped working after about 80 minutes (not the 24 hours we had assumed), and a warm Lambda kept its old copy. `cloud/settings.py` now caches each SSM secret for 300 s and the worker rebuilds its clients on the same schedule, so `put_secrets.py` is enough to rotate the token. A permanent system-user token would remove the problem; not done, since the app stays unpublished.
