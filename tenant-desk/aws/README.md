# A4: tenant-desk on AWS (SAM)

Status (21 Nov 2026): **written and tested locally against moto only. Not deployed. No AWS account yet.**

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

## What `deploy.ps1` would create (all in ap-southeast-2)

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
waits for `y`. Afterwards set the Meta callback URL to the `WebhookUrl` output + `webhook`.

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

`tests/test_cloud.py`, 12 tests, fake AWS in memory, no account:
- webhook Lambda: verify challenge ok / 403; signed POST (plain and base64 body) lands on SQS;
  bad or missing signature -> 401 and nothing queued.
- worker Lambda: text -> ticket + plain-text reply; duplicate delivery ignored; a bad body is
  reported in `batchItemFailures` (so SQS retries it, then the DLQ) while the good one in the same
  batch still goes through; voice note -> S3 object + pending text; an old message picks the
  template path but the real client blocks template sends.
- `transcribe_pending`: fills the transcript, updates category and urgency, second run does nothing.
- `put_secrets.py` writes SecureStrings; `build.py` output has the Lambda code and no server, `.env` or venv.
- `cfn-lint aws/template.yaml`: no errors.

## Not tested yet

- Nothing has run on real AWS: no deploy, no real SQS redrive, no CloudWatch logs, no IAM policy check.
- `sam build` / `sam deploy` have not been run (SAM CLI not installed yet).
- moto does not enforce IAM or the 3-receive redrive, so the DLQ path is only proven by the
  `batchItemFailures` unit test until `poison_test.py` runs on the real stack.
