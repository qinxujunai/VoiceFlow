# Stop latency and capsule fluency evaluation — 2026-10-26

> Documentation sync: **2026-10-26** · Historical evidence / release notes. Measured in a Linux cloud container (4 vCPU, SenseVoice with 2 threads), not on the release workstation; absolute times there are lower. Not a release measurement and not an accuracy claim.

The owner asked what can still make dictation feel smoother: how fast the words come once he stops talking, and how the capsule shows them while he talks. Everything here was measured before changing code.

## 1. Capsule preview while speaking: no change

The preview model shows a word only after two consecutive hypotheses agree. One idea was to show the model's unconfirmed guess at once in a lighter colour, as iOS dictation does. Replaying recordings through `OnlinePreviewTranscriber` in real-time 100 ms blocks showed that the guess would appear only about **80 ms** earlier: this transducer's hypotheses are already stable. The visible stutter comes from the model emitting text in bursts every 0.6–0.7 s.

Five streaming models were compared on the same audio (a 52 s CC BY 3.0 Chinese news talk cut into 8 s pieces, plus the two pinned SenseVoice samples). "Error vs final" is the character error rate of the preview against the SenseVoice result for the same audio. It measures how much the text changes when the final result replaces the preview.

| Preview model | First character | Update gap P95 | Chinese error vs final | English error vs final | Compute P95 per 100 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| small bilingual zh-en 2023-02-16 (current) | 1.2 s | 699 ms | 15.4 % | 21.7 % | 29 ms |
| bilingual zh-en 2023-02-20 | 1.2 s | 701 ms | 12.2 % | 11.6 % | 61 ms |
| multi-zh-hans 2023-12-12 (chunk 16) | 1.3 s | 601 ms | 12.1 % | no English | 60 ms |
| zh int8 2025-06-30 | 1.3 s | 600 ms | 19.7 % | no English | 97 ms |
| zh 14M 2023-02-23 | 1.2 s | 700 ms | 18.6 % | no English | 22 ms |

None of the models emits materially more often, so swapping the model does not fix the stutter. The 2023-02-20 bilingual model is the only real candidate: its preview is closer to the final text, so the swap at stop changes less. But it doubles preview CPU and adds about 140 MB to the installer. It is recorded here as an option, not adopted. A lighter-colour tentative tail was not built: it would contradict the append-only capsule contract for an 80 ms gain.

## 2. Stop to final text: changed

Under 20 s, the stop path recognized the whole recording again even though the progressive final cache had already recognized the pieces up to each pause. Whole-recording SenseVoice time grows with length: 0.2 s for 5 s of speech, 0.4–0.5 s for 10 s, 0.55–0.85 s for 15–20 s.

The pieces could not simply be used, because they were joined badly:

- **Late cut.** The preview recognizer reports a pause 0.93 s (median, max 1.17 s) after it began. Pieces were cut at that late sample, inside the next phrase's first word.
- **Duplicates at seams.** Each piece re-read 1 s of the previous one. The overlap merge often could not match the re-recognized text and produced duplicates such as 「电力电。电力」.
- **Stray space.** Chinese pieces were joined with a space: 「取了。 明天」.

These affected recordings of 20 s and longer before this change too.

Changes (`src/main.py`):

| Change | Why |
| --- | --- |
| A pause cut moves back to the quietest 200 ms within 1.6 s before the reported endpoint (`_quiet_cut`) | All 25 natural cuts in the evaluation landed inside the real pause (none did before) |
| After a pause cut, the next piece and the stop tail start exactly at the cut, with no overlap (`FinalSegmentCoverage.cut_in_pause`) | A cut inside silence loses no word. Forced cuts after 18 s without a pause keep the 1 s overlap |
| A piece is at least 4 s (was 2 s) | 2 s pieces cost about 3 points of character errors in the same evaluation |
| Pieces are used from 12 s (was 20 s) | Where the wait is long enough to feel. Below 12 s the whole recording is still recognized, so short dictation is unchanged |
| Chinese pieces, or a piece ending in Chinese punctuation, join without a space | Latin words keep their space |

## Result

Driven through VoiceFlow's own methods (`_next_final_segment_range`, `_quiet_cut`, `_commit_final_segment`, `_transcribe_final_result`) with the real preview recognizer and SenseVoice. Audio: 12 synthetic dictation utterances of 6.8–9.7 s, plus 6 joined pairs of 15.6–18.5 s (MeloTTS zh_en, Apache-2.0, 0.6–1.0 s pauses between phrases).

| Recordings | Path | Stop wait (mean) | Whole recording at stop | Character errors | Whole recording |
| --- | --- | ---: | ---: | ---: | ---: |
| 6.8–9.7 s (12) | whole, unchanged | 0.31 s | 0.32 s | 5.9 % | 5.9 % |
| 15.6–18.5 s (6) | pieces + tail | 0.19 s | 0.67 s | 8.7 % | 6.3 % |

Every recording kept complete coverage of the stopped audio. The remaining accuracy cost on long dictation comes from SenseVoice seeing each piece without the context of the others, not from cuts. It is the price of a 0.5 s shorter wait. If real use shows more errors on long dictation, raise `SEGMENTED_FINAL_MIN_SECONDS`.

The measured wait assumes the piece before the last one was already recognized when stop was pressed. If stop comes right after a pause, the stop path first waits for that piece (`FINAL_CACHE_HANDOFF_TIMEOUT_SECONDS`), so the wait can approach the length of that piece's recognition. That is still shorter than recognizing everything.

Synthetic speech checks mechanics reproducibly. It is not an authorized natural-speech corpus, and no public accuracy or speed claim follows from it.

## Reproduce

```bash
python scripts/make_dictation_samples.py <vits-melo-tts-zh_en> <samples>
xvfb-run python scripts/evaluate_stop_latency.py <sense-voice dir> <streaming preview dir> <samples>
```

Models are the official k2-fsa sherpa-onnx release archives (`asr-models`, `tts-models`). The preview archive matched the SHA-256 in `model-manifest.json`. Generated audio is not byte-identical between runs (the voice model is not deterministic): the whole-recording error rate of the short set was 9.0 % on one generation and 5.9 % on another. Evaluating the same files twice reproduced every number.
