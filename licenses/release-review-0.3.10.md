# VoiceFlow 0.3.10 dependency review

Review date: 2026-10-22. Scope: build 261022.1 on Windows.

The release preparation compared `requirements.lock`, `vendor/windows/`,
`model-manifest.json` and the existing `licenses/` records against tag v0.3.9.
These dependency, model and original license inputs are unchanged. The component
redistribution conclusions in `release-review-0.3.9.md` therefore apply to these
same inputs, including Microsoft Community entitlement, original runtime terms,
Qt/PySide/Shiboken/pynput LGPL obligations, native ASR attribution and model terms.
This record does not grant approval to different dependency bytes.

The 0.3.10 installer still requires its own packaged inventory, native import and
replacement checks, exact uploaded installer acceptance, installed-machine data
retention verification and artifact-bound `RELEASE_SIGNOFF.json`. Until those
records are complete this is a dependency review, not completed release approval.

The matching LGPL source archives retain the immutable commits and hashes in
`lgpl-sources.json`. They must accompany the new Release as
`VoiceFlow-0.3.10-LGPL-sources.zip`. The archive contents may be reused only after
verifying them against those pins. Preserve all original third-party notices.

The installer remains unsigned. Natural authorized speech holdout coverage is
incomplete; unchanged model weights do not establish an accuracy improvement.
