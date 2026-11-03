"""The release and its installer tests must cover the punctuation model."""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_windows_installer_pipelines_include_and_verify_punctuation():
    for filename, job in (("windows-quality.yml", "package-smoke"),
                          ("release.yml", "windows-release")):
        workflow = yaml.safe_load((ROOT / ".github" / "workflows" / filename).read_text(encoding="utf-8"))
        scripts = "\n".join(step.get("run", "") for step in workflow["jobs"][job]["steps"])
        assert "download_models.py --engine punctuation" in scripts
        assert "/DINCLUDE_PUNCTUATION=1" in scripts
        assert "-RequirePunctuation" in scripts


def test_public_release_checks_punctuation_distribution_decision():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"))
    check = next(step["run"] for step in workflow["jobs"]["windows-release"]["steps"]
                 if step.get("name") == "Verify bundled-model distribution decisions")
    assert "ct-transformer-punctuation-int8" in check


def test_installer_smoke_requires_a_live_punctuation_worker():
    script = (ROOT / "scripts" / "smoke_installer.ps1").read_text(encoding="utf-8")
    assert '$state.worker_pids.punctuation' in script
    assert 'Get-Process -Id $punctuationPid' in script


def test_punctuation_worker_is_in_runtime_worker_inventory():
    import sys
    from types import SimpleNamespace

    sys.path.insert(0, str(ROOT / "src"))
    from main import VoiceInputSystem

    system = object.__new__(VoiceInputSystem)
    system.punctuation_worker = SimpleNamespace(worker_pid=12345)
    assert system._worker_pids()["punctuation"] == 12345


def test_punctuation_worker_pid_requires_ready_and_live_process():
    import sys
    from types import SimpleNamespace

    sys.path.insert(0, str(ROOT / "src"))
    from punctuation_worker import SupervisedPunctuation

    worker = SupervisedPunctuation("unused")
    worker._process = SimpleNamespace(pid=12345, is_alive=lambda: True)
    assert worker.worker_pid is None
    worker._ready = True
    assert worker.worker_pid == 12345
    worker._process.is_alive = lambda: False
    assert worker.worker_pid is None
