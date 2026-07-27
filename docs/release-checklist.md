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
- Installed Start menu shortcut starts `VoiceFlow.exe` without a console.
- A maintainer source shortcut, if present, is not treated as installation
  evidence.
- Launching twice focuses the existing app instead of opening another main
  process.
- Short dictation stops quickly and shows the final checkmark.
- Long dictation keeps the overlay responsive and writes final text to clipboard
  and history.
- `logs\performance-evidence.jsonl` was regenerated on the release machine; it
  is evidence, not a repository fixture.

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
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" /DINCLUDE_SENSEVOICE=1 installer\VoiceFlow.iss
venv\Scripts\python.exe scripts\generate_release_assets.py --installer dist\installer\VoiceFlow-0.2.0-Windows-x64.exe --output-dir release\v0.2.0 --version 0.2.0
```

- The packaged app includes overlay, config, model manifest, knowledge base,
  license notices, the exact reviewed model license, redistribution decision,
  and icon.
- Qt LGPL, GPL, Chromium license texts and `docs/qt-lgpl-compliance.md` are
  present in the installed application.
- The selected default model has a recorded redistribution-license decision.
- The installer works per-user on a clean VM, upgrades the same AppId, rolls
  back using the previous signed installer, and removes its files on uninstall.
- A stable public installer and executable are Authenticode signed.
- Any unsigned release states that limitation in the website package details,
  README, and Release notes; it includes a SHA-256 file and is never described
  as trusted-signed.
- Public filenames follow `VoiceFlow-{version}-Windows-x64.exe`; channel labels
  such as `beta` do not appear in the customer-facing filename.
- `SBOM.cdx.json` parses as CycloneDX 1.6 and includes the bundled model.
- The tag-driven Release workflow publishes the installer, checksums, SBOM,
  notices, and GitHub build-provenance attestation from the same commit.
