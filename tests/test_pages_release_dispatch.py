"""Release tags must not bypass the protected master Pages deployment."""

from pathlib import Path

import yaml


def test_release_events_request_a_master_deployment_without_entering_pages():
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/pages.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    request = jobs["request-deploy"]
    assert "github.event_name == 'release'" in request["if"]
    assert "environment" not in request
    assert request["permissions"] == {"actions": "write", "contents": "read"}
    assert "gh workflow run pages.yml --ref master" in request["steps"][0]["run"]
    deploy = jobs["deploy"]
    assert "'release'" not in deploy["if"]
    assert "'workflow_dispatch'" in deploy["if"]
    assert deploy["environment"]["name"] == "github-pages"
