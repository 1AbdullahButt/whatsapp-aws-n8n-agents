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
- [ ] A2 real WhatsApp text (needs HUMAN_STEPS 1-2)
- [ ] B2 n8n end to end
- [ ] A3 voice note + handoff on phone
- [ ] B3 Airtable (needs HUMAN_STEPS 3)
- [ ] A4 AWS (needs HUMAN_STEPS 4, after A3)
- [ ] B4 AWS
- [ ] A5 pilot
- [ ] B5 optional RAG

Account facts: Meta app "Property Support Bot" + test number exist, no payment method. cloudflared installed. Airtable account exists, no base yet. AWS account not created (never had one, Free plan applies).
