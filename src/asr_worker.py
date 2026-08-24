"""Supervised process boundary for native final-ASR inference."""

from __future__ import annotations

import multiprocessing
import queue
import threading
import time
import uuid
from multiprocessing import shared_memory

import numpy as np


def _asr_worker_main(
    command_queue,
    response_queue,
    heartbeat,
    worker_config,
    engine,
):
    """Load and run the native recognizer outside the Qt process."""
    from transcriber import Transcriber

    stop_heartbeat = threading.Event()

    def pulse():
        while not stop_heartbeat.wait(0.25):
            heartbeat.value = time.monotonic()

    heartbeat.value = time.monotonic()
    heartbeat_thread = threading.Thread(
        target=pulse,
        name="voiceflow-asr-heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()
    try:
        transcriber = Transcriber(
            worker_config["config_path"],
            asset_roots=worker_config.get("asset_roots"),
        )
        transcriber.load_engine(engine)
        response_queue.put({"kind": "ready", "engine": engine})
        while True:
            command = command_queue.get()
            kind = command.get("kind")
            if kind == "shutdown":
                return
            if kind != "transcribe":
                continue
            request_id = command["request_id"]
            memory = None
            try:
                memory = shared_memory.SharedMemory(name=command["shm_name"])
                audio = np.ndarray(
                    (int(command["samples"]),),
                    dtype=np.int16,
                    buffer=memory.buf,
                )
                text = transcriber.transcribe(audio, int(command["sample_rate"]))
                response_queue.put(
                    {
                        "kind": "result",
                        "request_id": request_id,
                        "text": text or "",
                    }
                )
            except Exception as error:
                response_queue.put(
                    {
                        "kind": "error",
                        "request_id": request_id,
                        "error": str(error),
                    }
                )
            finally:
                if memory is not None:
                    memory.close()
    except Exception as error:
        response_queue.put({"kind": "startup_error", "error": str(error)})
    finally:
        stop_heartbeat.set()


class SupervisedTranscriber:
    """Transcriber-compatible proxy with heartbeat and bounded IPC.

    PCM is transferred through one request-scoped shared-memory segment, so a
    long recording is not duplicated through a multiprocessing queue.
    """

    def __init__(
        self,
        config_path,
        *,
        asset_roots=None,
        worker_target=None,
        startup_timeout=30.0,
        heartbeat_timeout=2.0,
    ):
        self.config_path = str(config_path)
        self.asset_roots = tuple(str(path) for path in (asset_roots or ()))
        self.worker_target = worker_target or _asr_worker_main
        self.startup_timeout = float(startup_timeout)
        self.heartbeat_timeout = float(heartbeat_timeout)
        self._context = multiprocessing.get_context("spawn")
        self._command_queue = None
        self._response_queue = None
        self._heartbeat = None
        self._process = None
        self._engine = None
        self._ready = False
        self._request_lock = threading.Lock()

    @property
    def is_ready(self):
        return bool(self._ready and self._process and self._process.is_alive())

    @property
    def worker_pid(self):
        return self._process.pid if self._process is not None else None

    @property
    def last_heartbeat(self):
        return float(self._heartbeat.value) if self._heartbeat is not None else 0.0

    @property
    def is_healthy(self):
        return bool(
            self.is_ready
            and time.monotonic() - self.last_heartbeat <= self.heartbeat_timeout
        )

    def ensure_healthy(self):
        if self.is_healthy:
            return True
        engine = self._engine or "sensevoice"
        self._terminate_worker()
        self.load_engine(engine)
        return self.is_healthy

    def load_engine(self, engine_name=None):
        engine = engine_name or "sensevoice"
        if self.is_ready and self._engine == engine:
            return
        self.shutdown()
        self._command_queue = self._context.Queue(maxsize=2)
        self._response_queue = self._context.Queue(maxsize=2)
        self._heartbeat = self._context.Value("d", time.monotonic())
        worker_config = {
            "config_path": self.config_path,
            "asset_roots": self.asset_roots,
        }
        self._process = self._context.Process(
            target=self.worker_target,
            args=(
                self._command_queue,
                self._response_queue,
                self._heartbeat,
                worker_config,
                engine,
            ),
            name="VoiceFlow-ASR",
            daemon=True,
        )
        self._process.start()
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if not self._process.is_alive():
                self.shutdown()
                raise RuntimeError("本地识别进程启动失败")
            try:
                response = self._response_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            if response.get("kind") == "ready":
                self._engine = engine
                self._ready = True
                return
            if response.get("kind") == "startup_error":
                error = response.get("error") or "未知错误"
                self.shutdown()
                raise RuntimeError(f"本地识别初始化失败: {error}")
        self.shutdown()
        raise RuntimeError("本地识别初始化超时")

    def transcribe(self, audio_data, sample_rate=16000):
        if not self.is_ready:
            raise RuntimeError("本地识别尚未就绪")
        audio = np.asarray(audio_data, dtype=np.int16).reshape(-1)
        if len(audio) == 0:
            return ""
        with self._request_lock:
            return self._transcribe_locked(audio, int(sample_rate))

    def _transcribe_locked(self, audio, sample_rate):
        request_id = uuid.uuid4().hex
        memory = shared_memory.SharedMemory(create=True, size=audio.nbytes)
        try:
            shared_audio = np.ndarray(audio.shape, dtype=np.int16, buffer=memory.buf)
            shared_audio[:] = audio
            self._command_queue.put(
                {
                    "kind": "transcribe",
                    "request_id": request_id,
                    "shm_name": memory.name,
                    "samples": len(audio),
                    "sample_rate": sample_rate,
                },
                timeout=1.0,
            )
            duration = len(audio) / max(1, sample_rate)
            deadline = time.monotonic() + max(15.0, min(300.0, duration * 0.15 + 15.0))
            while time.monotonic() < deadline:
                process = self._process
                if process is None or not process.is_alive():
                    self._ready = False
                    restarted = self._restart_once()
                    suffix = "，已自动恢复" if restarted else ""
                    raise RuntimeError(f"本地识别进程意外退出{suffix}，录音已保留")
                if time.monotonic() - self.last_heartbeat > self.heartbeat_timeout:
                    self._ready = False
                    restarted = self._restart_once()
                    suffix = "，已自动恢复" if restarted else ""
                    raise RuntimeError(f"本地识别进程无响应{suffix}，录音已保留")
                try:
                    response = self._response_queue.get(timeout=0.05)
                except queue.Empty:
                    continue
                if response.get("request_id") != request_id:
                    continue
                if response.get("kind") == "result":
                    return response.get("text") or ""
                error = response.get("error") or "未知错误"
                raise RuntimeError(f"本地识别失败: {error}")
            self._ready = False
            restarted = self._restart_once()
            suffix = "，已自动恢复" if restarted else ""
            raise RuntimeError(f"本地识别超时{suffix}，录音已保留")
        finally:
            memory.close()
            try:
                memory.unlink()
            except FileNotFoundError:
                pass

    def shutdown(self):
        process = self._process
        if process is not None and process.is_alive():
            try:
                self._command_queue.put_nowait({"kind": "shutdown"})
            except (queue.Full, OSError, ValueError):
                pass
            process.join(timeout=1.0)
        self._terminate_worker()

    def _restart_once(self):
        engine = self._engine
        self._terminate_worker()
        if not engine:
            return False
        try:
            self.load_engine(engine)
        except Exception:
            return False
        return True

    def _terminate_worker(self):
        process = self._process
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=1.0)
        for channel in (self._command_queue, self._response_queue):
            if channel is not None:
                try:
                    channel.close()
                    channel.join_thread()
                except (OSError, ValueError):
                    pass
        self._process = None
        self._command_queue = None
        self._response_queue = None
        self._heartbeat = None
        self._ready = False
