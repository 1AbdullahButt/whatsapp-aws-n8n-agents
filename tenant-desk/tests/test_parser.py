from app.parser import parse_webhook
from tests.helpers import (NOW, TENANT_PHONE, audio_message, build_payload, status_update,
                           text_message)


def test_parses_text_message():
    payload = build_payload([text_message("Hello", wa_id="wamid.A", at=NOW)])
    [msg] = parse_webhook(payload)
    assert msg.wa_message_id == "wamid.A"
    assert msg.from_phone == TENANT_PHONE
    assert msg.kind == "text"
    assert msg.text == "Hello"
    assert msg.timestamp == NOW


def test_parses_audio_message():
    [msg] = parse_webhook(build_payload([audio_message(media_id="MEDIA9")]))
    assert msg.kind == "audio"
    assert msg.media_id == "MEDIA9"


def test_ignores_status_updates_and_other_types():
    image = {"from": TENANT_PHONE, "id": "wamid.IMG", "timestamp": "1763632800",
             "type": "image", "image": {"id": "IMG1"}}
    payload = build_payload([image], statuses=[status_update()])
    assert parse_webhook(payload) == []


def test_empty_payload():
    assert parse_webhook({}) == []
