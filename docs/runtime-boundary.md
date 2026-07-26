# Runtime Boundary Specification

## Objective

VoiceFlow must behave correctly from source and from a frozen Windows
installation without writing user state into the application directory.
Configuration, history, logs, custom vocabulary, and downloaded models are
user-owned. Application binaries, bundled UI, manifests, licenses, and bundled
models are immutable resources.

## Runtime layout

```text
%LOCALAPPDATA%\Programs\VoiceFlow\   immutable installed application
%LOCALAPPDATA%\VoiceFlow\
  config.yaml                        writable runtime configuration
  runtime-state.json                 data schema and migration state
  logs\                              runtime log and transcription history
  knowledge-base\                    writable vocabulary and corrections
  models\                            user-downloaded model cache
```

Source runs use the same `AppPaths` API. Existing source-tree models remain
available as a read-only fallback so first migration does not copy hundreds of
megabytes or delete developer assets.

Asset resolution order is:

1. explicit absolute path;
2. user data directory;
3. immutable install/source directory.

## Migration contract

- Migration is idempotent and never overwrites or deletes an existing user
  file.
- Existing config, history, and knowledge-base files are copied atomically on
  first use.
- Models are not copied. Existing bundled/source models remain visible through
  fallback resolution.
- `runtime-state.json` records the data schema, runtime mode, and source install
  directory.
- A migration failure stops startup with the exact missing path; VoiceFlow
  never silently starts with a new empty configuration.

## Runtime adapters

- `RuntimeMode.SOURCE` may launch maintainer model tooling with the current
  Python interpreter, but writes downloads to the user model directory.
- `RuntimeMode.FROZEN` never invokes Python, a venv, or repository scripts.
- Frozen model repair reports that the signed installer must be re-run if a
  bundled model is missing.
- Settings diagnostics run in-process in both modes and do not require
  `scripts/doctor.py`.
- Frozen autostart points directly to the installed `VoiceFlow.exe`.

## Commands

```bat
venv\Scripts\python.exe -m pytest tests\test_runtime_paths.py tests\test_runtime_services.py tests\test_settings_store.py -q
venv\Scripts\python.exe scripts\verify.py --quick
venv\Scripts\pyinstaller.exe VoiceFlow.spec --noconfirm
```

## Testing strategy

- Unit tests cover discovery, precedence, migration idempotency, frozen
  autostart, model status, and in-process diagnostics.
- Contract tests reject source-only runtime actions in the installed settings
  implementation.
- Existing recording-state, long-dictation, overlay, and model tests remain
  mandatory regression gates.
- A clean Windows VM install/upgrade/uninstall matrix remains a P1 release gate.

## Boundaries

- Always preserve existing user files and keep core operation offline.
- Ask before changing the user-data root or adding network behavior.
- Never copy large models implicitly, restore an old clipboard, expose private
  transcription text in diagnostics, or make installed behavior depend on a
  source checkout.

## Success criteria

- Installed settings contain no venv or maintainer-script dependency.
- All writes target `%LOCALAPPDATA%\VoiceFlow`.
- User models override bundled models; bundled models remain a safe fallback.
- Re-running migration produces no duplicate or overwritten user data.
- The pinned SenseVoice redistribution decision, exact license, attribution,
  revision, and hashes ship with the packaged application.
