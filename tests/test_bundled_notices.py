from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def test_collects_verbatim_notices_only_for_distributions_used_by_analysis(tmp_path, monkeypatch):
    from bundled_notices import collect_distribution_notices

    (tmp_path / "used.py").write_text("value = 1\n")
    (tmp_path / "LICENSE").write_bytes(b"Copyright fixture\nMIT terms\n")
    used = SimpleNamespace(metadata={"Name": "Used_Lib"}, version="1.2",
                           files=["used.py", "LICENSE"], locate_file=lambda name: tmp_path / name)
    unused = SimpleNamespace(metadata={"Name": "Unused"}, version="9",
                             files=["other.py", "LICENSE"], locate_file=lambda name: tmp_path / name)
    monkeypatch.setattr("bundled_notices.importlib.metadata.distributions", lambda: [used, unused])
    datas, report = collect_distribution_notices([("used", str(tmp_path / "used.py"), "PYMODULE")])
    assert datas == [("licenses/python/used-lib-1.2/LICENSE", str(tmp_path / "LICENSE"), "DATA")]
    assert [row["name"] for row in report] == ["Used_Lib"]
    assert report[0]["notices"][0]["sha256"]
    assert str(tmp_path) not in str(report)


def test_missing_notices_are_explicit_and_unsafe_license_paths_are_rejected(tmp_path, monkeypatch):
    from bundled_notices import collect_distribution_notices

    (tmp_path / "used.py").write_text("value = 1\n")
    used = SimpleNamespace(metadata={"Name": "Used"}, version="1",
                           files=["used.py"], locate_file=lambda name: tmp_path / name)
    monkeypatch.setattr("bundled_notices.importlib.metadata.distributions", lambda: [used])
    entries = [("used", str(tmp_path / "used.py"), "PYMODULE")]
    datas, report = collect_distribution_notices(entries)
    assert datas == []
    assert report[0]["notices"] == []
    used.files.append("../LICENSE")
    with pytest.raises(ValueError, match="notice path"):
        collect_distribution_notices(entries)


def test_retains_patches_and_build_metadata_inside_original_wheel_license_directory(tmp_path, monkeypatch):
    from bundled_notices import collect_distribution_notices

    (tmp_path / "used.py").write_text("value = 1\n")
    patch = tmp_path / "used-1.dist-info/licenses/upstream-local.patch"
    patch.parent.mkdir(parents=True)
    patch.write_bytes(b"original native patch\r\n")
    used = SimpleNamespace(metadata={"Name": "Used"}, version="1",
        files=["used.py", "used-1.dist-info/licenses/upstream-local.patch"], locate_file=lambda name: tmp_path / name)
    monkeypatch.setattr("bundled_notices.importlib.metadata.distributions", lambda: [used])
    datas, report = collect_distribution_notices([("used", str(tmp_path / "used.py"), "PYMODULE")])
    assert len(datas) == 1
    assert datas[0][1] == str(patch)
    import hashlib
    assert report[0]["notices"][0]["sha256"] == hashlib.sha256(patch.read_bytes()).hexdigest()


def test_cffi_windows_libffi_notices_are_retained_separately_from_root_license():
    import hashlib
    import json

    root = Path(__file__).resolve().parents[1]
    bundle = root / "licenses/cffi-2.0.0"
    assert (bundle / "manifest.json").is_file(), "CFFI's embedded libffi notices are missing"
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["license_review_complete"] is False
    assert manifest["wheel_sha256"] == (
        "da68248800ad6320861f129cd9c1bf96ca849a2771a59e0344e88681905916f5")
    assert manifest["native_sha256"] == (
        "53de34afc3939d81bf2498b77425c52e2c3f3164f8cfe2543d3acc8f24134488")
    originals = {row["path"]: row for row in manifest["original_sources"]}
    assert {"libffi_x86_x64/ffi.c", "libffi_x86_x64/types.c",
            "libffi_x86_x64/prep_cif.c", "setup.py", "LICENSE"} <= set(originals)
    for name, row in originals.items():
        payload = (bundle / name).read_bytes()
        assert len(payload) == row["bytes"]
        assert hashlib.sha256(payload).hexdigest() == row["sha256"]
    assert "licenses/cffi-2.0.0/** -text" in (root / ".gitattributes").read_text()
    assert "licenses/cffi-2.0.0" in (root / "THIRD_PARTY_NOTICES.md").read_text()


def test_numpy_embedded_loader_and_blas_original_notices_are_retained():
    import hashlib
    import json

    root = Path(__file__).resolve().parents[1]
    bundle = root / "licenses/numpy-2.5.0-supplements"
    assert (bundle / "manifest.json").is_file(), "NumPy loader/BLAS original notices are missing"
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["license_review_complete"] is False
    assert manifest["delvewheel_template_exact_match"] is True
    expected = {
        "delvewheel-1.11.2-LICENSE": "e43d93da16aa3b61ef0969fff2130b135984859a05664fbce423ad126688c5d3",
        "scipy-openblas64-0.3.33.112.0-LICENSE.txt": "7317b3a9eb806cc83a0cc6b1c7c2fbe6018eed556daa9996e6e3a727a2a5bfbe",
    }
    assert {row["path"] for row in manifest["original_sources"]} == set(expected)
    for row in manifest["original_sources"]:
        payload = (bundle / row["path"]).read_bytes()
        assert len(payload) == row["bytes"]
        assert hashlib.sha256(payload).hexdigest() == row["sha256"] == expected[row["path"]]
    assert "licenses/numpy-2.5.0-supplements/** -text" in (root / ".gitattributes").read_text()
    assert "licenses/numpy-2.5.0-supplements" in (root / "THIRD_PARTY_NOTICES.md").read_text()
