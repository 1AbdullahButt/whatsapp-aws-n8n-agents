"""Pure helper functions in scripts/ (no Docker, no network)."""
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from review import host_resume_url                     # noqa: E402
from sanitize_workflow import check_clean, sanitize    # noqa: E402

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / "n8n" / "workflows"


def test_resume_url_keeps_path_and_query():
    url = "http://n8n:5678/webhook-waiting/42?signature=abc"
    assert host_resume_url(url) == "http://localhost:5690/webhook-waiting/42?signature=abc"


def test_resume_url_already_on_localhost_is_unchanged():
    url = "http://localhost:5690/webhook-waiting/7"
    assert host_resume_url(url) == url


def test_sanitize_drops_secrets_and_instance_data():
    exported = [{
        "id": "X1", "name": "W", "settings": {}, "connections": {},
        "active": True, "versionId": "v1", "pinData": {"a": []},
        "meta": {"instanceId": "abc"}, "shared": [{"projectId": "p"}],
        "nodes": [{"name": "HTTP", "credentials": {"httpBasicAuth": {"id": "1"}}}],
    }]
    clean = sanitize(exported)
    assert set(clean) == {"id", "name", "settings", "connections", "nodes", "active"}
    assert clean["active"] is False
    assert "credentials" not in clean["nodes"][0]
    check_clean(json.dumps(clean))


def test_check_clean_refuses_leftovers():
    with pytest.raises(ValueError):
        check_clean('{"credentials": {}}')


@pytest.mark.parametrize("name", ["invoice_intake.json", "invoice_errors.json"])
def test_saved_workflows_are_clean(name):
    text = (WORKFLOW_DIR / name).read_text(encoding="utf-8")
    check_clean(text)
    workflow = json.loads(text)
    assert workflow["active"] is False


def test_intake_uses_error_workflow():
    intake = json.loads((WORKFLOW_DIR / "invoice_intake.json").read_text(encoding="utf-8"))
    errors = json.loads((WORKFLOW_DIR / "invoice_errors.json").read_text(encoding="utf-8"))
    assert intake["settings"]["errorWorkflow"] == errors["id"]
