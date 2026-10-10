import hashlib
import json
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]


def test_cpython_native_notices_preserve_original_bytes_and_scope():
    bundle = ROOT / "licenses/cpython-3.12.13"
    assert (bundle / "manifest.json").is_file(), "CPython native component notices are missing"
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["license_review_complete"] is False
    assert manifest["python_version"] == "3.12.13"
    assert manifest["binary_archive"]["digest"] == (
        "sha256:dbada31f91a4fff934dae85e7998d91f1e926135bd88ffed4921a337d5680f48")
    originals = {row["path"]: row for row in manifest["original_sources"]}
    assert {"LICENSE.libffi.txt", "LICENSE.mpdecimal.txt", "LICENSE.zlib.txt",
            "CPython-expat-COPYING", "CPython-mpdecimal.h"} <= set(originals)
    for name, row in originals.items():
        relative = PurePosixPath(name)
        assert not relative.is_absolute() and ".." not in relative.parts
        payload = (bundle / relative).read_bytes()
        assert len(payload) == row["bytes"]
        assert hashlib.sha256(payload).hexdigest() == row["sha256"]
    assert originals["CPython-expat-COPYING"]["sha256"] == (
        "31b15de82aa19a845156169a17a5488bf597e561b2c318d159ed583139b25e87")
    assert len(manifest["binary_comparisons"]) == 23
    assert "licenses/cpython-3.12.13/** -text" in (ROOT / ".gitattributes").read_text()
    assert "licenses/cpython-3.12.13" in (ROOT / "THIRD_PARTY_NOTICES.md").read_text()
