"""Typed state shared by the dictation pipeline and compact capsule."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptViewState:
    session_id: int
    authoritative_prefix: str = ""
    draft_tail: str = ""
    visible_final_tail: str = ""
    covered_start_sample: int = 0
    covered_end_sample: int = 0


@dataclass(frozen=True)
class FinalizationTimeline:
    audio_frozen_ms: float
    audio_teardown_ms: float
    stream_handoff_ms: float
    transcription_ms: float
    safe_text_ms: float
    delivery_ms: float
