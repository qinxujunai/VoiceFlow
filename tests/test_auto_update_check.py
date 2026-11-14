"""Automatic update check: setting, daily schedule, domestic mirror."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from update_checker import (  # noqa: E402
    DOWNLOAD_ROOT,
    MIRROR_MANIFEST,
    MIRROR_ROOT,
    RELEASES_API,
    check_latest_release,
)
from update_schedule import CHECK_INTERVAL_SECONDS, UpdateSchedule, auto_check_enabled  # noqa: E402


def _offline_github(url):
    if url == RELEASES_API:
        raise OSError("github unreachable")
    raise AssertionError(url)


def _mirror(payload):
    def fetch(url):
        if url == RELEASES_API:
            raise OSError("github unreachable")
        assert url == MIRROR_MANIFEST
        return payload
    return fetch


def test_mirror_is_used_when_github_cannot_be_reached():
    url = f"{MIRROR_ROOT}releases/v0.4.0/VoiceFlow-0.4.0-Windows-x64.exe"
    result = check_latest_release(
        "0.3.12", fetch_json=_mirror({"version": "0.4.0", "installer_url": url, "sha256": "b" * 64})
    )
    assert result.state == "available"
    assert result.latest_version == "0.4.0"
    assert result.installer_url == url


def test_mirror_may_point_at_the_github_release_file():
    url = f"{DOWNLOAD_ROOT}v0.4.0/VoiceFlow-0.4.0-Windows-x64.exe"
    result = check_latest_release(
        "0.3.12", fetch_json=_mirror({"version": "0.4.0", "installer_url": url, "sha256": "c" * 64})
    )
    assert result.state == "available"


def test_mirror_rejects_foreign_links_missing_digests_and_bad_versions():
    good = f"{MIRROR_ROOT}releases/v0.4.0/VoiceFlow-0.4.0-Windows-x64.exe"
    for payload in (
        {"version": "0.4.0", "installer_url": "https://evil.example/VoiceFlow.exe", "sha256": "b" * 64},
        {"version": "0.4.0", "installer_url": good, "sha256": "not-a-digest"},
        {"version": "latest", "installer_url": good, "sha256": "b" * 64},
        {"version": "0.4.1", "installer_url": good, "sha256": "b" * 64},  # link names another version
        ["not", "a", "dict"],
    ):
        assert check_latest_release("0.3.12", fetch_json=_mirror(payload)).state == "unavailable"


def test_mirror_same_version_is_up_to_date():
    url = f"{MIRROR_ROOT}releases/v0.3.12/VoiceFlow-0.3.12-Windows-x64.exe"
    result = check_latest_release(
        "0.3.12", fetch_json=_mirror({"version": "0.3.12", "installer_url": url, "sha256": "d" * 64})
    )
    assert result.state == "up_to_date"


def test_both_sources_down_is_quietly_unavailable():
    def fetch(url):
        raise OSError("offline")
    assert check_latest_release("0.3.12", fetch_json=fetch).state == "unavailable"


def test_schedule_checks_at_most_once_a_day(tmp_path):
    now = [1_000_000.0]
    schedule = UpdateSchedule(tmp_path, clock=lambda: now[0])
    assert schedule.due()
    schedule.record_check()
    assert not schedule.due()
    now[0] += CHECK_INTERVAL_SECONDS - 1
    assert not schedule.due()
    now[0] += 1
    assert schedule.due()


def test_a_clock_moved_backwards_does_not_stop_checks(tmp_path):
    now = [2_000_000.0]
    schedule = UpdateSchedule(tmp_path, clock=lambda: now[0])
    schedule.record_check()
    now[0] -= 3600
    assert schedule.due()


def test_each_version_is_announced_once_and_remembered_offline(tmp_path):
    schedule = UpdateSchedule(tmp_path)
    assert schedule.should_announce("0.4.0")
    schedule.record_announced("0.4.0")
    assert not schedule.should_announce("0.4.0")
    assert schedule.should_announce("0.4.1")
    schedule.record_available("0.4.0")
    assert schedule.available_version("0.3.12") == "0.4.0"
    assert schedule.available_version("0.4.0") == "", "installed already: no tray item"


def test_corrupt_state_counts_as_due(tmp_path):
    (tmp_path / "update-check.json").write_text("{not json", encoding="utf-8")
    assert UpdateSchedule(tmp_path).due()


def test_setting_defaults_on_and_can_be_turned_off(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("engine:\n  active: sensevoice\n", encoding="utf-8")
    assert auto_check_enabled(config), "older configs without the key check by default"
    config.write_text("updates:\n  auto_check: false\n", encoding="utf-8")
    assert not auto_check_enabled(config)
    assert auto_check_enabled(tmp_path / "missing.yaml")


def test_writer_keeps_comments_and_adds_the_section_to_old_configs(tmp_path):
    from settings_store import update_auto_update_check

    config = tmp_path / "config.yaml"
    config.write_text("engine:  # 识别\n  active: sensevoice\n", encoding="utf-8")
    update_auto_update_check(config, False)
    text = config.read_text(encoding="utf-8")
    assert yaml.safe_load(text)["updates"] == {"auto_check": False}
    assert "# 识别" in text
    update_auto_update_check(config, True)
    text = config.read_text(encoding="utf-8")
    assert yaml.safe_load(text)["updates"] == {"auto_check": True}
    assert text.count("auto_check") == 1


def test_shipped_config_turns_the_check_on():
    config = yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text(encoding="utf-8"))
    assert config["updates"]["auto_check"] is True


def test_tray_offers_the_new_version_and_notifies_once(tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qt_compat import QApplication, QMenu
    import overlay_webview

    app = QApplication.instance() or QApplication([])
    messages = []
    menu = QMenu()
    menu.addAction("开始 / 停止听写")
    window = SimpleNamespace(
        paths=SimpleNamespace(data_dir=tmp_path),
        _tray_menu=menu,
        _update_action=None,
        _tray=SimpleNamespace(showMessage=lambda title, body: messages.append((title, body))),
        _open_update_page=lambda *_args: None,
    )
    announce = overlay_webview.OverlayWindow._announce_update
    announce(window, {"latest_version": "0.4.0"})
    announce(window, {"latest_version": "0.4.0"})
    assert menu.actions()[0].text() == "下载新版本 0.4.0"
    assert [text for text in (a.text() for a in menu.actions()) if text.startswith("下载新版本")] == ["下载新版本 0.4.0"]
    assert messages == [("VoiceFlow 有新版本", "0.4.0 已发布，点这里下载。")]
    announce(window, {"latest_version": "0.4.1"})
    assert menu.actions()[0].text() == "下载新版本 0.4.1"
    assert len(messages) == 2
    del app


def test_automatic_check_skips_when_turned_off_or_not_due(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import overlay_webview

    started = []
    monkeypatch.setattr(overlay_webview.threading, "Thread",
                        lambda **kwargs: SimpleNamespace(start=lambda: started.append(kwargs["name"])))
    config = tmp_path / "config.yaml"
    config.write_text("updates:\n  auto_check: false\n", encoding="utf-8")
    window = SimpleNamespace(paths=SimpleNamespace(config_file=config, data_dir=tmp_path),
                             _update_check_running=False, _update_notifier=None)
    check = overlay_webview.OverlayWindow._maybe_check_for_update
    check(window)
    assert started == []
    config.write_text("updates:\n  auto_check: true\n", encoding="utf-8")
    check(window)
    assert started == ["voiceflow-auto-update-check"]
    window._update_check_running = False
    UpdateSchedule(tmp_path).record_check()
    check(window)
    assert started == ["voiceflow-auto-update-check"], "checked less than a day ago"
