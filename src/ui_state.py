"""
UI state names and display metadata for VoiceFlow.
"""

from dataclasses import dataclass
from enum import Enum


class UiState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    STREAMING = "streaming"
    PROCESSING = "processing"
    SUCCESS = "success"
    ERROR = "error"
    CANCELED = "canceled"


# A sent paste ends like a confirmed one: the capsule fades out without words.
# Only a paste that could not be sent says how to paste (owner's decision, 2026-11-03).
SILENT_DELIVERY_STATUSES = frozenset({"landed_confirmed", "clipboard_verified_paste_dispatched"})


@dataclass(frozen=True)
class UiDisplay:
    label: str
    css_class: str
    tray_state: str


_DISPLAY = {
    UiState.IDLE: UiDisplay("准备就绪", "idle", "idle"),
    UiState.LISTENING: UiDisplay("聆听中...", "listening", "recording"),
    UiState.STREAMING: UiDisplay("", "streaming", "recording"),
    UiState.PROCESSING: UiDisplay("", "processing", "processing"),
    UiState.SUCCESS: UiDisplay("", "success", "idle"),
    UiState.ERROR: UiDisplay("出错了", "error", "error"),
    UiState.CANCELED: UiDisplay("已取消", "canceled", "idle"),
}


def display_for_state(state):
    if isinstance(state, str):
        state = UiState(state)
    return _DISPLAY[state]
