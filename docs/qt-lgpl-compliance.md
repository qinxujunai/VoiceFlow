# Qt / PySide6 LGPL Compliance Record

VoiceFlow 0.2.0 uses the dynamically linked PySide6 and Qt 6.11.1
runtime under the LGPL-3.0-only option. This record describes the exact source,
license texts, and replacement path used by the Windows onedir build. It is an
engineering compliance record, not legal advice.

## Pinned source

- PySide6 6.11.1:
  `qtproject/pyside-pyside-setup` tag `v6.11.1`, commit
  `73fb12a067c2e8f7a464a310aaee2860fa2b64d2`
- Qt Base 6.11.1:
  `qt/qtbase` tag `v6.11.1`, commit
  `59c81a3c2247b821b9b84b4eb8d939b77e07e276`
- Qt WebEngine 6.11.1:
  `qt/qtwebengine` tag `v6.11.1`, commit
  `eb0793cc4b76e93cf669f586fd68c76019f40ec9`

Corresponding source is available from:

- <https://github.com/qtproject/pyside-pyside-setup/tree/v6.11.1>
- <https://github.com/qt/qtbase/tree/v6.11.1>
- <https://github.com/qt/qtwebengine/tree/v6.11.1>

## Shipped notices

The installer includes:

- `licenses/Qt-LGPL-3.0-only.txt`, copied verbatim from Qt Base 6.11.1;
- `licenses/GPL-3.0-only.txt`, whose terms are incorporated by LGPL v3;
- `licenses/Chromium-BSD.txt`, copied verbatim from Qt WebEngine 6.11.1;
- `THIRD_PARTY_NOTICES.md`; and
- this compliance record.

The license files are pinned by Git blob identity in repository history.
Qt WebEngine's runtime resource bundle retains Chromium's generated credits
data; the Chromium license and upstream source location remain available even
though VoiceFlow does not expose a general-purpose browser address bar.

## Dynamic replacement

VoiceFlow uses a PyInstaller **onedir** layout. Qt and PySide6 remain separate
DLLs and resource files under the installation directory; they are not
statically linked into `VoiceFlow.exe`.

Users may inspect, debug, and replace those LGPL-covered files with a
compatible, user-built Qt/PySide6 6.11.1 build:

1. Exit VoiceFlow from the tray.
2. Back up the installation directory.
3. Replace the corresponding PySide6, Shiboken6, and Qt DLL/resource files
   while preserving the onedir paths and ABI compatibility.
4. Restart VoiceFlow and restore the backup if the replacement is incompatible.

VoiceFlow imposes no additional restriction on reverse engineering performed
for debugging or modifying LGPL-covered components.

## Release gate

Every packaged build must fail review if any pinned version changes without a
new source record, if the onedir layout stops permitting replacement, or if
the three license files and this record are absent from the installed product.
