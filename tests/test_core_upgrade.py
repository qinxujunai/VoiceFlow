import json
import numpy as np
import subprocess
import sys
import threading
import time
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
            store.append(
                raw_text="科瑟",
                clean_text="Cursor",
                corrected_text="Cursor",
                output_status="clipboard_copied_paste_sent",
                trigger_to_feedback_ms=42.5,
                stop_to_paste_ms=620.0,
                transcription_ms=410.0,
            )

            last = store.last()
            self.assertEqual(last["raw_text"], "科瑟")
            self.assertEqual(last["clean_text"], "Cursor")
            self.assertEqual(last["corrected_text"], "Cursor")
            self.assertEqual(last["output_status"], "clipboard_copied_paste_sent")
            self.assertEqual(last["trigger_to_feedback_ms"], 42.5)
            self.assertEqual(last["stop_to_paste_ms"], 620.0)
            self.assertEqual(last["transcription_ms"], 410.0)

            rows = (Path(tmp) / "history.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 1)
            self.assertEqual(json.loads(rows[0])["clean_text"], "Cursor")


class OutputHandlerContractTests(unittest.TestCase):
    def test_clipboard_status_is_truthful_about_paste_uncertainty(self):
        output_handler = (ROOT / "src" / "output_handler.py").read_text(encoding="utf-8")

        self.assertIn("clipboard_copied_paste_sent", output_handler)
        self.assertNotIn('return "pasted"', output_handler)


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
    def test_cleaner_preserves_non_empty_single_character_commands(self):
        from text_cleaner import TextCleaner

        config = {
            "cleaner": {
                "remove_fillers": False,
                "auto_space_en": False,
                "fix_mistakes": False,
                "basic_punctuation": False,
            },
        }

        cleaner = TextCleaner(config)

        self.assertEqual(cleaner.clean("开"), "开")
        self.assertEqual(cleaner.clean("1"), "1")

    def test_punctuation_only_is_not_meaningful_recognized_text(self):
        from audio_activity import has_lexical_content

        self.assertFalse(has_lexical_content("。"))
        self.assertFalse(has_lexical_content(" ...，！？ "))
        self.assertTrue(has_lexical_content("我。"))
        self.assertTrue(has_lexical_content("1。"))

    def test_single_character_correction_does_not_rewrite_inside_a_word(self):
        from text_cleaner import TextCleaner

        config = {
            "cleaner": {
                "remove_fillers": False,
                "auto_space_en": False,
                "fix_mistakes": True,
                "basic_punctuation": False,
            },
        }

        cleaner = TextCleaner(config)
        cleaner.corrections = {"软": "RAG"}

        self.assertEqual(cleaner.clean("软件升级"), "软件升级")
        self.assertEqual(cleaner.clean("软"), "RAG")

    def test_ascii_correction_respects_token_boundaries(self):
        from text_cleaner import TextCleaner

        config = {
            "cleaner": {
                "remove_fillers": False,
                "auto_space_en": False,
                "fix_mistakes": True,
                "basic_punctuation": False,
            },
        }

        cleaner = TextCleaner(config)
        cleaner.corrections = {"api": "API"}

        self.assertEqual(cleaner.clean("rapid api client"), "rapid API client")

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
        self.assertEqual(result.start_sample, 0)
        self.assertEqual(result.total_samples, 3)
        self.assertEqual(events, ["start", "stop"])


class HotkeyStateOwnershipTests(unittest.TestCase):
    def test_hotkey_emits_toggle_event_without_owning_recording_state(self):
        from hotkey_manager import HotkeyManager

        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text(
                "hotkeys:\n  push_to_talk: [f2]\n  cancel: escape\n",
                encoding="utf-8",
            )
            toggles = []
            manager = HotkeyManager(
                config_path=config_path,
                callbacks={"on_record_toggle": lambda event_time: toggles.append(event_time)},
            )

            manager._trigger_ptt()
            time.sleep(0.05)

            self.assertEqual(len(toggles), 1)
            self.assertIsInstance(toggles[0], float)
            self.assertNotIn("_recording", vars(manager))

    def test_cancel_is_forwarded_even_when_hotkey_layer_has_no_state(self):
        from hotkey_manager import HotkeyManager

        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text(
                "hotkeys:\n  push_to_talk: [f2]\n  cancel: escape\n",
                encoding="utf-8",
            )
            cancels = []
            manager = HotkeyManager(
                config_path=config_path,
                callbacks={"on_record_cancel": lambda: cancels.append("cancel")},
            )

            manager._on_cancel()
            time.sleep(0.05)

            self.assertEqual(cancels, ["cancel"])


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

    def test_stop_streaming_invalidates_generation_before_complete_join(self):
        main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
        stop_idx = main.index("def _stop_streaming")
        stop_block = main[stop_idx:main.index("def _final_text_from_cache", stop_idx)]

        self.assertIn("self._stream_generation += 1", stop_block)
        self.assertIn("self._stream_thread.join()", stop_block)
        self.assertNotIn("join(timeout=", stop_block)
        self.assertLess(
            stop_block.index("self._stream_generation += 1"),
            stop_block.index("self._stream_thread.join()"),
        )

    def test_normalized_overlap_merge_keeps_punctuation_and_tail(self):
        from main import VoiceInputSystem

        system = object.__new__(VoiceInputSystem)

        merged = VoiceInputSystem._merge_transcript_pair(
            system,
            "今天发布 VoiceFlow，尾部完整",
            "voiceflow 尾部完整。继续测试",
        )

        self.assertEqual(merged, "今天发布 VoiceFlow，尾部完整。继续测试")

    def test_one_character_overlap_is_not_deleted(self):
        from main import VoiceInputSystem

        system = object.__new__(VoiceInputSystem)

        merged = VoiceInputSystem._merge_transcript_pair(system, "我要开", "开始录音")

        self.assertEqual(merged, "我要开 开始录音")

    def test_main_uses_clean_text_as_output_text(self):
        main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")

        self.assertIn("output_status = self.output_handler.output(text)", main)
        self.assertIn("corrected_text=text", main)
        self.assertNotIn("_correct_final_text", main)

    def test_stream_preview_cadence_stays_responsive(self):
        from main import VoiceInputSystem

        self.assertEqual(VoiceInputSystem.STREAM_PREVIEW_INTERVAL_SECONDS, 0.8)

    def test_preview_result_older_than_two_seconds_is_dropped(self):
        from main import VoiceInputSystem

        class FakeAudio:
            sample_rate = 16000
            sample_count = sample_rate * 600

        system = object.__new__(VoiceInputSystem)
        system.audio = FakeAudio()

        self.assertTrue(VoiceInputSystem._preview_result_is_fresh(
            system,
            FakeAudio.sample_count - FakeAudio.sample_rate,
        ))
        self.assertFalse(VoiceInputSystem._preview_result_is_fresh(
            system,
            FakeAudio.sample_count - FakeAudio.sample_rate * 3,
        ))

    def test_streaming_preview_transcribes_recent_window_not_full_chunk_while_speaking(self):
        main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
        stream_idx = main.index("def _start_streaming")
        stop_idx = main.index("def _stop_streaming", stream_idx)
        stream_block = main[stream_idx:stop_idx]

        self.assertIn("self._audio_snapshot(", stream_block)
        self.assertIn("self._stream_preview_snapshot(", stream_block)
        self.assertIn("self._preview_result_is_fresh(captured_samples)", stream_block)
        self.assertNotIn("np.concatenate(buf", stream_block)

    def test_preview_window_is_duration_independent_after_a_full_day(self):
        from main import VoiceInputSystem

        class FakeAudio:
            sample_rate = 16000
            buffer_start_sample = sample_rate * (24 * 60 * 60 - 20)

        system = object.__new__(VoiceInputSystem)
        system.audio = FakeAudio()
        total = FakeAudio.sample_rate * 24 * 60 * 60
        finalized = total - FakeAudio.sample_rate * 2

        start, end = VoiceInputSystem._stream_preview_range(system, total, finalized)

        self.assertEqual(end, total)
        self.assertLessEqual(end - start, FakeAudio.sample_rate * 20)

    def test_pause_refresh_uses_complete_preview_before_stop(self):
        main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
        stream_idx = main.index("def _start_streaming")
        stop_idx = main.index("def _stop_streaming", stream_idx)
        stream_block = main[stream_idx:stop_idx]

        self.assertIn("A pause is a correction point", stream_block)
        self.assertIn("prefer_complete=True", stream_block)
        self.assertLess(
            stream_block.index("prefer_complete=True"),
            stream_block.index("last_sample_count = total_samples"),
        )

    def test_transcribe_audio_serializes_recognizer_access(self):
        from main import VoiceInputSystem

        class FakeAudio:
            sample_rate = 16000

        class FakeTranscriber:
            def __init__(self):
                self.active = 0
                self.max_active = 0
                self.lock = threading.Lock()

            def transcribe(self, audio, sample_rate):
                with self.lock:
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                time.sleep(0.02)
                with self.lock:
                    self.active -= 1
                return "文本"

        system = object.__new__(VoiceInputSystem)
        system.audio = FakeAudio()
        system.transcriber = FakeTranscriber()
        system._transcribe_lock = threading.Lock()

        threads = [
            threading.Thread(target=VoiceInputSystem._transcribe_audio, args=(system, [1, 2, 3]))
            for _ in range(3)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(system.transcriber.max_active, 1)

    def test_silence_never_reaches_the_recognizer(self):
        from main import VoiceInputSystem

        class FakeAudio:
            sample_rate = 16000

        class HallucinatingTranscriber:
            def __init__(self):
                self.calls = 0

            def transcribe(self, audio, sample_rate):
                self.calls += 1
                return "我。"

        system = object.__new__(VoiceInputSystem)
        system.audio = FakeAudio()
        system.transcriber = HallucinatingTranscriber()
        system._transcribe_lock = None
        system._speech_gate_enabled = True
        system._speech_rms_threshold = 0.02
        system._speech_min_active_ms = 90
        silence = np.zeros(FakeAudio.sample_rate * 2, dtype=np.int16)

        text = VoiceInputSystem._transcribe_audio(system, silence)

        self.assertEqual(text, "")
        self.assertEqual(system.transcriber.calls, 0)

    def test_short_single_word_energy_still_reaches_the_recognizer(self):
        from main import VoiceInputSystem

        class FakeAudio:
            sample_rate = 16000

        class SingleWordTranscriber:
            def __init__(self):
                self.calls = 0

            def transcribe(self, audio, sample_rate):
                self.calls += 1
                return "我。"

        system = object.__new__(VoiceInputSystem)
        system.audio = FakeAudio()
        system.transcriber = SingleWordTranscriber()
        system._transcribe_lock = None
        system._speech_gate_enabled = True
        system._speech_rms_threshold = 0.02
        system._speech_min_active_ms = 90
        t = np.arange(int(FakeAudio.sample_rate * 0.24)) / FakeAudio.sample_rate
        word = (np.sin(2 * np.pi * 220 * t) * 0.08 * 32767).astype(np.int16)
        audio = np.concatenate([
            np.zeros(1600, dtype=np.int16),
            word,
            np.zeros(1600, dtype=np.int16),
        ])

        text = VoiceInputSystem._transcribe_audio(system, audio)

        self.assertEqual(text, "我。")
        self.assertEqual(system.transcriber.calls, 1)

    def test_stop_final_still_transcribes_complete_audio(self):
        main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
        stop_idx = main.index("def _on_record_stop")
        stream_idx = main.index("def _start_streaming", stop_idx)
        stop_block = main[stop_idx:stream_idx]

        self.assertIn("raw_text = self._transcribe_final_text(", stop_block)
        self.assertIn("buffer_start_sample=result.start_sample", stop_block)
        self.assertIn("total_samples=total_samples", stop_block)
        self.assertIn("self.overlay.show_final_text(text, final_generation)", stop_block)

    def test_next_final_segment_keeps_recent_tail_unfinalized(self):
        from main import VoiceInputSystem

        class FakeAudio:
            sample_rate = 16000

        system = object.__new__(VoiceInputSystem)
        system.audio = FakeAudio()
        audio = np.arange(FakeAudio.sample_rate * 25, dtype=np.int16)

        segment, end = VoiceInputSystem._next_final_segment(system, audio, 0)

        self.assertEqual(len(segment), FakeAudio.sample_rate * 18)
        self.assertEqual(end, FakeAudio.sample_rate * 18)

    def test_next_final_segment_waits_for_enough_stable_audio(self):
        from main import VoiceInputSystem

        class FakeAudio:
            sample_rate = 16000

        system = object.__new__(VoiceInputSystem)
        system.audio = FakeAudio()
        audio = np.arange(FakeAudio.sample_rate * 18, dtype=np.int16)

        segment, end = VoiceInputSystem._next_final_segment(system, audio, 0)

        self.assertIsNone(segment)
        self.assertEqual(end, 0)

    def test_long_final_uses_cached_segments_and_only_transcribes_tail(self):
        from main import VoiceInputSystem

        class FakeAudio:
            sample_rate = 16000

        class FakeTranscriber:
            def __init__(self):
                self.lengths = []

            def transcribe(self, audio, sample_rate):
                self.lengths.append(len(audio))
                return "尾巴"

        system = object.__new__(VoiceInputSystem)
        system.audio = FakeAudio()
        system.transcriber = FakeTranscriber()
        system._final_segments = ["前半段"]
        system._finalized_audio_len = FakeAudio.sample_rate * 40
        system._final_cache_lock = None
        data = np.arange(FakeAudio.sample_rate * 60, dtype=np.int16)

        text = VoiceInputSystem._transcribe_final_text(system, data)

        self.assertEqual(text, "前半段 尾巴")
        self.assertEqual(system.transcriber.lengths, [FakeAudio.sample_rate * 21])

    def test_ten_minute_final_keeps_cached_body_and_transcribes_remaining_tail(self):
        from main import VoiceInputSystem

        class FakeAudio:
            sample_rate = 16000

        class FakeAudioData:
            def __init__(self, length):
                self.length = length

            def __len__(self):
                return self.length

            def __getitem__(self, item):
                if isinstance(item, slice):
                    start = item.start or 0
                    stop = self.length if item.stop is None else item.stop
                    return FakeAudioData(max(0, stop - start))
                raise TypeError(item)

        class FakeTranscriber:
            def __init__(self):
                self.lengths = []

            def transcribe(self, audio, sample_rate):
                self.lengths.append(len(audio))
                return "最后一分钟"

        system = object.__new__(VoiceInputSystem)
        system.audio = FakeAudio()
        system.transcriber = FakeTranscriber()
        system._transcribe_lock = None
        system._final_segments = ["前九分钟"]
        system._finalized_audio_len = FakeAudio.sample_rate * 540
        system._final_cache_lock = None
        data = FakeAudioData(FakeAudio.sample_rate * 600)

        text = VoiceInputSystem._transcribe_final_text(system, data)

        self.assertEqual(text, "前九分钟 最后一分钟")
        self.assertEqual(system.transcriber.lengths, [FakeAudio.sample_rate * 61])

    def test_final_text_uses_global_offsets_after_pcm_prefix_is_discarded(self):
        from main import VoiceInputSystem

        class FakeAudio:
            sample_rate = 16000

        class FakeTranscriber:
            def __init__(self):
                self.lengths = []

            def transcribe(self, audio, sample_rate):
                self.lengths.append(len(audio))
                return "尾巴"

        system = object.__new__(VoiceInputSystem)
        system.audio = FakeAudio()
        system.transcriber = FakeTranscriber()
        system._transcribe_lock = None
        system._final_segments = ["前半段"]
        system._finalized_audio_len = FakeAudio.sample_rate * 40
        system._final_cache_lock = None
        retained_start = FakeAudio.sample_rate * 39
        total = FakeAudio.sample_rate * 60
        retained = np.arange(total - retained_start, dtype=np.int16)

        text = VoiceInputSystem._transcribe_final_text(
            system,
            retained,
            buffer_start_sample=retained_start,
            total_samples=total,
        )

        self.assertEqual(text, "前半段 尾巴")
        self.assertEqual(system.transcriber.lengths, [FakeAudio.sample_rate * 21])

    def test_short_final_still_transcribes_complete_audio_once(self):
        from main import VoiceInputSystem

        class FakeAudio:
            sample_rate = 16000

        class FakeTranscriber:
            def __init__(self):
                self.lengths = []

            def transcribe(self, audio, sample_rate):
                self.lengths.append(len(audio))
                return "完整结果"

        system = object.__new__(VoiceInputSystem)
        system.audio = FakeAudio()
        system.transcriber = FakeTranscriber()
        system._final_segments = []
        system._finalized_audio_len = 0
        system._final_cache_lock = None
        data = np.arange(FakeAudio.sample_rate * 20, dtype=np.int16)

        text = VoiceInputSystem._transcribe_final_text(system, data)

        self.assertEqual(text, "完整结果")
        self.assertEqual(system.transcriber.lengths, [FakeAudio.sample_rate * 20])


if __name__ == "__main__":
    unittest.main()
