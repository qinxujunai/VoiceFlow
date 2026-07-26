"""Benchmark the real default ASR, cleaner, and output timing path."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import wave
from pathlib import Path

import numpy as np
import pyautogui
import pyperclip
import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from output_handler import OutputHandler  # noqa: E402
from main import VoiceInputSystem  # noqa: E402
from text_cleaner import TextCleaner  # noqa: E402
from transcriber import Transcriber  # noqa: E402


def _load_pcm(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise RuntimeError("performance sample must be mono 16-bit PCM")
        sample_rate = wav.getframerate()
        audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
    return audio, sample_rate


def _fit_duration(audio: np.ndarray, sample_rate: int, seconds: int) -> np.ndarray:
    target_samples = sample_rate * seconds
    repeats = max(1, math.ceil(target_samples / max(1, len(audio))))
    return np.tile(audio, repeats)[:target_samples].copy()


def _replace_pipeline_rows(path: Path, rows: list[dict]) -> None:
    existing = []
    if path.exists():
        existing = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    existing = [
        row for row in existing
        if row.get("source") != "deterministic_full_pipeline"
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in [*existing, *rows]
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def _prepare_progressive_cache(
    transcriber: Transcriber,
    audio: np.ndarray,
    sample_rate: int,
) -> tuple[list[str], int]:
    segment_samples = int(
        sample_rate * VoiceInputSystem.FINAL_SEGMENT_SECONDS
    )
    overlap_samples = int(
        sample_rate * VoiceInputSystem.FINAL_SEGMENT_OVERLAP_SECONDS
    )
    hold_samples = int(
        sample_rate * VoiceInputSystem.FINAL_SEGMENT_HOLD_SECONDS
    )
    stable_len = max(0, len(audio) - hold_samples)
    finalized = 0
    parts = []
    while stable_len - finalized >= segment_samples:
        start = max(0, finalized - overlap_samples)
        end = finalized + segment_samples
        text = transcriber.transcribe(audio[start:end], sample_rate)
        if text and text.strip():
            parts.append(text.strip())
        finalized = end
    return parts, finalized


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--short-seconds", type=int, default=10)
    parser.add_argument("--long-seconds", type=int, default=120)
    parser.add_argument(
        "--sample",
        default=str(ROOT / "models" / "sensevoice" / "test_wavs" / "zh.wav"),
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "logs" / "performance-evidence.jsonl"),
    )
    args = parser.parse_args()
    if args.samples < 1:
        raise SystemExit("--samples must be positive")

    config_path = ROOT / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    engine_name = config.get("engine", {}).get("active", "sensevoice")
    if engine_name != "sensevoice":
        raise RuntimeError("release performance evidence must use SenseVoice")

    audio, sample_rate = _load_pcm(Path(args.sample))
    short_audio = _fit_duration(audio, sample_rate, args.short_seconds)
    long_audio = _fit_duration(audio, sample_rate, args.long_seconds)
    transcriber = Transcriber(
        str(config_path),
        asset_roots=(ROOT,),
    )
    transcriber.load_engine(engine_name)
    cleaner = TextCleaner(config, base_dir=str(ROOT))
    output = OutputHandler(str(config_path), base_dir=str(ROOT))
    progressive_parts, finalized = _prepare_progressive_cache(
        transcriber,
        long_audio,
        sample_rate,
    )
    overlap_samples = int(
        sample_rate * VoiceInputSystem.FINAL_SEGMENT_OVERLAP_SECONDS
    )
    long_tail = long_audio[max(0, finalized - overlap_samples):]
    transcript_merger = object.__new__(VoiceInputSystem)

    original_copy = pyperclip.copy
    original_hotkey = pyautogui.hotkey
    original_press = pyautogui.press
    pyperclip.copy = lambda _text: None
    pyautogui.hotkey = lambda *_args, **_kwargs: None
    pyautogui.press = lambda *_args, **_kwargs: None

    rows = []
    measured_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    try:
        for duration, pcm in ((args.short_seconds, short_audio),):
            for _ in range(args.samples):
                started = time.perf_counter()
                raw_text = transcriber.transcribe(pcm, sample_rate)
                text = cleaner.clean(raw_text) if raw_text else ""
                output.output(text or raw_text or "VoiceFlow")
                elapsed_ms = (time.perf_counter() - started) * 1000
                rows.append(
                    {
                        "source": "deterministic_full_pipeline",
                        "measured_at": measured_at,
                        "engine": engine_name,
                        "duration": float(duration),
                        "stop_to_paste_ms": round(elapsed_ms, 3),
                    }
                )
        for _ in range(args.samples):
            started = time.perf_counter()
            tail_text = transcriber.transcribe(long_tail, sample_rate)
            raw_text = transcript_merger._join_transcript_parts(
                [*progressive_parts, tail_text]
            )
            text = cleaner.clean(raw_text) if raw_text else ""
            output.output(text or raw_text or "VoiceFlow")
            elapsed_ms = (time.perf_counter() - started) * 1000
            rows.append(
                {
                    "source": "deterministic_full_pipeline",
                    "measured_at": measured_at,
                    "engine": engine_name,
                    "duration": float(args.long_seconds),
                    "segment_count": len(progressive_parts),
                    "tail_seconds": round(len(long_tail) / sample_rate, 3),
                    "stop_to_paste_ms": round(elapsed_ms, 3),
                }
            )
    finally:
        pyperclip.copy = original_copy
        pyautogui.hotkey = original_hotkey
        pyautogui.press = original_press

    _replace_pipeline_rows(Path(args.output), rows)
    print(
        json.dumps(
            {
                "samples_per_duration": args.samples,
                "durations_seconds": [args.short_seconds, args.long_seconds],
                "output": str(Path(args.output)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
