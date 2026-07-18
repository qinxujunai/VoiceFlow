# VoiceFlow Release Checklist

Use this checklist before updating the GitHub default branch or publishing a
build.

## Local Verification

```bat
git status --short
venv\Scripts\python.exe scripts\verify.py --release
venv\Scripts\python.exe scripts\ui_quality_gate.py
```

- Working tree is clean before merge.
- Verify passes on the branch being released.
- Desktop shortcut starts the no-console launcher.
- Launching twice focuses the existing app instead of opening another main
  process.
- Short dictation stops quickly and shows the final checkmark.
- Long dictation keeps the overlay responsive and writes final text to clipboard
  and history.

## GitHub Verification

- Default branch README shows the animated `docs/voiceflow-demo.svg` product story.
- About description matches the product positioning.
- Quick Start matches the actual setup path.
- Model files remain outside Git.
- `docs/quality-gate.md` and `docs/asr-evaluation-plan.md` are linked from the
  README.

## Packaging Verification

```bat
venv\Scripts\pyinstaller.exe VoiceFlow.spec --noconfirm
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\VoiceFlow.iss
```

- The packaged app includes overlay, config, model manifest, knowledge base,
  license notices, and icon.
- The selected default model has a recorded redistribution-license decision.
- The installer works per-user on a clean VM, upgrades the same AppId, rolls
  back using the previous signed installer, and removes its files on uninstall.
- The public installer and executable are Authenticode signed.
