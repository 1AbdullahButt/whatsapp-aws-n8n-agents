# Portfolio summary: tenant-desk and invoice-agent

Two small automation projects built in November 2026, in Python 3.12.
All test data is synthetic. Nothing here has been used by real tenants or real customers.

## The two projects

**[tenant-desk](../tenant-desk/README.md)** is a WhatsApp maintenance desk for a small
landlord or letting agent. A tenant sends a text or voice note ("my sink is leaking"). The desk
checks that the webhook really came from Meta, ignores repeat deliveries, turns voice notes into
text with local Whisper, sorts the message into a category, flags urgent cases, opens or updates
a ticket and replies with the ticket number. Staff can take over a conversation from a small
command line tool and hand it back.

**[invoice-agent](../invoice-agent/README.md)** is for a small business or bookkeeper that
receives supplier invoices as PDFs. It pulls out the key fields (vendor, number, dates, currency,
line items, totals), gives each a confidence score, flags anything a person should check, and
catches invoices sent twice. An n8n workflow then checks payment status against a mock
accounting API, drafts a reminder for unpaid or overdue invoices and waits for a person to
approve it. Results sync to Airtable. Nothing is emailed.

## Milestones

| Milestone | What was built | Tested on | Result |
|---|---|---|---|
| A1 | Local prototype: signature check, dedupe, classification, tickets, staff CLI | Local, fake WhatsApp client | Unit tests with fakes, no network |
| A2 | Real WhatsApp text messages | Real WhatsApp test number, own phone, Cloudflare tunnel | Ticket created, plain-text reply on the phone |
| A3 | Voice notes + staff takeover | Real WhatsApp, local faster-whisper `base` | Voice note -> heating ticket; takeover, staff reply and release on the phone |
| A4 | SAM stack: Lambda function URL -> SQS -> worker Lambda -> DynamoDB, S3 for audio | moto, then real AWS (Sydney), one day | Text and voice note on the phone, poison message -> dead-letter queue; 81 tests |
| B1 | PDF field extraction, confidence, flags, duplicate key | Local, 12 synthetic PDFs | 99/108 fields correct (the 9 misses are the image-only PDF); 145 tests |
| B2 | n8n workflow: duplicate check, mock accounting API, reminder draft, approval, error workflow | Real n8n 2.48.7 in Docker | Live end-to-end 11/11; 176 tests |
| B3 | Airtable sync (upsert script) | Real Airtable base, free plan | 12 invoices + 3 drafts + 1 error row; 14 API calls; 185 tests |
| B4 | SAM stack: S3 upload -> SQS -> extractor Lambda -> DynamoDB | moto, then real AWS (Sydney), one day | 12/12 PDFs processed, 99/108 (same as local), poison PDF -> dead-letter queue; 193 tests |

Test counts are the full invoice-agent suite at the end of each milestone (from its README). For
tenant-desk only today's full suite is given: 81 tests.

## What ran on real AWS

Two CloudFormation stacks, `tenant-desk-a4` and `invoice-agent-b4`, deployed with AWS SAM in
ap-southeast-2 (Sydney) on the AWS Free plan on 21-22 November 2026 and deleted the same day.

Services used: Lambda (including a function URL for the WhatsApp webhook), SQS with a dead-letter
queue after 3 failed receives, DynamoDB on-demand, S3 (voice notes, invoice inbox), SSM Parameter
Store SecureString for the WhatsApp secrets, CloudWatch Logs with 7-day retention, and
CloudFormation through SAM. No API Gateway, VPC, Textract or Transcribe.

The screenshots show the stacks and their resources, the DynamoDB items (tickets, messages, the
voice note transcript, invoices with `duplicate` and `needs_review` status), the S3 objects, the
SQS queues, the three CloudWatch log lines of the poison test, the SSM parameters as SecureString,
the WhatsApp chat on the phone and both budgets at $0.00. Account and phone numbers are blurred.

How to read the phone screenshot (`00_whatsapp_chat.jpg`, times in Pakistan time, UTC+5):

- The upper part (voice note -> TD-0002 heating, "Water is now on the floor", the office reply
  and "Thanks") is the earlier **local run** (A3, server on the PC through a Cloudflare tunnel).
- The 4:09 pm message has **no reply**. That was the first message to AWS: the temporary WhatsApp
  token had expired, the reply failed with a 401, and because dedupe had already marked the
  message as seen, the SQS retry did not resend it (problem 3 and the first gap below).
- From 5:16 pm is the **AWS run** (A4): the same text sent again after a new token, replied to
  with TD-0001, then a voice note, also replied to.

- [tenant-desk/docs/screenshots/a4-aws-sydney/](../tenant-desk/docs/screenshots/a4-aws-sydney/)
- [invoice-agent/docs/screenshots/b4-aws-sydney/](../invoice-agent/docs/screenshots/b4-aws-sydney/)

Full results: [tenant-desk/aws/README.md](../tenant-desk/aws/README.md),
[invoice-agent/aws/README.md](../invoice-agent/aws/README.md).

## Real problems found

These are in [DECISIONS.md](DECISIONS.md) entries 17 to 19.

1. **Region lock.** The first deploy to us-east-1 failed with an "explicit deny". Read-only calls
   per service showed that the account's organization policy only allows ap-southeast-2. Fixed by
   moving both projects to Sydney; the organization policy was not changed.
2. **IAM policy with a double slash.** The deployed webhook answered 502. CloudWatch showed
   AccessDenied on `ssm:GetParameter`: SAM's `SSMParameterReadPolicy` adds its own `/`, so the
   policy pointed at `parameter//tenant-desk/*`. moto does not check IAM, so the local tests passed.
   Fixed with `SSMParameterWithSlashPrefixReadPolicy` and a test that fails if the old policy returns.
3. **Short-lived token.** A real message got no reply. The worker log showed a 401 from the
   WhatsApp API: the temporary token from the Meta dashboard had stopped working about 80 minutes
   after it was made, and the warm Lambda kept the old copy. Fixed by re-reading secrets from SSM
   every 5 minutes and rebuilding the clients on the same schedule, with tests for both.

## Not proven / known gaps

- A failed reply is not resent. Dedupe runs before the reply, so the SQS retry after the 401 did
  nothing; the 4:09 pm message in the phone screenshot never got an answer.
- Only WARNING and ERROR log lines reach CloudWatch; INFO lines do not.
- Voice notes are transcribed on a PC with `transcribe_pending.py`, not on AWS.
- A transcript only changes the ticket category when it was `other`, so one ticket stayed `plumbing`
  after a voice note about a boiler.
- "Water on the floor" is not marked urgent.
- The n8n UI has not been clicked through by a person; the workflow was run through its webhooks.
- A5 (pilot with real users) and B5 (optional RAG) are not done.
- No load testing. One phone, one WhatsApp test number, 12 synthetic invoices.

## Cost

No payment method was added to the AWS account (Free plan). Budget alerts at $0.01 and $1 both show $0.00, and both stacks were deleted after the demo. The exact credit used is not known (about $160 credit remained on the Free plan afterwards).

## Interview talking points

- **Why SQS and a dead-letter queue between the webhook and the worker:** the webhook only checks
  the signature, queues the body and answers 200, so Meta does not retry slow calls. The worker
  reports failed records in `batchItemFailures`, SQS retries them, and after 3 tries the message
  moves to the dead-letter queue (`tenant-desk/cloud/worker.py`).
- **Why dedupe by WhatsApp message id in storage:** Meta can deliver the same message twice. A
  DynamoDB conditional put (`attribute_not_exists`) on the message id catches repeats even after a
  restart. The trade-off is the known gap above: a failed reply is not retried.
- **Why secrets are cached for 5 minutes:** reading SSM on every message is slow, but caching
  forever kept an expired token. 300 seconds lets a new token arrive without a redeploy
  (`tenant-desk/cloud/settings.py`).
- **Why rules before an LLM for classification and extraction:** keyword rules and labelled-field
  patterns are free, explainable and unit tested, and every field carries a confidence score so
  low-confidence values go to a person instead of being trusted.
- **What moto did not catch:** IAM is not enforced in moto, so the slash bug only showed on real
  AWS. Local tests prove the logic; a short real deploy proves the permissions.
