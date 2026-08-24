# VoiceFlow 0.3.2 release verification evidence

Status: local release candidate passed the automated source, packaged-runtime,
and isolated-installer gates on the release workstation. Public asset hashes
are published in the matching GitHub Release `SHA256SUMS.txt`.

This document records engineering evidence. It is not a population-level
speech-accuracy claim.

## Candidate

- Version: `0.3.2`
- Build: `260825.2`
- Platform: Windows 11 x64
- Default final recognizer: bundled SenseVoice int8
- Preview recognizer: bundled bilingual streaming Zipformer int8
- Network behavior: no cloud recognition or hidden runtime download

## Automated gates

- Full Python suite, compilation, doctor, model-output safety benchmark, and
  end-to-end integration pipeline.
- 500 recording lifecycle state-machine cycles.
- 10,000 randomized start, stop, cancel, and exit sequences.
- One-hour recovery coverage using 57,600,000 samples / 115.2 MB PCM.
- 5,000 clipboard and delivery fault cases.
- 50,000 safe-text fuzz cases covering control characters and malformed model
  output.
- 1,000 settings navigation actions after the competing trial button was
  removed.
- Settings screenshots at 100%, 125%, 150%, and 200% scale.
- Isolated installation with verified bundled-model sizes and SHA-256 values,
  ready worker processes, registered hotkeys, retained user data after
  uninstall, and a required check that the installer contains no
  `history.jsonl`.

## Real installed lifecycle sample

Two short microphone lifecycles on the release workstation were recorded as a
manual smoke check before the final interface-only subtraction. Both covered
every captured sample and dispatched exactly one paste:

| Sample | Trigger to feedback | Stop to paste dispatch | Coverage |
| --- | ---: | ---: | ---: |
| 1 | 73.252 ms | 350.669 ms | 91,200 / 91,200 |
| 2 | 13.490 ms | 249.911 ms | 51,200 / 51,200 |

These two samples prove the installed lifecycle used in the local smoke. They
are not sufficient to claim a universal latency percentile.

## Product-data boundary

- The public installer contains program assets and reviewed bundled models,
  not a developer history file.
- Runtime history lives under the current Windows user's local VoiceFlow data
  directory.
- The History page provides per-entry deletion and confirmed clear-all.
- Configuration, dictionary, and history hashes are checked across local
  upgrade installation.
