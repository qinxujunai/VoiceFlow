from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from package_inventory import inventory_package


def test_inventory_attributes_used_distributions_and_excludes_unused(tmp_path, monkeypatch):
    site = tmp_path / "site-packages"
    site.mkdir()
    module = site / "used.py"
    module.write_text("value = 1\n")
    package = tmp_path / "package"
    package.mkdir()
    (package / "VoiceFlow.exe").write_bytes(b"fixture")
    toc = tmp_path / "Analysis-00.toc"
    toc.write_text(repr(([("used", str(module), "PYMODULE"),
                          ("used.namespace", "-", "PYMODULE")],)))
    used = SimpleNamespace(metadata={"Name": "Used", "License-Expression": "MIT"},
                           version="1.2.3", files=["used.py"], locate_file=lambda path: site / path)
    unused = SimpleNamespace(metadata={"Name": "Unused"}, version="9", files=[], locate_file=lambda path: site / path)
    monkeypatch.setattr("package_inventory.importlib.metadata.distributions", lambda: [used, unused])
    report = inventory_package(package, toc)
    assert report["complete_python_attribution"]
    assert [row["name"] for row in report["python_distributions"]] == ["Used"]
    assert report["python_distributions"][0]["version"] == "1.2.3"
    assert report["files"][0]["sha256"]
    assert report["namespace_modules"] == ["used.namespace"]


def test_unmapped_site_package_source_is_reported_as_incomplete(tmp_path, monkeypatch):
    site = tmp_path / "site-packages"
    site.mkdir()
    module = site / "unknown.py"
    module.write_text("value = 1\n")
    toc = tmp_path / "Analysis-00.toc"
    toc.write_text(repr(([("unknown", str(module), "PYMODULE")],)))
    package = tmp_path / "package"
    package.mkdir()
    monkeypatch.setattr("package_inventory.importlib.metadata.distributions", lambda: [])
    report = inventory_package(package, toc)
    assert not report["complete_python_attribution"]
    assert report["unattributed_site_package_sources"] == [str(module.resolve())]


def test_inventory_rejects_a_copied_binary_from_another_source(tmp_path):
    source = tmp_path / "source.dll"
    source.write_bytes(b"before")
    package = tmp_path / "package"
    package.mkdir()
    (package / "source.dll").write_bytes(b"after")
    toc = tmp_path / "Analysis-00.toc"
    toc.write_text(repr(([("source.dll", str(source), "BINARY")],)))
    with pytest.raises(ValueError, match="differs"):
        inventory_package(package, toc)


def test_generated_comtypes_initializer_requires_its_exact_generator_literal(tmp_path, monkeypatch):
    site = tmp_path / "site-packages"
    initializer = site / "comtypes/gen/__init__.py"
    generator = site / "comtypes/client/_code_cache.py"
    initializer.parent.mkdir(parents=True)
    generator.parent.mkdir(parents=True)
    expected = "# comtypes.gen package, directory for generated files.\n"
    initializer.write_text(expected)
    generator.write_text(f"output = {expected!r}\n")
    toc = tmp_path / "Analysis-00.toc"
    toc.write_text(repr(([("comtypes.gen", str(initializer), "PYMODULE")],)))
    package = tmp_path / "package"
    package.mkdir()
    distribution = SimpleNamespace(metadata={"Name": "comtypes"}, version="1.4.13",
                                   files=["comtypes/client/_code_cache.py"], locate_file=lambda path: site / path)
    monkeypatch.setattr("package_inventory.importlib.metadata.distributions", lambda: [distribution])
    report = inventory_package(package, toc)
    assert report["complete_python_attribution"]
    assert report["generated_source_provenance"][0]["generator_sha256"]
    initializer.write_text("unexpected executable code\n")
    assert not inventory_package(package, toc)["complete_python_attribution"]
