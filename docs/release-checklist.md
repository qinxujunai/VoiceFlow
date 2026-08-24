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
- Short dictation stops quickly, pastes once, and dismisses the capsule without
  a redundant success label.
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
venv\Scripts\python.exe scripts\generate_release_assets.py --installer dist\installer\VoiceFlow-<version>-Windows-x64.exe --output-dir release\v<version> --version <version>
```

- The packaged app includes overlay, config, model manifest, knowledge base,
  license notices, the exact reviewed model license, redistribution decision,
  and icon.
- Qt LGPL, GPL, Chromium license texts and `docs/qt-lgpl-compliance.md` are
  present in the installed application.
- The selected default model has a recorded redistribution-license decision.
- Every bundled preview model also has an explicit weight license; `NOASSERTION`
  is a hard public-release failure.
- When no preview model passes both the distribution and performance gates, the
  public installer omits it and uses the quiet recording capsule. The source
  and internal CI build may still exercise pinned experimental candidates.
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

## Last published 0.3.1 limitations

These are disclosed limitations, not unearned product claims:

- The authorized natural-speech accuracy corpus and untouched holdout are not
  complete. Therefore 0.3.1 makes no comparative accuracy claim.
- The bilingual preview has an Apache-2.0 weight license and passes control-token
  safety; it is described as preview, never as authoritative final text.
- The tag workflow repeats install, launch, model-integrity, upgrade, uninstall,
  and private-data tests on a clean Windows runner before it can publish.
- The executable and installer are not Authenticode signed. README, website,
  and Release notes disclose the Windows warning and publish exact SHA-256.
- Synthetic one-hour coverage and two-hour stress are automated; release users
  are not promised a measured physical-microphone accuracy rate for that duration.
- The final installed process tree measured 1,024 MB Private Bytes and 683.7 MB
  Working Set after both recognizers loaded; see the release performance evidence.
