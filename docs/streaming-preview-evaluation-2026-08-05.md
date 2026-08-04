# Streaming Preview Evaluation — 2026-08-05

Status: **bilingual first pass promoted; final accuracy still belongs to SenseVoice**

The experiment used the pinned public Chinese and English SenseVoice samples
on the same Windows machine. It verifies language coverage, emission behavior,
and control-token safety. Two samples are not an accuracy corpus and are not
used for marketing claims.

Configuration: 80 ms PCM feed, consecutive-hypothesis confirmation, no
unstable-character guard, CPU execution, and a fixed 48 ms capsule cadence.

| Sample | Speech onset to first confirmed delta | Update gap P95 | Chunk P95 / max | Queue delay P95 | Preview result |
| --- | ---: | ---: | ---: | ---: | --- |
| Chinese | 825.5 ms | 1280 ms | 2 / 2 | 48 ms | 太放时间早上九点至下午五点 |
| English | 759.9 ms | 320 ms | 8 / 9 Latin graphemes | 288 ms | The drival chief thim called for the boy and presented him that fifty pieces of good |

The first pass is intentionally replaceable and unpunctuated. The Chinese
sample demonstrates that stable streaming text can still contain a recognition
error; the English sample demonstrates that control tokens are gone but the
preview is not the final correction. On the same samples, the complete
SenseVoice pass remains the output authority.

The capsule contract is therefore:

1. show the first confirmed grapheme immediately;
2. append at 48 ms without rollback, replay, reverse motion, or acceleration;
3. never paste the preview when a valid complete final result exists;
4. stop the preview before final recognition and show only a compact completion
   summary instead of replaying the transcript.

The long Chinese update gap occurs in the model's emission sequence; animation
cannot invent reliable characters between model emissions. Replacing it with
rolling full-audio SenseVoice retranscription was rejected because it repeats
inference, causes hypothesis rollback, and grows in cost during long sessions.
Future promotion requires a larger authorized holdout plus latency, memory,
license, and packaged-runtime gates.
