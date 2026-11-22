# Portfolio repo: tenant-desk + invoice-agent

Read `docs/PLAN.md` for the full plan. This file is the short version plus current status.

## Rules
- $0 only. Check free-tier terms before using any cloud service. Card or billing prompt -> stop and ask Abdullah. See `docs/COST_CHECKLIST.md`.
- Honest claims: READMEs say what was tested, on what, and what was not. No "production", no invented metrics. Synthetic data only.
- Python 3.12 (`py -3.12`; plain `python` is 3.10). Simple code, small functions, plain comments.
- Secrets only in `.env` (gitignored). Commit `.env.example`. Never print secret values.
- Run tests and show real output before claiming anything works.
- Each project stays in its own folder. Shared helpers only in `/shared` (config, logging).
- Human-only steps go in `docs/HUMAN_STEPS.md`.
- Max 2 subagents in parallel. Commit after each milestone.
- n8n: fresh instance on port 5690, volume `invoice_agent_n8n_data`. Never reuse the LendLoop instance. Scan exported workflow JSON for credentials.
- MCP connectors only where they help, logged in `docs/DECISIONS.md`. Nothing that can bill.

## Layout
- `docs/` PLAN, HUMAN_STEPS, COST_CHECKLIST, DECISIONS
- `shared/` config.py, logging_setup.py
- `tenant-desk/` Project A (WhatsApp maintenance desk)
- `invoice-agent/` Project B (invoice workflow)

## Run tests
```
cd tenant-desk   && .venv\Scripts\python -m pytest -q
cd invoice-agent && .venv\Scripts\python -m pytest -q
```

## Status (update after every milestone)
- [x] Phase 0 plan approved (20 Nov 2026)
- [x] Phase 1 repo setup
- [x] A1 local prototype (59 tests green, commit 7d60bb3). Not run against real WhatsApp/Whisper/AWS yet.
- [x] B1 local extraction (145 tests green; 99/108 fields correct on own synthetic set, the 9 misses are the image-only PDF, flagged no_text_layer)
- [x] A2 real WhatsApp text (21 Nov 2026, second app "Tenant Desk Demo 2"; TD-0001 created, plain-text reply reached phone; 63 tests). First test number BANNED, see DECISIONS #15. Template sends blocked in code.
- [x] B2 n8n end to end (n8nio/n8n:2.48.7, port 5690; 176 unit tests + live e2e 11/11; start/stop in invoice-agent/docs/N8N.md). UI not clicked through by a human.
- [x] A3 voice note + handoff on phone (21 Nov 2026; local faster-whisper base; TD-0002 voice -> heating, takeover/staff reply/release all on phone; 66 tests). Gap: "water on the floor" not urgent.
- [x] B3 Airtable (21 Nov 2026; scripts/sync_airtable.py, upsert; fresh n8n e2e 11/11 then 12 invoices + 3 drafts + 1 error in the base; 14 API calls used; 185 tests)
- [x] B4 AWS (21 Nov 2026, ap-southeast-2): deployed, 12 PDFs -> 99/108 (same as local), duplicate/needs_review flags right, poison PDF -> DLQ after 3 tries; torn down. 193 tests.
- [x] A4 AWS (21-22 Nov 2026, ap-southeast-2): deployed, text -> ticket -> reply and voice note -> S3 + pending -> PC transcription on the phone, poison -> DLQ; torn down. Fixed SSM slash policy + 5-min secret refresh (81 tests). Gaps: failed reply not resent after dedupe, INFO logs not in CloudWatch.
- [ ] A5 pilot
- [ ] B5 optional RAG

Account facts: Meta app "Property Support Bot" test number is BANNED (unused). Active: app "Tenant Desk Demo 2" on portfolio "Abdullah Demo Lab", subscribed to its WABA, own phone on its recipient list, no payment method. Temp token lasts ~24h; tunnel URL changes on cloudflared restart. cloudflared installed. Airtable base "Invoice Agent" + scoped token exist (B3 done). AWS account exists (Free plan, member of an Organization whose SCP allows only ap-southeast-2; budgets zero-spend + monthly-1-usd). Nothing deployed now; all stacks, buckets, SSM params deleted 22 Nov 2026. IAM access key still active (user to deactivate).
