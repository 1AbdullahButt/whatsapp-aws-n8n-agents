"""Webhook Lambda behind a function URL.

GET  -> Meta's verify-token challenge.
POST -> check X-Hub-Signature-256, put the raw body on SQS, answer 200 at once.
The slow work (DynamoDB, Graph API) happens in the worker, so Meta never
waits on it and does not retry because of a slow reply.
"""
import base64

import boto3

from app.signature import verify_signature
from cloud import settings
from shared.logging_setup import get_logger

log = get_logger("tenant_desk.lambda.webhook")


def response(status, body=""):
    return {"statusCode": status, "headers": {"Content-Type": "text/plain"}, "body": body}


def raw_body(event):
    """The body exactly as Meta sent it, as bytes (needed for the signature)."""
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    return body.encode("utf-8")


def handle_verify(event):
    params = event.get("queryStringParameters") or {}
    if (params.get("hub.mode") == "subscribe"
            and params.get("hub.verify_token") == settings.secret("verify_token")):
        return response(200, params.get("hub.challenge", ""))
    return response(403, "forbidden")


def handle_post(event, sqs=None):
    body = raw_body(event)
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if not verify_signature(body, headers.get("x-hub-signature-256"), settings.secret("app_secret")):
        log.warning("Rejected webhook with bad or missing signature")
        return response(401, "invalid signature")
    sqs = sqs or boto3.client("sqs", region_name=settings.region())
    sqs.send_message(QueueUrl=settings.env("QUEUE_URL"), MessageBody=body.decode("utf-8"))
    return response(200, "ok")


def handler(event, context=None):
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    if method == "GET":
        return handle_verify(event)
    if method == "POST":
        return handle_post(event)
    return response(405, "method not allowed")
