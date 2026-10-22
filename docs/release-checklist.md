# VoiceFlow Release Checklist

> Documentation sync: **2026-10-22** · Current contract / guide. Synchronization date is not a new test date. [Current index](README.md).

Use this checklist before updating the GitHub default branch or publishing a
build.

## Local Verification

```bat
git status --short
venv\Scripts\python.exe scripts\verify.py --release
venv\Scripts\python.exe scripts\ui_quality_gate.py
```

- Commit the intended release changes; preserve unrelated local files and never
  use a broad clean/reset merely to obtain a clean working tree.
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
- The bilingual README links to development documentation, which links to the
  quality gate, ASR evaluation plan, latest dated release verification and
  [documentation index](README.md).
- Recheck the actual latest Release, installed EXE and live website metadata;
  a successful source checkout alone does not establish delivery.

## Packaging Verification

```powershell
venv\Scripts\python.exe -m PyInstaller VoiceFlow.spec --noconfirm
$toolRoot = Join-Path $env:TEMP ("VoiceFlow-build-tools-" + [guid]::NewGuid().ToString("N"))
$innoCompiler = ./scripts/prepare_inno_compiler.ps1 -ToolchainRoot $toolRoot
& $innoCompiler /DINCLUDE_SENSEVOICE=1 /DINCLUDE_STREAMING_PREVIEW=1 /DINCLUDE_PUNCTUATION=1 installer\VoiceFlow.iss
venv\Scripts\python.exe scripts\generate_release_assets.py --installer dist\installer\VoiceFlow-<version>-Windows-x64.exe --output-dir release\v<version> --version <version> --package-dir dist\VoiceFlow --analysis-toc build\VoiceFlow\Analysis-00.toc
venv\Scripts\python.exe scripts\check_release_compliance.py release\v<version>
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
- Exercise the exact uploaded installer on a disposable Windows runner/VM:
  `scripts/smoke_installer.ps1 -InstallerPath <installer> -FreshInstall
  -RequireStreamingPreview -RequirePunctuation`, then a separate invocation
  with `-PreviousInstallerPath <previous-installer>` instead of `-FreshInstall`.
  Verify first start, same-AppId upgrade, uninstall and retained user data.
  Never run this lifecycle smoke under the production Windows user: an isolated
  directory does not isolate HKCU uninstall registration.
- A hosted runner includes development tools. Record actual VC DLL load paths
  and static dependency closure; do not describe that as a pristine consumer OS.
- Rollback uses a verified program backup or previous verified installer after
  confirming the identified instance is idle and has exited. Preserve user data
  and shortcut targets; do not interrupt an active recording.
- Prefer Authenticode-signed executables and installers when signing is available.
- Any unsigned release states that limitation in the website package details,
  README, and Release notes; it includes a SHA-256 file and is never described
  as trusted-signed.
- Public filenames follow `VoiceFlow-{version}-Windows-x64.exe`; channel labels
  such as `beta` do not appear in the customer-facing filename.
- `SBOM.cdx.json` parses as CycloneDX 1.6 and reflects actual frozen distribution
  attribution, every frozen file, CPython and pinned packaged model files.
  Build/test requirements are not automatically declared as shipped libraries.
- `BUILD_PROVENANCE.json` records the embedded build inputs, actual package file
  hashes, application/installer PE identities and installer SHA256. Source changes
  after freezing require rebuilding. This record covers its explicit input list,
  not a complete dirty-working-tree archive. Installer payload equivalence still
  requires installed-file verification.
- An incomplete SBOM composition or unfinished native/component license review
  blocks release. Generated inventory is review evidence, not a compliance approval.
  The release workflow preserves the engineering materials, then checks that
  recorded review completion and SBOM compositions are complete and identify the
  same source/build/installer before attestation or public publication. Current
  engineering output deliberately fails this check until the review is finished;
  changing flags alone is not review evidence.
- For an artifact-bound review, retain the completed `RELEASE_SIGNOFF.json`,
  corresponding LGPL sources, original Microsoft redistribution terms and
  applicable entitlement record. Keep generated defaults fail-closed; changing
  completion flags without supporting evidence is not approval.
- The tag-driven workflow can publish and attest only after all its gates pass.
  A reviewed local installer promoted from a draft Release must retain its exact
  asset/digest identity; do not claim a GitHub build attestation for a local build.
- Compare local SHA256, uploaded GitHub digest, checksum file and an anonymous
  public download. Derive website downloads from the verified stable Release,
  not manually maintained version numbers.
- Release events request a `master` Pages deployment; only the deployment job
  enters the protected environment. Do not broaden its branch policy. Verify
  deployed metadata, desktop/mobile presentation, automatic demo loops, pause
  and reduced motion. The website has no Replay control.

## Current release evidence

See [0.3.9 release verification](release-validation-0.3.9.md) and the
[documentation index](README.md). The natural-speech holdout remains incomplete,
the installer is unsigned, and macOS is not a public download target.

## Historical 0.3.1 limitations

The following is an archived 0.3.1 snapshot, not the current build's measurements:

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
