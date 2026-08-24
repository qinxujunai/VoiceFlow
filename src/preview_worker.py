"""Supervised process boundary for the low-latency preview recognizer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import multiprocessing
from pathlib import Path
import queue
import threading
import time
import uuid

import numpy as np
import yaml

from streaming_transcriber import PreviewEvent


def _preview_worker_main(commands, responses, heartbeat, worker_config):
    """Own the native online recognizer and every recognizer stream."""
    from streaming_transcriber import OnlinePreviewTranscriber

    stop_heartbeat = threading.Event()

    def pulse():
        while not stop_heartbeat.wait(0.25):
            heartbeat.value = time.monotonic()

    heartbeat.value = time.monotonic()
    threading.Thread(
        target=pulse,
        name="voiceflow-preview-heartbeat",
        daemon=True,
    ).start()
    try:
        config_path = Path(worker_config["config_path"])
        with config_path.open("r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream) or {}
        asset_roots = tuple(Path(item) for item in worker_config["asset_roots"])

        def resolve_asset(raw_path):
            path = Path(raw_path)
            if path.is_absolute():
                return path
            for root in asset_roots:
                candidate = root / path
                if candidate.exists():
                    return candidate
            return asset_roots[0] / path

        preview = OnlinePreviewTranscriber.from_config(
            config,
            resolve_asset=resolve_asset,
            sample_rate=int(worker_config["sample_rate"]),
        )
        sessions = {}
        responses.put({"kind": "ready"})
        while True:
            command = commands.get()
            kind = command.get("kind")
            if kind == "shutdown":
                return
            request_id = command.get("request_id")
            try:
                if kind == "create_session":
                    sessions[command["session_id"]] = preview.create_session()
                    payload = {"ok": True}
                elif kind == "accept_pcm":
                    session = sessions[command["session_id"]]
                    pcm = np.frombuffer(command["pcm"], dtype=np.int16)
                    event = preview.accept_pcm(
                        session,
                        pcm,
                        int(command["sample_rate"]),
                    )
                    payload = {"ok": True, "event": asdict(event)}
                elif kind == "close_session":
                    sessions.pop(command["session_id"], None)
                    payload = {"ok": True}
                else:
                    continue
                responses.put(
                    {
                        "kind": "response",
                        "request_id": request_id,
                        **payload,
                    }
                )
            except Exception as error:
                responses.put(
                    {
                        "kind": "response",
                        "request_id": request_id,
                        "ok": False,
                        "error": str(error),
                    }
                )
    except Exception as error:
        responses.put({"kind": "startup_error", "error": str(error)})
    finally:
        stop_heartbeat.set()


@dataclass
class RemotePreviewSession:
    session_id: str
    committed_text: str = ""


class SupervisedPreviewTranscriber:
    """OnlinePreviewTranscriber-compatible proxy with bounded IPC."""

    def __init__(
        self,
        config_path,
        *,
        asset_roots=None,
        sample_rate=16000,
        worker_target=None,
        startup_timeout=30.0,
        command_timeout=2.0,
        heartbeat_timeout=2.0,
    ):
        self.config_path = str(config_path)
        self.asset_roots = tuple(str(path) for path in (asset_roots or ()))
        self.sample_rate = int(sample_rate)
        self.worker_target = worker_target or _preview_worker_main
        self.startup_timeout = float(startup_timeout)
        self.command_timeout = float(command_timeout)
        self.heartbeat_timeout = float(heartbeat_timeout)
        self._context = multiprocessing.get_context("spawn")
        self._commands = None
        self._responses = None
        self._heartbeat = None
        self._process = None
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
        self._terminate_worker()
        self.load()
        return self.is_healthy

    def load(self):
        if self.is_ready:
            return
        self.shutdown()
        self._commands = self._context.Queue(maxsize=8)
        self._responses = self._context.Queue(maxsize=8)
        self._heartbeat = self._context.Value("d", time.monotonic())
        self._process = self._context.Process(
            target=self.worker_target,
            args=(
                self._commands,
                self._responses,
                self._heartbeat,
                {
                    "config_path": self.config_path,
                    "asset_roots": self.asset_roots or (str(Path(self.config_path).parent),),
                    "sample_rate": self.sample_rate,
                },
            ),
            name="VoiceFlow-Preview",
            daemon=True,
        )
        self._process.start()
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if not self._process.is_alive():
                self.shutdown()
                raise RuntimeError("实时预览进程启动失败")
            try:
                response = self._responses.get(timeout=0.05)
            except queue.Empty:
                continue
            if response.get("kind") == "ready":
                self._ready = True
                return
            if response.get("kind") == "startup_error":
                error = response.get("error") or "未知错误"
                self.shutdown()
                raise RuntimeError(f"实时预览初始化失败: {error}")
        self.shutdown()
        raise RuntimeError("实时预览初始化超时")

    def create_session(self):
        session = RemotePreviewSession(session_id=uuid.uuid4().hex)
        self._request("create_session", session_id=session.session_id)
        return session

    def accept_pcm(self, session, pcm, sample_rate):
        samples = np.asarray(pcm, dtype=np.int16).reshape(-1)
        response = self._request(
            "accept_pcm",
            session_id=session.session_id,
            pcm=samples.tobytes(),
            sample_rate=int(sample_rate),
        )
        event = PreviewEvent(**response["event"])
        session.committed_text = event.committed_text
        return event

    def close_session(self, session):
        if self.is_ready:
            self._request("close_session", session_id=session.session_id)

    def shutdown(self):
        process = self._process
        if process is not None and process.is_alive():
            try:
                self._commands.put_nowait({"kind": "shutdown"})
            except (queue.Full, OSError, ValueError):
                pass
            process.join(timeout=1.0)
        self._terminate_worker()

    def _request(self, kind, **payload):
        if not self.is_ready:
            raise RuntimeError("实时预览尚未就绪")
        with self._request_lock:
            request_id = uuid.uuid4().hex
            try:
                self._commands.put(
                    {"kind": kind, "request_id": request_id, **payload},
                    timeout=0.5,
                )
            except queue.Full as error:
                self._terminate_worker()
                raise RuntimeError("实时预览任务拥堵") from error
            deadline = time.monotonic() + self.command_timeout
            while time.monotonic() < deadline:
                if self._process is None or not self._process.is_alive():
                    self._terminate_worker()
                    raise RuntimeError("实时预览进程意外退出")
                if time.monotonic() - self.last_heartbeat > self.heartbeat_timeout:
                    self._terminate_worker()
                    raise RuntimeError("实时预览进程无响应")
                try:
                    response = self._responses.get(timeout=0.05)
                except queue.Empty:
                    continue
                if response.get("request_id") != request_id:
                    continue
                if response.get("ok"):
                    return response
                raise RuntimeError(response.get("error") or "实时预览失败")
            self._terminate_worker()
            raise RuntimeError("实时预览超时")

    def _terminate_worker(self):
        process = self._process
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=1.0)
        for channel in (self._commands, self._responses):
            if channel is not None:
                try:
                    channel.close()
                    channel.join_thread()
                except (OSError, ValueError):
                    pass
        self._process = None
        self._commands = None
        self._responses = None
        self._heartbeat = None
        self._ready = False
