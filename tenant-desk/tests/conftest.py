"""Shared fixtures: fake clients, a SQLite repo in a temp folder, and a test app."""
import pytest
from fastapi.testclient import TestClient

from app.repo_sqlite import SqliteRepository
from app.transcriber import FakeTranscriber
from app.webhook import create_app
from app.whatsapp_client import FakeWhatsAppClient
from tests.helpers import make_deps


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "tenant_desk.db"


@pytest.fixture
def repo(db_path):
    return SqliteRepository(db_path)


@pytest.fixture
def wa():
    return FakeWhatsAppClient()


@pytest.fixture
def transcriber():
    return FakeTranscriber("the boiler is broken")


@pytest.fixture
def media_dir(tmp_path):
    return tmp_path / "media"


@pytest.fixture
def client(repo, wa, transcriber, media_dir):
    return TestClient(create_app(make_deps(repo, wa, transcriber, media_dir)))
