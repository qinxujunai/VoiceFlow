# Upgrade and local-data contract

Status: required product behavior

## Updates

VoiceFlow does not contact the network during ordinary startup or dictation.
The Settings > About VoiceFlow action is the only product update check. It
queries the fixed public GitHub repository and reads the latest stable Release
metadata plus `SHA256SUMS.txt`.

The app exposes a download link only when all of these checks pass:

- the Release tag is a stable `vX.Y.Z` version;
- `VoiceFlow-X.Y.Z-Windows-x64.exe` exists;
- `SHA256SUMS.txt` exists;
- both assets are uploaded, nonempty, and have GitHub SHA-256 digests;
- both download URLs point to that exact tag;
- the downloaded checksum file matches its GitHub size and digest; and
- its unique installer entry matches the installer asset's GitHub digest.

Duplicate asset names and oversized responses are rejected. This validates
release metadata and the checksum manifest; it does not hash an installer
download on the user's machine or replace publisher code signing.

The check does not download or execute an installer. The user starts the
versioned installer manually. A normal upgrade keeps `%LOCALAPPDATA%\VoiceFlow`
and therefore preserves configuration, vocabulary, and user model files.

## Local data

The History page keeps single-entry deletion, history clearing, and undo for a
single deletion. `Clear local data` is a separate confirmed action. It removes
the local transcription history and every recovery-recording directory,
including malformed recovery journals, while keeping configuration, vocabulary,
and models.

If a recovery directory cannot be deleted, the action reports failure instead
of claiming that all data was removed. The recovery store skips symlinks and
never follows them during the bulk operation.

Recording startup, cancellation, final delivery, recovery, and recovery-data
deletion cannot overlap. Data clearing and single-recording deletion reserve
the idle state atomically; busy operations reject deletion before touching
history or audio. Failed cancellation keeps the recording state blocked instead
of exposing potentially active audio as idle.

Native audio, final-ASR and preview workers monitor their owning process
sentinel. If the UI process dies, the workers terminate even if native calls
are stuck. Interrupted recovery PCM remains local; parent-exit handling does
not acknowledge delivery or delete recovery files.

## Evidence

- `src/update_checker.py` and `tests/test_update_checker.py` cover the public
  Release asset and checksum contract.
- `src/recovery_session.py` and `tests/test_recovery_session.py` cover complete
  recovery cleanup and deletion failure reporting.
- `VoiceFlow.spec` and `scripts/pyinstaller_qt_runtime_hook.py` keep the
  bundled Qt search path deterministic and remove host Poppler ICU collisions.
- `scripts/smoke_packaged_runtime.ps1` must pass before a packaged build is
  considered usable.
