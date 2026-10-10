from __future__ import annotations

import sys
import threading
from pathlib import Path

import yaml


def test_concurrent_first_use_and_runtime_save_preserve_both_changes(tmp_path, monkeypatch):
    from settings_store import set_onboarding_completed, update_runtime_settings

    config = tmp_path / "config.yaml"
    config.write_text('engine:\n  active: "sensevoice"\n  sensevoice:\n    language: "auto"\n'
                      'audio:\n  device_index: null\nui:\n  onboarding_completed: false\n',
                      encoding="utf-8")
    original_read = Path.read_text
    entered = threading.Event()
    release = threading.Event()
    second_finished = threading.Event()
    failures = []
    reads = []

    def observed_read(path, *args, **kwargs):
        text = original_read(path, *args, **kwargs)
        if path == config:
            reads.append(threading.get_ident())
            if len(reads) == 1:
                entered.set()
                assert release.wait(2)
        return text

    def save_settings():
        try:
            update_runtime_settings(config, engine="sensevoice", language="en", device_index=3)
        except Exception as error:
            failures.append(error)

    def save_first_use():
        try:
            set_onboarding_completed(config)
        except Exception as error:
            failures.append(error)
        finally:
            second_finished.set()

    monkeypatch.setattr(Path, "read_text", observed_read)
    settings_thread = threading.Thread(target=save_settings)
    first_use_thread = threading.Thread(target=save_first_use)
    settings_thread.start()
    try:
        assert entered.wait(1)
        first_use_thread.start()
        second_finished.wait(.1)
    finally:
        release.set()
        settings_thread.join(2)
        first_use_thread.join(2)
    assert not failures
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert payload["engine"]["sensevoice"]["language"] == "en"
    assert payload["audio"]["device_index"] == 3
    assert payload["ui"]["onboarding_completed"] is True


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
