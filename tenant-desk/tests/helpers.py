"""Build synthetic Meta webhook payloads for tests. All data is made up."""
import json
from datetime import datetime, timedelta, timezone

from app.parser import IncomingMessage
from app.signature import compute_signature
from app.webhook import Deps

TEST_SECRET = "test-app-secret"
TEST_VERIFY_TOKEN = "test-verify-token"
TENANT_PHONE = "15550000001"
OTHER_PHONE = "15550000002"

# A fixed "now" in November (a winter month) so tests are repeatable.
NOW = datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)


def text_message(text, wa_id="wamid.TEST001", phone=TENANT_PHONE, at=None):
    at = at or (NOW - timedelta(minutes=1))
    return {"from": phone, "id": wa_id, "timestamp": str(int(at.timestamp())),
            "type": "text", "text": {"body": text}}


def audio_message(media_id="MEDIA001", wa_id="wamid.AUDIO001", phone=TENANT_PHONE, at=None):
    at = at or (NOW - timedelta(minutes=1))
    return {"from": phone, "id": wa_id, "timestamp": str(int(at.timestamp())),
            "type": "audio",
            "audio": {"id": media_id, "mime_type": "audio/ogg; codecs=opus", "voice": True}}


def status_update(wa_id="wamid.OUT001"):
    return {"id": wa_id, "status": "delivered", "timestamp": "1763632800",
            "recipient_id": TENANT_PHONE}


def build_payload(messages=(), statuses=()):
    """Wrap messages in the entry/changes/value envelope Meta sends."""
    value = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "15550009999", "phone_number_id": "100000000000001"},
    }
    if messages:
        value["contacts"] = [{"profile": {"name": "Test Tenant"}, "wa_id": messages[0]["from"]}]
        value["messages"] = list(messages)
    if statuses:
        value["statuses"] = list(statuses)
    return {"object": "whatsapp_business_account",
            "entry": [{"id": "200000000000001", "changes": [{"field": "messages", "value": value}]}]}


def signed_post(client, payload, secret=TEST_SECRET):
    """POST a payload with a correct X-Hub-Signature-256 header."""
    body = json.dumps(payload).encode("utf-8")
    headers = {"X-Hub-Signature-256": compute_signature(body, secret),
               "Content-Type": "application/json"}
    return client.post("/webhook", content=body, headers=headers)


def make_deps(repo, wa, transcriber, media_dir, now=NOW):
    """Dependencies for create_app, with fakes and a fixed clock."""
    return Deps(repo=repo, wa_client=wa, transcriber=transcriber, media_dir=str(media_dir),
                app_secret=TEST_SECRET, verify_token=TEST_VERIFY_TOKEN, clock=lambda: now)


def incoming_text(text, wa_id="wamid.TEST001", phone=TENANT_PHONE, at=None):
    """An IncomingMessage directly, for service tests that skip HTTP."""
    return IncomingMessage(wa_message_id=wa_id, from_phone=phone,
                           timestamp=at or (NOW - timedelta(minutes=1)), kind="text", text=text)
