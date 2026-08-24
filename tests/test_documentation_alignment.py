from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_active_docs_match_021_preview_and_release_contract():
    model_strategy = (ROOT / "docs" / "model-strategy.md").read_text(
        encoding="utf-8"
    )
    evaluation = (ROOT / "docs" / "asr-evaluation-plan.md").read_text(
        encoding="utf-8"
    )
    release = (ROOT / "docs" / "release-checklist.md").read_text(
        encoding="utf-8"
    )

    assert "fixed 48 ms cadence" in model_strategy
    assert "160 authorized" in evaluation
    assert "VoiceFlow-<version>-Windows-x64.exe" in release
    assert "release\\v<version>" in release
    assert "VoiceFlow-0.2.0-Windows-x64.exe" not in release


def test_active_docs_do_not_restore_removed_preview_animation_contracts():
    active_docs = (
        ROOT / "AGENTS.md",
        ROOT / "docs" / "model-strategy.md",
        ROOT / "docs" / "asr-evaluation-plan.md",
        ROOT / "docs" / "quality-gate.md",
        ROOT / "docs" / "release-checklist.md",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in active_docs)

    assert "24ms" not in combined
    assert "150ms" not in combined
    assert "全文重播" not in combined


def test_resource_evidence_keeps_real_budget_visible():
    profile = (ROOT / "docs" / "resource-profile-2026-07-28.md").read_text(
        encoding="utf-8"
    )
    release = (ROOT / "docs" / "release-checklist.md").read_text(
        encoding="utf-8"
    )

    assert "1,324.6 MB" in profile
    assert "exceeds the 1.0 GB" in profile
    evidence = (ROOT / "docs" / "release-performance-evidence-2026-08-11.md").read_text(
        encoding="utf-8"
    )
    assert "1,024 MB Private Bytes" in release
    assert "1,024 MB" in evidence
    assert "683.7 MB" in evidence
