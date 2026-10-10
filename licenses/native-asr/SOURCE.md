# Native ASR source and attribution supplements

The Windows ASR build reads unmodified Eigen 5.0.1 headers. Their exact upstream
source archive is included next to this notice as `eigen-5.0.1.tar.gz`, so it can
be obtained from the installed application without a network request.

- Upstream: https://gitlab.com/libeigen/eigen/-/archive/5.0.1/eigen-5.0.1.tar.gz
- Archive SHA256: `e9c326dc8c05cd1e044c71f30f1b2e34a6161a3b6ecf445d56b53ff1669e3dec`
- Archive bytes: 2,967,272
- VoiceFlow modifications to Eigen: none

The source retains its original per-file copyright and license notices. The
archive's `COPYING.MPL2` contains the MPL 2.0 terms for covered Eigen files;
other files retain their own terms. These source rights are not restricted by
VoiceFlow's application license. MPL terms are also available at
https://www.mozilla.org/en-US/MPL/2.0/ .

`nlohmann-json-to_chars.hpp` is the unchanged compiled header from the pinned
nlohmann/json 3.12.0 archive. It retains Florian Loitsch's 2009 and Niels
Lohmann's 2013-2025 copyright attributions. The unchanged upstream MIT text is
included as `nlohmann-json-LICENSE.MIT`.

- Upstream header: https://github.com/nlohmann/json/blob/v3.12.0/include/nlohmann/detail/conversions/to_chars.hpp
- Upstream archive SHA256: `4b92eb0c06d10683f7447ce9406cb97cd4b453be18d7279320f7b2f025c10187`
- VoiceFlow modifications to this header: none

`simple-sentencepiece-darts.h` retains Susumu Yata's original 2008-2014 BSD
2-Clause notice from the actual simple-sentencepiece 0.7 compiler input.
`onnxruntime_float16.h` retains Microsoft's MIT attribution and Fabian Giesen's
2016 conversion-routine BSD notice from the actual ONNX Runtime 1.24.4 input.
Neither header was modified. These header notices are additional to the root
dependency license texts; they are not replaced by those texts.

The unchanged Eigen archive also retains embedded BSD notices in `Half.h`,
`MKL_support.h` and `AlignedBox.h`. Including `MKL_support.h` as a source input
does not establish that the optional MKL runtime is linked or shipped.

The build record and package inventory retain hashes of these supplements.
Original native dependency notices are additionally included under
`licenses/python/` in the packaged application. These supplements address
specific observed source and attribution gaps; they do not assert that every
native component or redistribution obligation has been fully reviewed.
