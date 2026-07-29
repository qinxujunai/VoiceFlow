from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def test_release_model_gate_blocks_unreviewed_weights():
    from check_release_models import unresolved_models

    manifest = {
        "models": {
            "ready": {
                "license": {
                    "distribution_review_required": False,
                }
            },
            "candidate": {
                "license": {
                    "name": "No explicit weight license",
                    "distribution_review_required": True,
                }
            },
        }
    }

    assert unresolved_models(manifest, ["ready"]) == []
    assert unresolved_models(manifest, ["candidate"]) == [
        "candidate: No explicit weight license"
    ]
    assert unresolved_models(manifest, ["missing"]) == [
        "missing: missing from manifest"
    ]
