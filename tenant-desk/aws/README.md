# A4: tenant-desk on AWS (SAM)

Status (22 Nov 2026): **deployed once to real AWS (ap-southeast-2, Free plan), demoed with a real phone, then torn down the same day.** Results below under "What ran on real AWS". Nothing is running now.

```
Meta --POST--> Lambda function URL (cloud/webhook.py)
                 check X-Hub-Signature-256 -> 401 if bad
                 put raw body on SQS, answer 200 at once
           --> SQS queue --(3 failed receives)--> dead-letter queue
           --> worker Lambda (cloud/worker.py), batch size 1, at most 2 at once
                 dedupe (DynamoDB conditional put) -> ticket -> plain-text reply
                 voice note: audio to S3, text "[voice note - transcription pending]"
PC: aws/transcribe_pending.py  -> faster-whisper locally -> transcript back into DynamoDB
```

AWS Transcribe is not on the Free plan, so voice notes are transcribed on the PC afterwards.
The worker reuses `app/service.py`, `app/repo_dynamodb.py` and `app/whatsapp_client.py`
(templates blocked) unchanged; only the media saver and transcriber are swapped.

## What `deploy.ps1` creates (all in ap-southeast-2)

| Resource | Count | Settings that limit cost |
|---|---|---|
| CloudFormation stack `tenant-desk-a4` | 1 | removed by `teardown.ps1` |
| Lambda functions (webhook, worker) + 2 IAM roles | 2 | 256 MB, 10 s / 30 s timeout |
| Lambda function URL (public, `AuthType NONE`) | 1 | every POST must carry Meta's HMAC signature |
| SQS queues (main + dead-letter) | 2 | 3 receives then DLQ; DLQ keeps 4 days |
| SQS -> worker event source mapping | 1 | batch 1, max concurrency 2 |
| DynamoDB table | 1 | on-demand (pay per request), no provisioned capacity |
| S3 bucket for voice notes | 1 | public access blocked, files expire after 7 days |
| CloudWatch log groups | 2 | 7-day retention |
| SAM artifact stack `aws-sam-cli-managed-default` (+ 1 S3 bucket) | 1 | made by `--resolve-s3`; holds the code zip |
| SSM SecureString parameters (by `put_secrets.py`, outside the stack) | 3 | standard tier (free) |

No API Gateway, NAT gateway, VPC, KMS customer key, Transcribe or Textract.
On the new-account **Free plan** none of this can be billed (credits only, and the account is
suspended instead of charged). Two budgets (zero spend and $1) must exist before deploying.

## Deploy (only after the budget check and Abdullah's yes)

```
cd D:\Project\Portfolio\tenant-desk
.venv\Scripts\python aws\put_secrets.py
powershell -ExecutionPolicy Bypass -File aws\deploy.ps1
```

`deploy.ps1` reads the phone number ID from `.env`, builds `aws/build/` (app, cloud, shared,
`httpx`), runs `sam build`, then `sam deploy --confirm-changeset`: SAM lists every resource and
waits for `y`. (On 21 Nov the resource list was approved in advance, so it ran with
`--no-confirm-changeset`.) Afterwards set the Meta callback URL to the `WebhookUrl` output + `webhook`.

Demo checks after deploy:
1. Text from the phone -> reply with a ticket number (worker logs in CloudWatch).
2. `.venv\Scripts\python aws\poison_test.py` -> a bad message ends up in the dead-letter queue.
3. Voice note -> `aws\transcribe_pending.py` fills in the transcript.
4. Switch the Meta callback URL back to the local tunnel (or leave it; the stack is deleted next).

## Teardown (same day)

```
powershell -ExecutionPolicy Bypass -File aws\teardown.ps1
```

Empties the bucket, `sam delete`s the stack, deletes the SSM parameters, then lists stacks,
functions, queues, tables and parameters so you can see nothing is left. After B4 is also done,
remove SAM's artifact stack: `sam delete --stack-name aws-sam-cli-managed-default --no-prompts`
(empty its bucket first if it complains). Then deactivate and delete the IAM access key.

## What was tested (locally, moto)

`tests/test_cloud.py`, 15 tests, fake AWS in memory, no account:
- webhook Lambda: verify challenge ok / 403; signed POST (plain and base64 body) lands on SQS;
  bad or missing signature -> 401 and nothing queued.
- worker Lambda: text -> ticket + plain-text reply; duplicate delivery ignored; a bad body is
  reported in `batchItemFailures` (so SQS retries it, then the DLQ) while the good one in the same
  batch still goes through; voice note -> S3 object + pending text; an old message picks the
  template path but the real client blocks template sends.
- `transcribe_pending`: fills the transcript, updates category and urgency, second run does nothing.
- `put_secrets.py` writes SecureStrings; `build.py` output has the Lambda code and no server, `.env` or venv.
- SSM read policy matches parameter names that start with `/`; secrets are cached, then
  re-read after 5 minutes; the worker rebuilds its clients on the same schedule.
- `cfn-lint aws/template.yaml`: no errors.

## What ran on real AWS (21-22 Nov 2026)

One deploy plus two stack updates, all in ap-southeast-2. The WhatsApp test number is the one
from A2 ("Tenant Desk Demo 2"); messages came from Abdullah's own phone.

| Check | Result |
|---|---|
| Verify GET with the right / wrong token, POST with a bad signature | 200 + challenge / 403 / 401 |
| Text message | queued, worker created the ticket, plain-text reply on the phone about 7 s after sending (cold start) |
| Voice note | `.ogg` (about 10 KB) stored in S3, ticket line `[voice note - transcription pending]`, reply on the phone |
| `transcribe_pending.py` on the PC | downloaded the audio from S3, faster-whisper `base` wrote "My boiler is broken. There is no hot water." back into DynamoDB |
| `poison_test.py` (body that is not JSON) | failed at receive counts 1, 2, 3 (one minute apart, `JSONDecodeError` in CloudWatch), then found in the dead-letter queue and deleted |
| Duplicate protection | one `WAMSG#` row per WhatsApp message id in DynamoDB |
| Teardown | `teardown.ps1` + SAM artifact stack removed; stacks, buckets, functions, queues, tables, log groups, SSM parameters and stack roles all listed empty |
| Cost | both budgets at $0.00; Free plan credits $159.999667 remaining after teardown |

Two bugs found only on real AWS, both fixed with a test (see `docs/DECISIONS.md` 18 and 19):
1. `SSMParameterReadPolicy` adds its own `/`, so `/tenant-desk/*` became `parameter//tenant-desk/*`
   and every secret read got AccessDenied (webhook answered 502). Now
   `SSMParameterWithSlashPrefixReadPolicy`.
2. The temporary WhatsApp token stopped working about 80 minutes after it was made, and the warm
   Lambda kept the old token forever. Secrets and clients are now re-read every 5 minutes, so a
   new token from `put_secrets.py` arrives without a redeploy.

## Still not proven / known gaps

- **A failed reply is not resent.** Dedupe (`mark_seen`) runs before the reply, so when the reply
  failed (expired token) the SQS retry did nothing and that message never got an answer. Retries only
  help for failures before dedupe (bad body, DynamoDB down).
- Only WARNING and ERROR lines reach CloudWatch; the worker's INFO lines (ticket id per message) do not.
- Voice notes are not transcribed in the cloud (Transcribe is not on the Free plan); someone has to
  run `transcribe_pending.py`.
- The ticket category is only changed by a transcript when it was `other`, so TD-0001 stayed
  `plumbing` after the boiler voice note.
- "Water on the floor" is still not classed as urgent (gap from A3).
- One tenant, a few messages, a test number with temporary tokens. No load test, no permanent token,
  no real tenants.
