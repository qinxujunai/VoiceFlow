from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def test_build_record_is_portable_and_detects_changed_or_added_inputs(tmp_path):
    from build_record import create_build_record, validate_build_record

    root = tmp_path / "source"
    (root / "src").mkdir(parents=True)
    (root / "src/version.py").write_text(
        'APP_VERSION = "1.2.3"\nBUILD_ID = "fixture.1"\nWINDOWS_REVISION = 4\n'
    )
    (root / "VoiceFlow.spec").write_text("# fixture\n")
    record = create_build_record(root)
    assert record == create_build_record(root)
    assert all(not Path(row["path"]).is_absolute() for row in record["source_inputs"])
    validate_build_record(root, record)
    (root / "src/new.py").write_text("value = 1\n")
    with pytest.raises(ValueError, match="source inputs"):
        validate_build_record(root, record)
    (root / "src/new.py").unlink()
    (root / "VoiceFlow.spec").write_text("# changed\n")
    with pytest.raises(ValueError, match="source inputs"):
        validate_build_record(root, record)


def test_build_record_rejects_tampered_digest(tmp_path):
    from build_record import create_build_record, validate_build_record

    (tmp_path / "src").mkdir()
    (tmp_path / "src/version.py").write_text(
        'APP_VERSION = "1.2.3"\nBUILD_ID = "fixture.1"\nWINDOWS_REVISION = 4\n'
    )
    record = create_build_record(tmp_path)
    record["source_inputs_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest"):
        validate_build_record(tmp_path, record)


def test_spec_embeds_the_build_record_from_the_build_work_directory():
    spec = (ROOT / "VoiceFlow.spec").read_text(encoding="utf-8")
    assert "write_build_record" in spec
    assert 'CONF["workpath"]' in spec
    assert '(str(build_record), ".")' in spec
