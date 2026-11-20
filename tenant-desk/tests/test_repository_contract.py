"""The same tests run against SQLite and DynamoDB (mocked locally by moto)."""
from datetime import timedelta

import boto3
import pytest
from moto import mock_aws

from app.repo_dynamodb import DynamoRepository
from app.repo_sqlite import SqliteRepository
from tests.helpers import NOW, OTHER_PHONE, TENANT_PHONE

TABLE = "tenant-desk-test"


@pytest.fixture
def dynamo_repo(monkeypatch):
    # Fake credentials so boto3 never looks for real ones.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        boto3.client("dynamodb", region_name="us-east-1").create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"},
                       {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"},
                                  {"AttributeName": "sk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield DynamoRepository(TABLE, region="us-east-1")


@pytest.fixture(params=["sqlite", "dynamodb"])
def any_repo(request, tmp_path):
    if request.param == "sqlite":
        return SqliteRepository(tmp_path / "contract.db")
    return request.getfixturevalue("dynamo_repo")


def test_mark_seen_dedupes(any_repo):
    assert any_repo.mark_seen("wamid.X") is True
    assert any_repo.mark_seen("wamid.X") is False
    assert any_repo.mark_seen("wamid.Y") is True


def test_ticket_numbers_count_up(any_repo):
    first = any_repo.create_ticket(TENANT_PHONE, "plumbing", False)
    second = any_repo.create_ticket(OTHER_PHONE, "heating", True)
    assert first.id == "TD-0001"
    assert second.id == "TD-0002"
    assert first.mode == "bot" and first.status == "open"


def test_get_ticket_and_open_ticket(any_repo):
    created = any_repo.create_ticket(TENANT_PHONE, "locks", True)
    assert any_repo.get_ticket(created.id).urgent is True
    assert any_repo.get_open_ticket(TENANT_PHONE).id == created.id
    assert any_repo.get_open_ticket(OTHER_PHONE) is None
    assert any_repo.get_ticket("TD-9999") is None


def test_set_mode(any_repo):
    ticket = any_repo.create_ticket(TENANT_PHONE, "pests", False)
    any_repo.set_mode(ticket.id, "human")
    assert any_repo.get_ticket(ticket.id).mode == "human"
    with pytest.raises(ValueError):
        any_repo.set_mode(ticket.id, "robot")


def test_mark_urgent(any_repo):
    ticket = any_repo.create_ticket(TENANT_PHONE, "plumbing", False)
    any_repo.mark_urgent(ticket.id)
    assert any_repo.get_ticket(ticket.id).urgent


def test_close_ticket_then_new_message_needs_new_ticket(any_repo):
    first = any_repo.create_ticket(TENANT_PHONE, "plumbing", False)
    any_repo.close_ticket(first.id)
    assert any_repo.get_ticket(first.id).status == "closed"
    assert any_repo.get_open_ticket(TENANT_PHONE) is None
    second = any_repo.create_ticket(TENANT_PHONE, "heating", False)
    assert second.id == "TD-0002"
    assert any_repo.get_open_ticket(TENANT_PHONE).id == "TD-0002"


def test_history_in_order(any_repo):
    ticket = any_repo.create_ticket(TENANT_PHONE, "plumbing", False)
    any_repo.add_message(ticket.id, "in", "Leak", NOW, wa_message_id="wamid.1")
    any_repo.add_message(ticket.id, "out", "Logged", NOW)
    any_repo.add_message(ticket.id, "staff", "Plumber Tuesday", NOW,
                         media_path=None)
    any_repo.add_message(ticket.id, "in", "voice", NOW, wa_message_id="wamid.2",
                         media_path="media/wamid.2.ogg")
    history = any_repo.get_history(ticket.id)
    assert [m.direction for m in history] == ["in", "out", "staff", "in"]
    assert history[0].wa_message_id == "wamid.1"
    assert history[3].media_path == "media/wamid.2.ogg"
    assert history[0].at == NOW


def test_list_tickets(any_repo):
    any_repo.create_ticket(TENANT_PHONE, "plumbing", False)
    any_repo.create_ticket(OTHER_PHONE, "other", False)
    assert [t.id for t in any_repo.list_tickets()] == ["TD-0001", "TD-0002"]


def test_last_inbound_time(any_repo):
    assert any_repo.last_inbound_time(TENANT_PHONE) is None
    ticket = any_repo.create_ticket(TENANT_PHONE, "plumbing", False)
    any_repo.add_message(ticket.id, "in", "first", NOW - timedelta(hours=5))
    any_repo.add_message(ticket.id, "in", "second", NOW - timedelta(hours=1))
    any_repo.add_message(ticket.id, "out", "bot reply", NOW)  # outbound does not count
    assert any_repo.last_inbound_time(TENANT_PHONE) == NOW - timedelta(hours=1)
    assert any_repo.last_inbound_time(OTHER_PHONE) is None
