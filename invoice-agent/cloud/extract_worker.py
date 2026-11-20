"""Worker Lambda: S3 "object created" events arrive via SQS; extract each PDF into DynamoDB.

DynamoDB items (single table, pk/sk):
    INVOICE#<s3 key>   META   file_id, fields, confidences, flags, status, duplicate_of, processed_at
    DUPKEY#<dup key>   SEEN   file_id of the first invoice with this vendor + number + total

status: "extracted", "needs_review" (blocking flags, e.g. no_text_layer) or "duplicate".
Processing the same S3 key again overwrites its item and is not called a duplicate.
"""
import io
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import unquote_plus

import boto3
from botocore.exceptions import ClientError

from extractor.duplicates import duplicate_key
from extractor.pipeline import extract_invoice
from extractor.validate import blocking_flags
from shared.logging_setup import get_logger

log = get_logger("invoice-agent.lambda.extract")

MAX_PDF_BYTES = 10 * 1024 * 1024   # same limit as the local API


def region():
    return os.environ.get("AWS_REGION", "us-east-1")


def s3_objects(sqs_body):
    """(bucket, key, size) for each object in one S3 event. S3's setup test event has none."""
    event = json.loads(sqs_body)
    if event.get("Event") == "s3:TestEvent":
        return []
    found = []
    for record in event.get("Records", []):
        obj = record["s3"]["object"]
        found.append((record["s3"]["bucket"]["name"], unquote_plus(obj["key"]), obj.get("size", 0)))
    return found


def to_dynamo(value):
    """DynamoDB wants Decimal instead of float; a JSON round trip converts the whole dict."""
    return json.loads(json.dumps(value), parse_float=Decimal)


def check_duplicate(table, fields, file_id):
    """Return the first file id with the same duplicate key, or None. Remembers new keys."""
    key = duplicate_key(fields.get("vendor"), fields.get("invoice_number"), fields.get("total"))
    if key is None:
        return None
    try:
        # Store the key unless another file already has it (same file again is fine).
        table.put_item(Item={"pk": f"DUPKEY#{key}", "sk": "SEEN", "file_id": file_id},
                       ConditionExpression="attribute_not_exists(pk) OR file_id = :f",
                       ExpressionAttributeValues={":f": file_id})
        return None
    except ClientError as error:
        if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        return table.get_item(Key={"pk": f"DUPKEY#{key}", "sk": "SEEN"})["Item"]["file_id"]


def process_object(bucket, key, size, s3, table, now):
    """Extract one PDF and store the result. Raises if the file cannot be read (-> retry, DLQ)."""
    if size > MAX_PDF_BYTES:
        raise ValueError(f"{key} is {size} bytes, over the {MAX_PDF_BYTES} limit")
    data = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    extraction = extract_invoice(io.BytesIO(data), key)
    duplicate_of = check_duplicate(table, extraction["fields"], key)
    if duplicate_of:
        status = "duplicate"
    elif blocking_flags(extraction["flags"]):
        status = "needs_review"
    else:
        status = "extracted"
    item = {"pk": f"INVOICE#{key}", "sk": "META", "file_id": key, "bucket": bucket,
            "fields": extraction["fields"], "confidences": extraction["confidences"],
            "flags": extraction["flags"], "status": status, "duplicate_of": duplicate_of,
            "processed_at": now.isoformat(timespec="seconds")}
    table.put_item(Item=to_dynamo(item))
    log.info("%s -> %s %s", key, status, ",".join(extraction["flags"]))
    return status


def handle_event(event, s3, table, now=None):
    """SQS batch -> {"batchItemFailures": [...]} so only failed messages are retried."""
    failures = []
    for record in event.get("Records", []):
        try:
            for bucket, key, size in s3_objects(record["body"]):
                process_object(bucket, key, size, s3, table, now or datetime.now(timezone.utc))
        except Exception:
            log.exception("Failed SQS message %s (receive count %s)", record.get("messageId"),
                          record.get("attributes", {}).get("ApproximateReceiveCount"))
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}


_clients = None


def handler(event, context=None):
    global _clients
    if _clients is None:
        _clients = (boto3.client("s3", region_name=region()),
                    boto3.resource("dynamodb", region_name=region()).Table(os.environ["TABLE_NAME"]))
    s3, table = _clients
    return handle_event(event, s3, table)
