"""A small pure-Pillow preview renderer.

Not a replacement for rlottie — a *preview* tool: it renders the shape
subset tgspipe itself emits (bezier paths, ellipses, rounded rects with
solid fills and animated layer transforms) so a build can be eyeballed
and fed to the QA gates without opening Telegram.

Frames are rendered at a configurable scale; emoji are judged at
100x100, so the default preview is exactly that size.
"""
from __future__ import annotations

import math
from typing import Any

from .validate import _keyframe_values, _values_equal  # reused semantics


def _sample(prop: dict | None, frame: float, default):
    """Sample a (possibly animated) property at a frame, linear easing."""
    if not prop:
        return default
    if prop.get("a") != 1:
        return prop.get("k", default)
    keys = [kf for kf in prop.get("k", []) if isinstance(kf, dict) and "s" in kf]
    if not keys:
        return default
    keys.sort(key=lambda kf: kf.get("t", 0))
    if frame <= keys[0]["t"]:
        return keys[0]["s"]
    for prev, nxt in zip(keys, keys[1:]):
        if prev["t"] <= frame <= nxt["t"]:
            span = max(1e-9, nxt["t"] - prev["t"])
            f = (frame - prev["t"]) / span
            a, b = prev["s"], nxt["s"]
            if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
                return [x + (y - x) * f for x, y in zip(a, b)]
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                return a + (b - a) * f
            return a
    return keys[-1]["s"]


def _bezier(p0, p1, p2, p3, t):
    mt = 1 - t
    return (mt**3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t**3 * p3[0],
            mt**3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t**3 * p3[1])


def _path_points(shape: dict, steps: int = 24) -> list[tuple[float, float]]:
    k = shape.get("ks", {}).get("k", {})
    verts, ins, outs = k.get("v", []), k.get("i", []), k.get("o", [])
    closed = k.get("c", True)
    if len(verts) < 2:
        return [(v[0], v[1]) for v in verts]
    pts: list[tuple[float, float]] = []
    n = len(verts)
    segments = n if closed else n - 1
    for i in range(segments):
        j = (i + 1) % n
        p0 = verts[i]
        p1 = (p0[0] + outs[i][0], p0[1] + outs[i][1])
        p3 = verts[j]
        p2 = (p3[0] + ins[j][0], p3[1] + ins[j][1])
        for s in range(steps):
            pts.append(_bezier(p0, p1, p2, p3, s / steps))
    pts.append(tuple(verts[0]) if closed else tuple(verts[-1]))
    return pts


def _collect_shapes(items, frame, out):
    # در ساختار Lottie، آیتم fill بعد از شکل‌هایی می‌آید که رنگشان می‌کند؛
    # پس شکل‌ها نگه داشته می‌شوند و با رسیدن fill، رنگ می‌گیرند.
    pending: list = []
    for item in items or []:
        ty = item.get("ty")
        if ty == "fl":
            c = item.get("c", {}).get("k", [0, 0, 0, 1])
            fill = tuple(int(round(v * 255)) for v in c[:3])
            for shape in pending:
                out.append((shape, fill))
            pending = []
        elif ty == "gr":
            _collect_shapes(item.get("it", []), frame, out)
        elif ty in ("sh", "el", "rc"):
            pending.append(item)
    for shape in pending:
        out.append((shape, (0, 0, 0)))


def render_frame(doc: dict[str, Any], frame: float, size: int = 100):
    """Render one frame to a Pillow RGBA image of size x size."""
    from PIL import Image, ImageDraw

    scale = size / float(doc.get("w", 512))
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for layer in reversed(doc.get("layers", [])):  # Lottie lists top-first
        ks = layer.get("ks", {})
        pos = _sample(ks.get("p"), frame, [256, 256, 0])
        anchor = _sample(ks.get("a"), frame, [0, 0, 0])
        scl = _sample(ks.get("s"), frame, [100, 100, 100])
        rot = _sample(ks.get("r"), frame, 0)
        shapes: list = []
        for group_item in layer.get("shapes", []):
            if group_item.get("ty") == "gr":
                _collect_shapes(group_item.get("it", []), frame, shapes)
        theta = math.radians(rot if isinstance(rot, (int, float)) else 0)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        sx = (scl[0] / 100.0) if isinstance(scl, list) else 1.0
        sy = (scl[1] / 100.0) if isinstance(scl, list) and len(scl) > 1 else sx

        def place(pt):
            x = (pt[0] - anchor[0]) * sx
            y = (pt[1] - anchor[1]) * sy
            xr = x * cos_t - y * sin_t + pos[0]
            yr = x * sin_t + y * cos_t + pos[1]
            return (xr * scale, yr * scale)

        for shape, fill in shapes:
            if fill is None:
                continue
            ty = shape.get("ty")
            if ty == "sh":
                pts = [place(p) for p in _path_points(shape)]
                if len(pts) >= 3:
                    draw.polygon(pts, fill=fill + (255,))
            elif ty == "el":
                p = shape.get("p", {}).get("k", [0, 0])
                s = shape.get("s", {}).get("k", [0, 0])
                cx, cy = place((p[0], p[1]))
                rx, ry = s[0] / 2 * scale * sx, s[1] / 2 * scale * sy
                draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=fill + (255,))
            elif ty == "rc":
                p = shape.get("p", {}).get("k", [0, 0])
                s = shape.get("s", {}).get("k", [0, 0])
                cx, cy = place((p[0], p[1]))
                rx, ry = s[0] / 2 * scale * sx, s[1] / 2 * scale * sy
                draw.rounded_rectangle([cx - rx, cy - ry, cx + rx, cy + ry],
                                       radius=min(rx, ry) * 0.3, fill=fill + (255,))
    return img


def render_frames(doc: dict[str, Any], count: int = 12, size: int = 100) -> list:
    op = doc.get("op", 180)
    return [render_frame(doc, i * op / count, size) for i in range(count)]


def contact_sheet(frames: list, cols: int = 6, bg=(24, 26, 32, 255)):
    from PIL import Image

    if not frames:
        raise ValueError("no frames")
    w, h = frames[0].size
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * w, rows * h), bg)
    for i, frame in enumerate(frames):
        sheet.alpha_composite(frame, ((i % cols) * w, (i // cols) * h))
    return sheet
