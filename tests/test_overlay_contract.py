from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_streaming_update_writes_text_before_measuring_width():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    set_width_idx = html.index("function setWidthForText(text)")
    text_write_idx = html.index("txt.textContent = text || '';", set_width_idx)
    measure_idx = html.index("var est = measureTextWidth(text);", set_width_idx)

    assert text_write_idx < measure_idx
    assert "setWidthForText(text);" in html[html.index("function updateStreaming(text)"):]
