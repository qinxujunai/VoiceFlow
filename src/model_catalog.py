"""Small, evidence-backed user model catalog.

Only models that have an intentional product role belong here.  The full pinned
engineering inventory remains in ``model-manifest.json``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    engine: str
    model_id: str
    target_dir: str
    title: str
    badge: str
    summary: str
    languages: str
    hardware: str
    download_bytes: int
    short_p95_ms: int
    peak_memory_mb: int
    clean_cer_percent: float
    recommended: bool
    availability: str
    evidence_note: str

    @property
    def download_size_label(self) -> str:
        return f"{self.download_bytes / (1024 ** 2):.0f} MB"


_PROFILES = (
    ModelProfile(
        engine="sensevoice",
        model_id="sensevoice-small-int8",
        target_dir="models/sensevoice",
        title="极速听写",
        badge="推荐",
        summary="低配置优先。默认自动判断中文、英文和中英混说；可手动固定语言。",
        languages="中文 · English · 粤语",
        hardware="CPU · 8 GB 内存可用",
        download_bytes=240500355,
        short_p95_ms=163,
        peak_memory_mb=355,
        clean_cer_percent=2.27,
        recommended=True,
        availability="public",
        evidence_note="同机初步语料：短句 P95 163 ms，Clean CER 2.27%。自然英文小样本显示自动检测可避免中文怪串，但样本仍不足以代表所有口音。",
    ),
    ModelProfile(
        engine="qwen3-asr",
        model_id="qwen3-asr-0.6b-int8",
        target_dir="models/qwen3-asr",
        title="多语言识别",
        badge="实验室",
        summary="可下载的多语言候选。当前同机证据尚未胜过极速听写，不默认推荐。",
        languages="中文 · English · 多语言候选",
        hardware="CPU · 建议 16 GB 内存",
        download_bytes=987015347,
        short_p95_ms=1298,
        peak_memory_mb=1459,
        clean_cer_percent=23.02,
        recommended=False,
        availability="lab",
        evidence_note="同机小样本初步语料：短句 P95 1,298 ms，Clean CER 23.02%。仅供主动实验，不构成更准确声明。",
    ),
)


def user_model_profiles() -> tuple[ModelProfile, ...]:
    return _PROFILES


def profile_for_engine(engine: str) -> ModelProfile:
    for profile in _PROFILES:
        if profile.engine == engine:
            return profile
    raise KeyError(f"engine is not in the user model catalog: {engine}")
