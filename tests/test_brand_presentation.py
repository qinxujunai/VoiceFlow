from pathlib import Path
import json
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path):
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_readmes_lead_with_real_demo_and_two_badges():
    for readme_name in ("README.md", "README.en.md"):
        readme = _read(readme_name)

        assert "docs/voiceflow-demo.svg" in readme
        assert "voiceflow-app-home" not in readme
        assert readme.count("badge.svg") == 1
        assert readme.count("img.shields.io") == 1


def test_product_site_uses_only_the_real_demo():
    page = _read("site/index.html")

    assert "assets/voiceflow-demo.svg" in page
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
    assert "无需下载或切换模型" in page
    assert "本版本" in page
    assert "__VOICEFLOW_VERSION__" in page
    assert "v0.2.2" not in page
    assert 'class="download"' not in page
    assert "尚未代码签名" not in page


def test_product_site_demo_matches_readme_demo():
    docs_demo = _read("docs/voiceflow-demo.svg")
    site_demo = _read("site/assets/voiceflow-demo.svg")

    assert site_demo == docs_demo
    assert "prefers-reduced-motion: reduce" in site_demo
    assert 'rx="48" fill="#f5f5f7"' in site_demo
    assert 'id="softPanel"' not in site_demo
    assert 'id="finalText"' in site_demo
    assert ">已完成</text>" in site_demo


def test_bilingual_demo_uses_the_real_short_completion_state():
    chinese_demo = _read("site/assets/voiceflow-demo.svg")
    english_demo = _read("site/assets/voiceflow-demo.en.svg")

    assert ">已完成</text>" in chinese_demo
    assert ">Done</text>" in english_demo
    assert "Copied" not in english_demo
    assert "· 21" not in english_demo


def test_public_copy_matches_stop_time_foreground_delivery_policy():
    page = _read("site/index.html")
    copy = _read("site/app.js")

    assert "停止时仍在普通应用，就发送一次粘贴" in page
    assert "停止时仍在普通应用，就发送一次粘贴" in copy
    assert "At stop time, VoiceFlow sends one paste" in copy
    assert "未知输入框只复制" not in page + copy
    assert "focus remains in a verified editor" not in copy


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
    assert "scripts/prepare_public_site.py" in workflow
    assert "VOICEFLOW_GITHUB_TOKEN" in workflow
    assert "path: ${{ runner.temp }}/voiceflow-site" in workflow
    assert "path: site" not in workflow


def test_existing_tag_update_does_not_restart_public_release_build():
    workflow = _read(".github/workflows/release.yml")

    assert "if: github.event.created == true" in workflow


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
