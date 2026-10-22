import json
import sys
from pathlib import Path

import pytest

# Exercises Win32 APIs, struct layouts or Windows release artifacts; covered by Windows quality.
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only contract")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.mark.parametrize("text", ["你好。", "Hello.", "你好？", "Hello!", "等等……",
                                 "内部，标点；原样。", '他说：“你好。”', "  你好。\n"])
def test_preserve_is_exact(text):
    from punctuation import apply_sentence_end

    assert apply_sentence_end(text, "preserve") == text


@pytest.mark.parametrize("source,expected", [("你好。", "你好"), ("Hello.", "Hello"),
                                             ("你好。 \n", "你好 \n"), ("无句号", "无句号")])
def test_omit_removes_only_one_final_period(source, expected):
    from punctuation import apply_sentence_end

    assert apply_sentence_end(source, "omit_period") == expected


@pytest.mark.parametrize("text", ["真的吗？", "Really?", "太好了！", "Yes!", "等等……",
                                 "Wait...", "等等。。。", '他说：“好。”', 'He said "Hello."',
                                 "https://example.com/path.", "C:\\Temp\\file.txt.",
                                 "README.md.", "v0.3.6.", "Dr.", "U.S.", "x = 1."])
@pytest.mark.parametrize("mode", ["omit_period", "complete_period"])
def test_protected_endings_and_technical_strings_are_unchanged(text, mode):
    from punctuation import apply_sentence_end

    assert apply_sentence_end(text, mode) == text


@pytest.mark.parametrize("source,expected", [("你好", "你好。"), ("Hello world", "Hello world."),
                                             ("你好 😊", "你好 😊。"), ("Hello\n", "Hello.\n"),
                                             ("123", "123"), ("你好，", "你好，")])
def test_complete_only_adds_a_natural_sentence_end(source, expected):
    from punctuation import apply_sentence_end

    assert apply_sentence_end(source, "complete_period") == expected


def test_format_mode_preserves_spaces_newlines_emoji_and_existing_punctuation():
    from punctuation import apply_sentence_end, FinalPunctuationRestorer
    from safe_text import SafeTextBoundary
    from text_cleaner import TextCleaner

    text = "  api = 1\r\n\t中文 👩‍💻。。。\n"
    safe = SafeTextBoundary().sanitize(text, preserve_format=True)
    assert safe.text == text
    assert TextCleaner({}).clean(text, preserve_format=True) == text
    assert FinalPunctuationRestorer().restore(text, preserve_format=True) == text
    assert apply_sentence_end(text, "complete_period", preserve_format=True) == text


def test_output_handler_never_changes_authoritative_final_or_format():
    from output_handler import OutputHandler

    handler = object.__new__(OutputHandler)
    handler.auto_period = True
    text = "  api = 1\r\n\t中文 👩‍💻。\n"
    assert handler._prepare_text(text) == text


@pytest.mark.parametrize("legacy,expected", [(True, "complete_period"), (False, "preserve")])
def test_preferences_migrate_legacy_intent_once_and_do_not_modify_config(tmp_path, legacy, expected):
    from dictation_preferences import DictationPreferencesStore

    path = tmp_path / "dictation-preferences.json"
    store = DictationPreferencesStore(path, legacy_output={"auto_period": legacy})
    assert store.options_for("notepad.exe").sentence_end == expected
    store.update(sentence_end="omit_period", preserve_format=False)
    restarted = DictationPreferencesStore(path, legacy_output={"auto_period": True})
    assert restarted.options_for("notepad.exe").sentence_end == "omit_period"
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_preferences_apply_only_explicit_executable_scope(tmp_path):
    from dictation_preferences import DictationPreferencesStore

    store = DictationPreferencesStore(tmp_path / "dictation-preferences.json")
    store.update(sentence_end="omit_period", preserve_format=False, app_id="MSedge.exe")
    assert store.options_for("msedge.EXE").sentence_end == "omit_period"
    assert store.options_for("chrome.exe").sentence_end == "preserve"
    assert store.options_for("").sentence_end == "preserve"
    assert store.options_for("Code.exe").preserve_format
    assert store.options_for("WindowsTerminal.exe").preserve_format
    store.update(sentence_end="complete_period", preserve_format=True, app_id="code.exe")
    assert store.options_for("Code.exe").preserve_format
    with pytest.raises(ValueError):
        store.update(sentence_end="invalid", preserve_format=False)
    with pytest.raises(ValueError):
        store.update(sentence_end="preserve", preserve_format=False, app_id="../code.exe")


@windows_only
def test_windows_application_scope_reads_only_current_executable_basename():
    import os
    from delivery import _process_executable_name

    assert _process_executable_name(os.getpid()) == Path(sys.executable).name.casefold()
    assert _process_executable_name(0) == ""


def test_application_override_can_follow_current_and_future_defaults(tmp_path):
    from dictation_preferences import DictationPreferencesStore

    store = DictationPreferencesStore(tmp_path / "preferences.json")
    store.update(sentence_end="omit_period", preserve_format=False, app_id="msedge.exe")
    store.update(app_id="msedge.exe", follow_default=True)
    assert "msedge.exe" not in store.snapshot()["apps"]
    store.update(sentence_end="complete_period", preserve_format=False)
    assert store.options_for("msedge.exe").sentence_end == "complete_period"
    assert DictationPreferencesStore(store.path).options_for("msedge.exe").sentence_end == "complete_period"
    with pytest.raises(ValueError):
        store.update(follow_default=True)


def test_stale_preferences_cannot_overwrite_a_newer_tray_change(tmp_path):
    from dictation_preferences import DictationPreferencesStore, PreferencesChangedError

    store = DictationPreferencesStore(tmp_path / "preferences.json")
    viewed = store.snapshot()["global"]
    store.update(sentence_end="complete_period", preserve_format=False)
    with pytest.raises(PreferencesChangedError):
        store.update(sentence_end="preserve", preserve_format=True, expected=viewed)
    assert store.options_for("notepad.exe").sentence_end == "complete_period"
    assert not store.options_for("notepad.exe").preserve_format


def test_failed_follow_default_preserves_application_override(tmp_path, monkeypatch):
    from dictation_preferences import DictationPreferencesStore

    store = DictationPreferencesStore(tmp_path / "preferences.json")
    store.update(sentence_end="omit_period", preserve_format=False, app_id="msedge.exe")
    before = store.path.read_bytes()
    monkeypatch.setattr(store, "_write", lambda *_: (_ for _ in ()).throw(OSError("fixture disk failure")))
    with pytest.raises(OSError):
        store.update(app_id="msedge.exe", follow_default=True)
    assert store.options_for("msedge.exe").sentence_end == "omit_period"
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("text", ["等等。。。", "等等……", "请打开 https://example.com/api.",
                                 "C:\\Temp\\api.json", "这个 API 叫 js.ts。"])
def test_final_pipeline_protects_technical_spans_and_ellipsis_before_policy(text):
    from main import VoiceInputSystem
    from dictation_preferences import DictationOptions
    from punctuation import FinalPunctuationRestorer
    from safe_text import SafeTextBoundary
    from text_cleaner import TextCleaner

    system = object.__new__(VoiceInputSystem)
    system._safe_text = SafeTextBoundary()
    system.cleaner = TextCleaner({})
    system.punctuation = FinalPunctuationRestorer()
    final, _safe = system._prepare_final_text(text, DictationOptions("omit_period"))
    assert final == text
