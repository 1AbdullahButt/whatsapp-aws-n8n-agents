"""Turn a Meta WhatsApp Cloud API webhook payload into simple objects.

Payload shape (only the parts we use):
    {"entry": [{"changes": [{"value": {
        "messages": [{"id": "wamid...", "from": "15550000001",
                      "timestamp": "1763632800", "type": "text",
                      "text": {"body": "My sink is leaking"}}],
        "statuses": [...]   # delivery/read receipts, ignored
    }}]}]}

Only "text" and "audio" messages are kept. Status updates and other
message types (image, sticker, location, ...) are skipped.
"""
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class IncomingMessage:
    wa_message_id: str
    from_phone: str
    timestamp: datetime  # UTC
    kind: str  # "text" or "audio"
    text: str = ""
    media_id: str = ""


def parse_webhook(payload):
    """Return a list of IncomingMessage found in the payload."""
    found = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for raw in value.get("messages", []):
                message = _parse_one(raw)
                if message is not None:
                    found.append(message)
    return found


def _parse_one(raw):
    """Convert one raw message dict, or return None if we do not handle it."""
    kind = raw.get("type")
    if kind not in ("text", "audio"):
        return None
    message = IncomingMessage(
        wa_message_id=raw["id"],
        from_phone=raw["from"],
        timestamp=_to_datetime(raw["timestamp"]),
        kind=kind,
    )
    if kind == "text":
        message.text = raw.get("text", {}).get("body", "")
    else:
        message.media_id = raw.get("audio", {}).get("id", "")
    return message


def _to_datetime(unix_seconds):
    """Meta sends the time as a string of seconds since 1970 (UTC)."""
    return datetime.fromtimestamp(int(unix_seconds), tz=timezone.utc)
