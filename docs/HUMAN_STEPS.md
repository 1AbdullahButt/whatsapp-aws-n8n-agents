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
| Meta developer account, app "Property Support Bot", WhatsApp test number | First test number was BANNED by Meta (21 Nov 2026), see `docs/DECISIONS.md` #15 |
| Second app "Tenant Desk Demo 2" on portfolio "Abdullah Demo Lab", new test number | Done, used for A2 (no payment method, keep it that way) |
| cloudflared installed | Done |
| Airtable account, base "Invoice Agent", scoped token | Done (B3, 21 Nov 2026) |
| AWS account | After A3 |

---

## Step 1 (before A2): new portfolio, new app, values into `tenant-desk/.env`

These are the steps that worked on 21 Nov 2026, after the first test number was banned. Meta's screens change often; the names below are what we saw.

1. https://business.facebook.com -> create a **new business portfolio** (we used "Abdullah Demo Lab"). Skip anything that asks for payment.
2. https://developers.facebook.com/apps -> **Create app**. Pick the **WhatsApp** use case ("Connect with customers through WhatsApp"), attach it to the new portfolio, name it (we used "Tenant Desk Demo 2").
3. Meta may ask for your **Facebook password again** at several points (creating the app, showing the secret, generating tokens). That is normal; re-enter it.
4. If a screen offers **Add payment method**, skip it. Never add one.
5. In the app: **WhatsApp** -> **API Setup**. A free test number is shown under **From**. Copy into `tenant-desk/.env`:
   - **Generate access token** -> `WHATSAPP_TOKEN=`
   - **Phone number ID** (a 15-16 digit number, not the +1 555 phone number) -> `WHATSAPP_PHONE_NUMBER_ID=`
   - **WhatsApp Business Account ID** -> `WHATSAPP_BUSINESS_ACCOUNT_ID=`
6. Same page, **To** -> **Manage phone number list** -> add your own WhatsApp number and enter the code Meta sends you. Each app has its own list: without this, replies fail with error **131030** "Recipient phone number not in allowed list".
7. **App settings** -> **Basic** -> **App secret** -> **Show** -> `WHATSAPP_APP_SECRET=`.
8. Make up a verify token (any long string) -> `WHATSAPP_VERIFY_TOKEN=`.

**Tokens expire.** The access token from API Setup lasts about 24 hours. When replies start failing with 401 / "Session has expired", generate a new one, paste it into `.env`, and ask Claude to restart the server (it reads `.env` only at start).

## Step 2 (before A2): connect the webhook through a tunnel

1. Claude starts the server (`.venv\Scripts\python -m app.webhook`, http://127.0.0.1:8001).
2. Your terminal: `cloudflared tunnel --url http://localhost:8001`. Leave it open. Copy the `https://....trycloudflare.com` URL.
3. Meta app -> **WhatsApp** -> **API Setup** -> **Step 2 Production setup** -> configure the webhook (in the new app it is there, not under a "Configuration" tab):
   - Callback URL: `<tunnel URL>/webhook` (just that, no `?hub...` query string)
   - Verify token: same as `WHATSAPP_VERIFY_TOKEN`
   - **Verify and save**. The server logs `GET /webhook ... 200`.
4. Webhook fields: make sure **messages** is subscribed.
5. Ask Claude to check that the app is subscribed to the WhatsApp Business Account (`subscribed_apps`). On the new app it was not, and real messages were not delivered until Claude subscribed it (with your yes). Meta's dashboard **Test** button works even when this is missing, so it proves nothing on its own.
6. From your phone, send "leaking tap in kitchen" to the test number. You should get a reply with `TD-0001`. Screenshot the chat (crop out your number).

The tunnel URL changes every time cloudflared restarts. Redo step 3 when it does.

## Step 2b (optional, to see B2 in the n8n UI): local n8n owner account

Only needed if you want to look at the workflows in the browser (for screenshots or a recording). The automated test does not need it.

1. In `D:\Project\Portfolio\invoice-agent`: `docker compose up -d`, then `powershell -ExecutionPolicy Bypass -File scripts\n8n_setup.ps1`.
2. Open http://localhost:5690. n8n asks you to set up an owner account. This account is stored only in the local Docker volume `invoice_agent_n8n_data`; it is not an n8n Cloud sign-up. Use any email and a new password (not one you use elsewhere). Skip/decline any "get a free license" or survey prompt.
3. Open **Invoice intake** to see the flow. When finished: `docker compose down`.

Do not open the old LendLoop instance (port 5678) for this project.

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

Do this only when you are ready to start A4: the Free plan's 6-month clock starts at sign-up.
**If any screen asks for a card or says "Paid plan", stop and tell Claude. Never click "Upgrade to Paid plan".**

1. https://aws.amazon.com -> **Create an AWS account**. Use an email you check. When asked for a plan, choose **Free plan** (credits, cannot be billed, account is suspended at the end instead of charged).
2. Sign in as the root user -> top right account menu -> **Security credentials** -> **Assign MFA device** -> authenticator app. Root is used only for billing and emergencies after this.
3. Region: top right, pick **US East (N. Virginia) us-east-1** and keep it for both projects.
4. Budgets (before anything is deployed): **Billing and Cost Management** -> **Budgets** -> **Create budget** -> **Use a template** -> **Zero spend budget**, your email. Then a second one: **Monthly cost budget**, amount **$1**, alerts at 50%, 80%, 100%. Tell Claude when both show in the list; Claude will ask for a screenshot of the Budgets list (no account number visible).
5. IAM user for deploys: **IAM** -> **Users** -> **Create user** `portfolio-deployer`, no console access. Permissions: **Attach policies directly** -> `AdministratorAccess` (simplest for a short demo; Claude will list exactly what SAM creates before each deploy). Then the user -> **Security credentials** -> **Create access key** -> **Command Line Interface (CLI)** -> tick the confirmation -> copy the two values. Do not paste them in chat.
6. Install the tools in a terminal:
   ```
   winget install Amazon.AWSCLI
   winget install Amazon.SAM-CLI
   ```
   Close and reopen the terminal, then `aws configure`: paste the access key id and secret, region `us-east-1`, output `json`. This stores them in `%USERPROFILE%\.aws\credentials`, outside the repo.
7. Check: `aws sts get-caller-identity` prints a user ARN ending in `portfolio-deployer`. Tell Claude "AWS ready".

After the demo Claude gives you `sam delete` commands and you delete the access key in IAM (step 5 screen -> **Deactivate** -> **Delete**).

## Step 5: phone tests and recordings (A2, A3, A5)

- A2: `tenant-desk/docs/A2_RECORDING_SCRIPT.md` (done 21 Nov 2026).
- A3: `tenant-desk/docs/A3_PHONE_TEST.md` (done 21 Nov 2026).
- A5: pilot guide, to be written.
