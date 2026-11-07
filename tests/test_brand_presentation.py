from pathlib import Path
import json
import hashlib
import pytest
import re
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path):
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_readmes_lead_with_one_animated_demo():
    # Owner, 2026-11-03: the static brand card drew a second capsule above the real demo.
    for readme_name, demo in (("README.md", "docs/voiceflow-demo.svg"),
                              ("README.en.md", "docs/voiceflow-demo.en.svg")):
        readme = _read(readme_name)

        assert "/releases/latest" in readme
        assert "Ctrl+V" in readme
        assert demo in readme
        assert readme.count(".svg)") == 1
        assert "voiceflow-app-home" not in readme
        assert "docs/voiceflow-brand." not in readme
        assert '<h1 align="center">VoiceFlow</h1>' in readme
        assert "badge.svg" not in readme
        assert "img.shields.io" not in readme
        assert "docs/help." in readme
        assert "## 验证" not in readme
        assert "## Verify" not in readme


def test_product_site_preserves_the_demo_and_explains_sentence_endings():
    page = _read("site/index.html")

    assert 'class="live-demo"' in page
    assert 'id="demo-transcript"' in page
    assert "句末" in page
    assert "voiceflow-app-home" not in page
    assert "voiceflow-ambient" not in page
    assert "voiceflow-overlay" not in page

    forbidden_copy = (
        "23 ms",
        "455 ms",
        "500×",
        "不把“模型更多”",
        "Fun-ASR Nano",
        "Whisper",
        "macOS",
    )
    for phrase in forbidden_copy:
        assert phrase not in page

    assert page.count("data-download") == 1
    assert "SenseVoice" not in page
    assert "Qwen3" not in page
    assert "安装后即可离线听写" in page
    assert "__VOICEFLOW_VERSION__" in page
    assert "v0.2.2" not in page
    assert 'class="download"' not in page
    assert "尚未代码签名" not in page


def test_product_site_demo_matches_readme_demo():
    docs_demo = _read("docs/voiceflow-demo.svg")
    site_demo = _read("site/assets/voiceflow-demo.svg")

    assert site_demo == docs_demo
    assert _read("site/assets/voiceflow-demo.en.svg") == _read("docs/voiceflow-demo.en.svg")
    assert "prefers-reduced-motion: reduce" in site_demo
    assert 'rx="48" fill="#f5f5f7"' in site_demo
    assert 'id="softPanel"' not in site_demo
    assert 'id="finalText"' in site_demo
    assert ">已完成</text>" not in site_demo
    assert "deliveryDismissState" in site_demo


@pytest.mark.parametrize("name,caption", [("docs/voiceflow-demo.svg", "按住说话，松开就输入"),
                                          ("docs/voiceflow-demo.en.svg", "Hold to speak, release to insert")])
def test_svg_demo_shows_hold_to_talk_and_whole_words(name, caption):
    import re
    import xml.etree.ElementTree as ET
    svg = _read(name)

    assert caption in svg
    assert "按一下开始" not in svg and "Press once" not in svg
    # The key stays down while speaking and comes up on release.
    assert 'id="keycap"' in svg and "@keyframes keyHold" in svg
    # Words fade in whole, like the app (140 ms); a sliding clip cut glyphs in half (「同步纟」).
    assert "previewReveal" not in svg and "clip-path" not in svg
    root = ET.fromstring(svg)
    live = next(e for e in root.iter() if e.get("id") == "liveText")
    chunks = [e for e in live if e.tag.endswith("}tspan")]
    assert len(chunks) >= 5
    assert "".join(e.text for e in chunks) == next(e for e in root.iter() if e.get("id") == "finalText").text.replace(" ", "")
    for index, chunk in enumerate(chunks, 1):
        assert chunk.get("class") == f"c{index}"
        assert re.search(rf"\.c{index} \{{ animation: c{index} 6\.8s linear infinite; \}}", svg)
        assert f"@keyframes c{index} " in svg


def _keyframes(svg, name):
    """Return {offset percent: {property: value}} for one CSS @keyframes rule of an SVG demo."""
    start = svg.index(f"@keyframes {name} {{") + len(f"@keyframes {name} {{")
    depth, end = 1, start
    while depth:
        depth += {"{": 1, "}": -1}.get(svg[end], 0)
        end += 1
    frames = {}
    for offsets, declarations in re.findall(r"([\d.%,\s]+)\{([^}]*)\}", svg[start:end - 1]):
        props = dict(part.split(":", 1) for part in declarations.split(";") if ":" in part)
        for offset in offsets.split(","):
            frames.setdefault(float(offset.strip().rstrip("%")), {}).update(
                {key.strip(): value.strip() for key, value in props.items()})
    return frames


@pytest.mark.parametrize("name", ["docs/voiceflow-demo.svg", "docs/voiceflow-demo.en.svg"])
def test_svg_demo_capsule_exists_only_while_f2_is_down(name):
    # Owner, 2026-11-03: hold to talk. The capsule appears when the key goes down and is gone after the
    # silent finish; the loop must not show a recording capsule before the press or an empty one at the end.
    svg = _read(name)
    key_down = min(offset for offset, props in _keyframes(svg, "keyHold").items() if "2px" in props["transform"])
    opacity = {offset: float(props["opacity"])
               for offset, props in _keyframes(svg, "capsuleState").items() if "opacity" in props}

    assert opacity[0.0] == 0 and opacity[100.0] == 0
    assert all(value == 0 for offset, value in opacity.items() if offset < key_down)
    shown = [offset for offset, value in opacity.items() if value > 0]
    gone = min(offset for offset, value in opacity.items() if value == 0 and offset > max(shown) - 1)
    assert min(shown) >= key_down
    assert all(value == 0 for offset, value in opacity.items() if offset >= gone)


def test_svg_demo_text_is_outside_filter_groups():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(_read("docs/voiceflow-demo.svg"))
    def inspect(element, filtered=False):
        filtered = filtered or "filter" in element.attrib
        if element.tag.endswith("}text"):
            assert not filtered
        for child in element:
            inspect(child, filtered)
    inspect(root)


def test_bilingual_demo_uses_the_real_quiet_success_state():
    chinese_demo = _read("site/assets/voiceflow-demo.svg")
    english_demo = _read("site/assets/voiceflow-demo.en.svg")

    assert ">已完成</text>" not in chinese_demo
    assert ">Done</text>" not in english_demo
    assert "deliveryDismissState" in chinese_demo
    assert "deliveryDismissState" in english_demo
    assert "Copied" not in english_demo
    assert "· 21" not in english_demo


def test_public_demo_descriptions_and_metrics_are_not_stale():
    page = _read("site/index.html")
    copy = _read("site/app.js")

    assert "当前输入框听写" in page + copy
    assert "at the current cursor" in copy
    for phrase in ("发布门槛", "内部候选", "10,000", "metricScopeValue",
                   "release gate", "Internal candidates"):
        assert phrase not in page + copy


def test_public_copy_describes_user_actions_and_manual_paste():
    page = _read("site/index.html")
    copy = _read("site/app.js")

    assert "按住 F2" in page + copy
    assert "按 F2 开始" not in page + copy and "再按 F2" not in page + copy
    assert "Press once" not in copy and "Press F2 again" not in copy
    assert "本地历史" in page + copy
    assert "local history" in copy
    assert "未知输入框只复制" not in page + copy
    assert "focus remains in a verified editor" not in copy


def test_product_site_keeps_one_demo_and_describes_hold_to_talk():
    page = _read("site/index.html")
    copy = _read("site/app.js")
    css = _read("site/styles.css")

    # Owner, 2026-11-03: one coded demo only; the static capsule picture is gone.
    assert 'class="live-demo"' in page
    assert "capsule-art" not in page + css
    for key in ("capsuleText", "capsuleArtNote", "capsuleAria"):
        assert key not in page + copy
    assert "按住说话，松开成文。" in page and 'heroTitleSecond: "按住说话，松开成文。"' in copy
    assert 'heroTitleSecond: "Hold to speak. Let go to write."' in copy
    assert 'demoStart: "按住 F2 · 开始说话"' in copy and 'demoFinish: "松开 F2 · 完成识别"' in copy
    assert 'demoStart: "Hold F2 · Start speaking"' in copy and 'demoFinish: "Release F2 · Finish recognition"' in copy
    assert "按住 F2 → 说话 → 松开就输入" in page
    assert 'filmCaption: "Hold F2 → Speak → Release to insert"' in copy


def test_removed_composite_assets_stay_removed():
    removed_assets = (
        "site/assets/voiceflow-ambient-v2.png",
        "site/assets/voiceflow-app-home-v2.png",
        "site/assets/voiceflow-overlay.png",
    )

    for relative_path in removed_assets:
        assert not (PROJECT_ROOT / relative_path).exists()


def test_public_release_uploads_installer_and_verification_assets():
    workflow = _read(".github/workflows/release.yml")
    publish_command = workflow.split(
        "gh release create $env:GITHUB_REF_NAME", maxsplit=1
    )[1]

    assert "VoiceFlow-$version-Windows-x64.exe" in publish_command
    assert "SHA256SUMS.txt" in publish_command
    assert "SBOM.cdx.json" in publish_command
    assert "THIRD_PARTY_NOTICES.md" in publish_command


def test_readmes_use_latest_release_instead_of_a_versioned_asset():
    for readme_name in ("README.md", "README.en.md"):
        readme = _read(readme_name)

        assert "/releases/latest" in readme
        assert "/releases/download/v0.2.2/" not in readme
        assert "VoiceFlow-0.2.2-Windows-x64.exe" not in readme


def test_pages_workflow_renders_only_a_verified_published_release():
    workflow = _read(".github/workflows/pages.yml")

    assert "  push:" not in workflow
    assert "release:" in workflow
    assert "published" in workflow
    assert "edited" in workflow
    assert "workflow_run:" in workflow
    assert 'workflows: ["Release"]' in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "scripts/prepare_public_site.py" in workflow
    assert "VOICEFLOW_GITHUB_TOKEN" in workflow
    assert "path: ${{ runner.temp }}/voiceflow-site" in workflow
    assert "path: site" not in workflow


def test_existing_tag_update_does_not_restart_public_release_build():
    workflow = _read(".github/workflows/release.yml")

    assert "if: github.event.created == true" in workflow



def _set_site_fixture_digests(release, checksum_file, release_file):
    for asset in release["assets"]:
        asset["browser_download_url"] = (
            "https://github.com/qinxujunai/VoiceFlow/releases/download/"
            f"{release['tag_name']}/{asset['name']}"
        )
        if asset["name"] == "SHA256SUMS.txt":
            data = checksum_file.read_bytes()
            asset["size"] = len(data)
            asset["digest"] = f"sha256:{hashlib.sha256(data).hexdigest()}"
    release_file.write_text(json.dumps(release), encoding="utf-8")


def test_public_site_renderer_validates_digest_and_replaces_placeholders(tmp_path):
    installer_name = "VoiceFlow-0.3.0-Windows-x64.exe"
    digest = "a" * 64
    release = {
        "tag_name": "v0.3.0",
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": installer_name,
                "size": 123456,
                "digest": f"sha256:{digest}",
                "state": "uploaded",
                "browser_download_url": (
                    "https://github.com/qinxujunai/VoiceFlow/releases/download/"
                    f"v0.3.0/{installer_name}"
                ),
            },
            {
                "name": "SHA256SUMS.txt",
                "size": 128,
                "digest": f"sha256:{'b' * 64}",
                "state": "uploaded",
                "browser_download_url": "https://example.invalid/SHA256SUMS.txt",
            },
            {
                "name": "SBOM.cdx.json",
                "size": 256,
                "digest": f"sha256:{'c' * 64}",
                "state": "uploaded",
                "browser_download_url": "https://example.invalid/SBOM.cdx.json",
            },
            {
                "name": "THIRD_PARTY_NOTICES.md",
                "size": 256,
                "digest": f"sha256:{'d' * 64}",
                "state": "uploaded",
                "browser_download_url": "https://example.invalid/THIRD_PARTY_NOTICES.md",
            },
        ],
    }
    release_file = tmp_path / "release.json"
    release_file.write_text(json.dumps(release), encoding="utf-8")
    checksum_file = tmp_path / "SHA256SUMS.txt"
    checksum_file.write_text(f"{digest}  {installer_name}\n", encoding="utf-8")
    _set_site_fixture_digests(release, checksum_file, release_file)
    output_dir = tmp_path / "site"

    subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "prepare_public_site.py"),
            "--release-json",
            str(release_file),
            "--checksums-file",
            str(checksum_file),
            "--output-dir",
            str(output_dir),
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    page = (output_dir / "index.html").read_text(encoding="utf-8")
    copy = (output_dir / "app.js").read_text(encoding="utf-8")
    assert "__VOICEFLOW_VERSION__" not in page + copy
    assert "v0.3.0" in page + copy
    assert 'src="app.js?v=0.3.0&amp;site=20261103c"' in page or 'src="app.js?v=0.3.0&site=20261103c"' in page
    assert 'href="styles.css?v=20261103c"' in page
    assert release["assets"][0]["browser_download_url"] in page


def test_public_site_renderer_rejects_a_checksum_mismatch(tmp_path):
    installer_name = "VoiceFlow-0.3.0-Windows-x64.exe"
    release = {
        "tag_name": "v0.3.0",
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": installer_name,
                "size": 123456,
                "digest": f"sha256:{'a' * 64}",
                "state": "uploaded",
                "browser_download_url": "https://example.invalid/installer.exe",
            },
            {
                "name": "SHA256SUMS.txt",
                "size": 128,
                "digest": f"sha256:{'b' * 64}",
                "state": "uploaded",
                "browser_download_url": "https://example.invalid/SHA256SUMS.txt",
            },
            {
                "name": "SBOM.cdx.json",
                "size": 256,
                "digest": f"sha256:{'c' * 64}",
                "state": "uploaded",
                "browser_download_url": "https://example.invalid/SBOM.cdx.json",
            },
            {
                "name": "THIRD_PARTY_NOTICES.md",
                "size": 256,
                "digest": f"sha256:{'d' * 64}",
                "state": "uploaded",
                "browser_download_url": "https://example.invalid/THIRD_PARTY_NOTICES.md",
            },
        ],
    }
    release_file = tmp_path / "release.json"
    release_file.write_text(json.dumps(release), encoding="utf-8")
    checksum_file = tmp_path / "SHA256SUMS.txt"
    checksum_file.write_text(
        f"{'b' * 64}  {installer_name}\n",
        encoding="utf-8",
    )

    _set_site_fixture_digests(release, checksum_file, release_file)

    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "prepare_public_site.py"),
            "--release-json",
            str(release_file),
            "--checksums-file",
            str(checksum_file),
            "--output-dir",
            str(tmp_path / "site"),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "digest" in result.stderr.casefold()


def test_public_site_renderer_rejects_a_non_uploaded_compliance_asset(tmp_path):
    installer_name = "VoiceFlow-0.3.0-Windows-x64.exe"
    digest = "a" * 64
    assets = [
        {
            "name": installer_name,
            "size": 123456,
            "digest": f"sha256:{digest}",
            "state": "uploaded",
            "browser_download_url": "https://example.invalid/installer.exe",
        },
        {
            "name": "SHA256SUMS.txt",
            "size": 128,
            "digest": f"sha256:{'b' * 64}",
            "state": "uploaded",
            "browser_download_url": "https://example.invalid/SHA256SUMS.txt",
        },
        {
            "name": "SBOM.cdx.json",
            "size": 256,
            "digest": f"sha256:{'c' * 64}",
            "state": "new",
            "browser_download_url": "https://example.invalid/SBOM.cdx.json",
        },
        {
            "name": "THIRD_PARTY_NOTICES.md",
            "size": 256,
            "digest": f"sha256:{'d' * 64}",
            "state": "uploaded",
            "browser_download_url": "https://example.invalid/THIRD_PARTY_NOTICES.md",
        },
    ]
    release_file = tmp_path / "release.json"
    release_file.write_text(
        json.dumps(
            {
                "tag_name": "v0.3.0",
                "draft": False,
                "prerelease": False,
                "assets": assets,
            }
        ),
        encoding="utf-8",
    )
    checksum_file = tmp_path / "SHA256SUMS.txt"
    checksum_file.write_text(f"{digest}  {installer_name}\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "prepare_public_site.py"),
            "--release-json",
            str(release_file),
            "--checksums-file",
            str(checksum_file),
            "--output-dir",
            str(tmp_path / "site"),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "not uploaded" in result.stderr.casefold()


def test_visual_capture_fixtures_use_natural_speech_not_engineering_copy():
    capture = (PROJECT_ROOT / "scripts" / "capture_ui_states.py").read_text(
        encoding="utf-8"
    )

    assert "正在稳定追加完整转写" not in capture
    assert "明早十点，把方案同步给团队。" in capture


@pytest.mark.parametrize("change", ["url", "checksum_digest", "checksum_size"])
def test_public_site_rejects_asset_source_and_manifest_tampering(tmp_path, change):
    import importlib.util
    spec = importlib.util.spec_from_file_location("site_renderer", PROJECT_ROOT / "scripts/prepare_public_site.py")
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    installer = "VoiceFlow-0.3.5-Windows-x64.exe"
    checksum_file = tmp_path / "SHA256SUMS.txt"
    checksum_file.write_bytes(f"{'a' * 64}  {installer}\n".encode())
    release = {"tag_name": "v0.3.5", "assets": [
        {"name": name, "size": 123, "digest": "sha256:" + "a" * 64,
         "state": "uploaded"} for name in
        (installer, "SHA256SUMS.txt", "SBOM.cdx.json", "THIRD_PARTY_NOTICES.md")
    ]}
    _set_site_fixture_digests(release, checksum_file, tmp_path / "release.json")
    if change == "url":
        release["assets"][0]["browser_download_url"] = "https://example.invalid/wrong.exe"
    elif change == "checksum_digest":
        release["assets"][1]["digest"] = "sha256:" + "b" * 64
    else:
        release["assets"][1]["size"] += 1
    with pytest.raises(ValueError):
        renderer._validated_release(release, checksums_file=str(checksum_file), token="")
