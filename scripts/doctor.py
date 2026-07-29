"""
VoiceFlow runtime doctor.

This is a fast, non-interactive check for maintainers and AI agents. It does
not record from the microphone and does not paste text anywhere.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from performance_profile import final_thread_count
REQUIRED_IMPORTS = (
    "numpy",
    "sherpa_onnx",
    "sounddevice",
    "soundfile",
    "pyperclip",
    "PySide6",
    "PySide6.QtWebEngineWidgets",
    "pynput",
    "yaml",
)
REQUIRED_SAMPLE_WAVS = ("zh.wav", "en.wav")
WARNING_STATUSES = {"warning"}
SILERO_VAD_SHA256 = "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6"


def _is_required_ok(item: dict[str, str]) -> bool:
    return item["status"] == "ok" or item["status"] in WARNING_STATUSES


def _check_python_runtime(root: Path) -> list[dict[str, str]]:
    rows = [
        {
            "name": "python_version",
            "status": "ok" if sys.version_info >= (3, 10) else "missing",
            "detail": sys.version.split()[0],
        },
        {
            "name": "python_executable",
            "status": "ok",
            "detail": sys.executable,
        },
    ]
    venv_python = root / "venv" / "Scripts" / "python.exe"
    rows.append({
        "name": "venv_python",
        "status": "ok" if venv_python.exists() else "warning",
        "detail": str(venv_python),
    })
    return rows


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
    asset_keys = {
        "sensevoice": ("model_path", "tokens_path"),
        "qwen3-asr": (
            "conv_frontend_path",
            "encoder_path",
            "decoder_path",
            "tokenizer_path",
        ),
        "fun-asr-nano": (
            "encoder_adaptor_path",
            "llm_path",
            "embedding_path",
            "tokenizer_path",
        ),
        "whisper-turbo": ("encoder_path", "decoder_path", "tokens_path"),
    }
    for key in asset_keys.get(active_name, ()):
        raw_path = active_config.get(key, "")
        path = root / raw_path
        rows.append({
            "name": key,
            "status": "ok" if path.exists() else "missing",
            "detail": str(path),
        })
    provider = str(active_config.get("provider", "cpu"))
    rows.append({"name": "provider", "status": "ok", "detail": provider})
    configured_threads = active_config.get("num_threads", "auto")
    effective_threads = final_thread_count(configured_threads)
    detail = (
        f"{effective_threads} (auto)"
        if str(configured_threads).lower() == "auto"
        else str(effective_threads)
    )
    rows.append({"name": "num_threads", "status": "ok", "detail": detail})
    return rows


def _check_streaming_preview(root: Path, config: dict[str, Any]) -> list[dict[str, str]]:
    preview = config.get("streaming_preview", {})
    if not preview.get("enabled", True):
        return [{
            "name": "streaming_preview",
            "status": "warning",
            "detail": "disabled",
        }]
    assets = {
        "preview_model_path": preview.get(
            "model_path",
            "models/streaming-preview/model.int8.onnx",
        ),
        "preview_tokens_path": preview.get(
            "tokens_path",
            "models/streaming-preview/tokens.txt",
        ),
    }
    packaged_without_preview = (
        (root / "VoiceFlow.exe").is_file()
        and all(not (root / raw_path).is_file() for raw_path in assets.values())
        and set(assets.values()) == {
            "models/streaming-preview/model.int8.onnx",
            "models/streaming-preview/tokens.txt",
        }
    )
    if packaged_without_preview:
        return [
            {
                "name": name,
                "status": "warning",
                "detail": "not bundled; quiet capsule is active",
            }
            for name in assets
        ]
    return [
        {
            "name": name,
            "status": "ok" if (root / raw_path).is_file() else "missing",
            "detail": str(root / raw_path),
        }
        for name, raw_path in assets.items()
    ]


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


def _check_vad(root: Path, config: dict[str, Any]) -> list[dict[str, str]]:
    vad = config.get("vad", {})
    path = root / vad.get("model_path", "assets/silero_vad.onnx")
    if not vad.get("enabled", True):
        return [{"name": "silero_vad_model", "status": "warning", "detail": "disabled"}]
    if not path.is_file():
        return [{"name": "silero_vad_model", "status": "missing", "detail": str(path)}]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return [{
        "name": "silero_vad_model",
        "status": "ok" if digest == SILERO_VAD_SHA256 else "invalid",
        "detail": f"{path} sha256={digest}",
    }]


def _check_delivery_files(root: Path) -> list[dict[str, str]]:
    logs_dir = root / "logs"
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    shortcut = desktop / "VoiceFlow.lnk"
    icon = root / "assets" / "voiceflow.ico"
    return [
        {
            "name": "logs_dir",
            "status": "ok",
            "detail": str(logs_dir if logs_dir.exists() else f"{logs_dir} (created on demand)"),
        },
        {
            "name": "app_icon",
            "status": "ok" if icon.exists() else "missing",
            "detail": str(icon),
        },
        {
            "name": "desktop_shortcut",
            "status": "ok" if shortcut.exists() else "warning",
            "detail": str(shortcut if shortcut.exists() else f"{shortcut} (run scripts/create_shortcut.ps1)"),
        },
    ]


def run_doctor(root: Path = ROOT) -> dict[str, Any]:
    config = _load_config(root)
    checks = []
    checks.extend(_check_python_runtime(root))
    checks.extend(_check_imports())
    checks.extend(_check_active_engine(root, config))
    checks.extend(_check_streaming_preview(root, config))
    checks.extend(_check_knowledge_base(root, config))
    checks.extend(_check_samples(root))
    checks.extend(_check_vad(root, config))
    checks.extend(_check_delivery_files(root))
    ok = all(_is_required_ok(item) for item in checks)
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
