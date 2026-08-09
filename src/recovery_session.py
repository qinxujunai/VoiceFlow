"""Crash-recoverable, local-only recording journals."""

from __future__ import annotations

import json
import os
import queue
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


@dataclass(frozen=True)
class RecoverableSession:
    session_id: str
    state: str
    sample_rate: int
    channels: int
    dtype: str
    model: str
    sample_count: int
    preview_text: str
    created_at: float
    updated_at: float
    session_dir: Path
    pcm_path: Path
    metadata_path: Path


class RecoveryJournal:
    """Append PCM without doing disk IO in the microphone callback."""

    METADATA_INTERVAL_SECONDS = 2.0

    def __init__(self, session_dir: Path, metadata: dict):
        self.session_dir = Path(session_dir)
        self.pcm_path = self.session_dir / "audio.pcm"
        self.metadata_path = self.session_dir / "session.json"
        self._metadata = dict(metadata)
        self._metadata_lock = threading.RLock()
        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=2048)
        self._writer_error: str | None = None
        self._closed = False
        self._last_metadata_write = 0.0
        self.session_dir.mkdir(parents=True, exist_ok=False)
        _write_json_atomic(self.metadata_path, self._metadata)
        self._thread = threading.Thread(
            target=self._writer_loop,
            name=f"voiceflow-recovery-{self.session_id}",
            daemon=True,
        )
        self._thread.start()

    @property
    def session_id(self) -> str:
        return str(self._metadata["session_id"])

    def append_pcm(self, pcm) -> bool:
        if self._closed:
            return False
        samples = np.asarray(pcm, dtype=np.int16).reshape(-1)
        if not len(samples):
            return True
        try:
            self._queue.put_nowait(samples.tobytes())
            return True
        except queue.Full:
            with self._metadata_lock:
                self._writer_error = "recovery_queue_full"
                self._metadata["writer_error"] = self._writer_error
            return False

    def mark_state(self, state: str, *, preview_text: str | None = None) -> None:
        with self._metadata_lock:
            self._metadata["state"] = str(state)
            self._metadata["updated_at"] = time.time()
            if preview_text is not None:
                self._metadata["preview_text"] = str(preview_text)
            if self._writer_error:
                self._metadata["writer_error"] = self._writer_error
            _write_json_atomic(self.metadata_path, self._metadata)
            self._last_metadata_write = time.monotonic()

    def close_interrupted(self) -> None:
        self.mark_state("recoverable")
        self._close_writer()

    def mark_delivered(self, text_sha256: str) -> None:
        with self._metadata_lock:
            self._metadata["text_sha256"] = str(text_sha256)
        self.mark_state("delivered")
        self._close_writer()
        shutil.rmtree(self.session_dir, ignore_errors=True)

    def close_without_recovery(self) -> None:
        self._close_writer()
        shutil.rmtree(self.session_dir, ignore_errors=True)

    def _close_writer(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=5.0)
        with self._metadata_lock:
            self._metadata["updated_at"] = time.time()
            if self._writer_error:
                self._metadata["writer_error"] = self._writer_error
            _write_json_atomic(self.metadata_path, self._metadata)

    def _writer_loop(self) -> None:
        try:
            with self.pcm_path.open("ab", buffering=0) as stream:
                while True:
                    payload = self._queue.get()
                    if payload is None:
                        break
                    stream.write(payload)
                    with self._metadata_lock:
                        self._metadata["sample_count"] += len(payload) // 2
                        self._metadata["updated_at"] = time.time()
                        now = time.monotonic()
                        if now - self._last_metadata_write >= self.METADATA_INTERVAL_SECONDS:
                            _write_json_atomic(self.metadata_path, self._metadata)
                            self._last_metadata_write = now
                stream.flush()
                os.fsync(stream.fileno())
        except Exception as exc:
            with self._metadata_lock:
                self._writer_error = f"{type(exc).__name__}: {exc}"
                self._metadata["writer_error"] = self._writer_error


class RecoverySessionStore:
    def __init__(self, root: str | Path, *, retention_hours: float = 24):
        self.root = Path(root)
        self.retention_seconds = max(0.0, float(retention_hours)) * 60 * 60
        self.root.mkdir(parents=True, exist_ok=True)

    def start_session(
        self,
        *,
        session_id: str,
        sample_rate: int,
        channels: int,
        dtype: str,
        model: str,
    ) -> RecoveryJournal:
        now = time.time()
        return RecoveryJournal(
            self.root / str(session_id),
            {
                "schema_version": 1,
                "session_id": str(session_id),
                "state": "arming",
                "sample_rate": int(sample_rate),
                "channels": int(channels),
                "dtype": str(dtype),
                "model": str(model),
                "sample_count": 0,
                "preview_text": "",
                "created_at": now,
                "updated_at": now,
            },
        )

    def list_recoverable(self) -> list[RecoverableSession]:
        sessions: list[RecoverableSession] = []
        if not self.root.is_dir():
            return sessions
        for session_dir in sorted(
            path
            for path in self.root.iterdir()
            if path.is_dir() and not path.is_symlink()
        ):
            metadata_path = session_dir / "session.json"
            pcm_path = session_dir / "audio.pcm"
            if not metadata_path.is_file() or not pcm_path.is_file():
                continue
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                if payload.get("state") in {"delivered", "complete", "canceled"}:
                    continue
                sessions.append(
                    RecoverableSession(
                        session_id=str(payload["session_id"]),
                        state=str(payload.get("state", "recoverable")),
                        sample_rate=int(payload.get("sample_rate", 16000)),
                        channels=int(payload.get("channels", 1)),
                        dtype=str(payload.get("dtype", "int16")),
                        model=str(payload.get("model", "unknown")),
                        sample_count=int(payload.get("sample_count", pcm_path.stat().st_size // 2)),
                        preview_text=str(payload.get("preview_text", "")),
                        created_at=float(payload.get("created_at", metadata_path.stat().st_mtime)),
                        updated_at=float(payload.get("updated_at", metadata_path.stat().st_mtime)),
                        session_dir=session_dir,
                        pcm_path=pcm_path,
                        metadata_path=metadata_path,
                    )
                )
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sessions

    def purge_expired(self, *, now: float | None = None) -> tuple[str, ...]:
        current = time.time() if now is None else float(now)
        removed: list[str] = []
        for session in self.list_recoverable():
            age_anchor = session.metadata_path.stat().st_mtime
            if current - age_anchor <= self.retention_seconds:
                continue
            shutil.rmtree(session.session_dir, ignore_errors=True)
            removed.append(session.session_id)
        return tuple(removed)

    def read_pcm(self, session_id: str) -> np.ndarray:
        session = self._find_exact(session_id)
        if session is None:
            return np.empty(0, dtype=np.int16)
        try:
            return np.fromfile(session.pcm_path, dtype=np.int16)
        except OSError:
            return np.empty(0, dtype=np.int16)

    def delete(self, session_id: str) -> bool:
        session = self._find_exact(session_id)
        if session is None:
            return False
        shutil.rmtree(session.session_dir, ignore_errors=True)
        return not session.session_dir.exists()

    def _find_exact(self, session_id: str) -> RecoverableSession | None:
        expected = str(session_id)
        return next(
            (session for session in self.list_recoverable() if session.session_id == expected),
            None,
        )
