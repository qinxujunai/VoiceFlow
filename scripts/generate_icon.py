"""
Generate the static VoiceFlow Windows icon.

The runtime tray icon is still state-aware and drawn by src/tray_icon.py.
This script creates the application/shortcut icon at assets/voiceflow.ico
without adding image dependencies.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "voiceflow.ico"
SIZE = 256


def _clamp(value: float) -> int:
    return max(0, min(255, int(round(value))))


def _blend(dst, src):
    sr, sg, sb, sa = src
    if sa <= 0:
        return dst
    if sa >= 255:
        return src
    dr, dg, db, da = dst
    alpha = sa / 255.0
    out_a = alpha + da / 255.0 * (1 - alpha)
    if out_a <= 0:
        return (0, 0, 0, 0)
    r = (sr * alpha + dr * (da / 255.0) * (1 - alpha)) / out_a
    g = (sg * alpha + dg * (da / 255.0) * (1 - alpha)) / out_a
    b = (sb * alpha + db * (da / 255.0) * (1 - alpha)) / out_a
    return (_clamp(r), _clamp(g), _clamp(b), _clamp(out_a * 255))


def _rounded_rect_alpha(x, y, left, top, right, bottom, radius):
    inside_x = left + radius <= x <= right - radius
    inside_y = top + radius <= y <= bottom - radius
    if inside_x and top <= y <= bottom:
        return 255
    if inside_y and left <= x <= right:
        return 255
    cx = left + radius if x < left + radius else right - radius
    cy = top + radius if y < top + radius else bottom - radius
    dist = math.hypot(x - cx, y - cy)
    if dist <= radius - 1:
        return 255
    if dist <= radius + 1:
        return _clamp((radius + 1 - dist) * 127.5)
    return 0


def _bar_alpha(x, y, cx, cy, width, height, radius):
    left = cx - width / 2
    right = cx + width / 2
    top = cy - height / 2
    bottom = cy + height / 2
    return _rounded_rect_alpha(x, y, left, top, right, bottom, radius)


def _make_pixels():
    pixels = [(0, 0, 0, 0)] * (SIZE * SIZE)
    for y in range(SIZE):
        for x in range(SIZE):
            # Soft shadow.
            dx = max(abs(x - SIZE / 2) - 86, 0)
            dy = max(abs(y - SIZE / 2) - 86, 0)
            shadow_dist = math.hypot(dx, dy)
            shadow = max(0, 42 - shadow_dist * 5)
            color = (0, 0, 0, _clamp(shadow))

            # Dark rounded square.
            a = _rounded_rect_alpha(x, y, 34, 34, 222, 222, 44)
            if a:
                color = _blend(color, (24, 24, 26, a))

            # Thin inner highlight.
            border_a = _rounded_rect_alpha(x, y, 37, 37, 219, 219, 41)
            inner_a = _rounded_rect_alpha(x, y, 39, 39, 217, 217, 39)
            if border_a and not inner_a:
                color = _blend(color, (255, 255, 255, 36))

            # Voice bars.
            bars = [(101, 128, 16, 68), (128, 128, 16, 108), (155, 128, 16, 82)]
            for cx, cy, w, h in bars:
                ba = _bar_alpha(x, y, cx, cy, w, h, 8)
                if ba:
                    color = _blend(color, (245, 245, 247, ba))

            pixels[y * SIZE + x] = color
    return pixels


def _write_ico(path: Path, pixels):
    path.parent.mkdir(parents=True, exist_ok=True)

    # ICO stores DIB rows bottom-up in BGRA order. Height is doubled to
    # include the unused 1-bit AND mask.
    header = struct.pack(
        "<IIIHHIIIIII",
        40,
        SIZE,
        SIZE * 2,
        1,
        32,
        0,
        SIZE * SIZE * 4,
        0,
        0,
        0,
        0,
    )
    xor = bytearray()
    for y in range(SIZE - 1, -1, -1):
        for x in range(SIZE):
            r, g, b, a = pixels[y * SIZE + x]
            xor += bytes((b, g, r, a))
    and_mask = bytes(((SIZE + 31) // 32) * 4 * SIZE)
    image = header + xor + and_mask

    icon_dir = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(image), 6 + 16)
    path.write_bytes(icon_dir + entry + image)


def main():
    _write_ico(OUT, _make_pixels())
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
