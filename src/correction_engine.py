"""
Optional AI correction layer for streaming and final dictation text.
"""

from __future__ import annotations

import json
import threading
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class CorrectionRequest:
    text: str
    stable_text: str = ""
    terms: list[str] | None = None


class DisabledCorrectionEngine:
    def correct(self, request, stable_text="", terms=None):
        if isinstance(request, CorrectionRequest):
            return request.text
        return request or ""


class OllamaCorrectionEngine:
    def __init__(
        self,
        model,
        url="http://localhost:11434",
        timeout=2.0,
        num_predict=80,
    ):
        self.model = model
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.num_predict = num_predict

    def correct(self, request):
        if not isinstance(request, CorrectionRequest):
            request = CorrectionRequest(text=request or "")
        if not request.text.strip():
            return request.text

        payload = self._build_payload(request)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = urllib.request.Request(
            f"{self.url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(http_request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        corrected = body.get("message", {}).get("content", "").strip()
        return corrected or request.text

    def _build_payload(self, request):
        terms = ", ".join(request.terms or [])
        system = (
            "你是语音输入法校对器。只修正错别字、AI和编程术语、明显断句。"
            "不要解释，不要扩写，不要总结，不要改变原意，只输出校对后的原句。"
        )
        if terms:
            system += f" 优先保留这些术语的标准写法：{terms}。"
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": request.text},
            ],
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0,
                "num_predict": min(int(self.num_predict), 120),
            },
        }


def correct_with_timeout(engine, request, timeout):
    original = request.text if isinstance(request, CorrectionRequest) else str(request or "")
    result = {"text": original}

    def run():
        try:
            corrected = engine.correct(request)
            result["text"] = corrected or original
        except Exception:
            result["text"] = original

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=max(0.0, float(timeout)))
    if thread.is_alive():
        return original
    return result["text"]


def build_correction_engine(config):
    cfg = (config or {}).get("correction", {})
    provider = cfg.get("provider", "disabled")
    if provider == "ollama":
        ollama = cfg.get("ollama", {})
        return OllamaCorrectionEngine(
            model=ollama.get("model", "qwen3.5:4b"),
            url=ollama.get("url", "http://localhost:11434"),
            timeout=ollama.get("timeout", cfg.get("timeout", 2.0)),
            num_predict=ollama.get("num_predict", 80),
        )
    return DisabledCorrectionEngine()
