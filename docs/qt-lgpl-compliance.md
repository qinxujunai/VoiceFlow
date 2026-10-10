# Qt / PySide6 LGPL Compliance Record

VoiceFlow's current native development package uses dynamically linked PySide6 and Qt 6.11.1
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
- Qt SVG 6.11.1 (SVG image/icon plugins):
  `qt/qtsvg` tag `v6.11.1`, commit
  `2596f43da2dc72d2afecc084355b0f5f87922a6c`
- Qt Image Formats 6.11.1 (retained image plugins):
  `qt/qtimageformats` tag `v6.11.1`, commit
  `77f35e5694885844c3eb3a737769b5ed290b8ccc`. The official binary SPDX omits
  this module's commit; attribution/COPYRIGHT/PATENTS source matches and the
  unlisted WebP COPYING file's more limited tag provenance are recorded in
  `licenses/qt-6.11.1/manifest.json`.
- Historical WebEngine renderer, excluded from the native candidate: Qt WebEngine 6.11.1:
  `qt/qtwebengine` tag `v6.11.1`, commit
  `eb0793cc4b76e93cf669f586fd68c76019f40ec9`

Corresponding source is available from:

- <https://github.com/qtproject/pyside-pyside-setup/tree/v6.11.1>
- <https://github.com/qt/qtbase/tree/v6.11.1>
- <https://github.com/qt/qtsvg/tree/v6.11.1>
- <https://github.com/qt/qtimageformats/tree/v6.11.1>
- <https://github.com/qt/qtwebengine/tree/v6.11.1>

## Shipped notices

The installer includes:

- `licenses/Qt-LGPL-3.0-only.txt`, copied verbatim from Qt Base 6.11.1;
- `licenses/GPL-3.0-only.txt`, whose terms are incorporated by LGPL v3;
- `licenses/Chromium-BSD.txt`, copied verbatim from Qt WebEngine 6.11.1;
- `THIRD_PARTY_NOTICES.md`; and
- this compliance record.

The next native package also includes `licenses/qt-6.11.1/`: 110 unchanged
original attribution, copyright, license and supplementary notice files,
eight official upstream build/source SBOM documents, and a manifest of their
URLs, sizes and SHA256 values. The upstream documents include unshipped tools
and build interfaces; they are supporting provenance, not VoiceFlow's product
SBOM or a claim that every upstream record ships. Applicability and license
obligations still require review. Dev4 predates this bundle.

The source bundle now also includes `licenses/qt-6.11.1/public-suffix-data/`.
It preserves the original preferred MPL 2.0 list at its upstream SPDX-pinned
revision, Qt's generated C++ table, and the original standalone BSD generator
and notice. A reviewed local regeneration reproduces the C++ file byte for byte;
its 55,320-byte table occurs exactly once in the current Qt Network DLL. The
parent manifest records exact Git blob identities, hashes and comparison limits.
`SOURCE.md` explains how to obtain or regenerate the source without a network
request. Dev16 predates this covered-source bundle; a new package is required.
This does not approve the complete Qt source/build or product license review.

The license files are pinned by Git blob identity in repository history.
The inspected `261007.dev4` native package ships Qt Core/Gui/Widgets/Network/Svg
DLLs and 20 plugins, with no separate `Qt6OpenGL.dll`, and
excludes WebEngine, PDF, VirtualKeyboard, QML, Quick, Chromium executables and their
resource packs. These exclusions are checked against collected files by
`scripts/check_frozen_qt.py`; Python-module exclusions alone were insufficient.
Earlier local working packages failed that file-level boundary and must not be
used as native release candidates. The historical Chromium
notice and source location remain in the repository for prior-build review.
All 25 retained QtBase/SVG/ImageFormats DLL payloads match their official Qt
6.11.1 Windows MSVC2022 SDK archives after excluding only PE checksum and
signature metadata; whole-file identity is not claimed. The manifest records
both package and official archive file hashes. Any change requires review
against the matching upstream build again.

Any redistribution of the historical WebEngine build must also retain its
bundled generated Chromium credits resources.

## Software OpenGL provenance

The retained `PySide6/opengl32sw.dll` contains Mesa 11.2.2 and LLVM 3.6.2 version
strings. Its code/data sections and all PE payload bytes excluding checksum,
security-directory entry and certificate table match Qt's official
`opengl32sw-64-mesa_11_2_2-signed_sha256.7z`. The whole DLL hashes differ because
their signing metadata differs; they must not be described as byte-identical.
The upstream archive SHA256 is
`c61f801c1760aa24b02c7a8354323cddf368b86f8f5c34b50b3b224f7d728afd`,
verified against [Qt's published checksums](https://download.qt.io/development_releases/prebuilt/llvmpipe/windows/sha256sums.txt).

The source notices are retained in `licenses/Mesa-llvmpipe-NOTICES.txt` from
[Qt's attribution](https://doc.qt.io/qt-6.5/qt-attribution-llvmpipe.html) and
`licenses/LLVM-3.6.2-LICENSE.txt` from the
[exact LLVM release](https://raw.githubusercontent.com/llvm/llvm-project/llvmorg-3.6.2/llvm/LICENSE.TXT).
LLVM's release license also identifies component-specific notices; their
regex, ARM and MD5 notices are retained unchanged in the corresponding
`licenses/LLVM-3.6.2-*` files. Exact linked-component applicability still needs
review. The development
dev2 package predates these additional notice files and must be rebuilt before
redistribution. The comparison did not execute the downloaded DLL.

## Dynamic replacement

VoiceFlow uses a PyInstaller **onedir** layout. Qt and PySide6 remain separate
DLLs and resource files under the installation directory; they are not
statically linked into `VoiceFlow.exe`. The current spec also collects the
PySide6/Shiboken6 Python modules as external original `.py` files. Compatible
changes to these library portions do not require editing the embedded EXE
archive. Actual frozen replacement verification is required for this path;
dev15 and earlier seal these Python modules in PYZ.

Users may inspect, debug, and replace those LGPL-covered files with a
compatible, user-built Qt/PySide6 6.11.1 build:

1. Exit VoiceFlow from the tray.
2. Back up the installation directory.
3. Replace the corresponding PySide6, Shiboken6, and Qt DLL/resource/source files
   while preserving the onedir paths and ABI compatibility.
4. Restart VoiceFlow and restore the backup if the replacement is incompatible.

VoiceFlow imposes no additional restriction on reverse engineering performed
for debugging or modifying LGPL-covered components.

## Release gate

This source/replacement record is one part of the release review. The complete
native dependency inventory and corresponding third-party attributions (including
the retained software OpenGL runtime) must be reviewed against the exact final
package. This record alone does not certify redistribution readiness. The dev4
working package predates the Qt original notice bundle and this correction;
a final build must include both.

Every packaged build must fail review if any pinned version changes without a
new source record, if the onedir layout stops permitting replacement, or if
the three license files and this record are absent from the installed product.
