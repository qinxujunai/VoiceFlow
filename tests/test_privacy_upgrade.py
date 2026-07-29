from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _digest(value: str) -> str:
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()


def test_v1_vocabulary_migration_removes_seed_and_preserves_user_content(tmp_path):
    from runtime_paths import AppPaths, RuntimeMode, prepare_runtime_layout

    install_dir = tmp_path / "install"
    data_dir = tmp_path / "data"
    install_knowledge = install_dir / "knowledge-base"
    data_knowledge = data_dir / "knowledge-base"
    install_knowledge.mkdir(parents=True)
    data_knowledge.mkdir(parents=True)
    (install_dir / "config.yaml").write_text("hotwords:\n  files: []\n", encoding="utf-8")
    (data_dir / "config.yaml").write_text("hotwords:\n  files: []\n", encoding="utf-8")
    (data_dir / "runtime-state.json").write_text(
        json.dumps({"schema_version": 1}),
        encoding="utf-8",
    )

    private_seed = "legacy-private-seed"
    private_correction = "legacy-wrong=legacy-private-seed"
    custom_word = "user-kept-word"
    custom_correction = "user-wrong=user-correct"
    (data_knowledge / "user-dictionary.txt").write_text(
        f"{private_seed}\n{custom_word}\n",
        encoding="utf-8",
    )
    (data_knowledge / "corrections.txt").write_text(
        f"{private_correction}\n{custom_correction}\n",
        encoding="utf-8",
    )
    (data_knowledge / "company-terms.txt").write_text(
        f"{private_seed}\nlegacy-user-added\n",
        encoding="utf-8",
    )

    paths = AppPaths(
        mode=RuntimeMode.FROZEN,
        install_dir=install_dir,
        data_dir=data_dir,
        executable=install_dir / "VoiceFlow.exe",
    )
    private_hashes = {_digest(private_seed), _digest(private_correction)}

    first = prepare_runtime_layout(paths, private_entry_hashes=private_hashes)
    second = prepare_runtime_layout(paths, private_entry_hashes=private_hashes)

    user_dictionary = (data_knowledge / "user-dictionary.txt").read_text(
        encoding="utf-8"
    )
    corrections = (data_knowledge / "corrections.txt").read_text(encoding="utf-8")
    assert private_seed not in user_dictionary
    assert private_correction not in corrections
    assert custom_word in user_dictionary
    assert "legacy-user-added" in user_dictionary
    assert custom_correction in corrections
    assert not (data_knowledge / "company-terms.txt").exists()
    assert first.schema_version == 2
    assert second.schema_version == 2
    assert user_dictionary == (data_knowledge / "user-dictionary.txt").read_text(
        encoding="utf-8"
    )
    assert corrections == (data_knowledge / "corrections.txt").read_text(
        encoding="utf-8"
    )


def test_public_defaults_and_source_do_not_contain_private_seed_hashes():
    from runtime_paths import PRIVATE_ENTRY_SHA256

    scanned = [
        ROOT / "config.yaml",
        ROOT / "src" / "text_cleaner.py",
        *sorted((ROOT / "knowledge-base").glob("*.txt")),
    ]
    matches = []
    for path in scanned:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if _digest(line) in PRIVATE_ENTRY_SHA256:
                matches.append(f"{path.relative_to(ROOT)}:{line_number}")

    assert matches == []
    assert not (ROOT / "knowledge-base" / "company-terms.txt").exists()
    assert not (ROOT / "knowledge-base" / "user-custom.txt").exists()
    assert not (ROOT / "knowledge-base" / "ai-terms.txt").exists()


def test_legacy_file_is_not_removed_when_destination_write_fails(tmp_path, monkeypatch):
    import runtime_paths

    knowledge_dir = tmp_path / "knowledge-base"
    knowledge_dir.mkdir()
    legacy = knowledge_dir / "company-terms.txt"
    legacy.write_text("user-kept-word\n", encoding="utf-8")

    def fail_write(path, values):
        raise OSError("simulated destination failure")

    monkeypatch.setattr(runtime_paths, "_append_unique_lines", fail_write)

    with pytest.raises(OSError, match="simulated destination failure"):
        runtime_paths._migrate_legacy_vocabulary(knowledge_dir, frozenset())

    assert legacy.read_text(encoding="utf-8") == "user-kept-word\n"


def test_packaged_vocabulary_scanner_rejects_private_seed_hash(tmp_path):
    from scripts.scan_private_vocabulary import scan_tree

    knowledge = tmp_path / "knowledge-base"
    knowledge.mkdir()
    (knowledge / "builtin-ai.txt").write_text("public-ai-term\n", encoding="utf-8")
    private_line = "legacy-private-seed"
    private_hashes = frozenset({_digest(private_line)})

    assert scan_tree(tmp_path, private_hashes=private_hashes) == []

    (knowledge / "user-dictionary.txt").write_text(
        f"{private_line}\n",
        encoding="utf-8",
    )
    assert scan_tree(tmp_path, private_hashes=private_hashes) == [
        "knowledge-base/user-dictionary.txt:1"
    ]
