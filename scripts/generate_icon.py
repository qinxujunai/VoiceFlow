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
SIZES = (16, 20, 24, 32, 48, 64, 128, 256)


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


def _make_pixels(size):
    pixels = [(0, 0, 0, 0)] * (size * size)
    scale = size / 256
    for y in range(size):
        for x in range(size):
            # Soft shadow.
            dx = max(abs(x - size / 2) - 86 * scale, 0)
            dy = max(abs(y - size / 2) - 86 * scale, 0)
            shadow_dist = math.hypot(dx, dy)
            shadow = max(0, 42 - shadow_dist * 5 / scale)
            color = (0, 0, 0, _clamp(shadow))

            # Dark rounded square.
            a = _rounded_rect_alpha(
                x,
                y,
                34 * scale,
                34 * scale,
                222 * scale,
                222 * scale,
                44 * scale,
            )
            if a:
                color = _blend(color, (24, 24, 26, a))

            # Thin inner highlight.
            border_a = _rounded_rect_alpha(
                x,
                y,
                37 * scale,
                37 * scale,
                219 * scale,
                219 * scale,
                41 * scale,
            )
            inner_a = _rounded_rect_alpha(
                x,
                y,
                39 * scale,
                39 * scale,
                217 * scale,
                217 * scale,
                39 * scale,
            )
            if border_a and not inner_a:
                color = _blend(color, (255, 255, 255, 36))

            # Voice bars.
            bars = [(101, 128, 16, 68), (128, 128, 16, 108), (155, 128, 16, 82)]
            for cx, cy, w, h in bars:
                ba = _bar_alpha(
                    x,
                    y,
                    cx * scale,
                    cy * scale,
                    w * scale,
                    h * scale,
                    8 * scale,
                )
                if ba:
                    color = _blend(color, (245, 245, 247, ba))

            pixels[y * size + x] = color
    return pixels


def _image_bytes(size, pixels):
    # ICO stores DIB rows bottom-up in BGRA order. Height is doubled to
    # include the unused 1-bit AND mask.
    header = struct.pack(
        "<IIIHHIIIIII",
        40,
        size,
        size * 2,
        1,
        32,
        0,
        size * size * 4,
        0,
        0,
        0,
        0,
    )
    xor = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            r, g, b, a = pixels[y * size + x]
            xor += bytes((b, g, r, a))
    and_mask = bytes(((size + 31) // 32) * 4 * size)
    return header + xor + and_mask


def _write_ico(path: Path, images):
    path.parent.mkdir(parents=True, exist_ok=True)

    icon_dir = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = bytearray()
    payload = bytearray()
    for size, pixels in images:
        image = _image_bytes(size, pixels)
        size_byte = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII",
            size_byte,
            size_byte,
            0,
            0,
            1,
            32,
            len(image),
            offset,
        )
        payload += image
        offset += len(image)

    path.write_bytes(icon_dir + entries + payload)


def main():
    images = [(size, _make_pixels(size)) for size in SIZES]
    _write_ico(OUT, images)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
