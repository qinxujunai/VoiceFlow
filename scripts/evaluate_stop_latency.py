"""Stop latency: how long after the stop key the final text is ready, and what it costs in accuracy.

Drives VoiceFlow's own progressive final cache and stop path (src/main.py: _next_final_segment_range,
_quiet_cut, _commit_final_segment, _transcribe_final_result) with the real preview recognizer and SenseVoice,
one 100 ms block at a time, and compares with recognizing the whole recording at stop.
Results: docs/stop-latency-evaluation-2026-10-26.md. Needs a display for Qt imports (xvfb-run on Linux).

    python scripts/evaluate_stop_latency.py <sensevoice dir> <streaming preview dir> <samples dir with meta.json>
"""
import sys, wave, time, json, threading, statistics as st
from pathlib import Path
import numpy as np
import sherpa_onnx
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from streaming_transcriber import OnlinePreviewTranscriber
import main as vf

SR = 16000
SV, PREVIEW, SAMPLES = (Path(a) for a in sys.argv[1:4])


def norm(s):
    return "".join(c for c in s.lower() if c.isalnum())


def cer(hyp, ref):
    """Character error rate over letters and digits (punctuation and spaces do not count)."""
    h, r = norm(hyp), norm(ref)
    d = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        p, d[0] = d[0], i
        for j, hc in enumerate(h, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (rc != hc))
    return d[len(h)] / max(1, len(r))


meta = json.load(open(SAMPLES / "meta.json", encoding="utf-8"))
def load(n):
    with wave.open(str(SAMPLES / n)) as f: return np.frombuffer(f.readframes(f.getnframes()), np.int16)
items = [(m['wav'], load(m['wav']), m['reference']) for m in meta]
items += [(f"{a[0]}+{b[0]}", np.concatenate([a[1], np.zeros(int(.8*SR), np.int16), b[1]]), a[2]+'，'+b[2]) for a, b in zip(items[::2], items[1::2])]
R = sherpa_onnx.OfflineRecognizer.from_sense_voice(model=str(SV/'model.int8.onnx'), tokens=str(SV/'tokens.txt'), use_itn=True, num_threads=2)
def decode(x):
    s = R.create_stream(); s.accept_waveform(SR, np.asarray(x).astype(np.float32)/32768); R.decode_stream(s); return s.result.text
pre = OnlinePreviewTranscriber.from_config({'streaming_preview': {'enabled': True, 'runtime_engine': 'online-transducer',
    'encoder_path': 'encoder-epoch-99-avg-1.int8.onnx', 'decoder_path': 'decoder-epoch-99-avg-1.onnx', 'joiner_path': 'joiner-epoch-99-avg-1.int8.onnx',
    'tokens_path': 'tokens.txt', 'stability_guard_chars': 0}}, resolve_asset=lambda p: str(PREVIEW/Path(p).name))
class Audio: sample_rate = SR
def system_for(x):
    s = object.__new__(vf.VoiceInputSystem); s.audio = Audio(); s._buf = x; s._n = 0
    s._final_segments = []; s._finalized_audio_len = 0; s._final_cache_lock = threading.Lock()
    s._preview_endpoint_lock = threading.Lock(); s._preview_endpoint_samples = []; s._latest_text = ''
    s._audio_snapshot = lambda a, b: s._buf[max(0, int(a)):min(int(b), s._n)]
    s._audio_sample_count = lambda: s._n
    s._transcribe_audio = lambda pcm, blocking=True, return_activity=False: ((decode(pcm), True) if return_activity else decode(pcm))
    return s
rows = []
for name, x, ref in items:
    s = system_for(x); ps = pre.create_session()
    for i in range(0, len(x), 1600):
        s._n = min(len(x), i + 1600)
        ev = pre.accept_pcm(ps, x[i:i+1600], SR)
        if ev.endpoint_final: s._note_preview_endpoint(ev.audio_end_sample)
        # one pass of final_cache_loop's body, with the same method calls
        rng = s._next_final_segment_range(s._audio_sample_count(), s._snapshot_final_cache()[1])
        if rng:
            start, endpoint_end = rng
            at_pause = s._is_preview_endpoint(endpoint_end)
            end = s._quiet_cut(start, endpoint_end) if at_pause else endpoint_end
            text, speech = s._transcribe_audio(s._audio_snapshot(start, end), return_activity=True)
            s._consume_preview_endpoint(endpoint_end)
            s._commit_final_segment(text, start, end, speech, cut_in_pause=at_pause)
    t0 = time.perf_counter(); res = s._transcribe_final_result(x, buffer_start_sample=0, total_samples=len(x)); t = time.perf_counter() - t0
    t0 = time.perf_counter(); whole = decode(x); tw = time.perf_counter() - t0
    rows.append(dict(name=name, sec=round(len(x)/SR, 1), source=res.final_source, pieces=len(s._final_segments), coverage=res.coverage_ok,
                     stop_ms=round(t*1000), whole_ms=round(tw*1000), cer=round(cer(res.text, ref), 3), cer_whole=round(cer(whole, ref), 3), text=res.text))
for r in rows: print(json.dumps(r, ensure_ascii=False))
single = len(meta)
for label, rs in (('single utterances', rows[:single]), ('two joined', rows[single:])):
    print(label, {k: round(st.mean(r[k] for r in rs), 3) for k in ('stop_ms', 'whole_ms', 'cer', 'cer_whole')}, 'all covered:', all(r['coverage'] for r in rs))
