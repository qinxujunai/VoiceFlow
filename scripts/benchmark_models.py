"""
Benchmark available VoiceFlow ASR model variants.

This does not change config.yaml. It probes local model files and reports
load time, transcription time, RTF, and output text for bundled test wavs.
"""

from __future__ import annotations

import argparse
import copy
import json
import tempfile
import time
import wave
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

import sys

sys.path.insert(0, str(SRC))

from transcriber import Transcriber  # noqa: E402
from vocabulary import Vocabulary  # noqa: E402


def _variant_configs(config):
    variants = []
    engine = config.get("engine", {})
    sense = copy.deepcopy(engine.get("sensevoice", {}))
    qwen = copy.deepcopy(engine.get("qwen3-asr", {}))

    if sense:
        int8 = copy.deepcopy(config)
        int8["engine"]["active"] = "sensevoice"
        int8["engine"]["sensevoice"]["model_path"] = "models/sensevoice/model.int8.onnx"
        variants.append(("sensevoice-int8", int8))

        fp32_path = ROOT / "models" / "sensevoice" / "model.onnx"
        if fp32_path.exists():
            fp32 = copy.deepcopy(config)
            fp32["engine"]["active"] = "sensevoice"
            fp32["engine"]["sensevoice"]["model_path"] = "models/sensevoice/model.onnx"
            variants.append(("sensevoice-fp32", fp32))

    qwen_model = ROOT / qwen.get("model_path", "")
    qwen_tokens = ROOT / qwen.get("tokens_path", "")
    if qwen and qwen_model.exists() and qwen_tokens.exists():
        qwen_cfg = copy.deepcopy(config)
        qwen_cfg["engine"]["active"] = "qwen3-asr"
        variants.append(("qwen3-asr", qwen_cfg))

    return variants


def _write_temp_config(config):
    handle = tempfile.NamedTemporaryFile(
        "w",
        suffix=".yaml",
        prefix=".benchmark-",
        dir=ROOT,
        delete=False,
        encoding="utf-8",
    )
    with handle:
        yaml.safe_dump(config, handle, allow_unicode=True, sort_keys=False)
    return handle.name


def _wav_files(limit=None):
    wav_dir = ROOT / "models" / "sensevoice" / "test_wavs"
    files = sorted(wav_dir.glob("*.wav"))
    samples = [{"id": path.stem, "audio": path, "reference": ""} for path in files]
    return samples[:limit] if limit else samples


def _eval_samples(manifest_path, limit=None):
    samples = []
    manifest = Path(manifest_path)
    with manifest.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            item = json.loads(line)
            audio = Path(item["audio"])
            if not audio.is_absolute():
                audio = manifest.parent / audio
            samples.append({
                "id": item.get("id") or audio.stem,
                "audio": audio,
                "reference": item.get("reference", ""),
            })
    return samples[:limit] if limit else samples


def _read_wav(path):
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if sample_width != 2:
        raise ValueError(f"Only 16-bit PCM wav is supported: {path}")

    import numpy as np

    audio = np.frombuffer(frames, dtype=np.int16)
    if channels > 1:
        audio = audio.reshape(-1, channels)[:, 0]
    return audio.copy(), sample_rate


def _domain_terms(config):
    hotwords = config.get("hotwords", {})
    files = hotwords.get("files")
    directory = hotwords.get("directory", "knowledge-base")
    vocab = Vocabulary(ROOT, files=files, directory=directory)
    return sorted(vocab.terms, key=len, reverse=True)


def _term_stats(text, terms):
    if not text:
        return 0, []
    hits = [term for term in terms if term and term in text]
    return len(hits), hits[:8]


def _char_error_rate(reference, hypothesis):
    reference = "".join(str(reference or "").split())
    hypothesis = "".join(str(hypothesis or "").split())
    if not reference:
        return None
    previous = list(range(len(hypothesis) + 1))
    for i, ref_char in enumerate(reference, start=1):
        current = [i]
        for j, hyp_char in enumerate(hypothesis, start=1):
            cost = 0 if ref_char == hyp_char else 1
            current.append(min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + cost,
            ))
        previous = current
    return previous[-1] / len(reference)


def benchmark(limit=None, manifest=None):
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    samples = _eval_samples(manifest, limit) if manifest else _wav_files(limit)
    terms = _domain_terms(config)
    if not samples:
        raise SystemExit("No benchmark samples found")

    for name, cfg in _variant_configs(config):
        cfg_path = _write_temp_config(cfg)
        try:
            transcriber = Transcriber(cfg_path)

            t0 = time.time()
            transcriber.load_engine(cfg["engine"]["active"])
            load_time = time.time() - t0
            print(f"\n== {name} | load {load_time:.2f}s ==")

            for sample in samples:
                audio, sample_rate = _read_wav(sample["audio"])
                duration = len(audio) / sample_rate
                t1 = time.time()
                text = transcriber.transcribe(audio, sample_rate)
                elapsed = time.time() - t1
                rtf = elapsed / duration if duration else 0
                term_count, term_hits = _term_stats(text, terms)
                cer = _char_error_rate(sample["reference"], text)
                cer_label = "-" if cer is None else f"{cer:.3f}"
                print(
                    f"{sample['id']:>12} | {elapsed:.2f}s | RTF {rtf:.3f} | "
                    f"CER {cer_label} | terms {term_count:02d} | {text}"
                )
                if term_hits:
                    print(f"{'':>12} | term hits: {', '.join(term_hits)}")
        finally:
            Path(cfg_path).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Benchmark local VoiceFlow ASR models")
    parser.add_argument("--limit", type=int, default=None, help="limit number of wav files")
    parser.add_argument("--manifest", default=None, help="JSONL eval manifest with audio/reference fields")
    args = parser.parse_args()
    benchmark(limit=args.limit, manifest=args.manifest)


if __name__ == "__main__":
    main()
