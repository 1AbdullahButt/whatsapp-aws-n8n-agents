# B4: invoice extraction on AWS (SAM)

Status (21 Nov 2026): **written and tested locally against moto only. Not deployed. No AWS account yet.**

```
PDF uploaded to the inbox bucket
  --(S3 event notification, *.pdf only)--> SQS queue --(3 failed receives)--> dead-letter queue
  --> extract Lambda (cloud/extract_worker.py), batch size 1, at most 2 at once
        same pdfplumber extractor and duplicate key as B1/B2
  --> DynamoDB: INVOICE#<file> (fields, confidences, flags, status) and DUPKEY#<key> (first file)
```

No Textract (not on the AWS Free plan); the B1 extractor is pure Python and runs in Lambda as is.
This leg covers extraction only. The n8n approval flow and Airtable stay local (B2, B3).

## What `deploy.ps1` would create (us-east-1)

| Resource | Count | Settings that limit cost |
|---|---|---|
| CloudFormation stack `invoice-agent-b4` | 1 | removed by `teardown.ps1` |
| Lambda function + IAM role | 1 | 512 MB, 60 s timeout |
| S3 inbox bucket `invoice-agent-b4-inbox-<account id>` | 1 | public access blocked, files expire after 7 days, events only for `.pdf` |
| SQS queues (uploads + dead-letter) + queue policy for S3 | 2 | 3 receives then DLQ; DLQ keeps 4 days |
| SQS -> Lambda event source mapping | 1 | batch 1, max concurrency 2 |
| DynamoDB table | 1 | on-demand |
| CloudWatch log group | 1 | 7-day retention |
| SAM artifact stack `aws-sam-cli-managed-default` (shared with A4) | 1 | holds the code zip |

No API Gateway, VPC, NAT, Textract or KMS customer key. On the Free plan this cannot be billed.

## Deploy, demo, teardown (only after the budget check and Abdullah's yes)

```
cd D:\Project\Portfolio\invoice-agent
powershell -ExecutionPolicy Bypass -File aws\deploy.ps1        # SAM lists the change set, waits for y
.venv\Scripts\python aws\upload_demo.py                        # 12 PDFs up, results + accuracy back
.venv\Scripts\python aws\poison_test.py                        # broken PDF -> retries -> DLQ (~15 min)
powershell -ExecutionPolicy Bypass -File aws\teardown.ps1      # same day
```

After both A4 and B4 are torn down: `sam delete --stack-name aws-sam-cli-managed-default --no-prompts`
(empty its bucket first if asked), then deactivate and delete the IAM access key.

`sam build` installs pdfplumber's Linux wheels (pdfminer.six, pypdfium2, Pillow). If it cannot
find wheels for the Lambda platform on Windows, `sam build --use-container` (Docker) is the fallback.

## What was tested (locally, moto)

`tests/test_cloud.py`, 8 tests, fake S3 / SQS / DynamoDB, no account:
- All 12 synthetic PDFs through the worker: inv_09 stored as `duplicate` of inv_01, inv_11 and
  inv_12 as `needs_review`, the rest `extracted`. Scored with `upload_demo.py`'s own comparison,
  the DynamoDB round trip gives **99/108 fields correct, the same as the local accuracy report**.
- Same file processed twice is not a duplicate of itself; URL-encoded keys with spaces work.
- A broken "PDF" is reported in `batchItemFailures` (so SQS retries it) while a good file in the
  same batch is stored; an oversized file is refused before download; S3's setup test event is ignored.
- S3 bucket notification -> SQS -> worker, wired in moto the way the template wires it.
- `build.py` output holds only the Lambda code (no API, review queue or `.env`).
- `cfn-lint aws/template.yaml`: no errors.

## Not tested yet

- Nothing on real AWS: no deploy, no real S3 events, no IAM check, no CloudWatch logs.
- `sam build` has not been run, so the Lambda package size and the Linux wheels are unchecked.
- moto does not enforce the 3-receive redrive; `poison_test.py` will show it on the real stack.
