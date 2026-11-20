"""Send messages and download media through the WhatsApp Cloud API (Graph API).

WhatsAppClient talks to Meta over HTTPS with httpx.
FakeWhatsAppClient has the same methods but only records the calls,
so tests never touch the network.
"""
import httpx

from shared.logging_setup import get_logger

GRAPH_URL = "https://graph.facebook.com/v21.0"
log = get_logger("tenant_desk.whatsapp")


class WhatsAppClient:
    def __init__(self, token, phone_number_id, base_url=GRAPH_URL, timeout=15.0,
                 allow_templates=False):
        self.token = token
        self.phone_number_id = phone_number_id
        self.base_url = base_url
        self.timeout = timeout
        # Template messages can be charged by Meta, so they are blocked unless
        # someone deliberately passes allow_templates=True in code.
        self.allow_templates = allow_templates

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _post_message(self, body):
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        response = httpx.post(url, json=body, headers=self._headers(), timeout=self.timeout)
        if response.is_error:
            # Meta's error JSON says what went wrong (code, message). It holds no secrets.
            log.error("Graph API error %s: %s", response.status_code, response.text[:500])
        response.raise_for_status()
        return response.json()

    def send_text(self, to, text):
        """Free-form text. Only allowed inside the 24-hour window."""
        return self._post_message({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        })

    def send_template(self, to, name, params, language="en"):
        """Pre-approved template message, the only kind allowed outside the window.

        `params` fills the {{1}}, {{2}}, ... placeholders in the template body.
        Blocked (nothing is sent) unless allow_templates is True.
        """
        if not self.allow_templates:
            log.warning("Template %s to tenant NOT sent: template sends are disabled "
                        "(simulated only, they can be charged).", name)
            return {"simulated": True}
        return self._post_message({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": name,
                "language": {"code": language},
                "components": [{
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in params],
                }],
            },
        })

    def download_media(self, media_id):
        """Two steps: ask Graph API for the media URL, then download it with our token."""
        lookup = httpx.get(f"{self.base_url}/{media_id}", headers=self._headers(),
                           timeout=self.timeout)
        lookup.raise_for_status()
        media_url = lookup.json()["url"]
        download = httpx.get(media_url, headers=self._headers(), timeout=self.timeout)
        download.raise_for_status()
        return download.content


class FakeWhatsAppClient:
    """Records every call in self.calls instead of sending anything."""

    def __init__(self, media_bytes=b"fake-audio-bytes"):
        self.calls = []
        self.media_bytes = media_bytes

    def send_text(self, to, text):
        self.calls.append({"method": "send_text", "to": to, "text": text})
        return {"messages": [{"id": f"wamid.fake.out.{len(self.calls)}"}]}

    def send_template(self, to, name, params, language="en"):
        self.calls.append({"method": "send_template", "to": to, "name": name,
                           "params": list(params), "language": language})
        return {"messages": [{"id": f"wamid.fake.out.{len(self.calls)}"}]}

    def download_media(self, media_id):
        self.calls.append({"method": "download_media", "media_id": media_id})
        return self.media_bytes

    def sent(self):
        """Only the outgoing messages (text and template), not media downloads."""
        return [c for c in self.calls if c["method"] in ("send_text", "send_template")]
