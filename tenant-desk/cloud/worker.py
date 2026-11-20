"""Worker Lambda: reads webhook bodies from SQS and runs the normal service flow.

One SQS message = one webhook body (it can hold several WhatsApp messages).
If handling fails, the SQS message is reported as failed, SQS retries it,
and after 3 receives it moves to the dead-letter queue.

Note on dedupe: mark_seen runs first (see app/service.py). So a retry only
helps when the failure happens before that, for example a body that is not
valid JSON or a DynamoDB outage. A failed reply after mark_seen is not resent.
"""
import json
from datetime import datetime, timezone

import boto3

from app.parser import parse_webhook
from app.repo_dynamodb import DynamoRepository
from app.service import handle_message, safe_filename
from app.whatsapp_client import WhatsAppClient
from cloud import settings
from shared.logging_setup import get_logger

log = get_logger("tenant_desk.lambda.worker")

PENDING_TEXT = "[voice note - transcription pending]"


class PendingTranscriber:
    """AWS Transcribe is not on the Free plan, so the cloud worker does not
    transcribe. It stores a placeholder; aws/transcribe_pending.py fills it in."""

    def transcribe(self, audio_path):
        return PENDING_TEXT


class S3MediaSaver:
    """Download the voice note from Meta and store it in S3. Returns an s3:// URL."""

    def __init__(self, bucket, s3=None):
        self.bucket = bucket
        self.s3 = s3 or boto3.client("s3", region_name=settings.region())

    def __call__(self, wa_client, msg):
        key = f"media/{safe_filename(msg.wa_message_id)}.ogg"
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=wa_client.download_media(msg.media_id),
                           ContentType="audio/ogg")
        return f"s3://{self.bucket}/{key}"


def build_deps():
    """Real objects for Lambda. Tests build their own with moto and fakes."""
    return {
        "repo": DynamoRepository(settings.env("TABLE_NAME"), region=settings.region()),
        "wa_client": WhatsAppClient(settings.secret("whatsapp_token"), settings.env("PHONE_NUMBER_ID")),
        "transcriber": PendingTranscriber(),
        "media_saver": S3MediaSaver(settings.env("MEDIA_BUCKET")),
    }


def process_body(body, deps, now):
    """Handle every WhatsApp message in one webhook body. Raises on failure."""
    payload = json.loads(body)   # a bad body raises here, before any dedupe
    for msg in parse_webhook(payload):
        result = handle_message(msg, deps["repo"], deps["wa_client"], deps["transcriber"],
                                None, now, media_saver=deps["media_saver"])
        log.info("message %s -> %s %s", msg.wa_message_id, result.status, result.ticket_id)


def handle_event(event, deps, now=None):
    """SQS batch -> {"batchItemFailures": [...]} so only failed messages are retried."""
    failures = []
    for record in event.get("Records", []):
        try:
            process_body(record["body"], deps, now or datetime.now(timezone.utc))
        except Exception:
            log.exception("Failed SQS message %s (receive count %s)", record.get("messageId"),
                          record.get("attributes", {}).get("ApproximateReceiveCount"))
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}


_deps = None


def handler(event, context=None):
    global _deps
    if _deps is None:
        _deps = build_deps()   # once per container, reused while it stays warm
    return handle_event(event, _deps)
