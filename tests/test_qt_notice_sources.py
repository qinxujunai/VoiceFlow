import hashlib
import json
from pathlib import Path, PurePosixPath

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_original_notice_bytes_are_not_changed_by_git_checkout():
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "licenses/qt-6.11.1/** -text" in attributes
    assert "licenses/PortAudio-LICENSE.txt -text" in attributes
    assert "licenses/Silero-MIT.txt -text" in attributes


def test_qt_notice_bundle_preserves_pinned_originals_and_review_scope():
    bundle = ROOT / "licenses/qt-6.11.1"
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["license_review_complete"] is False
    assert "build" in manifest["scope"]
    revisions = {"qtbase": "59c81a3c2247b821b9b84b4eb8d939b77e07e276",
                 "qtsvg": "2596f43da2dc72d2afecc084355b0f5f87922a6c",
                 "qtimageformats": "77f35e5694885844c3eb3a737769b5ed290b8ccc"}
    assert {row["module"]: row["revision"] for row in manifest["modules"]} == revisions
    assert [len(row["retained_payloads"]) for row in manifest["modules"]] == [17, 3, 5]
    paths = set()
    for module in manifest["modules"]:
        assert len(module["archive"]["sha256"]) == 64
        for row in module["original_sources"] + module["upstream_sboms"]:
            relative = PurePosixPath(row["path"])
            assert not relative.is_absolute() and ".." not in relative.parts
            assert str(relative) not in paths
            paths.add(str(relative))
            payload = (bundle / relative).read_bytes()
            assert len(payload) == row["bytes"]
            assert hashlib.sha256(payload).hexdigest() == row["sha256"]
        for row in module["original_sources"]:
            assert f"/qt/{module['module']}/{module['revision']}/" in row["url"]
        assert all(row["payload_except_signing_fields_identical"] for row in module["retained_payloads"])
    assert "qtimageformats/src/3rdparty/libwebp/PATENTS" in paths
    assert "qtsvg/src/svg/LICENSE.XSVG.txt" in paths
    assert any(path.endswith("libtiff/COPYRIGHT") for path in paths)


@pytest.mark.parametrize("name,digest", [
    ("public_suffix_list.dat", "8932f171723344c037d0f4a7fe5e4c553880f6f70e3e3e317ea15383c6e3e4e2"),
    ("psl_data.cpp", "ceba7d5244fd9599201bdd2f9eac490a3caaaab5c08e22a87cdad98b1a4d4023"),
    ("psl-make-dafsa", "bae0c67459150063c253ed308d35a1b2b1ef883dd89de6d294037afac9b41779"),
])
def test_qt_public_suffix_preferred_source_and_generator_are_bundled(name, digest):
    bundle = ROOT / "licenses/qt-6.11.1"
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    supplement = manifest["covered_source_supplements"]["public_suffix_data"]
    assert supplement["preferred_source_revision"] == "944fb53321606f08740f04ef7c386f64df34ff76"
    assert supplement["dafsa_sha256"] == "962518d29af9a2fd7d983f0bae881ff465628bb5043e9341ee686c08b7c09534"
    assert supplement["exact_preferred_source_regeneration_verified"] is True
    assert supplement["complete_qt_license_approval"] is False
    record = next(row for row in supplement["original_sources"] if row["path"] == "public-suffix-data/" + name)
    payload = (bundle / record["path"]).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == record["sha256"] == digest
    assert len(payload) == record["bytes"]
    assert record["matches_pinned_repository_blob"] is True
    assert (bundle / "public-suffix-data/LICENSE.chromium").read_bytes() == (
        bundle / "qtbase/src/3rdparty/libpsl/src/LICENSE.chromium").read_bytes()


@pytest.mark.parametrize("acknowledgment", [
    "This software is based in part on the work of the FreeType Team.",
    "This software is based in part on the work of the Independent JPEG Group.",
    "Qt's smooth-scaling code used by VoiceFlow is based on Imlib2",
])
def test_qt_binary_distribution_has_explicit_product_acknowledgments(acknowledgment):
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert acknowledgment in notices
