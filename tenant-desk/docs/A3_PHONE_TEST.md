# A3 phone test: voice note + human handoff (about 5 minutes)

Uses the same setup as A2 (app "Tenant Desk Demo 2", test number, tunnel, server on port 8001).
Everything is free: Whisper runs locally (model `base`, CPU), and every reply is a plain-text
message inside the 24-hour window. No template is ever sent.

Claude runs the staff commands and watches the server log. You use the phone.

| # | Who | Action | Expected |
|---|---|---|---|
| 1 | You | Send a **voice note** (5-10 s, English): "My boiler is broken and there is no hot water." | Reply: "logged your request as ticket TD-0002 (heating)". Log: audio downloaded, saved under `media/`, transcribed. |
| 2 | Claude | `staff_cli.py show TD-0002` | The transcript is stored with `[audio: media/...ogg]`. |
| 3 | Claude | `staff_cli.py takeover TD-0002` | Ticket mode is `human`. |
| 4 | You | Send two texts: "Hello? Is anyone there?" and "Water is now on the floor" | **No** auto reply. Both stored on TD-0002. |
| 5 | Claude | `staff_cli.py reply TD-0002 "Hi, this is the office. An engineer is booked for Tuesday 9am."` | You receive that text (plain text, inside the window). |
| 6 | Claude | `staff_cli.py release TD-0002` | Mode back to `bot`. |
| 7 | You | Send "Thanks" | Auto reply again, on TD-0002. |
| 8 | Claude | `staff_cli.py show TD-0002` | Full history in order: in (voice), out, in, in, staff, in, out. |

Screenshot the phone chat after step 7 (crop out your number). Optional: record it with the
phone's screen recorder; the A2 script's "Before recording" rules apply.

Notes
- Whisper's first load downloads the free `base` model from Hugging Face (about 145 MB, no account).
  The server loads it at start, so the first voice note is not slow.
- Accuracy on accents, noise or mixed Urdu/English is not measured. Whatever the transcript says
  is recorded as-is in the README.
