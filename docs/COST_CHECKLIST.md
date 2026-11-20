# $0 cost checklist

Checked 20 Nov 2026. Re-check a service's free terms on the day before first using it.

**Rule: if any screen asks for a card or payment method, stop and tell Claude. Do not enter it.**

| Service | Free allowance | What would cause a charge | Guard |
|---|---|---|---|
| AWS account (Free plan) | $100 credits at sign-up, up to $100 more from activities, 6 months | Nothing can bill on the Free plan. Clicking "Upgrade to Paid plan" can. | Never upgrade. Create a $1 AWS Budget with email alerts at 50/80/100% before any deploy. Check credits in Billing after each demo. Tear down the same day. |
| Lambda, DynamoDB, S3, SQS, CloudWatch Logs, SSM Parameter Store (standard) | Always-free limits, then credits | Resources left running, log growth, retry loops | DLQ after 3 tries, Lambda reserved concurrency 2, 7-day log retention, DynamoDB on-demand, `sam delete` after recording |
| Textract, Transcribe | Not available on the Free plan | Would need Paid plan | Not used |
| WhatsApp Cloud API | 1,000 service messages per number per month | A payment method on the WhatsApp Business Account, plus volume or template sends | Never add a payment method. Template sends simulated only. |
| Airtable Free | 1,000 records per base, 1,000 API calls per workspace per month | Upgrading or a trial | Decline trials. Fake client in tests. Batched writes. Call counter. |
| Cloudflare quick tunnel | Free, no account | Nothing | n/a |
| n8n community edition (Docker) | Free self-hosted | Signing up for n8n Cloud | Local only, port 5690 |
| faster-whisper, pdfplumber, reportlab, pgvector, MiniLM | Open source, local | Nothing | n/a |
| Optional LLM | Terms unstable | Enabling billing on a key | Off by default. Ask Abdullah before enabling. |
| MCP connectors (Supabase, Make, Airtable) | Varies | Creating paid projects or paid operations | Only used where noted in DECISIONS.md. Supabase: no project creation (could hit paid tier). Make: not used. |

## How to set the AWS budget alert (do this before A4)

1. Sign in to the AWS console as root.
2. Search bar: type **Budgets**, open **AWS Budgets**.
3. **Create budget** -> **Use a template (simplified)** -> **Zero spend budget**.
4. Budget name `zero-spend`, email: your email -> **Create budget**.
5. Also create a second budget: **Customize (advanced)** -> **Cost budget** -> Monthly, amount `1.00` USD -> alerts at 50%, 80%, 100% actual -> your email.
6. Tell Claude "budget created". Claude will not deploy until you do.

## After every AWS demo

- Run the teardown command given in the project README.
- Console -> **Billing and Cost Management** -> **Credits**: note the remaining credit.
- Console -> **CloudFormation**: no stacks left from this project.
