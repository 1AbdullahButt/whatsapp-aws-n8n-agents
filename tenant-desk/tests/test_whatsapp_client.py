"""The real WhatsAppClient must never send a template unless told to (cost guard)."""
import httpx

from app import whatsapp_client
from app.whatsapp_client import WhatsAppClient


class FakeResponse:
    status_code = 200
    is_error = False
    text = "{}"

    def raise_for_status(self):
        pass

    def json(self):
        return {"messages": [{"id": "wamid.out"}]}


def record_posts(monkeypatch):
    posts = []

    def fake_post(url, json, headers, timeout):
        posts.append(json)
        return FakeResponse()

    monkeypatch.setattr(whatsapp_client.httpx, "post", fake_post)
    return posts


def test_template_is_blocked_by_default(monkeypatch):
    posts = record_posts(monkeypatch)
    client = WhatsAppClient("token", "123")
    assert client.send_template("15550000001", "ticket_update", ["TD-0001", "hi"]) == {"simulated": True}
    assert posts == []


def test_template_sent_only_when_allowed(monkeypatch):
    posts = record_posts(monkeypatch)
    client = WhatsAppClient("token", "123", allow_templates=True)
    client.send_template("15550000001", "ticket_update", ["TD-0001", "hi"])
    assert posts[0]["type"] == "template"


def test_text_still_sent(monkeypatch):
    posts = record_posts(monkeypatch)
    WhatsAppClient("token", "123").send_text("15550000001", "Ticket TD-0001 logged")
    assert posts[0]["type"] == "text"


def test_graph_error_is_raised(monkeypatch):
    request = httpx.Request("POST", "https://graph.facebook.com/v21.0/123/messages")
    bad = httpx.Response(400, json={"error": {"code": 131030}}, request=request)
    monkeypatch.setattr(whatsapp_client.httpx, "post", lambda *a, **k: bad)
    try:
        WhatsAppClient("token", "123").send_text("15550000001", "x")
    except httpx.HTTPStatusError:
        pass
    else:
        raise AssertionError("expected HTTPStatusError")
