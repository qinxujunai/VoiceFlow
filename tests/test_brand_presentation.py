from pathlib import Path


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
    assert "SenseVoice" in page
    assert "Qwen3" not in page
    assert "无需下载或切换模型" in page
    assert "开发预览" in page
    assert "不属于当前下载的 v0.2.2 安装包" in page
    assert 'class="download"' not in page
    assert "尚未代码签名" not in page


def test_product_site_demo_matches_readme_demo():
    docs_demo = _read("docs/voiceflow-demo.svg")
    site_demo = _read("site/assets/voiceflow-demo.svg")

    assert site_demo == docs_demo
    assert "prefers-reduced-motion: reduce" in site_demo
    assert 'rx="48" fill="#f5f5f7"' in site_demo
    assert 'id="softPanel"' not in site_demo


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
