import sys
import types
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


class _SilentAudioCapture:
    started = False

    @classmethod
    def list_devices(cls):
        return [
            {
                "index": 1,
                "name": "Fixture microphone",
                "channels": 1,
                "sample_rate": 16000,
            }
        ]

    def __init__(self):
        self.sample_rate = 16000

    def start_recording(self):
        type(self).started = True

    def stop_recording(self):
        return np.zeros(1600, dtype=np.int16)


def _load_test_mic(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "audio_capture",
        types.SimpleNamespace(AudioCapture=_SilentAudioCapture),
    )
    sys.modules.pop("test_mic", None)
    import test_mic

    return test_mic


def test_mic_help_does_not_start_recording(monkeypatch):
    test_mic = _load_test_mic(monkeypatch)
    _SilentAudioCapture.started = False

    with pytest.raises(SystemExit) as exit_info:
        test_mic.main(["--help"])

    assert exit_info.value.code == 0
    assert _SilentAudioCapture.started is False


def test_mic_silence_fails_before_asr_and_does_not_write_default_file(
    monkeypatch,
    tmp_path,
    capsys,
):
    test_mic = _load_test_mic(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(test_mic.time, "sleep", lambda _seconds: None)
    monkeypatch.setitem(
        sys.modules,
        "transcriber",
        types.SimpleNamespace(
            Transcriber=lambda: (_ for _ in ()).throw(
                AssertionError("silence must not reach ASR")
            )
        ),
    )

    return_code = test_mic.main(["--duration", "0", "--countdown", "0"])

    assert return_code == 2
    assert "未检测到有效语音" in capsys.readouterr().out
    assert not (tmp_path / "test_recording.wav").exists()
