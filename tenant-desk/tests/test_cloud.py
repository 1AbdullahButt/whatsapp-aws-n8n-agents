"""A4 Lambda handlers against moto (fake AWS in memory). No AWS account is used."""
import base64
import json
from datetime import timedelta

import boto3
import pytest
from moto import mock_aws

from app.repo_dynamodb import DynamoRepository
from app.signature import compute_signature
from app.transcriber import FakeTranscriber
from app.whatsapp_client import FakeWhatsAppClient
from cloud import pending, settings, webhook, worker
from tests.helpers import NOW, TENANT_PHONE

REGION = "us-east-1"
SECRET = "test-app-secret"
VERIFY = "test-verify-token"


def text_payload(text, wa_id="wamid.CLOUD1", at=NOW):
    return {"object": "whatsapp_business_account", "entry": [{"id": "0", "changes": [{
        "field": "messages", "value": {
            "messaging_product": "whatsapp", "metadata": {"phone_number_id": "0"},
            "messages": [{"from": TENANT_PHONE, "id": wa_id, "timestamp": str(int(at.timestamp())),
                          "type": "text", "text": {"body": text}}]}}]}]}


def audio_payload(wa_id="wamid.VOICE1", at=NOW):
    payload = text_payload("", wa_id, at)
    message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    message.update({"type": "audio", "audio": {"id": "MEDIA9", "mime_type": "audio/ogg"}})
    del message["text"]
    return payload


@pytest.fixture
def aws(monkeypatch):
    for name, value in {"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
                        "AWS_SESSION_TOKEN": "testing", "AWS_DEFAULT_REGION": REGION,
                        "AWS_REGION": REGION}.items():
        monkeypatch.setenv(name, value)
    settings.secret.cache_clear()
    with mock_aws():
        ssm = boto3.client("ssm", region_name=REGION)
        for name, value in (("app-secret", SECRET), ("verify-token", VERIFY), ("whatsapp-token", "tok")):
            ssm.put_parameter(Name=f"/tenant-desk/{name}", Value=value, Type="SecureString")
        monkeypatch.setenv("APP_SECRET_PARAM", "/tenant-desk/app-secret")
        monkeypatch.setenv("VERIFY_TOKEN_PARAM", "/tenant-desk/verify-token")
        monkeypatch.setenv("WHATSAPP_TOKEN_PARAM", "/tenant-desk/whatsapp-token")
        queue_url = boto3.client("sqs", region_name=REGION).create_queue(QueueName="q")["QueueUrl"]
        monkeypatch.setenv("QUEUE_URL", queue_url)
        boto3.client("dynamodb", region_name=REGION).create_table(
            TableName="tickets", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"},
                       {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"},
                                  {"AttributeName": "sk", "AttributeType": "S"}])
        boto3.client("s3", region_name=REGION).create_bucket(Bucket="media-bucket")
        yield {"queue_url": queue_url}
    settings.secret.cache_clear()


@pytest.fixture
def deps(aws):
    wa = FakeWhatsAppClient(media_bytes=b"OggS-voice")
    return {"repo": DynamoRepository("tickets", region=REGION), "wa_client": wa,
            "transcriber": worker.PendingTranscriber(),
            "media_saver": worker.S3MediaSaver("media-bucket")}


def url_event(method, body="", query=None, headers=None, b64=False):
    """The shape of a Lambda function URL event (payload format 2.0)."""
    if b64:
        body = base64.b64encode(body.encode()).decode()
    return {"requestContext": {"http": {"method": method}}, "queryStringParameters": query,
            "headers": headers or {}, "body": body, "isBase64Encoded": b64}


def sqs_event(*bodies):
    return {"Records": [{"messageId": f"m{i}", "body": b, "attributes": {"ApproximateReceiveCount": "1"}}
                        for i, b in enumerate(bodies)]}


# --- webhook Lambda -----------------------------------------------------------

def test_verify_challenge(aws):
    ok = webhook.handler(url_event("GET", query={"hub.mode": "subscribe", "hub.verify_token": VERIFY,
                                                 "hub.challenge": "42"}))
    assert ok["statusCode"] == 200 and ok["body"] == "42"
    bad = webhook.handler(url_event("GET", query={"hub.mode": "subscribe", "hub.verify_token": "no",
                                                  "hub.challenge": "42"}))
    assert bad["statusCode"] == 403


@pytest.mark.parametrize("b64", [False, True])
def test_signed_post_goes_to_sqs(aws, b64):
    body = json.dumps(text_payload("My sink is leaking"))
    headers = {"X-Hub-Signature-256": compute_signature(body.encode(), SECRET)}
    assert webhook.handler(url_event("POST", body, headers=headers, b64=b64))["statusCode"] == 200
    got = boto3.client("sqs", region_name=REGION).receive_message(QueueUrl=aws["queue_url"])
    assert got["Messages"][0]["Body"] == body


def test_bad_signature_is_rejected_and_not_queued(aws):
    body = json.dumps(text_payload("hi"))
    headers = {"x-hub-signature-256": compute_signature(body.encode(), "wrong")}
    assert webhook.handler(url_event("POST", body, headers=headers))["statusCode"] == 401
    assert webhook.handler(url_event("POST", body))["statusCode"] == 401
    got = boto3.client("sqs", region_name=REGION).receive_message(QueueUrl=aws["queue_url"])
    assert "Messages" not in got


# --- worker Lambda ------------------------------------------------------------

def test_worker_creates_ticket_and_replies_with_text(deps):
    result = worker.handle_event(sqs_event(json.dumps(text_payload("My sink is leaking"))), deps,
                                 now=NOW + timedelta(seconds=5))
    assert result == {"batchItemFailures": []}
    ticket = deps["repo"].get_ticket("TD-0001")
    assert ticket.category == "plumbing"
    [sent] = deps["wa_client"].sent()
    assert sent["method"] == "send_text" and "TD-0001" in sent["text"]


def test_worker_duplicate_delivery_is_ignored(deps):
    body = json.dumps(text_payload("My sink is leaking"))
    worker.handle_event(sqs_event(body), deps, now=NOW)
    worker.handle_event(sqs_event(body), deps, now=NOW)
    assert len(deps["repo"].list_tickets()) == 1
    assert len(deps["wa_client"].sent()) == 1


def test_worker_reports_bad_body_as_failure_for_retry(deps):
    good = json.dumps(text_payload("My sink is leaking"))
    result = worker.handle_event(sqs_event("not json", good), deps, now=NOW)
    assert result == {"batchItemFailures": [{"itemIdentifier": "m0"}]}
    assert len(deps["repo"].list_tickets()) == 1   # the good one still went through


def test_worker_voice_note_goes_to_s3_as_pending(deps):
    worker.handle_event(sqs_event(json.dumps(audio_payload())), deps, now=NOW)
    [stored] = deps["repo"].get_history("TD-0001")[:1]
    assert stored.text == worker.PENDING_TEXT
    assert stored.media_path == "s3://media-bucket/media/wamid.VOICE1.ogg"
    obj = boto3.client("s3", region_name=REGION).get_object(Bucket="media-bucket",
                                                            Key="media/wamid.VOICE1.ogg")
    assert obj["Body"].read() == b"OggS-voice"


def test_worker_never_sends_a_real_template(deps, monkeypatch):
    # An old message (outside the 24h window) would need a template.
    old = NOW - timedelta(days=3)
    worker.handle_event(sqs_event(json.dumps(text_payload("leak", at=old))), deps, now=NOW)
    assert deps["wa_client"].sent()[-1]["method"] == "send_template"   # chosen...
    from app.whatsapp_client import WhatsAppClient
    assert WhatsAppClient("t", "p").send_template("x", "ticket_update", []) == {"simulated": True}  # ...but blocked for real


# --- helper scripts -------------------------------------------------------------

def test_put_secrets_stores_secure_strings(aws):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aws"))
    import put_secrets
    ssm = boto3.client("ssm", region_name=REGION)
    put_secrets.put_all(ssm, {"WHATSAPP_TOKEN": "a", "WHATSAPP_APP_SECRET": "b", "WHATSAPP_VERIFY_TOKEN": "c"})
    param = ssm.get_parameter(Name="/tenant-desk/app-secret", WithDecryption=True)["Parameter"]
    assert param["Type"] == "SecureString" and param["Value"] == "b"


def test_build_has_lambda_code_but_no_server_or_secrets():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aws"))
    import build
    build.main()
    files = {p.relative_to(build.BUILD).as_posix() for p in build.BUILD.rglob("*") if p.is_file()}
    assert {"cloud/webhook.py", "cloud/worker.py", "app/service.py", "shared/config.py",
            "requirements.txt"} <= files
    assert "app/webhook.py" not in files
    assert not any(name.endswith(".env") or ".venv" in name for name in files)


# --- pending transcription (runs on a PC) --------------------------------------

def test_transcribe_pending_fills_text_and_updates_ticket(deps):
    worker.handle_event(sqs_event(json.dumps(audio_payload())), deps, now=NOW)
    assert deps["repo"].get_ticket("TD-0001").category == "other"
    fake = FakeTranscriber("I can smell gas in the kitchen")
    done = pending.transcribe_pending(deps["repo"], boto3.client("s3", region_name=REGION), fake, NOW)
    assert done == [("TD-0001", "I can smell gas in the kitchen")]
    ticket = deps["repo"].get_ticket("TD-0001")
    assert ticket.category == "heating" and ticket.urgent
    assert deps["repo"].get_history("TD-0001")[0].text == "I can smell gas in the kitchen"
    # Running again finds nothing left to do.
    assert pending.transcribe_pending(deps["repo"], boto3.client("s3", region_name=REGION), fake, NOW) == []
