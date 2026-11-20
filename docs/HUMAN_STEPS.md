# Steps only Abdullah can do

Secrets go **only** into the `.env` file named in each step. Never paste them in chat, commits or screenshots.
Each project has a `.env.example`; copy it to `.env` first:

```
copy tenant-desk\.env.example tenant-desk\.env
copy invoice-agent\.env.example invoice-agent\.env
```

## Status

| Step | Status |
|---|---|
| Meta developer account, app "Property Support Bot", WhatsApp test number | Done (no payment method, keep it that way) |
| cloudflared installed | Done |
| Airtable account | Done. Base + token: before B3 |
| AWS account | After A3 |

---

## Step 1 (before A2): put the WhatsApp values in `tenant-desk/.env`

1. Go to https://developers.facebook.com/apps and open **Property Support Bot**.
2. Left menu: **WhatsApp** -> **API Setup**.
3. Copy these into `tenant-desk/.env`:
   - **Temporary access token** -> `WHATSAPP_TOKEN=`
   - **Phone number ID** (under the "From" test number) -> `WHATSAPP_PHONE_NUMBER_ID=`
4. In **To**, make sure your own phone number is added and verified (Meta sends a code by WhatsApp).
5. Left menu: **App settings** -> **Basic** -> **App secret** -> **Show** (asks for your Facebook password) -> copy into `WHATSAPP_APP_SECRET=`.
6. Make up a random verify token (any long string, e.g. 30 random letters) -> `WHATSAPP_VERIFY_TOKEN=`. You will type the same string into Meta in Step 2.

The temporary token expires in about 24 hours. When replies stop working with a 401 error, repeat 1-3 for the token only.

## Step 2 (before A2): connect the webhook through a tunnel

Claude will tell you when the local server is ready. Then:

1. Terminal 1, in `D:\Project\Portfolio\tenant-desk`: start the server with the command from the README (`.venv\Scripts\python -m uvicorn app.webhook:app --port 8001`).
2. Terminal 2: `cloudflared tunnel --url http://localhost:8001`
3. Copy the `https://....trycloudflare.com` URL it prints.
4. Meta app -> **WhatsApp** -> **Configuration** -> **Webhook** -> **Edit**.
   - Callback URL: `<that URL>/webhook`
   - Verify token: the same string as `WHATSAPP_VERIFY_TOKEN`
   - **Verify and save**. Terminal 1 should log a GET /webhook 200.
5. Same page, **Webhook fields** -> **Manage** -> tick **messages** -> **Done**.
6. From your phone, send "Hi, my kitchen tap is leaking" to the test number.
7. You should get a reply with a ticket number like `TD-0001`. Screenshot the WhatsApp chat (crop out your phone number) and tell Claude.

The tunnel URL changes every time cloudflared restarts. Redo step 4 when it does.

## Step 3 (before B3): Airtable base and token

Claude will write the exact schema to `invoice-agent/docs/AIRTABLE_SCHEMA.md` first.

1. https://airtable.com -> **Create** -> **Start from scratch**, name it `Invoice Agent`. Decline any trial offer.
2. Create the tables and fields exactly as in the schema file.
3. Copy the base id from the URL (`https://airtable.com/appXXXXXXXX/...`, the `app...` part) -> `invoice-agent/.env` `AIRTABLE_BASE_ID=`.
4. https://airtable.com/create/tokens -> **Create new token**, name `invoice-agent`.
   - Scopes: `data.records:read`, `data.records:write`, `schema.bases:read`.
   - Access: only the `Invoice Agent` base.
   - Copy the token -> `AIRTABLE_TOKEN=`.

## Step 4 (after A3, before A4): AWS account

Detailed click-by-click will be added before A4. Outline: sign up on the **Free plan**, root MFA, IAM user for deploys, install AWS CLI and SAM CLI (`winget install Amazon.AWSCLI`, `winget install Amazon.SAM-CLI`), `aws configure`, then the budget in `COST_CHECKLIST.md`. If sign-up asks for a card, stop and tell Claude.

## Step 5: phone tests and recordings (A2, A3, A5)

Scripts will be added to `tenant-desk/docs/` at A2.
