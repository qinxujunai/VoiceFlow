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


@dataclass(frozen=True)
class UiDisplay:
    label: str
    css_class: str
    tray_state: str


_DISPLAY = {
    UiState.IDLE: UiDisplay("准备就绪", "idle", "idle"),
    UiState.LISTENING: UiDisplay("聆听中...", "listening", "recording"),
    UiState.STREAMING: UiDisplay("", "streaming", "recording"),
    UiState.PROCESSING: UiDisplay("处理中...", "processing", "processing"),
    UiState.SUCCESS: UiDisplay("", "success", "idle"),
    UiState.ERROR: UiDisplay("出错了", "error", "error"),
    UiState.CANCELED: UiDisplay("已取消", "canceled", "idle"),
}


def display_for_state(state):
    if isinstance(state, str):
        state = UiState(state)
    return _DISPLAY[state]
