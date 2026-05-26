import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


class UiStateTests(unittest.TestCase):
    def test_ui_state_has_display_metadata(self):
        from ui_state import UiState, display_for_state

        listening = display_for_state(UiState.LISTENING)
        self.assertEqual(listening.label, "聆听中...")
        self.assertEqual(listening.tray_state, "recording")
        self.assertEqual(display_for_state(UiState.IDLE).tray_state, "idle")


class HistoryStoreTests(unittest.TestCase):
    def test_appends_jsonl_and_returns_last_entry(self):
        from history_store import HistoryStore

        with TemporaryDirectory() as tmp:
            store = HistoryStore(Path(tmp) / "history.jsonl")
            store.append(raw_text="科瑟", clean_text="Cursor", corrected_text="Cursor", output_status="pasted")

            last = store.last()
            self.assertEqual(last["raw_text"], "科瑟")
            self.assertEqual(last["clean_text"], "Cursor")
            self.assertEqual(last["corrected_text"], "Cursor")
            self.assertEqual(last["output_status"], "pasted")

            rows = (Path(tmp) / "history.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 1)
            self.assertEqual(json.loads(rows[0])["clean_text"], "Cursor")


class VocabularyTests(unittest.TestCase):
    def test_loads_terms_and_corrections_without_lowercase_overreach(self):
        from vocabulary import Vocabulary

        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            kb = base / "knowledge-base"
            kb.mkdir()
            (kb / "builtin-ai.txt").write_text("Cursor\nQwen\nvLLM\n", encoding="utf-8")
            (kb / "corrections.txt").write_text("科瑟=Cursor\n扣问=Qwen\n", encoding="utf-8")
            (kb / "user-dictionary.txt").write_text("奇点云\n", encoding="utf-8")
            (kb / "phrases.txt").write_text("本地语音输入\n", encoding="utf-8")

            vocab = Vocabulary(base, files=[
                "builtin-ai.txt",
                "corrections.txt",
                "user-dictionary.txt",
                "phrases.txt",
            ])

            self.assertIn("Cursor", vocab.terms)
            self.assertEqual(vocab.corrections["科瑟"], "Cursor")
            self.assertEqual(vocab.apply_corrections("我用科瑟和扣问"), "我用Cursor和Qwen")
            self.assertEqual(vocab.apply_corrections("cursor 应保持原样"), "cursor 应保持原样")


class AccuracyLoopTests(unittest.TestCase):
    def test_cleaner_applies_longer_corrections_first(self):
        from text_cleaner import TextCleaner

        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            kb = base / "knowledge-base"
            kb.mkdir()
            (kb / "corrections.txt").write_text(
                "扣问=Qwen\n大扣问=BigQwen\n",
                encoding="utf-8",
            )
            config = {
                "hotwords": {"files": ["corrections.txt"]},
                "cleaner": {
                    "remove_fillers": False,
                    "auto_space_en": False,
                    "fix_mistakes": True,
                    "basic_punctuation": False,
                },
            }

            cleaner = TextCleaner(config, base_dir=base)

            self.assertEqual(cleaner.clean("我在用大扣问"), "我在用BigQwen")

    def test_cleaner_reloads_corrections_without_restart(self):
        from text_cleaner import TextCleaner

        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            kb = base / "knowledge-base"
            kb.mkdir()
            corrections = kb / "corrections.txt"
            corrections.write_text("科瑟=Cursor\n", encoding="utf-8")
            config = {
                "hotwords": {"files": ["corrections.txt"]},
                "cleaner": {
                    "remove_fillers": False,
                    "auto_space_en": False,
                    "fix_mistakes": True,
                    "basic_punctuation": False,
                },
            }

            cleaner = TextCleaner(config, base_dir=base)
            self.assertEqual(cleaner.clean("科瑟"), "Cursor")

            corrections.write_text("科瑟=Cursor\n扣问=Qwen\n", encoding="utf-8")

            self.assertEqual(cleaner.clean("扣问"), "Qwen")

    def test_add_correction_cli_updates_existing_pair(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            kb = base / "knowledge-base"
            kb.mkdir()
            corrections = kb / "corrections.txt"
            corrections.write_text("科瑟=Cursor\n扣问=旧值\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "add_correction.py"),
                    "扣问",
                    "Qwen",
                    "--base-dir",
                    str(base),
                ],
                text=True,
                capture_output=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                corrections.read_text(encoding="utf-8").splitlines(),
                ["科瑟=Cursor", "扣问=Qwen"],
            )


class RecordingSessionTests(unittest.TestCase):
    def test_session_tracks_lifecycle_and_duration(self):
        from recording_session import RecordingSession

        events = []

        class FakeAudio:
            sample_rate = 16000
            is_recording = False

            def start_recording(self):
                self.is_recording = True
                events.append("start")

            def stop_recording(self):
                self.is_recording = False
                events.append("stop")
                return [1, 2, 3]

            def cancel_recording(self):
                self.is_recording = False
                events.append("cancel")

        session = RecordingSession(FakeAudio(), clock=lambda: 10.0)
        session.start()
        self.assertTrue(session.is_active)

        session.clock = lambda: 12.5
        result = session.stop()
        self.assertFalse(session.is_active)
        self.assertEqual(result.audio_data, [1, 2, 3])
        self.assertEqual(result.duration, 2.5)
        self.assertEqual(events, ["start", "stop"])


class FinalTextSelectionTests(unittest.TestCase):
    def test_prefers_streaming_preview_for_instant_stop(self):
        from main import VoiceInputSystem

        class Cleaner:
            def clean(self, text):
                return text.strip()

        system = object.__new__(VoiceInputSystem)
        system._latest_text = "  这是流式结果  "
        system.cleaner = Cleaner()

        raw, clean, cached = VoiceInputSystem._final_text_from_cache(system)
        self.assertEqual(raw, "这是流式结果")
        self.assertEqual(clean, "这是流式结果")
        self.assertTrue(cached)

    def test_ignores_empty_streaming_preview(self):
        from main import VoiceInputSystem

        system = object.__new__(VoiceInputSystem)
        system._latest_text = " "
        raw, clean, cached = VoiceInputSystem._final_text_from_cache(system)
        self.assertEqual(raw, "")
        self.assertEqual(clean, "")
        self.assertFalse(cached)

    def test_stop_streaming_invalidates_generation_before_short_join(self):
        main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
        stop_idx = main.index("def _stop_streaming")
        stop_block = main[stop_idx:main.index("def _final_text_from_cache", stop_idx)]

        self.assertIn("self._stream_generation += 1", stop_block)
        self.assertIn("self._stream_thread.join(timeout=0.2)", stop_block)
        self.assertLess(
            stop_block.index("self._stream_generation += 1"),
            stop_block.index("self._stream_thread.join(timeout=0.2)"),
        )

    def test_main_uses_clean_text_as_output_text(self):
        main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")

        self.assertIn("output_status = self.output_handler.output(text)", main)
        self.assertIn("corrected_text=text", main)
        self.assertNotIn("_correct_final_text", main)


if __name__ == "__main__":
    unittest.main()
