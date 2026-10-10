"""Crash-recoverable, local-only recording journals."""

from __future__ import annotations

import json
import math
import os
import queue
import shutil
import stat
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np


def _write_json_atomic(path: Path, payload: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
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
    durable_sample_count: int = 0
    partial: bool = False
    can_recover: bool = True
    error: str = ""


class RecoveryJournal:
    """Append PCM without doing disk IO in the microphone callback."""

    METADATA_INTERVAL_SECONDS = 2.0

    def __init__(self, session_dir: Path, metadata: dict, *, max_pcm_bytes=None):
        self.session_dir = Path(session_dir)
        self.pcm_path = self.session_dir / "audio.pcm"
        self.metadata_path = self.session_dir / "session.json"
        self._metadata = dict(metadata)
        self._metadata_lock = threading.RLock()
        self._persistence_lock = threading.Lock()
        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=2048)
        self._writer_stop = threading.Event()
        self._writer_error: str | None = None
        self._closed = False
        self._last_metadata_write = 0.0
        self._max_pcm_bytes = max_pcm_bytes
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
        if self._closed or self._writer_error:
            return False
        samples = np.asarray(pcm, dtype=np.int16).reshape(-1)
        if not len(samples):
            return True
        payload = samples.tobytes()
        with self._metadata_lock:
            if self._closed or self._writer_error:
                return False
            accepted = int(self._metadata.get("accepted_sample_count", 0))
            if self._max_pcm_bytes is not None and accepted * 2 + len(payload) > self._max_pcm_bytes:
                self._writer_error = "recovery_storage_limit"
                self._metadata["writer_error"] = self._writer_error
                return False
            try:
                self._queue.put_nowait(payload)
            except queue.Full:
                self._writer_error = "recovery_queue_full"
                self._metadata["writer_error"] = self._writer_error
                return False
            self._metadata["accepted_sample_count"] = (
                int(self._metadata.get("accepted_sample_count", 0)) + len(samples)
            )
        return True

    def mark_state(self, state: str, *, preview_text: str | None = None) -> None:
        with self._metadata_lock:
            self._metadata["state"] = str(state)
            self._metadata["updated_at"] = time.time()
            if preview_text is not None:
                self._metadata["preview_text"] = str(preview_text)
            if self._writer_error:
                self._metadata["writer_error"] = self._writer_error
        self._persist_metadata()

    @property
    def writer_error(self) -> str | None:
        with self._metadata_lock:
            return self._writer_error

    def status(self) -> dict:
        with self._metadata_lock:
            return {
                "writer_error": self._writer_error,
                "accepted_sample_count": int(self._metadata.get("accepted_sample_count", 0)),
                "sample_count": int(self._metadata.get("sample_count", 0)),
                "durable_sample_count": int(self._metadata.get("durable_sample_count", 0)),
                "closed": self._closed and not self._thread.is_alive(),
            }

    def _record_writer_error(self, code: str) -> None:
        with self._metadata_lock:
            self._writer_error = self._writer_error or str(code)
            self._metadata["writer_error"] = self._writer_error

    def _persist_metadata(self) -> bool:
        # Callback-side append never waits for a filesystem write to release
        # the metadata lock. Serialize snapshots separately from that lock.
        with self._persistence_lock:
            with self._metadata_lock:
                snapshot = dict(self._metadata)
            try:
                _write_json_atomic(self.metadata_path, snapshot)
            except OSError:
                self._record_writer_error("recovery_metadata_write_failed")
                return False
            self._last_metadata_write = time.monotonic()
            return True

    def close_interrupted(self) -> None:
        with self._metadata_lock:
            self._metadata["state"] = "recoverable"
        self._close_writer()

    def mark_delivered(self, text_sha256: str) -> None:
        with self._metadata_lock:
            self._metadata["text_sha256"] = str(text_sha256)
            self._metadata["state"] = "delivered"
        if self._close_writer():
            shutil.rmtree(self.session_dir, ignore_errors=True)

    def close_without_recovery(self) -> None:
        if self._close_writer():
            shutil.rmtree(self.session_dir, ignore_errors=True)

    def _close_writer(self) -> bool:
        with self._metadata_lock:
            self._closed = True
        self._writer_stop.set()
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=5.0)
        if self._thread.is_alive():
            self._record_writer_error("recovery_close_timeout")
            return False
        with self._metadata_lock:
            self._metadata["updated_at"] = time.time()
            if self._writer_error:
                self._metadata["writer_error"] = self._writer_error
        return self._persist_metadata()

    def _writer_loop(self) -> None:
        try:
            with self.pcm_path.open("ab", buffering=0) as stream:
                while True:
                    try:
                        payload = self._queue.get(timeout=0.05)
                    except queue.Empty:
                        if self._writer_stop.is_set():
                            break
                        continue
                    if payload is None:
                        break
                    if stream.write(payload) != len(payload):
                        raise OSError("short recovery PCM write")
                    with self._metadata_lock:
                        self._metadata["sample_count"] += len(payload) // 2
                        self._metadata["updated_at"] = time.time()
                        now = time.monotonic()
                    if now - self._last_metadata_write >= self.METADATA_INTERVAL_SECONDS:
                        stream.flush()
                        os.fsync(stream.fileno())
                        with self._metadata_lock:
                            self._metadata["durable_sample_count"] = self._metadata["sample_count"]
                        if not self._persist_metadata():
                            break
                stream.flush()
                os.fsync(stream.fileno())
                with self._metadata_lock:
                    self._metadata["durable_sample_count"] = self._metadata["sample_count"]
        except Exception:
            self._record_writer_error("recovery_pcm_write_failed")


class RecoverySessionStore:
    DEFAULT_MAX_STORAGE_BYTES = 512 * 1024 * 1024
    DEFAULT_MIN_FREE_BYTES = 64 * 1024 * 1024

    def __init__(self, root: str | Path, *, retention_hours: float = 24,
                 max_storage_bytes=DEFAULT_MAX_STORAGE_BYTES,
                 min_free_bytes=DEFAULT_MIN_FREE_BYTES):
        self.root = Path(root)
        self.retention_seconds = max(0.0, float(retention_hours)) * 60 * 60
        self.max_storage_bytes = max(0, int(max_storage_bytes))
        self.min_free_bytes = max(0, int(min_free_bytes))
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
        directories = self._session_directories()
        used = sum(path.stat().st_size for path in (directory / "audio.pcm" for directory in directories)
                   if path.is_file() and not path.is_symlink())
        available = min(self.max_storage_bytes - used,
                        shutil.disk_usage(self.root).free - self.min_free_bytes)
        if available < 2:
            raise OSError("恢复录音空间不足，请先恢复或删除不再需要的录音，或释放磁盘空间。")
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
            max_pcm_bytes=available,
        )

    def list_recoverable(self) -> list[RecoverableSession]:
        sessions: list[RecoverableSession] = []
        for session_dir in sorted(self._session_directories()):
            metadata_path = session_dir / "session.json"
            pcm_path = session_dir / "audio.pcm"
            if not pcm_path.is_file() or pcm_path.is_symlink() or metadata_path.is_symlink():
                continue
            try:
                pcm_bytes = pcm_path.stat().st_size
                timestamp = session_dir.stat().st_mtime
                if not metadata_path.is_file() or metadata_path.stat().st_size > 1024 * 1024:
                    raise ValueError("invalid recovery metadata")
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict) or str(payload.get("session_id", "")) != session_dir.name:
                    raise ValueError("invalid recovery identity")
                schema_version = payload.get("schema_version", 1)
                if type(schema_version) is not int or schema_version != 1:
                    raise ValueError("unsupported recovery schema")
                if payload.get("state") in {"delivered", "complete", "canceled"}:
                    continue
                sample_rate = int(payload.get("sample_rate", 16000))
                channels = int(payload.get("channels", 1))
                dtype = str(payload.get("dtype", "int16"))
                created_at = float(payload.get("created_at", timestamp))
                updated_at = float(payload.get("updated_at", timestamp))
                if (not 8000 <= sample_rate <= 192000 or channels != 1 or dtype != "int16"
                        or not math.isfinite(created_at) or not math.isfinite(updated_at)
                        or not 0 <= created_at <= time.time() + 86400
                        or not 0 <= updated_at <= time.time() + 86400):
                    raise ValueError("unsupported recovery metadata")
                sample_count = pcm_bytes // 2
                written = max(0, int(payload.get("sample_count", sample_count)))
                durable = min(sample_count, max(0, int(payload.get("durable_sample_count", 0))))
                accepted = max(0, int(payload.get("accepted_sample_count", written)))
                error = str(payload.get("writer_error", ""))
                sessions.append(
                    RecoverableSession(
                        session_id=str(payload["session_id"]),
                        state=str(payload.get("state", "recoverable")),
                        sample_rate=sample_rate,
                        channels=channels,
                        dtype=dtype,
                        model=str(payload.get("model", "unknown")),
                        sample_count=sample_count,
                        preview_text=str(payload.get("preview_text", "")),
                        created_at=created_at,
                        updated_at=updated_at,
                        session_dir=session_dir,
                        pcm_path=pcm_path,
                        metadata_path=metadata_path,
                        durable_sample_count=durable,
                        partial=bool(error or pcm_bytes % 2 or written != sample_count
                                     or accepted != sample_count or durable < sample_count
                                     or payload.get("state") in {"arming", "recording"}),
                        error=error,
                    )
                )
            except (OSError, ValueError, KeyError, TypeError):
                try:
                    timestamp = session_dir.stat().st_mtime
                except OSError:
                    continue
                sessions.append(RecoverableSession(
                    session_id=session_dir.name, state="invalid", sample_rate=16000,
                    channels=1, dtype="int16", model="unknown", sample_count=0,
                    preview_text="", created_at=timestamp, updated_at=timestamp,
                    session_dir=session_dir, pcm_path=pcm_path, metadata_path=metadata_path,
                    partial=True, can_recover=False, error="recovery_metadata_invalid",
                ))
        return sessions

    def purge_expired(self, *, now: float | None = None) -> tuple[str, ...]:
        """Compatibility entry point: age never authorizes deleting undelivered PCM."""
        return ()

    def overdue_session_ids(self, *, now: float | None = None) -> tuple[str, ...]:
        """Return reminders for old sessions without changing their data or state."""
        current = time.time() if now is None else float(now)
        overdue: list[str] = []
        for session in self.list_recoverable():
            try:
                age_anchor = session.metadata_path.stat().st_mtime
            except OSError:
                continue
            if current - age_anchor <= self.retention_seconds:
                continue
            overdue.append(session.session_id)
        return tuple(overdue)

    def read_pcm(self, session_id: str) -> np.ndarray:
        return self.read_recording(session_id)[1]

    def read_recording(self, session_id: str) -> tuple[RecoverableSession | None, np.ndarray]:
        session = self._find_exact(session_id)
        if session is None or not session.can_recover:
            return session, np.empty(0, dtype=np.int16)
        try:
            audio = np.fromfile(session.pcm_path, dtype=np.int16, count=session.sample_count)
        except OSError:
            return session, np.empty(0, dtype=np.int16)
        if len(audio) != session.sample_count:
            session = replace(session, sample_count=len(audio), partial=True)
        return session, audio

    def delete(self, session_id: str) -> bool:
        session = self._find_exact(session_id)
        if session is None:
            return False
        shutil.rmtree(session.session_dir, ignore_errors=True)
        return not session.session_dir.exists()

    def clear_all(self) -> tuple[str, ...]:
        """Delete every local recovery directory, including malformed journals."""
        removed: list[str] = []
        failures: list[str] = []
        for session_dir in self._session_directories():
            try:
                shutil.rmtree(session_dir)
            except OSError:
                failures.append(session_dir.name)
            else:
                removed.append(session_dir.name)
        if failures:
            raise OSError(
                "无法删除恢复录音目录：" + ", ".join(sorted(failures))
            )
        return tuple(removed)

    def _session_directories(self) -> tuple[Path, ...]:
        def linked(path):
            attributes = getattr(path.lstat(), "st_file_attributes", 0)
            return path.is_symlink() or bool(
                attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            )

        if self.root.is_symlink() or (self.root.exists() and linked(self.root)):
            raise OSError("恢复录音目录是链接，无法安全访问，请检查数据目录。")
        if not self.root.is_dir():
            return ()
        children = tuple(self.root.iterdir())
        # Inspect all entries before deleting any owned session.
        if any(linked(path) for path in children):
            raise OSError("恢复录音目录包含链接，无法安全访问，请检查数据目录。")
        return tuple(path for path in children if path.is_dir())

    def _find_exact(self, session_id: str) -> RecoverableSession | None:
        expected = str(session_id)
        return next(
            (session for session in self.list_recoverable() if session.session_id == expected),
            None,
        )
