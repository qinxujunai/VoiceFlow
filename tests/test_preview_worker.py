import multiprocessing

import numpy as np


def fake_preview_worker(commands, responses, heartbeat, _worker_config):
    heartbeat.value = 1.0e12
    responses.put({"kind": "ready"})
    committed = {}
    while True:
        command = commands.get()
        if command["kind"] == "shutdown":
            return
        if command["kind"] == "create_session":
            committed[command["session_id"]] = ""
            responses.put(
                {
                    "kind": "response",
                    "request_id": command["request_id"],
                    "ok": True,
                }
            )
            continue
        if command["kind"] == "accept_pcm":
            session_id = command["session_id"]
            samples = np.frombuffer(command["pcm"], dtype=np.int16)
            delta = "测" if len(samples) else ""
            committed[session_id] += delta
            responses.put(
                {
                    "kind": "response",
                    "request_id": command["request_id"],
                    "ok": True,
                    "event": {
                        "text": committed[session_id],
                        "delta": delta,
                        "segment_id": 0,
                        "audio_end_sample": len(samples),
                        "committed_text": committed[session_id],
                        "provisional_text": "",
                        "endpoint_final": False,
                        "hypothesis_diverged": False,
                    },
                }
            )


def test_preview_model_and_session_live_outside_ui_process():
    from preview_worker import SupervisedPreviewTranscriber

    preview = SupervisedPreviewTranscriber(
        "unused.yaml",
        worker_target=fake_preview_worker,
        startup_timeout=2.0,
    )
    preview.load()
    try:
        assert preview.worker_pid != multiprocessing.current_process().pid
        session = preview.create_session()
        event = preview.accept_pcm(
            session,
            np.array([1, 2, 3], dtype=np.int16),
            16000,
        )
        assert event.delta == "测"
        assert session.committed_text == "测"
    finally:
        preview.shutdown()


def test_preview_worker_shutdown_is_idempotent():
    from preview_worker import SupervisedPreviewTranscriber

    preview = SupervisedPreviewTranscriber(
        "unused.yaml",
        worker_target=fake_preview_worker,
        startup_timeout=2.0,
    )
    preview.load()
    preview.shutdown()
    preview.shutdown()
    assert not preview.is_ready
