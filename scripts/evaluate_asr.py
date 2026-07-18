"""Run the reproducible, offline VoiceFlow Model Lab evaluation."""

from __future__ import annotations

import argparse
import copy
import ctypes
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import wave
from ctypes import wintypes
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from model_lab import (  # noqa: E402
    character_error_rate,
    evaluate_hard_gates,
    normalize_text,
    select_winner,
    summarize_results,
)
from model_registry import load_model_manifest, verify_model_assets  # noqa: E402
from text_cleaner import TextCleaner  # noqa: E402
from transcriber import Transcriber  # noqa: E402


def _load_samples(manifest_path: str | Path, limit: int | None = None) -> list[dict[str, Any]]:
    manifest = Path(manifest_path)
    samples: list[dict[str, Any]] = []
    with manifest.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            item = json.loads(line)
            audio = Path(item["audio"])
            if not audio.is_absolute():
                audio = manifest.parent / audio
            if not audio.is_file():
                raise FileNotFoundError(f"line {line_number}: audio not found: {audio}")
            reference = item.get("reference", item.get("expected", ""))
            samples.append({
                **item,
                "id": item.get("id") or audio.stem,
                "audio": audio,
                "reference": str(reference),
                "terms": list(item.get("terms", [])),
            })
            if limit and len(samples) >= limit:
                break
    return samples


def _read_wav(path: str | Path):
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())
    if width != 2:
        raise ValueError(f"only 16-bit PCM WAV is supported: {path}")
    import numpy as np

    audio = np.frombuffer(frames, dtype=np.int16)
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1).astype(np.int16)
    return audio.copy(), sample_rate


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _peak_memory_bytes() -> int:
    if os.name != "nt":
        return 0
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    get_current_process = ctypes.windll.kernel32.GetCurrentProcess
    get_current_process.restype = ctypes.c_void_p
    process = get_current_process()
    get_process_memory_info = ctypes.windll.kernel32.K32GetProcessMemoryInfo
    get_process_memory_info.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    get_process_memory_info.restype = wintypes.BOOL
    ok = get_process_memory_info(
        process,
        ctypes.byref(counters),
        counters.cb,
    )
    return int(counters.PeakWorkingSetSize) if ok else 0


def _term_metrics(text: str, terms: list[str]) -> tuple[int, int, list[str]]:
    normalized = normalize_text(text)
    missed = [term for term in terms if normalize_text(term) not in normalized]
    return len(terms) - len(missed), len(terms), missed


def _digit_error(reference: str, hypothesis: str) -> bool:
    return re.findall(r"\d+(?:\.\d+)?", reference) != re.findall(
        r"\d+(?:\.\d+)?", hypothesis
    )


def _tail_complete(reference: str, hypothesis: str, tail_reference: str | None = None) -> bool:
    reference_normalized = normalize_text(reference)
    hypothesis_normalized = normalize_text(hypothesis)
    tail = normalize_text(tail_reference) if tail_reference else reference_normalized[-10:]
    return bool(tail) and hypothesis_normalized.endswith(tail)


def _temporary_config(config: dict[str, Any], engine_name: str) -> Path:
    candidate = copy.deepcopy(config)
    candidate["engine"]["active"] = engine_name
    engine_config = candidate["engine"].get(engine_name, {})
    if "language" in engine_config:
        engine_config["language"] = "auto"
    handle = tempfile.NamedTemporaryFile(
        "w",
        suffix=".yaml",
        prefix=".model-lab-",
        dir=ROOT,
        delete=False,
        encoding="utf-8",
    )
    with handle:
        yaml.safe_dump(candidate, handle, allow_unicode=True, sort_keys=False)
    return Path(handle.name)


def _evaluate_model(
    model_id: str,
    model: dict[str, Any],
    samples: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    stability_cycles: int,
    stability_failures: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    engine_name = model["runtime_engine"]
    config_path = _temporary_config(config, engine_name)
    rows: list[dict[str, Any]] = []
    try:
        cleaner = TextCleaner(config, base_dir=ROOT)
        transcriber = Transcriber(str(config_path))
        started = time.perf_counter()
        transcriber.load_engine(engine_name)
        load_ms = (time.perf_counter() - started) * 1000

        for sample in samples:
            audio, sample_rate = _read_wav(sample["audio"])
            duration = len(audio) / sample_rate if sample_rate else 0
            started = time.perf_counter()
            raw_text = transcriber.transcribe(audio, sample_rate)
            clean_text = cleaner.clean(raw_text)
            stop_to_ready_ms = (time.perf_counter() - started) * 1000
            term_hits, term_total, missed_terms = _term_metrics(clean_text, sample["terms"])
            reference = sample["reference"]
            is_long_tail = bool(sample.get("long_tail")) or duration >= 60
            row = {
                "schema_version": 1,
                "model_id": model_id,
                "sample_id": sample["id"],
                "category": sample.get("category", "unspecified"),
                "duration_seconds": round(duration, 6),
                "reference": reference,
                "raw_text": raw_text,
                "clean_text": clean_text,
                "clean_cer": character_error_rate(reference, clean_text),
                "term_hits": term_hits,
                "term_total": term_total,
                "missed_terms": missed_terms,
                "blank_error": bool(normalize_text(reference)) and not bool(normalize_text(clean_text)),
                "hallucination": not bool(normalize_text(reference)) and bool(normalize_text(clean_text)),
                "digit_error": _digit_error(reference, clean_text),
                "is_long_tail": is_long_tail,
                "tail_complete": (
                    _tail_complete(reference, clean_text, sample.get("tail_reference"))
                    if is_long_tail else True
                ),
                "stop_to_ready_ms": round(stop_to_ready_ms, 3),
                "rtf": round((stop_to_ready_ms / 1000) / duration, 6) if duration else 0,
            }
            rows.append(row)
            print(
                f"{model_id:28} {sample['id']:20} "
                f"CER={row['clean_cer']} latency={row['stop_to_ready_ms']:.1f}ms"
            )

        summary = summarize_results(
            model_id,
            rows,
            load_ms=load_ms,
            peak_memory_bytes=_peak_memory_bytes(),
            offline=True,
            package_ready=True,
            stability_cycles=stability_cycles,
            stability_failures=stability_failures,
        )
        return rows, summary
    finally:
        config_path.unlink(missing_ok=True)


def _evaluate_model_isolated(
    model_id: str,
    evaluation_manifest: Path,
    model_manifest: Path,
    *,
    limit: int | None,
    stability_cycles: int,
    stability_failures: int,
    worker_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Evaluate one native recognizer in a fresh process.

    Native ASR runtimes retain allocators and model pages after Python objects are
    released. Process isolation makes the peak-memory result attributable to one
    candidate and prevents a previous candidate from contaminating the next one.
    """
    worker_output = worker_dir / f"{model_id}.json"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--manifest",
        str(evaluation_manifest),
        "--model-manifest",
        str(model_manifest),
        "--worker-model-id",
        model_id,
        "--worker-output",
        str(worker_output),
        "--stability-cycles",
        str(stability_cycles),
        "--stability-failures",
        str(stability_failures),
    ]
    if limit is not None:
        command.extend(["--limit", str(limit)])
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"{model_id} worker failed: {detail}")
    payload = json.loads(worker_output.read_text(encoding="utf-8"))
    return payload["rows"], payload["summary"]


def _run_worker(args: argparse.Namespace) -> None:
    model_manifest = load_model_manifest(args.model_manifest)
    model = model_manifest["models"].get(args.worker_model_id)
    if model is None:
        raise ValueError(f"unknown model id: {args.worker_model_id}")
    model_dir = ROOT / model["target_dir"]
    asset_errors = verify_model_assets(model_dir, model)
    if asset_errors:
        raise RuntimeError("; ".join(asset_errors))
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    samples = _load_samples(args.manifest, args.limit)
    rows, summary = _evaluate_model(
        args.worker_model_id,
        model,
        samples,
        config,
        stability_cycles=args.stability_cycles,
        stability_failures=args.stability_failures,
    )
    Path(args.worker_output).write_text(
        json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _promote_engine(config_path: Path, engine_name: str) -> None:
    text = config_path.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'(?m)^(\s*active:\s*)["\'][^"\']+["\']\s*$',
        rf'\1"{engine_name}"',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("could not locate engine.active in config.yaml")
    temporary = config_path.with_suffix(".yaml.tmp")
    temporary.write_text(updated, encoding="utf-8")
    os.replace(temporary, config_path)


def run(args: argparse.Namespace) -> dict[str, Any]:
    model_manifest_path = Path(
        getattr(args, "model_manifest", ROOT / "model-manifest.json")
    ).resolve()
    model_manifest = load_model_manifest(model_manifest_path)
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    samples = _load_samples(args.manifest, args.limit)
    if not samples:
        raise SystemExit("evaluation manifest has no samples")

    requested = list(model_manifest["models"])
    if args.model_id:
        requested = args.model_id
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("%Y%m%d-%H%M%S")
    worker_dir = output_dir / f"{run_id}-workers"
    worker_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / f"{run_id}-results.jsonl"
    summaries: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []

    for model_id in requested:
        model = model_manifest["models"].get(model_id)
        if model is None:
            raise ValueError(f"unknown model id: {model_id}")
        if model.get("eligible") is False:
            print(f"SKIP {model_id}: {model.get('ineligibility_reason', 'not eligible')}")
            continue
        model_dir = ROOT / model["target_dir"]
        asset_errors = verify_model_assets(model_dir, model)
        if asset_errors:
            print(f"SKIP {model_id}: {'; '.join(asset_errors)}")
            continue
        rows, summary = _evaluate_model_isolated(
            model_id,
            Path(args.manifest).resolve(),
            model_manifest_path,
            limit=args.limit,
            stability_cycles=args.stability_cycles,
            stability_failures=args.stability_failures,
            worker_dir=worker_dir,
        )
        all_rows.extend(rows)
        summaries.append(summary)

    if not summaries:
        raise SystemExit("no installed candidate passed asset verification")
    baseline = next(
        (item for item in summaries if item["model_id"] == "sensevoice-small-int8"),
        None,
    )
    for summary in summaries:
        comparison = None if summary is baseline else baseline
        summary["hard_gate"] = evaluate_hard_gates(summary, baseline=comparison)

    with results_path.open("w", encoding="utf-8") as handle:
        for row in all_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    winner = select_winner(summaries)
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "evaluation_manifest": str(Path(args.manifest).resolve()),
        "model_manifest": str(model_manifest_path),
        "results": str(results_path.resolve()),
        "summaries": summaries,
        "winner": winner["model_id"] if winner else None,
    }
    report_path = output_dir / f"{run_id}-summary.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.promote:
        if winner is None:
            raise SystemExit("no model passed every hard gate; default remains unchanged")
        winning_model = model_manifest["models"][winner["model_id"]]
        _promote_engine(ROOT / "config.yaml", winning_model["runtime_engine"])
        print(f"promoted default engine: {winning_model['runtime_engine']}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="VoiceFlow offline ASR model lab")
    parser.add_argument("--manifest", required=True, help="JSONL evaluation manifest")
    parser.add_argument(
        "--model-manifest",
        default=str(ROOT / "model-manifest.json"),
        help="pinned model asset manifest",
    )
    parser.add_argument("--model-id", action="append", help="candidate ID; repeat to compare")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output-dir", default=str(ROOT / "logs" / "model-lab"))
    parser.add_argument("--stability-cycles", type=int, default=0)
    parser.add_argument("--stability-failures", type=int, default=0)
    parser.add_argument("--promote", action="store_true")
    parser.add_argument("--worker-model-id", help=argparse.SUPPRESS)
    parser.add_argument("--worker-output", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker_model_id:
        if not args.worker_output:
            parser.error("--worker-output is required in worker mode")
        _run_worker(args)
        return 0
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
