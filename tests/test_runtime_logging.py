import json
import logging

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
