# Stop latency and capsule fluency evaluation — 2026-10-26

> Documentation sync: **2026-10-26** · Historical evidence / release notes. Measured in a Linux cloud container (4 vCPU, SenseVoice with 2 threads), not on the release workstation; absolute times there are lower. Not a release measurement and not an accuracy claim.

The owner asked what can still make dictation feel smoother: how fast the words come once he stops talking, and how the capsule shows them while he talks. Everything here was measured before the code was changed, and every change was measured again afterwards.

## 1. Capsule preview while speaking: no change

The preview shows a word only after two consecutive hypotheses agree. One idea was to show the model's unconfirmed guess at once in a lighter colour, as iOS dictation does. Replaying recordings through `OnlinePreviewTranscriber` in real-time 100 ms blocks showed that the guess would appear only about **80 ms** earlier: this transducer's hypotheses are already stable. The visible stutter comes from the model emitting text in bursts every 0.6–0.7 s.

Five streaming models were compared on the same audio: a 52 s CC BY 3.0 Chinese news talk cut into 8 s pieces, plus the two pinned SenseVoice samples. "Error vs final" is the preview's character error rate against the SenseVoice result for the same audio, which is how much the text changes when the final replaces the preview.

| Preview model | First character | Update gap P95 | Chinese error vs final | English error vs final | Compute P95 per 100 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| small bilingual zh-en 2023-02-16 (current) | 1.2 s | 699 ms | 15.4 % | 21.7 % | 29 ms |
| bilingual zh-en 2023-02-20 | 1.2 s | 701 ms | 12.2 % | 11.6 % | 61 ms |
| multi-zh-hans 2023-12-12 (chunk 16) | 1.3 s | 601 ms | 12.1 % | no English | 60 ms |
| zh int8 2025-06-30 | 1.3 s | 600 ms | 19.7 % | no English | 97 ms |
| zh 14M 2023-02-23 | 1.2 s | 700 ms | 18.6 % | no English | 22 ms |

None of these emits materially more often, so swapping among them does not fix the stutter, and a tentative tail would contradict the append-only capsule contract for an 80 ms gain. Newer candidates found in the same search are listed under [Open](#open).

## 2. Stop to final text

### Before

| Recording | Final text | Stop wait (cloud) |
| --- | --- | ---: |
| under 20 s | the whole recording, recognized after stop | 0.35 s at 7–10 s, 0.68–0.78 s at 15–20 s |
| from 20 s | pieces recognized while recording at preview endpoints, plus the tail | about 0.2 s |

The pieces had three defects:

- **Cut inside a word.** The preview recognizer reports a pause 0.93 s (median; max 1.17 s) after it began, so a piece was cut at that late sample, often inside the next phrase's first word.
- **Duplicated words.** Each piece re-read 1 s of the previous one, and the overlap merge often failed to match the re-recognized text, giving duplicates such as 「电力电。电力」.
- **Stray spaces.** Chinese pieces were joined with a space: 「取了。 明天」.

### Under 20 s: speculative final recognition (new)

While the speaker talks, the final cache tracks speech level in 100 ms frames. A frame counts as speech when its energy is at least a tenth of the loudest frame so far and above a fixed floor.

- After 0.3 s of quiet following speech, the whole recording so far is recognized in the background, with 0.6 s of silence appended so the last syllable ends cleanly.
- At stop, if no speech came after that point, that result is the final text.
- The tail after it must pass the ASR worker's gate as non-speech (energy floor plus Silero VAD). Without that gate, SenseVoice invents a character on pure background noise (「그.」 in one case), and the result would never be used.
- If the speaker went on talking, the whole recording is recognized at stop as before, with no extra check.

Results from `scripts/evaluate_speculative_final.py`:
- **Audio**: 18 synthetic dictations (12 of 6.8–9.7 s, 6 of 15.6–18.5 s), MeloTTS zh_en (Apache-2.0), with pauses between phrases.
- **Noise**: a −50 dBFS microphone noise floor.
- **When stop is pressed**: 0.2–1.2 s after the last word.
- **Timing**: the background recognition takes real time, so if stop comes while it is still running, the wait includes the rest of it.

| Stop after last word | Length | Guess used | Wait | Whole at stop | Errors | Errors whole at stop |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 0.2 s | 6–10 s | 0/12 | 0.38 s | 0.42 s | 9.8 % | 9.8 % |
| 0.2 s | 15–20 s | 0/6 | 0.85 s | 0.89 s | 10.2 % | 10.2 % |
| 0.5 s | 6–10 s | 12/12 | 0.31 s | 0.44 s | 9.1 % | 10.0 % |
| 0.5 s | 15–20 s | 6/6 | 0.70 s | 0.78 s | 9.8 % | 10.5 % |
| 0.8 s | 6–10 s | 12/12 | 0.04 s | 0.45 s | 9.1 % | 8.6 % |
| 0.8 s | 15–20 s | 6/6 | 0.40 s | 0.81 s | 9.8 % | 9.8 % |
| 1.2 s | 6–10 s | 12/12 | 0.03 s | 0.50 s | 9.1 % | 8.6 % |
| 1.2 s | 15–20 s | 6/6 | 0.08 s | 0.77 s | 9.8 % | 9.5 % |

(This run's machine was slower than the earlier one: the whole-recording times are 0.42–0.89 s here.)

Accuracy is the same within measurement noise (−0.9 to +0.5 points), because the guess is SenseVoice on the same whole recording. The cost is CPU while recording: one background recognition of the recording so far at each pause, in the ASR worker process, for recordings under 20 s only.

### Safeguards (from a second independent review)

- A guess or piece written by a cache worker of an earlier recording (for example one cancelled with Esc while a guess was running) is discarded: each reset moves an epoch, and workers write only within their own.
- The guess is not used if the tail after it has speech by the worker's VAD, even when the recognizer returns no text for it (a soft last syllable), or if the tail is longer than 1.5 s, or at 20 s and longer.
- The speech tracker measures against the noise floor (a frame is speech at 8x the quietest recent frame, or at -30 dBFS), so one cough does not hide quieter speech; it is rescanned at stop.
- Below 14 s no pieces are recognized while recording (they are not used under 20 s and would hold the recognizer at stop).
- A pause cut needs the quietest 200 ms at least 15 dB below the speech in the window, and the 4 s minimum is counted from the last cut.

### Rejected: pieces from 12 s

Using the pause-cut pieces from 12 s instead of 20 s cut the 15–20 s wait from 0.67–0.78 s to 0.19–0.22 s. But it cost about 2.5 points of character errors in every condition tried: 8.9 % vs 6.3 % without noise, 10.8 % vs 8.2 % at −55 dBFS, 11.5 % vs 9.0 % at −45 dBFS. All 25 cuts landed in real pauses, so the loss comes from SenseVoice seeing each piece without the others' context. One more wrong character costs the user more than 0.5 s. Speculation gets the speed without the loss.

### From 20 s: pieces fixed

Changes in `src/main.py`:

| Change | Why |
| --- | --- |
| A pause cut moves back to the quietest 200 ms within 1.6 s before the endpoint (`_quiet_cut`). It counts as a pause only if that stretch is near silence or at most a tenth of the speech in the window; otherwise it is a forced cut | All cuts land in the real pause. Noise-like speech without a dip keeps the 1 s overlap |
| After a pause cut, the next piece and the stop tail start exactly at the cut, and are appended without the overlap merge (`FinalSegmentCoverage.cut_in_pause`, `_join_segments`) | A cut inside silence loses no word. The merge would delete words the speaker really repeated across the seam (「设置。设置里」). Forced cuts keep the 1 s overlap and the merge |
| A piece is at least 4 s (was 2 s), enforced in both the endpoint choice and the cut | 2 s pieces cost about 3 points of character errors |
| Chinese pieces, kana, or a piece ending in Chinese punctuation join without a space | Latin words keep theirs |

On 30–38 s dictations (four utterances each, −50 dBFS), driven through the same methods with `scripts/evaluate_stop_latency.py`:

| Code | Stop wait | Character errors | Whole recording (2.0 s wait) |
| --- | ---: | ---: | ---: |
| before | 0.16 s | 12.7 % | 9.1 % |
| after | 0.21–0.23 s | 11.7–11.8 % | 9.1 % |

## Limits of this evidence

- Synthetic speech checks mechanics reproducibly. It is not an authorized natural-speech corpus, and no public accuracy or speed claim follows from it.
- Generated audio is not byte-identical between runs (the voice model is not deterministic). The short set's whole-recording error rate was 9.0 % on one generation and 5.9 % on another; evaluating the same files twice reproduced every number.
- The pauses are digital silence plus an added white-noise floor. A real room (keyboard, fan, breathing) may trip the speech tracker more often; the worst case is a guess that is not used.
- Nothing was measured on the Windows release workstation. Real-microphone feel is still to be judged there.

## Open

These are the newer candidates found on 2026-10-26, not yet evaluated:
- **X-ASR zh-en** (Apache-2.0, 0.16B, Zipformer transducer, about 1 M hours, with punctuation). Measured on the same benchmark as section 1:

  | Variant | First character | Update gap P95 | Chinese error vs final | English error vs final | Compute P95 per 100 ms |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | 160 ms | 1.41 s | 500 ms | 12.2 % | 11.6 % | 148 ms |
  | 480 ms | 1.70 s | 501 ms | 9.9 % | 2.9 % | 169 ms |

  It previews much more accurately and updates more often. But the first character comes later, and the fp32 encoder (about 590 MB) needs more than real time on this CPU, so it cannot be the preview as it is. Worth revisiting with an int8 export measured on the release workstation.
- **Final-model candidates newer than the July comparison**: FireRedASR2 CTC, Qwen3-ASR 0.6B (2026-03), Fun-ASR-Nano (2025-12), and a 2025-09 SenseVoice re-export.

## Reproduce

```bash
python scripts/make_dictation_samples.py <vits-melo-tts-zh_en> <samples>
xvfb-run python scripts/evaluate_speculative_final.py <sense-voice dir> <samples> -50
xvfb-run python scripts/evaluate_stop_latency.py <sense-voice dir> <streaming preview dir> <samples> -50 [src dir]
```

Models are the official k2-fsa sherpa-onnx release archives (`asr-models`, `tts-models`). The preview archive matched the SHA-256 in `model-manifest.json`.
