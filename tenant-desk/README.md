# Tenant Desk (milestones A1-A4: local prototype, real WhatsApp text and voice notes on a test number, AWS leg)

A WhatsApp maintenance desk for a small landlord or letting agent. A tenant
sends a WhatsApp message (text or voice note) such as "my sink is leaking".
The desk:

1. checks the webhook really came from Meta (signature),
2. ignores repeated deliveries of the same message (dedupe),
3. turns a voice note into text (local Whisper),
4. sorts it into a category (plumbing, electrical, heating, locks, pests, other)
   and flags urgent cases (gas smell, flooding, fire, smoke, sparks, locked out,
   no heating in Nov-Feb),
5. opens a ticket (`TD-0001`, ...) or adds to the tenant's open ticket,
6. replies with the ticket number, unless a staff member has taken over.

Staff use a small command line tool to list tickets, read history, take over
a conversation, hand it back to the bot, and reply.

All names and phone numbers in this repo are made up (e.g. `15550000001`).

## Run the tests

```
cd tenant-desk
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest -q
```

Last local run: `81 passed` (23 Nov 2026). The tests need no network and no accounts.

## Run the server locally

```
copy .env.example .env      # then fill in the values (see comments in the file)
.venv\Scripts\python -m app.webhook
```

It listens on `http://127.0.0.1:8001/webhook`. To receive real WhatsApp
webhooks you need a public HTTPS URL (e.g. a cloudflared tunnel); that is
milestone A2. For voice notes with real Whisper, also run
`.venv\Scripts\python -m pip install -r requirements-voice.txt`, or set
`TRANSCRIBER=fake` to skip it.

Staff commands:

```
.venv\Scripts\python staff_cli.py list
.venv\Scripts\python staff_cli.py show TD-0001
.venv\Scripts\python staff_cli.py takeover TD-0001
.venv\Scripts\python staff_cli.py release TD-0001
.venv\Scripts\python staff_cli.py reply TD-0001 "Plumber booked for Tuesday 9am"
.venv\Scripts\python staff_cli.py close TD-0001
```

`reply` outside the 24-hour window would need a template; real template sends are disabled,
so the CLI says "NOT messaged" and only saves the note on the ticket.

## Architecture

Everything lives in `app/`. Each file does one job:

- `signature.py` checks `X-Hub-Signature-256` (HMAC-SHA256 of the raw body with the app secret, `hmac.compare_digest`).
- `parser.py` turns Meta's `entry[].changes[].value.messages[]` into `IncomingMessage` objects; status updates and non text/audio types are skipped.
- `classifier.py` keyword rules in a dict give a `Classification(category, urgent, reason)`. The month is a parameter.
- `window.py` `inside_24h(last_inbound_ts, now)`.
- `repository.py` the storage interface (see its docstring for every method).
- `repo_sqlite.py` SQLite. `seen_messages.wa_message_id` is the PRIMARY KEY, inserted with `INSERT OR IGNORE`, so dedupe survives a restart.
- `repo_dynamodb.py` DynamoDB single table (`pk`/`sk`, layout in the file's docstring). Dedupe by conditional put `attribute_not_exists(pk)`, ticket numbers by atomic `ADD`. Used by the AWS worker (milestone A4, see [aws/README.md](aws/README.md)); the local server uses SQLite.
- `whatsapp_client.py` `WhatsAppClient` (httpx, Graph API v21.0: `send_text`, `send_template`, `download_media`) and `FakeWhatsAppClient`, which only records calls.
- `transcriber.py` `FasterWhisperTranscriber` (model `base`, CPU, int8, imported lazily) and `FakeTranscriber`.
- `service.py` `handle_message` (the main flow) and `send_update` (any later message to a tenant).
- `webhook.py` FastAPI app. `build_deps()` creates the real objects; tests pass fakes to `create_app(deps)`.
- `../staff_cli.py` the argparse staff tool.

### Repository interface notes

- Dedupe is a separate first step, `mark_seen(wa_message_id) -> bool`, instead of
  `save_message_once(msg, ticket_id)`. The message has no ticket yet when we
  need to know whether it is a duplicate, and claiming the id first means a
  duplicate can never create a second ticket or a second reply. Trade-off: if
  the process crashes right after `mark_seen`, Meta's retry of that message is
  ignored too.
- `add_message` takes an `at` time, so the 24h window uses WhatsApp's own
  message timestamp.
- `get_ticket(ticket_id)` was added for the staff CLI. The ticket id is the
  number itself (`TD-0001`).

### How the 24-hour window is decided

WhatsApp allows free-form messages only within 24 hours of the tenant's
latest inbound message; outside it, only pre-approved templates.

- Auto replies: the inbound message is stored first, then the window is checked
  with `last_inbound_time(phone)`. So the window is measured from the message
  we just received, and a normal reply is free-form text, even if the tenant
  had been silent for days. (Checking before storing would wrongly look at the
  old message and force a template.) A test covers this case.
- Later updates (`send_update`, used by `staff_cli.py reply`): if the tenant has
  not written for 24 hours, the message goes out as the template
  `ticket_update` with parameters `[ticket id, text]`. That template would have
  to be created in WhatsApp Manager and approved by Meta before it could be
  sent for real.

## What was tested

- Local pytest only (Windows, Python 3.12), with synthetic webhook payloads
  built in `tests/helpers.py`.
- Signature good / bad / missing (401) and the GET verification challenge (ok / 403), through FastAPI's TestClient.
- Duplicate delivery gives one ticket and one reply, also after a "restart" (new repository object and new app on the same SQLite file).
- Staff takeover: new messages land on the same ticket, no auto reply, full history kept; release turns replies back on.
- Urgent routing ("I can smell gas in the kitchen") and category rules. A later urgent message on an open ticket raises that ticket to urgent (it never lowers it).
- 24h window: inside uses `send_text`, outside uses `send_template`, both via `FakeWhatsAppClient`.
- Voice note path with a fake media download and `FakeTranscriber`: file saved to a temp media folder, ticket category heating.
- Repository contract tests run against both SQLite and DynamoDB mocked by moto (`mock_aws`, fake credentials, us-east-1).

### Real WhatsApp test (milestone A2, 21 Nov 2026)

- One real text conversation through the WhatsApp Cloud API **test number** of an unpublished Meta app,
  the local server on Windows, and a Cloudflare quick tunnel. One tester (the developer's own phone).
- "Leaking tap on kitchen" arrived as a signed `POST /webhook`, created `TD-0001` (plumbing).
  A second message went onto the same ticket and the plain-text reply
  ("Thanks, we have added your message to ticket TD-0001.") reached the phone (Graph API 200).
- The first reply attempt failed with Meta error 131030 because the phone was not yet on the new
  app's recipient list. After adding it, replies worked.
- Setup notes (second app after the first test number was restricted by Meta, subscribing the app to the
  WhatsApp Business Account, recipient list, token expiry, tunnel URL changes) are in
  `../docs/HUMAN_STEPS.md` Steps 1-2 and `../docs/DECISIONS.md` #15.
- Template sends are blocked in `WhatsAppClient` (nothing is sent unless code passes
  `allow_templates=True`); only free-form replies inside the 24-hour window go out for real.

### Voice note and human handoff on a phone (milestone A3, 21 Nov 2026)

Same setup as A2, with `faster-whisper==1.2.1` (model `base`, CPU, int8, free and local) installed
from `requirements-voice.txt`. One tester, one phone. Steps in `docs/A3_PHONE_TEST.md`.

- A 5-second English voice note was downloaded from Meta, saved under `media/`, and transcribed
  locally as "My boiler is broken, there is no hot water." It opened `TD-0002` (heating) and
  the plain-text auto reply arrived. Whisper's language confidence was low (0.41) even though
  the text was right.
- `staff_cli.py takeover TD-0002`: the next two texts were stored with **no** auto reply.
- `staff_cli.py reply ...`: the staff text was sent as plain text inside the 24-hour window (Graph 200).
- `staff_cli.py release TD-0002`: the next message ("Thanks") got an auto reply again.
- Final history, in order: in (voice), out, in, in, staff, in, out.
- Before the phone test, a synthetic voice note (Windows text-to-speech, converted to Opus)
  went through the real Whisper model and the same service code with a fake WhatsApp client.
- Known gap seen in this test: "Water is now on the floor" was **not** marked urgent; the
  urgent rules match words like "flood"/"flooding", not that phrase.

## What was not tested

- Real WhatsApp beyond A2-A3: only about ten messages from one phone to a test number of an
  unpublished app. No other testers, accents, noisy audio or Urdu/English mixed voice notes.
- Whisper accuracy is not measured; only the two transcripts above were checked by eye.
- Real AWS (A4) ran once, 21-22 Nov 2026, in ap-southeast-2 on the Free plan, then was torn down:
  text -> ticket -> reply, voice note -> S3 + "transcription pending" -> transcribed on the PC,
  poison message -> dead-letter queue after 3 tries, $0.00 spent. Gaps found there (a failed
  reply is not resent, INFO logs not in CloudWatch) are listed in `aws/README.md`.
- The `ticket_update` template has not been created, approved or sent for real;
  all template sends are simulated by the fake client.
- Load, concurrency between several server processes, and long-running use.

## Cost note

Replies inside the 24-hour window are service messages. Since October 2026
WhatsApp gives 1,000 free service messages per month; check Meta's current
pricing before relying on it. Template messages outside the window can be
charged, which is one more reason template sends are only simulated here.
