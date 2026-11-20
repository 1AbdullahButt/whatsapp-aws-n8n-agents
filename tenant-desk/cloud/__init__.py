"""AWS version of the tenant desk (milestone A4).

    Meta -> Lambda function URL (webhook.py): check signature, put raw body on SQS, return 200
         -> SQS (3 tries, then dead-letter queue)
         -> worker Lambda (worker.py): dedupe in DynamoDB, ticket, plain-text reply
    Voice notes are stored in S3 and marked "transcription pending"; a local
    script (aws/transcribe_pending.py) transcribes them with faster-whisper,
    because AWS Transcribe is not on the Free plan.

The handlers reuse app/ (signature, parser, service, DynamoRepository,
WhatsAppClient). They never import app.webhook, so FastAPI is not needed in Lambda.
"""
