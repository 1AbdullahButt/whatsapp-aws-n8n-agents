# A2 screen recording script (about 60 seconds)

Goal: show one real WhatsApp text from a phone becoming a ticket, with the reply.
Record with Windows **Win + Alt + R** (Xbox Game Bar) for the PC side and the phone's own screen recorder for the phone.

## Before recording
- Close any window that shows `.env`, tokens, or the Meta app secret.
- Hide your own phone number: in the phone recording, crop or blur the chat header. On the PC, do not show the Meta "API Setup" page.
- Reset the demo database so the ticket is `TD-0001`: stop the server, delete `tenant-desk\data\tenant_desk.db`, start the server again.
- Have two windows side by side: the server terminal (logs) and a terminal for the staff CLI.

## Shots
1. **(5 s) Title.** Say: "Tenant maintenance desk: WhatsApp Cloud API test number, local Python webhook, Cloudflare tunnel."
2. **(15 s) Phone.** Open the chat with the Meta test number. Type: `Hi, my kitchen tap is leaking and water is dripping under the sink`. Send.
3. **(10 s) PC.** Point at the server log: the `POST /webhook 200` line and the "ticket TD-0001 created" line.
4. **(10 s) Phone.** Show the reply arriving with the ticket number.
5. **(15 s) PC.** In the second terminal run:
   ```
   .venv\Scripts\python staff_cli.py list
   .venv\Scripts\python staff_cli.py show TD-0001
   ```
   Say: "One ticket, category plumbing, both messages stored."
6. **(5 s) Close.** Say: "This used a Meta test number and synthetic content. It is a portfolio demo, not a live service."

## Optional extra shot (urgent)
Send `I can smell gas in the hallway`. Show the reply with the URGENT notice and `staff_cli.py list` showing the ticket marked urgent.

## Do not
- Do not show the duplicate test by resending; Meta does the retries, the tests cover that.
- Do not claim it handles real tenants yet. That is A5.
