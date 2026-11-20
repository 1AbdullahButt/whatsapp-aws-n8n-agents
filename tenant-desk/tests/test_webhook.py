"""HTTP-level tests through FastAPI's TestClient."""
import json

from fastapi.testclient import TestClient

from app.repo_sqlite import SqliteRepository
from app.signature import compute_signature, verify_signature
from app.webhook import create_app
from app.whatsapp_client import FakeWhatsAppClient
from tests.helpers import (TEST_VERIFY_TOKEN, build_payload, make_deps, signed_post,
                           status_update, text_message)


def test_verify_signature_function():
    body = b'{"a": 1}'
    good = compute_signature(body, "secret")
    assert verify_signature(body, good, "secret")
    assert not verify_signature(body, good, "other-secret")
    assert not verify_signature(b'{"a": 2}', good, "secret")
    assert not verify_signature(body, None, "secret")
    assert not verify_signature(body, good.replace("sha256=", ""), "secret")


def test_good_signature_returns_200(client, wa):
    response = signed_post(client, build_payload([text_message("My sink is leaking")]))
    assert response.status_code == 200
    assert len(wa.sent()) == 1


def test_bad_signature_returns_401(client, wa, repo):
    body = json.dumps(build_payload([text_message("My sink is leaking")])).encode()
    response = client.post("/webhook", content=body,
                           headers={"X-Hub-Signature-256": "sha256=" + "0" * 64})
    assert response.status_code == 401
    assert wa.calls == []
    assert repo.list_tickets() == []


def test_missing_signature_returns_401(client, wa):
    body = json.dumps(build_payload([text_message("My sink is leaking")])).encode()
    response = client.post("/webhook", content=body)
    assert response.status_code == 401
    assert wa.calls == []


def test_get_challenge_ok(client):
    response = client.get("/webhook", params={"hub.mode": "subscribe",
                                              "hub.verify_token": TEST_VERIFY_TOKEN,
                                              "hub.challenge": "12345"})
    assert response.status_code == 200
    assert response.text == "12345"


def test_get_challenge_wrong_token_403(client):
    response = client.get("/webhook", params={"hub.mode": "subscribe",
                                              "hub.verify_token": "wrong",
                                              "hub.challenge": "12345"})
    assert response.status_code == 403


def test_status_updates_are_ignored(client, wa, repo):
    response = signed_post(client, build_payload(statuses=[status_update()]))
    assert response.status_code == 200
    assert wa.calls == []
    assert repo.list_tickets() == []


def test_signed_but_invalid_json_still_200(client, wa):
    body = b"not json"
    response = client.post("/webhook", content=body,
                           headers={"X-Hub-Signature-256": compute_signature(body, "test-app-secret")})
    assert response.status_code == 200
    assert wa.calls == []


def test_duplicate_delivery_one_ticket_one_reply(client, wa, repo):
    payload = build_payload([text_message("My sink is leaking", wa_id="wamid.DUP1")])
    assert signed_post(client, payload).status_code == 200
    assert signed_post(client, payload).status_code == 200
    assert len(repo.list_tickets()) == 1
    assert len(wa.sent()) == 1


def test_restart_then_duplicate_still_one_ticket(db_path, transcriber, media_dir):
    payload = build_payload([text_message("My toilet is blocked", wa_id="wamid.RESTART1")])

    # First "server run".
    wa_first = FakeWhatsAppClient()
    first_app = create_app(make_deps(SqliteRepository(db_path), wa_first, transcriber, media_dir))
    signed_post(TestClient(first_app), payload)

    # "Restart": new repository object and new app on the same SQLite file.
    wa_second = FakeWhatsAppClient()
    second_repo = SqliteRepository(db_path)
    second_app = create_app(make_deps(second_repo, wa_second, transcriber, media_dir))
    assert signed_post(TestClient(second_app), payload).status_code == 200

    assert len(second_repo.list_tickets()) == 1
    assert len(wa_first.sent()) == 1
    assert wa_second.sent() == []
