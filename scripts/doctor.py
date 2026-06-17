"""
VoiceFlow runtime doctor.

This is a fast, non-interactive check for maintainers and AI agents. It does
not record from the microphone and does not paste text anywhere.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_IMPORTS = (
    "numpy",
    "sherpa_onnx",
    "sounddevice",
    "soundfile",
    "pyperclip",
    "PyQt6",
    "pynput",
    "yaml",
)
REQUIRED_SAMPLE_WAVS = ("zh.wav", "en.wav")


def _check_imports() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for module_name in REQUIRED_IMPORTS:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            rows.append({"name": module_name, "status": "missing", "detail": str(exc)})
        else:
            rows.append({"name": module_name, "status": "ok", "detail": ""})
    return rows


def _load_config(root: Path) -> dict[str, Any]:
    config_path = root / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(config_path)
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def _check_active_engine(root: Path, config: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    engine = config.get("engine", {})
    active_name = engine.get("active", "sensevoice")
    active_config = engine.get(active_name) or {}
    rows.append({"name": "active_engine", "status": "ok" if active_config else "missing", "detail": str(active_name)})
    for key in ("model_path", "tokens_path"):
        raw_path = active_config.get(key, "")
        path = root / raw_path
        rows.append({
            "name": key,
            "status": "ok" if path.exists() else "missing",
            "detail": str(path),
        })
    provider = str(active_config.get("provider", "cpu"))
    rows.append({"name": "provider", "status": "ok", "detail": provider})
    rows.append({"name": "num_threads", "status": "ok", "detail": str(active_config.get("num_threads", 6))})
    return rows


def _check_knowledge_base(root: Path, config: dict[str, Any]) -> list[dict[str, str]]:
    hotwords = config.get("hotwords", {})
    directory = root / hotwords.get("directory", "knowledge-base")
    rows = [{"name": "knowledge_base_dir", "status": "ok" if directory.exists() else "missing", "detail": str(directory)}]
    for filename in hotwords.get("files", []):
        path = directory / filename
        rows.append({"name": f"hotword:{filename}", "status": "ok" if path.exists() else "missing", "detail": str(path)})
    return rows


def _check_samples(root: Path) -> list[dict[str, str]]:
    wav_dir = root / "models" / "sensevoice" / "test_wavs"
    rows = [{"name": "sample_wav_dir", "status": "ok" if wav_dir.exists() else "missing", "detail": str(wav_dir)}]
    for filename in REQUIRED_SAMPLE_WAVS:
        path = wav_dir / filename
        rows.append({"name": f"sample:{filename}", "status": "ok" if path.exists() else "missing", "detail": str(path)})
    return rows


def run_doctor(root: Path = ROOT) -> dict[str, Any]:
    config = _load_config(root)
    checks = []
    checks.extend(_check_imports())
    checks.extend(_check_active_engine(root, config))
    checks.extend(_check_knowledge_base(root, config))
    checks.extend(_check_samples(root))
    ok = all(item["status"] == "ok" for item in checks)
    return {"ok": ok, "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check VoiceFlow runtime readiness without recording audio.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    result = run_doctor()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in result["checks"]:
            print(f"{item['status']:>7}  {item['name']:<28} {item['detail']}")
        print("")
        print("VoiceFlow doctor:", "ok" if result["ok"] else "failed")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
