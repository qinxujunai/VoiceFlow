# VoiceFlow platform release contract

This document is an internal release contract. Consumer-facing pages describe
only platforms that have a verified public asset.

## Supported release shapes

- Windows: one x64 installer built with PyInstaller onedir and Inno Setup.
- macOS: two native disk images, one for Apple Silicon and one for Intel.
- Do not label either macOS image as universal. A universal build is a separate
  deliverable and must prove that every Python, Qt, sherpa-onnx, ONNX, and audio
  binary contains both architectures.

The three desktop assets for a public version must be built from the same signed
Git tag and must report the same application version. A website button may be
added only after its matching GitHub Release asset exists and its download URL
returns a successful response.

## macOS runtime contract

- User data lives in `~/Library/Application Support/VoiceFlow`.
- The app uses the system microphone only while recording and keeps core ASR
  offline.
- Final text is written to the clipboard before VoiceFlow sends Command+V.
- Global triggers use the native macOS event path. The tray menu always keeps a
  `开始 / 停止听写` action so the product remains operable when a global trigger
  is unavailable.
- Login start uses `~/Library/LaunchAgents/ai.voiceflow.app.plist` and points at
  the installed app executable, never a source checkout or virtual environment.
- The app bundle must include both the final ASR model and the streaming preview
  model at their pinned revisions and checksums.

## macOS release evidence

Both Apple Silicon and Intel must pass:

1. Build the `.app` and `.dmg` on their native GitHub-hosted architecture.
2. Run the packaged `--runtime-smoke` contract from the app bundle.
3. Verify the app bundle, disk image, embedded assets, version, and SHA-256.
4. Install by dragging to `/Applications`, start from Finder, quit from the tray,
   relaunch, enable/disable login start, and remove the app without deleting user
   data.
5. Complete microphone and global-input permission flows from a clean macOS user.
6. Dictate into Notes, Safari, and a third-party editor. Cursor text, clipboard,
   and local history must match.
7. Complete 10-second, 25-second, 2-minute, 5-minute, and 10-minute recordings.
   The start, middle, and tail must all be present; preview must never replay or
   move backwards.
8. Repeat after sleep/wake and after disconnecting and reconnecting an audio
   device.

Public distribution additionally requires the repository's reviewed Apple
signing and notarization workflow. Internal CI artifacts are test inputs, not
public downloads.

## Website and Release sequencing

1. Merge tested product changes.
2. Build all platform assets from the version tag.
3. Complete the platform matrix and compare SHA-256 values with the build jobs.
4. Publish the GitHub Release assets.
5. Verify every public asset URL without downloading through an intermediate
   draft link.
6. Update the website and README platform buttons.
7. Wait for GitHub Pages, then verify the rendered page and each download again.

If any platform asset fails after publication, remove that platform from the
website recommendation and publish a new patch version. Never move or replace an
existing version tag.
