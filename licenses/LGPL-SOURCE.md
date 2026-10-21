# Library source and replacement

Corresponding source for the unchanged Qt/PySide6 6.11.1 and pynput 1.8.2 libraries
bundled with VoiceFlow 0.3.9. Original sources and their licenses are retained in
each archive. SOURCES.json pins origin, revision and SHA256. See the upstream
README/CMake files for build instructions. Compatible user-built library files
may replace the separate onedir libraries; VoiceFlow imposes no restriction on
reverse engineering for debugging modifications to LGPL-covered components.
No bit-reproducibility claim is made. The signed Qt SDK payload/source review
and replacement procedure are in installed docs/qt-lgpl-compliance.md.

The matching source archive is a separate asset beside the Windows installer:

https://github.com/qinxujunai/VoiceFlow/releases/download/v0.3.9/VoiceFlow-0.3.9-LGPL-sources.zip

SHA256: `5137f59bab8df5002446cf2a8910b2105eb3eed6876574c09769857f7160e816`

Exact archive origins and checksums: `licenses/lgpl-sources.json`. Original Eigen
MPL source and Qt public-suffix data are already included in the installation,
under `licenses/native-asr` and `licenses/qt-6.11.1/public-suffix-data`.
