"""Preview IPC must not retransmit the complete dictation at every PCM block."""

from dataclasses import asdict
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import preview_worker
from streaming_transcriber import PreviewEvent


def test_wire_packet_size_does_not_grow_with_previous_committed_text():
    from multiprocessing.reduction import ForkingPickler

    def packet(size):
        return preview_worker._preview_event_payload(PreviewEvent(
            text="current segment", delta="新增🙂", segment_id=1,
            audio_end_sample=1600, committed_text="测" * size + "新增🙂"))

    short, long = packet(0), packet(100000)
    assert "committed_text" not in long
    assert long["committed_characters"] == 100003
    assert len(ForkingPickler.dumps(long)) - len(ForkingPickler.dumps(short)) < 16


def test_remote_reconstructs_unicode_and_empty_deltas_once_across_segments():
    preview = preview_worker.SupervisedPreviewTranscriber("unused.yaml")
    session = preview_worker.RemotePreviewSession("fixture")
    frames = [
        PreviewEvent("你好", "你", 0, 1600, "你", "好"),
        PreviewEvent("你好", "", 0, 3200, "你", "好"),
        PreviewEvent("你好", "好", 0, 4800, "你好", "", True),
        PreviewEvent("🙂👩‍💻", "🙂👩‍💻", 1, 6400, "你好🙂👩‍💻"),
    ]
    for frame in frames:
        payload = asdict(frame)
        payload.pop("committed_text")
        payload["committed_characters"] = len(frame.committed_text)
        preview._request = lambda *_args, **_kwargs: {"event": payload}
        event = preview.accept_pcm(session, np.zeros(1600, np.int16), 16000)
        assert event == frame
        assert session.committed_text == frame.committed_text


@pytest.mark.parametrize("length", [0, 10, -1, True, "1"])
def test_missing_replayed_or_invalid_delta_never_changes_remote_committed_text(length):
    preview = preview_worker.SupervisedPreviewTranscriber("unused.yaml")
    session = preview_worker.RemotePreviewSession("fixture", committed_text="之前")
    payload = asdict(PreviewEvent("新", "新", 0, 1600))
    payload.pop("committed_text")
    payload["committed_characters"] = length
    preview._request = lambda *_args, **_kwargs: {"event": payload}
    with pytest.raises(RuntimeError, match="预览"):
        preview.accept_pcm(session, np.zeros(1600, np.int16), 16000)
    assert session.committed_text == "之前"
