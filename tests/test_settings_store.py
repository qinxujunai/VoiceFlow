from __future__ import annotations

import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_runtime_settings_update_is_atomic_and_preserves_comments(tmp_path):
    from settings_store import update_runtime_settings

    config = tmp_path / "config.yaml"
    config.write_text(
        """# product contract
engine:
  active: "sensevoice"
  sensevoice:
    language: "zh"              # keep language note
  qwen3-asr:
    language: "auto"
audio:
  sample_rate: 16000
  device_index: null            # keep device note
vad:
  enabled: true
""",
        encoding="utf-8",
    )

    update_runtime_settings(
        config,
        engine="qwen3-asr",
        language="en",
        device_index=3,
    )

    text = config.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    assert parsed["engine"]["active"] == "qwen3-asr"
    assert parsed["engine"]["qwen3-asr"]["language"] == "en"
    assert parsed["audio"]["device_index"] == 3
    assert "# product contract" in text
    assert "# keep language note" in text
    assert "# keep device note" in text
    assert not config.with_suffix(".yaml.tmp").exists()


def test_frozen_autostart_uses_packaged_executable_without_source_runtime(tmp_path):
    from runtime_paths import AppPaths, RuntimeMode
    from settings_store import autostart_command

    executable = tmp_path / "VoiceFlow" / "VoiceFlow.exe"
    paths = AppPaths(
        mode=RuntimeMode.FROZEN,
        install_dir=executable.parent,
        data_dir=tmp_path / "data",
        executable=executable,
    )

    command = autostart_command(paths)

    assert command == f'"{executable.resolve()}"'
    assert "venv" not in command
    assert "scripts" not in command


def test_onboarding_state_update_is_atomic_and_preserves_config(tmp_path):
    from settings_store import onboarding_completed, set_onboarding_completed

    config = tmp_path / "config.yaml"
    config.write_text(
        """# keep me
engine:
  active: "sensevoice"
""",
        encoding="utf-8",
    )

    assert onboarding_completed(config) is False
    set_onboarding_completed(config, True)
    assert onboarding_completed(config) is True
    assert "# keep me" in config.read_text(encoding="utf-8")

    set_onboarding_completed(config, False)
    assert onboarding_completed(config) is False
    assert not config.with_suffix(".yaml.tmp").exists()
