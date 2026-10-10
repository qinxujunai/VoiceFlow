"""Exercise source startup/exit with real native workers and no recording or input."""

import argparse
import hashlib
import json
import multiprocessing
from pathlib import Path
import shutil
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def exercise(stage, directory, connection):
    import main as runtime
    from runtime_paths import AppPaths, RuntimeMode, prepare_runtime_layout

    data = Path(directory)
    data.mkdir()
    shutil.copy2(ROOT / "config.yaml", data / "config.yaml")
    empty_legacy = data / "empty-legacy"
    empty_legacy.mkdir()
    runtime.prepare_runtime_layout = lambda paths: prepare_runtime_layout(
        paths, legacy_root=empty_legacy)
    paths = AppPaths(mode=RuntimeMode.FROZEN, install_dir=ROOT, data_dir=data,
                     executable=Path(sys.executable))
    system = runtime.VoiceInputSystem(paths=paths, register_hotkeys=False)
    entered, release = threading.Event(), threading.Event()
    callback_states = []
    classes = {"audio": (runtime.SupervisedAudioCapture, "prepare"),
               "ASR": (runtime.SupervisedTranscriber, "load_engine"),
               "preview": (runtime.SupervisedPreviewTranscriber, "load")}
    cls, name = classes[stage]
    original = getattr(cls, name)

    def pause_after_native_ready(instance, *args, **kwargs):
        result = original(instance, *args, **kwargs)
        entered.set()
        if not release.wait(30):
            raise TimeoutError("exit fixture release timeout")
        return result

    setattr(cls, name, pause_after_native_ready)
    initializer = runtime._InitWorker(
        system, lambda: callback_states.append("ready"),
        lambda _error: callback_states.append("error"))
    failure = []
    stopper = None
    try:
        initializer.start()
        if not entered.wait(45):
            raise TimeoutError(f"native startup did not reach {stage}")
        worker_processes = [worker._process for worker in (
            getattr(system, "audio", None), getattr(system, "transcriber", None),
            getattr(system, "preview_transcriber", None))
            if worker is not None and worker._process is not None]
        worker_ids = [process.pid for process in worker_processes]
        assert len(worker_ids) == {"audio": 1, "ASR": 2, "preview": 3}[stage]

        def close():
            try:
                system.shutdown()
            except Exception as error:
                failure.append(type(error).__name__)

        started = time.perf_counter()
        stopper = threading.Thread(target=close)
        stopper.start()
        assert system._runtime_supervisor_stop.wait(1)
        release.set()
        initializer.join(10)
        stopper.join(10)
        elapsed_ms = (time.perf_counter() - started) * 1000
        assert not initializer.is_alive() and not stopper.is_alive()
        assert not failure and not callback_states
        assert all(not process.is_alive() for process in worker_processes)
        assert not multiprocessing.active_children()
        assert not hasattr(system, "output_handler"), "exit must precede clipboard/focus startup"
        connection.send({"stage": stage, "worker_pids": worker_ids,
                         "shutdown_ms": elapsed_ms, "all_owned_workers_exited": True,
                         "late_callbacks": callback_states,
                         "output_handler_started": False})
    finally:
        release.set()
        initializer.join(5)
        if stopper is not None:
            stopper.join(5)
        setattr(cls, name, original)
        if not system._shutdown_started:
            system.shutdown()
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    directory = args.output.parent / ("native-exit-" + uuid.uuid4().hex)
    directory.mkdir(parents=True)
    context = multiprocessing.get_context("spawn")
    rows = []
    for stage in ("audio", "ASR", "preview"):
        parent, child = context.Pipe(duplex=False)
        process = context.Process(target=exercise, args=(stage, directory / stage, child))
        process.start()
        child.close()
        try:
            if not parent.poll(60):
                raise TimeoutError(f"native exit fixture timed out: {stage}")
            rows.append(parent.recv())
            process.join(10)
            if process.exitcode != 0:
                raise RuntimeError(f"native exit fixture failed: {stage}, {process.exitcode}")
        finally:
            if process.is_alive():
                process.terminate()
                process.join(5)
            parent.close()
    report = {
        "kind": "source_native_startup_shutdown",
        "scope": "Three isolated source instances, actual microphone worker initialization and native final/preview model loading. No microphone stream, GUI, clipboard, keys, user history or packaged acceptance. Exit is latched at a controlled barrier after each native stage becomes ready.",
        "source_sha256": {name: hashlib.sha256((ROOT / "src" / name).read_bytes()).hexdigest()
                          for name in ("main.py", "audio_worker.py", "asr_worker.py", "preview_worker.py")},
        "fixture": str(directory), "cases": rows,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
