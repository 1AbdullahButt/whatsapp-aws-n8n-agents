"""Transcribe voice notes the cloud worker left as "transcription pending".

Run on a PC (aws/transcribe_pending.py), not in Lambda: faster-whisper is
free and local, AWS Transcribe is not on the Free plan.

For each pending message: download the audio from S3, transcribe, write
the text back, and update the ticket (category if it was "other", urgent
if the transcript is urgent). Nothing is sent to the tenant.
"""
import tempfile
from pathlib import Path

from app.classifier import classify
from cloud.worker import PENDING_TEXT


def split_s3_url(url):
    """'s3://bucket/media/x.ogg' -> ('bucket', 'media/x.ogg')."""
    bucket, key = url.removeprefix("s3://").split("/", 1)
    return bucket, key


def pending_items(table):
    """DynamoDB message items whose text is still the placeholder (a Scan; fine for a demo)."""
    items, kwargs = [], {}
    while True:
        page = table.scan(FilterExpression="#t = :p",
                          ExpressionAttributeNames={"#t": "text"},
                          ExpressionAttributeValues={":p": PENDING_TEXT}, **kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def transcribe_pending(repo, s3, transcriber, now):
    """Returns a list of (ticket id, transcript) for what was done."""
    done = []
    for item in pending_items(repo.table):
        ticket_id = item["pk"].removeprefix("TICKET#")
        bucket, key = split_s3_url(item["media_path"])
        with tempfile.TemporaryDirectory() as folder:
            local = Path(folder) / Path(key).name
            s3.download_file(bucket, key, str(local))
            text = transcriber.transcribe(str(local))
        repo.table.update_item(Key={"pk": item["pk"], "sk": item["sk"]},
                               UpdateExpression="SET #t = :t",
                               ExpressionAttributeNames={"#t": "text"},
                               ExpressionAttributeValues={":t": text})
        update_ticket(repo, ticket_id, text, now)
        done.append((ticket_id, text))
    return done


def update_ticket(repo, ticket_id, text, now):
    result = classify(text, now.month)
    ticket = repo.get_ticket(ticket_id)
    if ticket.category == "other" and result.category != "other":
        repo.table.update_item(Key={"pk": f"TICKET#{ticket_id}", "sk": "META"},
                               UpdateExpression="SET category = :c",
                               ExpressionAttributeValues={":c": result.category})
    if result.urgent and not ticket.urgent:
        repo.mark_urgent(ticket_id)
