"""Compile and exercise shared Inno guards in an isolated, registry-free fixture."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.compiler = args.compiler.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    work = args.output.parent / ("installer-safety-" + uuid.uuid4().hex)
    work.mkdir()
    install = work / "install"
    other = work / "other"
    other.mkdir()
    csharp = work / "Fixture.cs"
    csharp.write_text(
        'using System; using System.IO; using System.Threading; '
        'class Fixture { static void Main(string[] args) { '
        'while (!File.Exists(args[0])) Thread.Sleep(20); } }', encoding="utf-8")
    compiler = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
    payload = work / "VoiceFlow.exe"
    def run(command, timeout=30):
        return subprocess.run([str(value) for value in command], capture_output=True,
                              text=True, errors="replace", timeout=timeout,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    compiled = run([compiler, "/nologo", "/target:winexe", f"/out:{payload}", csharp])
    if compiled.returncode:
        raise RuntimeError(compiled.stdout + compiled.stderr)
    other_exe = other / "VoiceFlow.exe"
    other_exe.write_bytes(payload.read_bytes())
    guard = ROOT / "installer" / "runtime_guard.iss"
    product_source = (ROOT / "installer" / "VoiceFlow.iss").read_text(encoding="utf-8")
    mode_match = re.search(r"^UninstallLogMode=.+$", product_source, re.MULTILINE)
    uninstall_mode = mode_match.group(0) if mode_match else "UninstallLogMode=append"
    script = work / "Fixture.iss"
    script.write_text(f'''#define MyAppExeName "VoiceFlow.exe"
[Setup]
AppId=VoiceFlow.SafetyFixture.{uuid.uuid4().hex}
AppName=VoiceFlow Safety Fixture
AppVersion=1.0.0
DefaultDirName={install}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
CreateUninstallRegKey=no
CloseApplications=no
RestartApplications=no
{uninstall_mode}
OutputDir={work}
OutputBaseFilename=FixtureSetup
Compression=lzma2
[Files]
Source: "{payload}"; DestDir: "{{app}}"; Flags: ignoreversion
#include "{guard}"
''', encoding="utf-8-sig")
    compiled = run([args.compiler, script], timeout=60)
    (work / "compiler.log").write_text(compiled.stdout + compiled.stderr, encoding="utf-8")
    if compiled.returncode:
        raise RuntimeError(compiled.stdout + compiled.stderr)
    setup = work / "FixtureSetup.exe"
    legacy_script = work / "LegacyFixture.iss"
    legacy_marker = work / "legacy-uninstall-action.txt"
    legacy_source = script.read_text(encoding="utf-8-sig").replace(
        "OutputBaseFilename=FixtureSetup", "OutputBaseFilename=LegacyFixtureSetup"
    ).replace(uninstall_mode, "UninstallLogMode=append").replace(f'#include "{guard}"', f'''[UninstallRun]
Filename: "{{cmd}}"; Parameters: "/d /c echo legacy-action>{legacy_marker}"; Flags: runhidden; RunOnceId: "StopVoiceFlow"
[UninstallDelete]
Type: filesandordirs; Name: "{{app}}"
''')
    legacy_script.write_text(legacy_source, encoding="utf-8-sig")
    compiled = run([args.compiler, legacy_script], timeout=60)
    if compiled.returncode:
        raise RuntimeError(compiled.stdout + compiled.stderr)
    legacy_setup = work / "LegacyFixtureSetup.exe"
    results = []
    processes = []
    def invoke(executable, label, expected_success, target=None):
        command = [executable, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                   "/NOICONS", f"/LOG={work / (label + '.log')}"]
        if executable in (setup, legacy_setup):
            command.append(f"/DIR={target or install}")
        result = run(command)
        results.append({"case": label, "exit_code": result.returncode,
                        "expected_success": expected_success})
        assert (result.returncode == 0) == expected_success, results[-1]
    def start(executable, label):
        stop_file = work / (label + ".stop")
        process = subprocess.Popen([str(executable), str(stop_file)],
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        processes.append((process, stop_file))
        time.sleep(.2)
        assert process.poll() is None
        return process, stop_file
    try:
        invoke(setup, "fresh-install", True)
        uninstaller = install / "unins000.exe"
        own, own_stop = start(install / "VoiceFlow.exe", "own")
        unrelated, _ = start(other_exe, "other")
        sentinel = install / "user-notes.txt"
        sentinel.write_text("untracked user file", encoding="utf-8")
        before_hash = hashlib.sha256((install / "VoiceFlow.exe").read_bytes()).hexdigest()
        alias = work / "install-alias"
        linked = run(["cmd", "/d", "/c", "mklink", "/J", alias, install])
        assert linked.returncode == 0 and alias.resolve() == install.resolve()
        hardlink = work / "install-hardlink"
        hardlink.mkdir()
        os.link(install / "VoiceFlow.exe", hardlink / "VoiceFlow.exe")
        invoke(setup, "upgrade-running-own-instance", False)
        invoke(uninstaller, "uninstall-running-own-instance", False)
        invoke(setup, "upgrade-running-directory-alias", False, target=alias)
        invoke(setup, "upgrade-running-file-hardlink", False, target=hardlink)
        invoke(alias / "unins000.exe", "uninstall-running-directory-alias", False)
        assert own.poll() is None and unrelated.poll() is None
        assert hashlib.sha256((install / "VoiceFlow.exe").read_bytes()).hexdigest() == before_hash
        assert sentinel.read_text(encoding="utf-8") == "untracked user file"
        own_stop.touch()
        own.wait(timeout=5)
        invoke(setup, "upgrade-other-location-running", True)
        invoke(uninstaller, "uninstall-other-location-running", True)
        assert unrelated.poll() is None
        assert not (install / "VoiceFlow.exe").exists()
        assert sentinel.read_text(encoding="utf-8") == "untracked user file"
        invoke(legacy_setup, "legacy-install", True)
        invoke(setup, "upgrade-legacy-uninstall-log", True)
        invoke(uninstaller, "uninstall-after-legacy-upgrade", True)
        assert not legacy_marker.exists(), "legacy uninstall action survived upgrade"
        assert sentinel.read_text(encoding="utf-8") == "untracked user file"
        report = {"kind": "compiled_inno_shared_runtime_guard_fixture",
                  "compiler": str(args.compiler),
                  "compiler_sha256": hashlib.sha256(args.compiler.read_bytes()).hexdigest(),
                  "guard_sha256": hashlib.sha256(guard.read_bytes()).hexdigest(),
                  "fixture": str(work), "cases": results,
                  "scope": "Registry-free fixture, owned headless C# processes. Same shared installer guard; no product installer, microphone, real recording, clean-machine or graceful-close IPC acceptance."}
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        for process, stop_file in processes:
            stop_file.touch()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
