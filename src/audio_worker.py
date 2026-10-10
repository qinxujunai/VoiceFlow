"""Supervised microphone process that cannot freeze VoiceFlow's Qt UI."""

from __future__ import annotations

import bisect
import multiprocessing
import queue
import threading
import time
import uuid
from multiprocessing import shared_memory

import numpy as np
import yaml


def _audio_worker_main(commands, events, heartbeat, config_path):
    from worker_lifecycle import watch_parent_exit

    capture = None
    journal = None
    published_samples = 0

    def close_recovery():
        if journal is not None:
            if capture is not None and capture.is_recording:
                capture.freeze_recording()
            journal.close_interrupted()

    watch_parent_exit(close_recovery)
    from audio_capture import AudioCapture
    from recovery_session import RecoverySessionStore

    stop_heartbeat = threading.Event()
    memories = {}

    def pulse():
        while not stop_heartbeat.wait(0.25):
            heartbeat.value = time.monotonic()
            if journal is not None and journal.writer_error:
                if capture is not None and capture.is_recording:
                    capture.freeze_recording()
                try:
                    events.put_nowait({"kind": "recovery_error", "error": journal.writer_error})
                except queue.Full:
                    pass

    def publish_pcm(block):
        nonlocal published_samples
        samples = np.asarray(block, dtype=np.int16).reshape(-1)
        start_sample = published_samples
        published_samples += len(samples)
        try:
            events.put_nowait(
                {
                    "kind": "pcm",
                    "payload": samples.tobytes(),
                    "start_sample": start_sample,
                }
            )
        except queue.Full:
            pass

    def publish_level(levels):
        try:
            events.put_nowait({"kind": "level", "levels": list(levels)})
        except queue.Full:
            pass

    heartbeat.value = time.monotonic()
    threading.Thread(
        target=pulse,
        name="voiceflow-audio-heartbeat",
        daemon=True,
    ).start()
    try:
        capture = AudioCapture(config_path)
        capture.set_pcm_callback(publish_pcm)
        capture.set_level_callback(publish_level)
        enumerate_devices = getattr(capture, "list_devices", None)
        microphones = enumerate_devices() if enumerate_devices is not None else []
        events.put(
            {
                "kind": "ready",
                "sample_rate": capture.sample_rate,
                "channels": capture.channels,
                "dtype": capture.dtype,
                "microphones": [(device["name"], device["index"]) for device in microphones[:128]],
            }
        )
        while True:
            command = commands.get()
            kind = command.get("kind")
            request_id = command.get("request_id")
            if kind == "shutdown":
                close_recovery()
                if capture.is_recording:
                    capture.cancel_recording()
                return
            try:
                if kind == "start":
                    close_recovery()
                    journal = None
                    published_samples = 0
                    recovery = command.get("recovery")
                    if recovery:
                        store = RecoverySessionStore(
                            recovery["root"],
                            max_storage_bytes=recovery.get("max_storage_bytes", RecoverySessionStore.DEFAULT_MAX_STORAGE_BYTES),
                            min_free_bytes=recovery.get("min_free_bytes", RecoverySessionStore.DEFAULT_MIN_FREE_BYTES),
                        )
                        journal = store.start_session(
                            session_id=recovery["session_id"],
                            sample_rate=capture.sample_rate,
                            channels=capture.channels,
                            dtype=capture.dtype,
                            model=recovery["model"],
                        )
                        capture.set_recovery_sink(journal)
                    else:
                        capture.set_recovery_sink(None)
                    capture.start_recording()
                    if journal is not None:
                        journal.mark_state("recording")
                    events.put(
                        {"kind": "response", "request_id": request_id, "ok": True,
                         "recovery": journal.status() if journal is not None else None}
                    )
                elif kind == "freeze":
                    samples = capture.freeze_recording()
                    events.put(
                        {
                            "kind": "response",
                            "request_id": request_id,
                            "ok": True,
                            "samples": samples,
                        }
                    )
                elif kind == "stop":
                    audio = capture.stop_recording()
                    close_recovery()
                    recovery_status = journal.status() if journal is not None else None
                    if recovery_status is not None and recovery_status["closed"]:
                        capture.set_recovery_sink(None)
                        journal = None
                    memory = shared_memory.SharedMemory(create=True, size=max(2, audio.nbytes))
                    if len(audio):
                        np.ndarray(audio.shape, dtype=np.int16, buffer=memory.buf)[:] = audio
                    memories[request_id] = memory
                    events.put(
                        {
                            "kind": "response",
                            "request_id": request_id,
                            "ok": True,
                            "shm_name": memory.name,
                            "samples": len(audio),
                            "recovery": recovery_status,
                        }
                    )
                elif kind == "cancel":
                    capture.cancel_recording()
                    if journal is not None:
                        journal.close_without_recovery()
                    journal = None
                    events.put(
                        {"kind": "response", "request_id": request_id, "ok": True,
                         "reusable": capture.wait_for_stream_teardown()}
                    )
                elif kind == "ack":
                    target = command.get("target_request_id")
                    memory = memories.pop(target, None)
                    if memory is not None:
                        memory.close()
                        try:
                            memory.unlink()
                        except FileNotFoundError:
                            pass
                    events.put(
                        {"kind": "response", "request_id": request_id, "ok": True,
                         "reusable": capture.wait_for_stream_teardown()}
                    )
                elif kind == "recovery_state":
                    if journal is not None and journal.session_id != command["session_id"]:
                        raise RuntimeError("recovery session changed")
                    if journal is not None:
                        journal.mark_state(command["state"], preview_text=command.get("preview_text"))
                    events.put({"kind": "response", "request_id": request_id, "ok": True,
                                "recovery": journal.status() if journal is not None else None})
                elif kind == "recovery_close":
                    if journal is not None and journal.session_id != command["session_id"]:
                        raise RuntimeError("recovery session changed")
                    close_recovery()
                    events.put({"kind": "response", "request_id": request_id, "ok": True,
                                "recovery": journal.status() if journal is not None else None})
            except Exception as error:
                events.put(
                    {
                        "kind": "response",
                        "request_id": request_id,
                        "ok": False,
                        "error": str(error),
                    }
                )
    except Exception as error:
        events.put({"kind": "startup_error", "error": str(error)})
    finally:
        stop_heartbeat.set()
        close_recovery()
        for memory in memories.values():
            memory.close()
            try:
                memory.unlink()
            except FileNotFoundError:
                pass


class _WorkerRecoveryJournal:
    """Host-side handle; PCM is accepted and journaled only in the audio worker."""

    def __init__(self, capture, store, descriptor):
        self._capture = capture
        self._store = store
        self.session_id = descriptor["session_id"]

    @property
    def writer_error(self):
        return self._capture.recovery_error

    def mark_state(self, state, *, preview_text=None):
        try:
            response = self._capture._request("recovery_state", session_id=self.session_id,
                                             state=state, preview_text=preview_text)
            self._capture._raise_if_failed(response, "录音保存状态无法更新")
            self._capture._update_recovery_status(response)
        except RuntimeError:
            self._capture._recovery_error = "recovery_worker_unavailable"

    def close_interrupted(self):
        if self._capture._recovery_closed_session == self.session_id:
            return True
        try:
            response = self._capture._request("recovery_close", session_id=self.session_id)
            self._capture._update_recovery_status(response)
        except RuntimeError:
            self._capture._recovery_error = "recovery_worker_unavailable"
        return self._capture._recovery_closed_session == self.session_id

    def mark_delivered(self, _text_sha256):
        if self.close_interrupted():
            deleted = self._store.delete(self.session_id)
            self._capture._recovery_descriptor = None
            return deleted
        return False

    def close_without_recovery(self):
        # An explicit cancel command already closes/deletes the worker journal.
        # On failure, retain files until the worker is proven stopped.
        if self._capture._process is None or self.close_interrupted():
            deleted = self._store.delete(self.session_id)
            self._capture._recovery_descriptor = None
            return deleted
        return False


class SupervisedAudioCapture:
    """AudioCapture-compatible proxy backed by a disposable worker process."""

    def __init__(
        self,
        config_path,
        *,
        worker_target=None,
        startup_timeout=10.0,
        command_timeout=2.0,
        heartbeat_timeout=2.0,
    ):
        self.config_path = str(config_path)
        with open(self.config_path, "r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream) or {}
        audio = config.get("audio", {})
        self.sample_rate = int(audio.get("sample_rate", 16000))
        self.channels = int(audio.get("channels", 1))
        self.dtype = str(audio.get("dtype", "int16"))
        self.worker_target = worker_target or _audio_worker_main
        self.startup_timeout = float(startup_timeout)
        self.command_timeout = float(command_timeout)
        self.heartbeat_timeout = float(heartbeat_timeout)
        self._context = multiprocessing.get_context("spawn")
        self._process = None
        self._commands = None
        self._events = None
        self._heartbeat = None
        self._ready_event = threading.Event()
        self._startup_error = ""
        self._receiver_stop = threading.Event()
        self._receiver_thread = None
        self._waiters = {}
        self._waiters_lock = threading.Lock()
        self._lock = threading.RLock()
        self._pcm_closed = False
        self._audio_buffer = []
        self._audio_buffer_ends = []
        self._total_samples = 0
        self._buffer_start_sample = 0
        self._last_total_samples = 0
        self._last_buffer_start_sample = 0
        self._is_recording = False
        self._is_frozen = False
        self._on_level_callback = None
        self._recovery_descriptor = None
        self._recovery_closed_session = None
        self._recovery_error = None
        self._recovery_drop_count = 0
        self._preview_pcm_gap = False
        self._callback_status_count = 0
        self._microphones = []

    @property
    def worker_pid(self):
        return self._process.pid if self._process is not None else None

    @property
    def last_heartbeat(self):
        return float(self._heartbeat.value) if self._heartbeat is not None else 0.0

    @property
    def is_ready(self):
        return bool(
            self._process
            and self._process.is_alive()
            and self._ready_event.is_set()
        )

    @property
    def is_healthy(self):
        return bool(
            self.is_ready
            and time.monotonic() - self.last_heartbeat <= self.heartbeat_timeout
        )

    @property
    def is_recording(self):
        return self._is_recording

    @property
    def is_frozen(self):
        return self._is_frozen

    @property
    def sample_count(self):
        with self._lock:
            return self._total_samples

    @property
    def buffer_start_sample(self):
        with self._lock:
            return self._buffer_start_sample

    @property
    def last_total_samples(self):
        return self._last_total_samples

    @property
    def last_buffer_start_sample(self):
        return self._last_buffer_start_sample

    @property
    def callback_status_count(self):
        return self._callback_status_count

    @property
    def recovery_drop_count(self):
        return self._recovery_drop_count

    @property
    def recovery_error(self):
        return self._recovery_error

    @property
    def preview_pcm_gap(self):
        return self._preview_pcm_gap

    @property
    def microphones(self):
        return list(self._microphones)

    def set_level_callback(self, callback):
        self._on_level_callback = callback

    def set_recovery_sink(self, sink):
        if sink is not None:
            raise ValueError("recovery PCM belongs to the audio worker")

    def create_recovery_journal(self, store, *, session_id, model):
        descriptor = {"root": str(store.root), "session_id": str(session_id),
                      "sample_rate": self.sample_rate, "channels": self.channels,
                      "dtype": self.dtype, "model": str(model),
                      "max_storage_bytes": store.max_storage_bytes,
                      "min_free_bytes": store.min_free_bytes}
        self._recovery_descriptor = descriptor
        self._recovery_closed_session = None
        self._recovery_error = None
        return _WorkerRecoveryJournal(self, store, descriptor)

    def _update_recovery_status(self, response):
        status = response.get("recovery")
        if not status:
            return
        if status.get("writer_error"):
            self._recovery_error = str(status["writer_error"])
        if status.get("closed") and self._recovery_descriptor:
            self._recovery_closed_session = self._recovery_descriptor["session_id"]

    def prepare(self):
        """Start the disposable device process before the first hotkey tap."""
        self._ensure_worker()

    def ensure_healthy(self):
        if self.is_healthy:
            return True
        self._terminate_worker()
        self.prepare()
        return self.is_healthy

    def start_recording(self):
        self._ensure_worker()
        with self._lock:
            self._pcm_closed = False
            self._audio_buffer = []
            self._audio_buffer_ends = []
            self._total_samples = 0
            self._buffer_start_sample = 0
            self._last_total_samples = 0
            self._last_buffer_start_sample = 0
            self._recovery_drop_count = 0
            self._preview_pcm_gap = False
        response = self._request("start", recovery=self._recovery_descriptor)
        self._raise_if_failed(response, "麦克风打开失败")
        self._update_recovery_status(response)
        self._is_recording = True
        self._is_frozen = False

    def freeze_recording(self):
        if not self._is_recording:
            return self._last_total_samples if self._is_frozen else 0
        response = self._request("freeze")
        self._raise_if_failed(response, "麦克风停止失败")
        frozen = int(response.get("samples", self.sample_count))
        deadline = time.monotonic() + min(0.5, self.command_timeout)
        while self.sample_count < frozen and time.monotonic() < deadline:
            time.sleep(0.005)
        self._last_total_samples = frozen
        self._last_buffer_start_sample = self._buffer_start_sample
        self._is_recording = False
        self._is_frozen = True
        return frozen

    def stop_recording(self):
        if not self._is_recording and not self._is_frozen:
            return np.empty(0, dtype=np.int16)
        if self._is_recording:
            self.freeze_recording()
        request_id = uuid.uuid4().hex
        reusable = False
        try:
            response = self._request("stop", request_id=request_id)
            self._raise_if_failed(response, "麦克风停止失败")
            self._update_recovery_status(response)
            samples = int(response.get("samples", 0))
            memory = shared_memory.SharedMemory(name=response["shm_name"])
            try:
                audio = np.ndarray(
                    (samples,),
                    dtype=np.int16,
                    buffer=memory.buf,
                ).copy()
            finally:
                memory.close()
            try:
                acknowledgement = self._request(
                    "ack",
                    target_request_id=request_id,
                    timeout=min(0.5, self.command_timeout),
                )
                reusable = bool(acknowledgement.get("ok") and acknowledgement.get("reusable"))
            except RuntimeError:
                pass
        except RuntimeError:
            audio = self.snapshot_audio()
        finally:
            if not reusable:
                self._terminate_worker()
            self._release_pcm()
            self._is_recording = False
            self._is_frozen = False
        return audio

    def _release_pcm(self):
        # The caller owns a detached final copy; reject any late preview PCM.
        with self._lock:
            self._pcm_closed = True
            self._audio_buffer = []
            self._audio_buffer_ends = []
            self._total_samples = 0
            self._buffer_start_sample = 0

    def cancel_recording(self):
        reusable = False
        try:
            if self._process is not None:
                response = self._request("cancel")
                reusable = bool(response.get("ok") and response.get("reusable"))
        except RuntimeError:
            pass
        finally:
            if not reusable:
                self._terminate_worker()
            self._release_pcm()
            self._is_recording = False
            self._is_frozen = False

    def snapshot_audio(self, start_sample=0, end_sample=None):
        with self._lock:
            total = self._total_samples
            start = max(self._buffer_start_sample, min(int(start_sample), total))
            end = total if end_sample is None else max(start, min(int(end_sample), total))
            if start >= end or not self._audio_buffer:
                return np.empty(0, dtype=np.int16)
            first = bisect.bisect_right(self._audio_buffer_ends, start)
            last = bisect.bisect_left(self._audio_buffer_ends, end) + 1
            blocks = tuple(self._audio_buffer[first:last])
            base = (
                self._buffer_start_sample
                if first == 0
                else self._audio_buffer_ends[first - 1]
            )
        selected = np.concatenate(blocks).reshape(-1)
        return selected[start - base : end - base].copy()

    def discard_before(self, sample_index):
        with self._lock:
            target = max(
                self._buffer_start_sample,
                min(int(sample_index), self._total_samples),
            )
            drop_count = bisect.bisect_right(self._audio_buffer_ends, target)
            if drop_count <= 0:
                return self._buffer_start_sample
            self._buffer_start_sample = self._audio_buffer_ends[drop_count - 1]
            del self._audio_buffer[:drop_count]
            del self._audio_buffer_ends[:drop_count]
            return self._buffer_start_sample

    def shutdown(self):
        self._terminate_worker()

    def _ensure_worker(self):
        if self._process is not None and self._process.is_alive():
            return
        self._ready_event = threading.Event()
        self._receiver_stop = threading.Event()
        self._startup_error = ""
        self._commands = self._context.Queue(maxsize=8)
        self._events = self._context.Queue(maxsize=2048)
        self._heartbeat = self._context.Value("d", time.monotonic())
        self._process = self._context.Process(
            target=self.worker_target,
            args=(self._commands, self._events, self._heartbeat, self.config_path),
            name="VoiceFlow-Audio",
            daemon=True,
        )
        self._process.start()
        self._receiver_thread = threading.Thread(
            target=self._receive_events,
            name="voiceflow-audio-events",
            daemon=True,
        )
        self._receiver_thread.start()
        if not self._ready_event.wait(timeout=self.startup_timeout):
            self._terminate_worker()
            raise RuntimeError("麦克风进程启动超时")
        if self._startup_error:
            error = self._startup_error
            self._terminate_worker()
            raise RuntimeError(f"麦克风进程启动失败: {error}")

    def _request(self, kind, *, request_id=None, timeout=None, **payload):
        process = self._process
        if process is None or not process.is_alive():
            raise RuntimeError("麦克风进程不可用")
        request_id = request_id or uuid.uuid4().hex
        waiter = queue.Queue(maxsize=1)
        with self._waiters_lock:
            self._waiters[request_id] = waiter
        try:
            command = {"kind": kind, "request_id": request_id}
            command.update(payload)
            self._commands.put(command, timeout=min(0.5, self.command_timeout))
            try:
                return waiter.get(timeout=self.command_timeout if timeout is None else timeout)
            except queue.Empty:
                raise RuntimeError(f"麦克风动作超时: {kind}")
        finally:
            with self._waiters_lock:
                self._waiters.pop(request_id, None)

    @staticmethod
    def _raise_if_failed(response, prefix):
        if not response.get("ok"):
            raise RuntimeError(f"{prefix}: {response.get('error', '未知错误')}")

    def _receive_events(self):
        while not self._receiver_stop.is_set():
            try:
                event = self._events.get(timeout=0.05)
            except queue.Empty:
                process = self._process
                if process is None or not process.is_alive():
                    return
                continue
            kind = event.get("kind")
            if kind == "ready":
                self.sample_rate = int(event.get("sample_rate", self.sample_rate))
                self.channels = int(event.get("channels", self.channels))
                self.dtype = str(event.get("dtype", self.dtype))
                self._microphones = list(event.get("microphones") or [])[:128]
                self._ready_event.set()
            elif kind == "startup_error":
                self._startup_error = str(event.get("error", "未知错误"))
                self._ready_event.set()
            elif kind == "pcm":
                self._accept_pcm(event.get("payload", b""), start_sample=event.get("start_sample"))
            elif kind == "recovery_error":
                self._recovery_error = str(event.get("error", "recovery_write_failed"))
            elif kind == "level":
                callback = self._on_level_callback
                if callback is not None:
                    try:
                        callback(event.get("levels") or [])
                    except Exception:
                        pass
            elif kind == "response":
                request_id = event.get("request_id")
                with self._waiters_lock:
                    waiter = self._waiters.get(request_id)
                if waiter is not None:
                    try:
                        waiter.put_nowait(event)
                    except queue.Full:
                        pass

    def _accept_pcm(self, payload, *, start_sample=None):
        block = np.frombuffer(payload, dtype=np.int16).copy()
        if not len(block):
            return
        with self._lock:
            if self._pcm_closed:
                return
            if self._preview_pcm_gap or (
                start_sample is not None and int(start_sample) != self._total_samples
            ):
                self._preview_pcm_gap = True
                return
            self._audio_buffer.append(block)
            self._total_samples += len(block)
            self._audio_buffer_ends.append(self._total_samples)

    def _terminate_worker(self):
        process = self._process
        if process is not None and process.is_alive():
            try:
                self._commands.put_nowait({"kind": "shutdown"})
            except (queue.Full, OSError, ValueError):
                pass
            active_journal = self._recovery_descriptor is not None and (
                self._recovery_closed_session != self._recovery_descriptor["session_id"]
            )
            process.join(timeout=2.0 if active_journal else 0.25)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1.0)
        self._receiver_stop.set()
        thread = self._receiver_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=0.25)
        for channel in (self._commands, self._events):
            if channel is not None:
                try:
                    channel.close()
                    channel.join_thread()
                except (OSError, ValueError):
                    pass
        self._process = None
        self._commands = None
        self._events = None
        self._heartbeat = None
        self._receiver_thread = None
