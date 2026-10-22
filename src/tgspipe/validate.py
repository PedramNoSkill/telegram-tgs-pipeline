"""Hard validation gates for Telegram .tgs files.

The spec (core.telegram.org/stickers, re-checked in docs/telegram-limits.md):
512x512 canvas, <= 60 fps, <= 3 s, <= 64 KB gzipped, seamless loop, and a
long list of Lottie features Telegram simply does not render. A file that
violates any of these does not fail "somewhere in production" — it fails
here, in CI, with a named rule.

Exit semantics used by the CLI: any ERROR -> fail, WARN -> pass with notes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .lottieio import animated_properties, load_any, walk

MAX_SIZE_BYTES = 64 * 1024
WARN_SIZE_BYTES = 52 * 1024
CANVAS = 512
MAX_FPS = 60
MAX_SECONDS = 3.0

# Lottie layer types Telegram rejects outright.
FORBIDDEN_LAYER_TYPES = {1: "solid layer", 2: "image layer", 5: "text layer"}
# Keys that betray a forbidden feature wherever they appear.
FORBIDDEN_KEYS = {
    "masksProperties": "masks",
    "tt": "track matte",
    "ef": "layer effects",
    "x": "expressions",
}
# Shape types Telegram rejects (ty values inside shape groups).
FORBIDDEN_SHAPES = {
    "sr": "polystar (star shape)",
    "rp": "repeater",
    "mm": "merge paths",
    "gs": "gradient stroke",
}
WARN_SHAPES = {"tm": "trim paths (renders, but brittle across clients)"}
PRIMITIVE_SHAPES = {"el", "rc"}


@dataclass
class Finding:
    level: str  # "ERROR" | "WARN"
    rule: str
    detail: str


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "ERROR"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, level: str, rule: str, detail: str) -> None:
        self.findings.append(Finding(level, rule, detail))


def _keyframe_values(prop: dict) -> list[Any]:
    return [kf.get("s") for kf in prop.get("k", []) if isinstance(kf, dict)]


def _values_equal(a: Any, b: Any, tol: float = 1e-6) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), abs_tol=tol)
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return all(_values_equal(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_values_equal(a[k], b[k], tol) for k in a)
    return a == b


def check_loop(doc: dict[str, Any], report: Report) -> None:
    """A Telegram animation must loop seamlessly: for every animated
    property, the value at the last keyframe must equal the first."""
    broken = []
    for path, prop in animated_properties(doc):
        values = _keyframe_values(prop)
        if len(values) >= 2 and not _values_equal(values[0], values[-1]):
            broken.append(path)
    if broken:
        shown = "; ".join(broken[:5])
        report.add("ERROR", "loop-seam",
                   f"{len(broken)} animated propertie(s) do not return to their "
                   f"first keyframe value (loop will jump): {shown}")
    else:
        report.stats["loop"] = "seamless"


def validate_doc(doc: dict[str, Any], size_bytes: int | None = None) -> Report:
    report = Report()

    # --- composition basics -------------------------------------------------
    w, h = doc.get("w"), doc.get("h")
    if (w, h) != (CANVAS, CANVAS):
        report.add("ERROR", "canvas", f"canvas is {w}x{h}, Telegram requires 512x512")
    fr = doc.get("fr")
    if not isinstance(fr, (int, float)) or fr <= 0:
        report.add("ERROR", "fps", f"frame rate missing/invalid: {fr!r}")
        fr = 0
    elif fr > MAX_FPS:
        report.add("ERROR", "fps", f"frame rate {fr} exceeds 60 fps")
    ip, op = doc.get("ip", 0), doc.get("op", 0)
    frames = op - ip
    if fr and frames / fr > MAX_SECONDS + 1e-9:
        report.add("ERROR", "duration",
                   f"duration {frames / fr:.2f}s ({frames} frames) exceeds 3s")
    report.stats.update({"canvas": f"{w}x{h}", "fps": fr, "frames": frames})

    # --- size budget ----------------------------------------------------------
    if size_bytes is not None:
        report.stats["size_bytes"] = size_bytes
        if size_bytes > MAX_SIZE_BYTES:
            report.add("ERROR", "size", f"{size_bytes} bytes exceeds the 64 KB limit")
        elif size_bytes > WARN_SIZE_BYTES:
            report.add("WARN", "size",
                       f"{size_bytes} bytes is close to the 64 KB limit; "
                       "run the optimizer before adding anything else")

    # --- forbidden features ---------------------------------------------------
    seen_forbidden: dict[str, str] = {}
    primitives = shapes = 0
    for path, node in walk(doc):
        if not isinstance(node, dict):
            continue
        for key, label in FORBIDDEN_KEYS.items():
            if key in node and label not in seen_forbidden:
                # 'x' is also a legit coordinate key inside some dicts; only
                # flag it as an expression when it holds a string payload.
                if key == "x" and not isinstance(node.get("x"), str):
                    continue
                seen_forbidden[label] = path
        ty = node.get("ty")
        if ty in FORBIDDEN_SHAPES and FORBIDDEN_SHAPES[ty] not in seen_forbidden:
            seen_forbidden[FORBIDDEN_SHAPES[ty]] = path
        if ty in WARN_SHAPES:
            report.add("WARN", "shape", f"{WARN_SHAPES[ty]} at {path}")
        if ty in PRIMITIVE_SHAPES:
            primitives += 1
            shapes += 1
        elif ty in ("sh", "el", "rc", "fl", "st", "gf", "tr", "gr"):
            shapes += 1
    for label, path in seen_forbidden.items():
        report.add("ERROR", "forbidden", f"{label} found at {path}")

    for layer in doc.get("layers", []):
        if not isinstance(layer, dict):
            continue
        lty = layer.get("ty")
        if lty in FORBIDDEN_LAYER_TYPES:
            report.add("ERROR", "layer-type",
                       f"layer {layer.get('nm', '?')!r} is a {FORBIDDEN_LAYER_TYPES[lty]}")
        if layer.get("ddd") == 1:
            report.add("ERROR", "layer-type",
                       f"layer {layer.get('nm', '?')!r} is a 3D layer")
        if layer.get("ao") == 1:
            report.add("ERROR", "layer-type",
                       f"layer {layer.get('nm', '?')!r} is auto-oriented")

    # --- readability heuristic --------------------------------------------------
    # An emoji is read at ~100x100 px. Art built only from ellipse/rect
    # primitives reads as clip-art at that size; heroes should be beziers.
    if shapes >= 4 and primitives == shapes:
        report.add("WARN", "primitive-ratio",
                   "every shape is an ellipse/rect primitive; at 100x100 this "
                   "reads as clip-art — give the hero a bezier silhouette")
    report.stats["shapes"] = shapes

    check_loop(doc, report)
    return report


def validate_file(path: str) -> Report:
    doc, size = load_any(path)
    if size is None:  # plain JSON: report the would-be .tgs size
        import gzip
        import json
        size = len(gzip.compress(json.dumps(doc, separators=(",", ":")).encode(),
                                 compresslevel=9, mtime=0))
    return validate_doc(doc, size)
