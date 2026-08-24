import json

from runtime_logging import configure_runtime_logging


def test_runtime_logger_writes_structured_exception(tmp_path):
    log_path = tmp_path / "runtime.jsonl"
    logger = configure_runtime_logging(log_path)
    try:
        raise RuntimeError("microphone disconnected")
    except RuntimeError:
        logger.exception("recording failed")

    payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert payload["level"] == "error"
    assert payload["message"] == "recording failed"
    assert "RuntimeError: microphone disconnected" in payload["exception"]


def test_runtime_logger_emits_allowlisted_operational_fields_only(tmp_path):
    log_path = tmp_path / "runtime.jsonl"
    logger = configure_runtime_logging(log_path)
    logger.info(
        "action completed",
        extra={
            "event": "action_finished",
            "action": "trial_toggle",
            "duration_ms": 12.5,
            "secret_transcript": "绝不能进入日志",
        },
    )

    payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert payload["event"] == "action_finished"
    assert payload["action"] == "trial_toggle"
    assert payload["duration_ms"] == 12.5
    assert "secret_transcript" not in payload
