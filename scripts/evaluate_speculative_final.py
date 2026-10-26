"""Stop wait with speculative final recognition (recordings under SEGMENTED_FINAL_MIN_SECONDS).

Replays each dictation in 100 ms blocks through VoiceFlow's own `_speculation_due` and
`_transcribe_final_result`, with the ASR worker's gate (energy floor + Silero VAD), SenseVoice and a
microphone noise floor. The background guess takes
real time: if stop comes while it is still running, the wait includes the rest of it. The speaker stops
DELAY seconds after the last word. Results: docs/stop-latency-evaluation-2026-10-26.md.
Needs a display for Qt imports (xvfb-run on Linux).

    python scripts/evaluate_speculative_final.py <sensevoice dir> <samples dir with meta.json> [noise dBFS]
"""
import json, statistics as st, sys, threading, time, wave
from pathlib import Path
import numpy as np
import sherpa_onnx
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import main as vf

SR = 16000
SV, SAMPLES = Path(sys.argv[1]), Path(sys.argv[2])
NOISE_DBFS = float(sys.argv[3]) if len(sys.argv) > 3 else -50.0
DELAYS = (0.2, 0.5, 0.8, 1.2)
R = sherpa_onnx.OfflineRecognizer.from_sense_voice(model=str(SV / "model.int8.onnx"), tokens=str(SV / "tokens.txt"),
                                                   use_itn=True, num_threads=2)


from audio_activity import SileroSpeechDetector, has_speech_activity
VAD = SileroSpeechDetector(Path(__file__).resolve().parents[1] / "assets" / "silero_vad.onnx")


def worker(pcm):
    """What the ASR worker returns: (text, has_speech), with its energy floor and Silero VAD in front."""
    if not len(pcm) or not has_speech_activity(pcm, SR, rms_threshold=0.002, min_active_ms=90) or not VAD.has_speech(pcm, SR):
        return "", False
    return decode(pcm), True


def decode(x):
    s = R.create_stream(); s.accept_waveform(SR, np.asarray(x).astype(np.float32) / 32768); R.decode_stream(s)
    return s.result.text


def noise(n, seed):
    return np.random.default_rng(seed).normal(0, 32768 * 10 ** (NOISE_DBFS / 20), n)


class Audio:
    sample_rate = SR


def system_for(x):
    s = object.__new__(vf.VoiceInputSystem); s.audio = Audio(); s._n = 0
    s._final_segments = []; s._finalized_audio_len = 0; s._final_cache_lock = threading.Lock()
    s._preview_endpoint_lock = threading.Lock(); s._preview_endpoint_samples = []; s._latest_text = ""
    s._speculative_final = None; s._speech_scan = (0, 0.0, 0); s._speech_gate_enabled = False
    s._audio_snapshot = lambda a, b: x[max(0, int(a)):min(int(b), s._n)]
    s._audio_sample_count = lambda: s._n
    s._transcribe_audio = lambda pcm, blocking=True, return_activity=False, **_: worker(pcm) if return_activity else worker(pcm)[0]
    return s


meta = json.load(open(SAMPLES / "meta.json", encoding="utf-8"))
def norm(t):
    return "".join(c for c in t.lower() if c.isalnum())


def cer(hyp, ref):
    h, r = norm(hyp), norm(ref)
    d = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        p, d[0] = d[0], i
        for j, hc in enumerate(h, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (rc != hc))
    return d[len(h)] / max(1, len(r))


refs = [m["reference"] for m in meta]
refs += [a + "，" + b for a, b in zip(refs[::2], refs[1::2])]
speech = []
for m in meta:
    with wave.open(str(SAMPLES / m["wav"])) as f:
        x = np.frombuffer(f.readframes(f.getnframes()), np.int16)
    speech.append(np.trim_zeros(x, "b"))
speech += [np.concatenate([a, np.zeros(int(0.8 * SR), np.int16), b]) for a, b in zip(speech[::2], speech[1::2])]
rows = []
for k, words in enumerate(speech):
    for delay in DELAYS:
        x = np.concatenate([words, np.zeros(int(delay * SR), np.int16)]).astype(np.float64)
        x = np.clip(x + noise(len(x), k), -32768, 32767).astype(np.int16)
        s = system_for(x); busy_until = -1.0; guess_done_at = None
        for i in range(0, len(x), 1600):
            s._n = min(len(x), i + 1600); now = s._n / SR
            if now >= busy_until and (to := s._speculation_due(s._n)) is not None:
                t0 = time.perf_counter(); text = worker(np.concatenate([x[:to], np.zeros(int(SR * vf.VoiceInputSystem.SPECULATIVE_TAIL_PAD_SECONDS), np.int16)]))[0]; took = time.perf_counter() - t0
                s._speculative_final = (to, text.strip()); busy_until = now + took; guess_done_at = busy_until
        stop = len(x) / SR
        pending = max(0.0, (guess_done_at or 0) - stop)
        t0 = time.perf_counter(); res = s._transcribe_final_result(x, buffer_start_sample=0, total_samples=len(x))
        wait = pending + time.perf_counter() - t0
        t0 = time.perf_counter(); whole = worker(x)[0]; whole_wait = time.perf_counter() - t0
        rows.append(dict(seconds=round(len(words) / SR, 1), delay=delay, source=res.final_source,
                         wait_ms=round(wait * 1000), whole_ms=round(whole_wait * 1000),
                         cer=cer(res.text, refs[k]), cer_whole=cer(whole, refs[k])))
for delay in DELAYS:
    for label, lo, hi in (("6-10 s", 0, 11), ("15-20 s", 11, 99)):
        rs = [r for r in rows if r["delay"] == delay and lo <= r["seconds"] < hi]
        print(json.dumps({"stop_after_last_word_s": delay, "length": label, "used_guess": f"{sum(r['source'] == 'speculative_full' for r in rs)}/{len(rs)}",
                          "wait_ms": round(st.mean(r["wait_ms"] for r in rs)), "whole_ms": round(st.mean(r["whole_ms"] for r in rs)),
                          "errors": round(st.mean(r["cer"] for r in rs), 3), "errors_whole_at_stop": round(st.mean(r["cer_whole"] for r in rs), 3)}, ensure_ascii=False))
