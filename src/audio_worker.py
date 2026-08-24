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
    from audio_capture import AudioCapture

    stop_heartbeat = threading.Event()
    memories = {}

    def pulse():
        while not stop_heartbeat.wait(0.25):
            heartbeat.value = time.monotonic()

    def publish_pcm(block):
        try:
            events.put_nowait(
                {
                    "kind": "pcm",
                    "payload": np.asarray(block, dtype=np.int16).reshape(-1).tobytes(),
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
    capture = None
    try:
        capture = AudioCapture(config_path)
        capture.set_pcm_callback(publish_pcm)
        capture.set_level_callback(publish_level)
        events.put(
            {
                "kind": "ready",
                "sample_rate": capture.sample_rate,
                "channels": capture.channels,
                "dtype": capture.dtype,
            }
        )
        while True:
            command = commands.get()
            kind = command.get("kind")
            request_id = command.get("request_id")
            if kind == "shutdown":
                if capture.is_recording:
                    capture.cancel_recording()
                return
            try:
                if kind == "start":
                    capture.start_recording()
                    events.put(
                        {"kind": "response", "request_id": request_id, "ok": True}
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
                        }
                    )
                elif kind == "cancel":
                    capture.cancel_recording()
                    events.put(
                        {"kind": "response", "request_id": request_id, "ok": True}
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
                        {"kind": "response", "request_id": request_id, "ok": True}
                    )
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
        for memory in memories.values():
            memory.close()
            try:
                memory.unlink()
            except FileNotFoundError:
                pass


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
        self._audio_buffer = []
        self._audio_buffer_ends = []
        self._total_samples = 0
        self._buffer_start_sample = 0
        self._last_total_samples = 0
        self._last_buffer_start_sample = 0
        self._is_recording = False
        self._is_frozen = False
        self._on_level_callback = None
        self._recovery_sink = None
        self._recovery_drop_count = 0
        self._callback_status_count = 0

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

    def set_level_callback(self, callback):
        self._on_level_callback = callback

    def set_recovery_sink(self, sink):
        self._recovery_sink = sink

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
            self._audio_buffer = []
            self._audio_buffer_ends = []
            self._total_samples = 0
            self._buffer_start_sample = 0
            self._last_total_samples = 0
            self._last_buffer_start_sample = 0
            self._recovery_drop_count = 0
        response = self._request("start")
        self._raise_if_failed(response, "麦克风打开失败")
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
        try:
            response = self._request("stop", request_id=request_id)
            self._raise_if_failed(response, "麦克风停止失败")
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
                self._request(
                    "ack",
                    target_request_id=request_id,
                    timeout=min(0.5, self.command_timeout),
                )
            except RuntimeError:
                pass
        except RuntimeError:
            audio = self.snapshot_audio()
        finally:
            self._terminate_worker()
            self._is_recording = False
            self._is_frozen = False
        return audio

    def cancel_recording(self):
        try:
            if self._process is not None:
                self._request("cancel")
        except RuntimeError:
            pass
        finally:
            self._terminate_worker()
            with self._lock:
                self._audio_buffer = []
                self._audio_buffer_ends = []
                self._total_samples = 0
                self._buffer_start_sample = 0
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
                self._ready_event.set()
            elif kind == "startup_error":
                self._startup_error = str(event.get("error", "未知错误"))
                self._ready_event.set()
            elif kind == "pcm":
                self._accept_pcm(event.get("payload", b""))
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

    def _accept_pcm(self, payload):
        block = np.frombuffer(payload, dtype=np.int16).copy()
        if not len(block):
            return
        with self._lock:
            self._audio_buffer.append(block)
            self._total_samples += len(block)
            self._audio_buffer_ends.append(self._total_samples)
        recovery_sink = self._recovery_sink
        if recovery_sink is not None and not recovery_sink.append_pcm(block):
            self._recovery_drop_count += 1

    def _terminate_worker(self):
        process = self._process
        if process is not None and process.is_alive():
            try:
                self._commands.put_nowait({"kind": "shutdown"})
            except (queue.Full, OSError, ValueError):
                pass
            process.join(timeout=0.25)
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
