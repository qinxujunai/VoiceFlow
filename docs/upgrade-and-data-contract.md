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
- both download URLs point to that exact tag; and
- the checksum file has exactly one SHA-256 entry for that installer name.

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

## Evidence

- `src/update_checker.py` and `tests/test_update_checker.py` cover the public
  Release asset and checksum contract.
- `src/recovery_session.py` and `tests/test_recovery_session.py` cover complete
  recovery cleanup and deletion failure reporting.
- `VoiceFlow.spec` and `scripts/pyinstaller_qt_runtime_hook.py` keep the
  bundled Qt search path deterministic and remove host Poppler ICU collisions.
- `scripts/smoke_packaged_runtime.ps1` must pass before a packaged build is
  considered usable.
