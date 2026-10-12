"""Bounded, optional final punctuation outside the Qt/audio/ASR processes."""

from __future__ import annotations

import multiprocessing
import queue
import re
import threading
import time
from pathlib import Path


MODEL_SHA256 = "65a3fb9f5ad7bfb96bf69e0dc4481df97f6ee60513c1d94ce981ba6effd524b1"
MODEL_SIZE = 75519198
MAX_CHARACTERS = 2000


def _punctuation_worker_main(commands, responses, model_path):
    from worker_lifecycle import watch_parent_exit
    from model_registry import sha256_file
    watch_parent_exit()
    try:
        path = Path(model_path)
        if path.stat().st_size != MODEL_SIZE or sha256_file(path) != MODEL_SHA256:
            raise ValueError("punctuation weights differ from the reviewed artifact")
        import sherpa_onnx
        engine = sherpa_onnx.OfflinePunctuation(sherpa_onnx.OfflinePunctuationConfig(
            model=sherpa_onnx.OfflinePunctuationModelConfig(
                ct_transformer=str(path), num_threads=1, provider="cpu")))
        responses.put({"kind": "ready"})
        while True:
            command = commands.get()
            if command["kind"] == "shutdown":
                return
            source = command["text"]
            try:
                # CT-Transformer preserves existing sentence stops. Rebuild them
                # for Chinese prose, retaining paragraphs and lexical punctuation.
                paragraphs = []
                for paragraph in source.split("\n"):
                    bare = re.sub(r"[，。！？；：,.!?;:]", "", paragraph)
                    paragraphs.append(engine.add_punctuation(bare) if bare.strip() else paragraph)
                responses.put({"kind": "result", "text": "\n".join(paragraphs)})
            except Exception:
                responses.put({"kind": "result", "text": source})
    except Exception:
        responses.put({"kind": "unavailable"})


class SupervisedPunctuation:
    """Unavailable, busy, late or failed inference always returns the input."""

    def __init__(self, model_path, *, worker_target=None, timeout=.6, startup_timeout=5):
        self.model_path = str(model_path)
        self._target = worker_target or _punctuation_worker_main
        self.timeout = float(timeout)
        self.startup_timeout = float(startup_timeout)
        self._context = multiprocessing.get_context("spawn")
        self._process = None
        self._commands = None
        self._responses = None
        self._ready = False
        self._lock = threading.Lock()

    def load(self):
        with self._lock:
            if self._process is not None:
                return self._ready
            self._commands = self._context.Queue(maxsize=1)
            self._responses = self._context.Queue(maxsize=1)
            self._process = self._context.Process(target=self._target,
                args=(self._commands, self._responses, self.model_path),
                name="voiceflow-punctuation")
            self._process.start()
            try:
                self._ready = self._responses.get(timeout=self.startup_timeout)["kind"] == "ready"
            except queue.Empty:
                self._ready = False
            if not self._ready:
                self._close()
            return self._ready

    def restore(self, source):
        if (not source or len(source) > MAX_CHARACTERS
                or not re.search(r"[\u3400-\u9fff]", source)
                or not self._lock.acquire(blocking=False)):
            return source
        try:
            if not self._ready or not self._process.is_alive():
                return source
            started = time.monotonic()
            self._commands.put_nowait({"kind": "restore", "text": source})
            response = self._responses.get(timeout=self.timeout)
            if time.monotonic() - started > self.timeout:
                self._close()
                return source
            return response.get("text", source)
        except (queue.Empty, queue.Full, OSError, EOFError):
            # Dispose the whole request channel: a late result must never be
            # applied to the next dictation.
            self._close()
            return source
        finally:
            self._lock.release()

    def _close(self):
        self._ready = False
        process = self._process
        if process is not None:
            if process.is_alive():
                try:
                    self._commands.put_nowait({"kind": "shutdown"})
                except (queue.Full, OSError):
                    pass
                process.join(timeout=.1)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
            if process.is_alive():
                raise RuntimeError("punctuation worker did not stop")
            process.close()
        self._process = None
        for channel in (self._commands, self._responses):
            if channel is not None:
                channel.cancel_join_thread()
                channel.close()

    def shutdown(self):
        with self._lock:
            self._close()
