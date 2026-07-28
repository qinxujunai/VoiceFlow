# Resource profile — 2026-07-28

This document records measurements from the current Windows 0.2.1 candidate.
It is release evidence, not a claim about every computer.

## Same-machine measurements

| Runtime state | Private Bytes | Working Set |
|---|---:|---:|
| Source runtime before ASR models | 499.9 MB | 27.5 MB |
| Source runtime with SenseVoice | 796.2 MB | 331.4 MB |
| Source runtime with SenseVoice and current preview model | 842.3 MB | 376.7 MB |
| Installed PyInstaller process tree | 1,324.6 MB | Windows had trimmed most idle pages |
| Installed Qt renderer child | 106.5 MB | included in the process-tree total |

SenseVoice thread-count measurements at 1, 2, 4, and 6 threads stayed within
approximately 792.7–795.0 MB Private Bytes. Thread count is therefore not the
main source of the installed-build overhead.

## Interpretation

- The current preview model adds roughly 46 MB in the isolated source-runtime
  comparison. Removing it is necessary for the public-license gate but is not
  enough to reach the resource target on its own.
- Qt WebEngine contributes a visible child process, but that child accounts for
  only about 106.5 MB of the installed process tree. Replacing the capsule UI
  without first profiling PyInstaller and ONNX Runtime would be speculative.
- The installed candidate exceeds the 1.0 GB Private Bytes target. This remains
  a P1 release blocker.
- Working Set and Private Bytes measure different things. An idle Working Set
  reduced by Windows memory trimming must not be presented as the application's
  real committed-memory footprint.

## Next profiling work

1. Compare the same frozen build before and after loading each recognizer.
2. Measure ONNX Runtime arena settings with fixed audio and accuracy output.
3. Compare a package with WebEngine disabled to isolate packaging and renderer
   overhead; do not replace the product UI unless the measured saving justifies
   the regression risk.
4. Repeat on the minimum and recommended hardware tiers with 20 samples.

No public release may claim the resource budget has passed until the installed
process tree is at or below 1.0 GB Private Bytes under the documented test
conditions.
