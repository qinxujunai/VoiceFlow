# Qt Network public-suffix data source

This directory includes the unchanged preferred source for the Public Suffix
List embedded in the bundled Qt 6.11.1 Network library. The list is covered by
MPL 2.0; its original source header and the full terms in
`../qtbase/src/3rdparty/libpsl/PSL-LICENSE.txt` remain available locally.
VoiceFlow does not restrict those source rights and has not modified the list.

- Preferred source: `public_suffix_list.dat`, publicsuffix/list revision
  `944fb53321606f08740f04ef7c386f64df34ff76`.
- Original generated table: `psl_data.cpp`, qt/qtbase revision
  `59c81a3c2247b821b9b84b4eb8d939b77e07e276`.
- Original standalone generator: `psl-make-dafsa`, from that Qt revision,
  under the accompanying `LICENSE.chromium` BSD terms.

All original files retain their byte identity. URLs, sizes, hashes and the
comparison scope are recorded in `../manifest.json` under
`covered_source_supplements.public_suffix_data`. Original repositories:

- https://github.com/publicsuffix/list/tree/944fb53321606f08740f04ef7c386f64df34ff76
- https://github.com/qt/qtbase/tree/59c81a3c2247b821b9b84b4eb8d939b77e07e276/src/3rdparty/libpsl

For an optional local regeneration with a compatible Python interpreter:

```text
python psl-make-dafsa public_suffix_list.dat regenerated-psl-data.cpp
```

The reviewed regeneration reproduces the original C++ file byte for byte, and
its 55,320-byte table occurs exactly once in the current Qt6Network.dll. No
network request is needed for that regeneration. The separate upstream update
shell script is not shipped or executed by VoiceFlow. This table correspondence
does not certify the complete Qt source, build or redistribution review.
