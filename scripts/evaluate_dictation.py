"""Accuracy of recorded dictations through VoiceFlow's real final path.

Each manifest WAV is fed to the app's own progressive final cache and stop path (src/main.py:
_next_final_segment_range, _quiet_cut, _commit_final_segment, _transcribe_final_result) one 100 ms block
at a time, with the real streaming preview recognizer finding pauses and the app's Transcriber doing the
final recognition. The result then goes through the same TextCleaner as delivery. This is what the user
gets; scripts/evaluate_asr.py instead recognizes each file in one pass, which SenseVoice is not built for
beyond about 30 s.

Scores: MER, the mixed error rate (each Chinese character and each English word is one token; case,
spaces and punctuation are ignored), and important-term hits (case and spaces ignored).
Manifest format: eval/README.md. Needs a display for Qt imports (xvfb-run on Linux).

    python scripts/evaluate_dictation.py --manifest eval/private/local.jsonl [--engine sensevoice]
"""
import argparse
import copy
import json
import re
import statistics
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dictation_preferences import DictationOptions  # noqa: E402
from punctuation import FinalPunctuationRestorer  # noqa: E402
from safe_text import SafeTextBoundary  # noqa: E402
from streaming_transcriber import OnlinePreviewTranscriber  # noqa: E402
from text_cleaner import TextCleaner  # noqa: E402
from transcriber import Transcriber  # noqa: E402
import main as vf  # noqa: E402

SR = 16000
BLOCK = SR // 10
PREVIEW_DIR = ROOT / "models" / "streaming-preview"
TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?|[㐀-鿿]")


def tokens(text):
    return TOKEN.findall(text.lower())


def mer(hyp, ref):
    h, r = tokens(hyp), tokens(ref)
    d = list(range(len(h) + 1))
    for i, rt in enumerate(r, 1):
        p, d[0] = d[0], i
        for j, ht in enumerate(h, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (rt != ht))
    return d[len(h)] / max(1, len(r))


def term_hit(term, text):
    def squash(s):
        return re.sub(r"\s+", "", s.lower())
    return squash(term) in squash(text)


def read_wav(path):
    with wave.open(str(path)) as f:
        if (f.getframerate(), f.getnchannels(), f.getsampwidth()) != (SR, 1, 2):
            raise SystemExit(f"{path}: needs 16 kHz mono 16-bit PCM")
        return np.frombuffer(f.readframes(f.getnframes()), np.int16)


def system_for(x, transcribe):
    s = object.__new__(vf.VoiceInputSystem)
    s.audio = type("Audio", (), {"sample_rate": SR})()
    s._buf, s._n = x, 0
    s._final_segments = []
    s._finalized_audio_len = 0
    s._final_cache_lock = threading.Lock()
    s._preview_endpoint_lock = threading.Lock()
    s._preview_endpoint_samples = []
    s._latest_text = ""
    s._audio_snapshot = lambda a, b: s._buf[max(0, int(a)):min(int(b), s._n)]
    s._audio_sample_count = lambda: s._n
    s._transcribe_audio = (
        lambda pcm, blocking=True, return_activity=False:
        (transcribe(pcm), True) if return_activity else transcribe(pcm)
    )
    return s


def run_final_path(x, preview, transcribe):
    """One pass of final_cache_loop's body per 100 ms block, then the stop path."""
    s = system_for(x, transcribe)
    session = preview.create_session()
    for i in range(0, len(x), BLOCK):
        s._n = min(len(x), i + BLOCK)
        event = preview.accept_pcm(session, x[i:i + BLOCK], SR)
        if event.endpoint_final:
            s._note_preview_endpoint(event.audio_end_sample)
        found = s._next_final_segment_range(s._audio_sample_count(), s._snapshot_final_cache()[1])
        if found:
            start, endpoint_end = found
            end, at_pause = (
                s._quiet_cut(start, endpoint_end)
                if s._is_preview_endpoint(endpoint_end) else (endpoint_end, False)
            )
            text, speech = s._transcribe_audio(s._audio_snapshot(start, end), return_activity=True)
            s._consume_preview_endpoint(endpoint_end)
            s._commit_final_segment(text, start, end, speech, cut_in_pause=at_pause)
    started = time.perf_counter()
    result = s._transcribe_final_result(x, buffer_start_sample=0, total_samples=len(x))
    elapsed_ms = (time.perf_counter() - started) * 1000
    pieces = [(round(seg.start_sample / SR, 2), round(seg.end_sample / SR, 2),
               bool(getattr(seg, "cut_in_pause", False)), s._segment_text(seg)) for seg in s._final_segments]
    return result, pieces, elapsed_ms


def main():
    parser = argparse.ArgumentParser(description="Accuracy of recorded dictations through VoiceFlow's real final path.")
    parser.add_argument("--manifest", required=True, help="JSONL evaluation manifest (eval/README.md)")
    parser.add_argument("--engine", default="sensevoice", help="engine key in config.yaml")
    parser.add_argument("--show-pieces", action="store_true", help="print each recognized piece and its cut")
    args = parser.parse_args()

    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    candidate = copy.deepcopy(config)
    candidate["engine"]["active"] = args.engine
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", prefix=".dictation-eval-", dir=ROOT,
                                     delete=False, encoding="utf-8") as handle:
        yaml.safe_dump(candidate, handle, allow_unicode=True)
    try:
        transcriber = Transcriber(handle.name)
        transcriber.load_engine(args.engine)
    finally:
        Path(handle.name).unlink(missing_ok=True)
    # The same text preparation as delivery (src/main.py: _prepare_final_text), punctuation worker included.
    finisher = object.__new__(vf.VoiceInputSystem)
    finisher._safe_text = SafeTextBoundary()
    finisher.cleaner = TextCleaner(config, base_dir=ROOT)
    finisher.punctuation = FinalPunctuationRestorer()
    worker = None
    punctuation_model = ROOT / "models" / "punctuation" / "model.int8.onnx"
    if punctuation_model.is_file():
        from punctuation_worker import SupervisedPunctuation
        worker = SupervisedPunctuation(punctuation_model)
        if worker.load():
            finisher.punctuation.backend = worker.restore
        else:
            print("punctuation worker unavailable; recognizer punctuation kept", file=sys.stderr)
    preview = OnlinePreviewTranscriber.from_config({"streaming_preview": {
        "enabled": True, "runtime_engine": "online-transducer",
        "encoder_path": "encoder-epoch-99-avg-1.int8.onnx", "decoder_path": "decoder-epoch-99-avg-1.onnx",
        "joiner_path": "joiner-epoch-99-avg-1.int8.onnx", "tokens_path": "tokens.txt",
        "stability_guard_chars": 0}}, resolve_asset=lambda p: str(PREVIEW_DIR / Path(p).name))

    def transcribe(pcm):
        return transcriber.transcribe(np.asarray(pcm, dtype=np.int16), SR)

    manifest = Path(args.manifest)
    rows = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        x = read_wav(manifest.parent / item["audio"])
        result, piece_list, stop_ms = run_final_path(x, preview, transcribe)
        pieces = len(piece_list)
        if args.show_pieces:
            for start, end, at_pause, text in piece_list:
                print(f"  piece {start:6.2f}-{end:6.2f}s pause_cut={at_pause}: {text}")
            print(f"  final_source={result.final_source}")
        clean = finisher._prepare_final_text(result.text, DictationOptions())[0] if result.text else ""
        terms = item.get("terms", [])
        rows.append({
            "id": item["id"], "sec": round(len(x) / SR, 1), "pieces": pieces, "covered": result.coverage_ok,
            "stop_ms": round(stop_ms), "mer_raw": round(mer(result.text, item["reference"]), 3),
            "mer_clean": round(mer(clean, item["reference"]), 3),
            "missed_terms": [t for t in terms if not term_hit(t, clean)], "text": clean,
        })
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    if rows:
        print("mean", {k: round(statistics.mean(r[k] for r in rows), 3) for k in ("mer_raw", "mer_clean", "stop_ms")},
              "all covered:", all(r["covered"] for r in rows))
    if worker is not None:
        worker.shutdown()


if __name__ == "__main__":
    main()
