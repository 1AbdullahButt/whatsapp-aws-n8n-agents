"""B4 extraction Lambda against moto (fake S3, SQS and DynamoDB in memory). No AWS account."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from cloud import extract_worker

PROJECT = Path(__file__).resolve().parents[1]
INVOICE_DIR = PROJECT / "synthetic" / "invoices"
EXPECTED = json.loads((PROJECT / "synthetic" / "expected.json").read_text(encoding="utf-8"))
REGION = "us-east-1"
BUCKET = "inbox-test"
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def aws(monkeypatch):
    for name, value in {"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
                        "AWS_SESSION_TOKEN": "testing", "AWS_DEFAULT_REGION": REGION}.items():
        monkeypatch.setenv(name, value)
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET)
        boto3.client("dynamodb", region_name=REGION).create_table(
            TableName="invoices", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"},
                       {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"},
                                  {"AttributeName": "sk", "AttributeType": "S"}])
        table = boto3.resource("dynamodb", region_name=REGION).Table("invoices")
        yield s3, table


def s3_event(key, size=1000):
    """What S3 puts on the queue for one upload (keys arrive URL-encoded)."""
    return json.dumps({"Records": [{"s3": {"bucket": {"name": BUCKET},
                                           "object": {"key": key.replace(" ", "+"), "size": size}}}]})


def sqs_event(*bodies):
    return {"Records": [{"messageId": f"m{i}", "body": b, "attributes": {"ApproximateReceiveCount": "1"}}
                        for i, b in enumerate(bodies)]}


def upload_and_handle(s3, table, name, key=None):
    key = key or name
    s3.upload_file(str(INVOICE_DIR / name), BUCKET, key)
    return extract_worker.handle_event(sqs_event(s3_event(key)), s3, table, now=NOW)


def item(table, key):
    return table.get_item(Key={"pk": f"INVOICE#{key}", "sk": "META"}).get("Item")


def test_all_synthetic_invoices_get_the_same_results_as_locally(aws):
    s3, table = aws
    for name in sorted(EXPECTED):
        assert upload_and_handle(s3, table, name) == {"batchItemFailures": []}
    statuses = {name: item(table, name)["status"] for name in EXPECTED}
    assert statuses["inv_09_resent_copy.pdf"] == "duplicate"
    assert item(table, "inv_09_resent_copy.pdf")["duplicate_of"] == "inv_01_classic_usd.pdf"
    assert statuses["inv_12_image_only.pdf"] == "needs_review"
    assert statuses["inv_11_malformed.pdf"] == "needs_review"
    assert statuses["inv_01_classic_usd.pdf"] == "extracted"
    first = item(table, "inv_01_classic_usd.pdf")["fields"]
    assert first["invoice_number"] == EXPECTED["inv_01_classic_usd.pdf"]["fields"]["invoice_number"]
    assert float(first["total"]) == EXPECTED["inv_01_classic_usd.pdf"]["fields"]["total"]


def test_same_file_again_is_not_a_duplicate_of_itself(aws):
    s3, table = aws
    upload_and_handle(s3, table, "inv_01_classic_usd.pdf")
    upload_and_handle(s3, table, "inv_01_classic_usd.pdf")
    assert item(table, "inv_01_classic_usd.pdf")["status"] == "extracted"


def test_key_with_spaces_is_decoded(aws):
    s3, table = aws
    upload_and_handle(s3, table, "inv_02_twocol_eur.pdf", key="march invoices/inv 02.pdf")
    assert item(table, "march invoices/inv 02.pdf")["status"] in ("extracted", "needs_review")


def test_broken_pdf_is_reported_for_retry(aws):
    s3, table = aws
    s3.put_object(Bucket=BUCKET, Key="broken.pdf", Body=b"this is not a pdf")
    s3.upload_file(str(INVOICE_DIR / "inv_01_classic_usd.pdf"), BUCKET, "good.pdf")
    result = extract_worker.handle_event(sqs_event(s3_event("broken.pdf"), s3_event("good.pdf")),
                                         s3, table, now=NOW)
    assert result == {"batchItemFailures": [{"itemIdentifier": "m0"}]}
    assert item(table, "broken.pdf") is None
    assert item(table, "good.pdf")["status"] == "extracted"


def test_oversized_file_is_refused_without_download(aws):
    s3, table = aws
    big = extract_worker.MAX_PDF_BYTES + 1
    result = extract_worker.handle_event(sqs_event(s3_event("huge.pdf", size=big)), s3, table, now=NOW)
    assert result["batchItemFailures"] == [{"itemIdentifier": "m0"}]


def test_s3_setup_test_event_is_ignored(aws):
    s3, table = aws
    body = json.dumps({"Service": "Amazon S3", "Event": "s3:TestEvent", "Bucket": BUCKET})
    assert extract_worker.handle_event(sqs_event(body), s3, table, now=NOW) == {"batchItemFailures": []}


def test_s3_notification_reaches_sqs_and_the_worker(aws):
    """Wire S3 -> SQS like the template does, upload, and feed the queued event to the worker."""
    s3, table = aws
    sqs = boto3.client("sqs", region_name=REGION)
    queue_url = sqs.create_queue(QueueName="uploads")["QueueUrl"]
    queue_arn = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    s3.put_bucket_notification_configuration(Bucket=BUCKET, NotificationConfiguration={
        "QueueConfigurations": [{"QueueArn": queue_arn, "Events": ["s3:ObjectCreated:*"],
                                 "Filter": {"Key": {"FilterRules": [{"Name": "suffix", "Value": ".pdf"}]}}}]})
    s3.upload_file(str(INVOICE_DIR / "inv_03_labelright_gbp.pdf"), BUCKET, "inv_03_labelright_gbp.pdf")
    messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)["Messages"]
    bodies = [m["Body"] for m in messages if "s3:TestEvent" not in m["Body"]]
    assert len(bodies) == 1
    extract_worker.handle_event(sqs_event(*bodies), s3, table, now=NOW)
    assert item(table, "inv_03_labelright_gbp.pdf")["fields"]["vendor"] == \
        EXPECTED["inv_03_labelright_gbp.pdf"]["fields"]["vendor"]


def test_build_has_only_the_lambda_code():
    sys.path.insert(0, str(PROJECT / "aws"))
    import build
    build.main()
    files = {p.relative_to(build.BUILD).as_posix() for p in build.BUILD.rglob("*") if p.is_file()}
    assert {"cloud/extract_worker.py", "extractor/pipeline.py", "extractor/duplicates.py",
            "shared/logging_setup.py", "requirements.txt"} <= files
    assert not any(name.endswith(("api.py", "review_queue.py", ".env")) for name in files)
    assert (build.BUILD / "requirements.txt").read_text().startswith("pdfplumber==")
