"""Block a public installer while any bundled model still needs review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def unresolved_models(manifest, model_ids):
    unresolved = []
    for model_id in model_ids:
        model = manifest["models"].get(model_id)
        if model is None:
            unresolved.append(f"{model_id}: missing from manifest")
            continue
        license_info = model.get("license", {})
        if license_info.get("distribution_review_required", True):
            unresolved.append(
                f"{model_id}: {license_info.get('name', 'license review required')}"
            )
    return unresolved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model_ids", nargs="+")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "model-manifest.json",
    )
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    unresolved = unresolved_models(manifest, args.model_ids)
    if unresolved:
        raise SystemExit(
            "Public release blocked by unresolved model distribution review:\n- "
            + "\n- ".join(unresolved)
        )
    print("Bundled model distribution decisions are recorded.")


if __name__ == "__main__":
    main()
