import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_release_compliance import check_release_compliance


def _materials(root):
    provenance = {"license_review_complete": True,
                  "build_record": {"app_version": "1.2.3", "build_id": "test.1",
                                   "source_inputs_sha256": "a" * 64},
                  "installer": {"sha256": "b" * 64}}
    sbom = {"bomFormat": "CycloneDX", "specVersion": "1.6",
            "metadata": {"component": {"version": "1.2.3", "properties": [
                {"name": "voiceflow:build-id", "value": "test.1"},
                {"name": "voiceflow:source-inputs-sha256", "value": "a" * 64},
                {"name": "voiceflow:installer-sha256", "value": "b" * 64}]}},
            "compositions": [{"aggregate": "complete"}]}
    for name, payload in (("BUILD_PROVENANCE.json", provenance), ("SBOM.cdx.json", sbom)):
        (root / name).write_text(json.dumps(payload), encoding="utf-8")
    return provenance, sbom


def test_complete_matching_review_passes(tmp_path):
    _materials(tmp_path)
    check_release_compliance(tmp_path)


@pytest.mark.parametrize("fault", ["unreviewed", "truthy_string", "missing_review",
                                   "incomplete", "unknown", "missing_composition",
                                   "mixed_composition", "wrong_build", "wrong_installer",
                                   "duplicate_property"])
def test_incomplete_or_mismatched_review_blocks_publication(tmp_path, fault):
    provenance, sbom = _materials(tmp_path)
    if fault in {"unreviewed", "truthy_string", "missing_review"}:
        provenance["license_review_complete"] = False if fault == "unreviewed" else "true"
        if fault == "missing_review":
            del provenance["license_review_complete"]
    elif fault in {"incomplete", "unknown"}:
        sbom["compositions"][0]["aggregate"] = fault
    elif fault == "missing_composition":
        del sbom["compositions"]
    elif fault == "mixed_composition":
        sbom["compositions"].append({"aggregate": "incomplete"})
    elif fault == "wrong_build":
        provenance["build_record"]["build_id"] = "other"
    elif fault == "wrong_installer":
        provenance["installer"]["sha256"] = "c" * 64
    else:
        sbom["metadata"]["component"]["properties"].append(
            {"name": "voiceflow:build-id", "value": "test.1"})
    for name, payload in (("BUILD_PROVENANCE.json", provenance), ("SBOM.cdx.json", sbom)):
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        check_release_compliance(tmp_path)


def test_release_workflow_checks_compliance_before_publication():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    gate = workflow.index("python scripts/check_release_compliance.py")
    assert workflow.index("Preserve compliance bundle") < gate
    assert gate < workflow.index("Attest installer provenance")
    assert gate < workflow.index("gh release create")
    assert 'if ($LASTEXITCODE -ne 0) { throw "Release compliance review is incomplete" }' in workflow
