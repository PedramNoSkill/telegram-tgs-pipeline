"""Character rigging and Lottie building blocks.

The rig model is the part most .tgs codebases get wrong: parts are drawn
as flat shapes and moved by hand, so pivots drift, arms rotate around
their centre instead of their shoulder, and every fix breaks the loop.

Here a character is a set of named *parts*. Each part owns:
  * a bezier silhouette (never an ellipse/rect primitive for the hero),
  * a pivot — the point it rotates/scales around, in part-local coords,
  * a z-order and a parent part (or None for the root).

`build_character` compiles that into a flat Lottie document whose loops
close by construction: every motion track is defined on [0, 1] of the
loop and the compiler appends the first keyframe value at the end.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

FR, OP, SIZE = 60, 180, 512

# name -> (out-tangent, in-tangent) cubic-bezier control points (Lottie i/o)
EASE: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {
    "smooth": ((0.45, 0.0), (0.55, 1.0)),
    "snap_in": ((0.55, 0.0), (0.85, 0.0)),
    "soft_out": ((0.15, 1.0), (0.45, 1.0)),
    "pop": ((0.34, 1.56), (0.64, 1.0)),
    "float": ((0.37, 0.0), (0.63, 1.0)),
    "linear": ((0.0, 0.0), (1.0, 1.0)),
}


def r2(value: float) -> float:
    out = round(float(value), 2)
    return 0.0 if out == 0 else out


def hex_color(hexstr: str) -> list[float]:
    """'#F2C230' -> [0.949, 0.761, 0.188, 1.0] (Lottie RGBA, 0..1)."""
    h = hexstr.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"bad hex colour: {hexstr!r}")
    return [round(int(h[i:i + 2], 16) / 255.0, 4) for i in (0, 2, 4)] + [1.0]


def static(value: Any) -> dict:
    return {"a": 0, "k": value}


def track(keys: list[tuple[float, Any]], ease: str = "smooth") -> dict:
    """Build an animated property from (loop_fraction, value) keys.

    Fractions must start at 0.0; the compiler appends the t=0 value at
    t=1.0 (frame OP) so the loop closes by construction.
    """
    if not keys or keys[0][0] != 0.0:
        raise ValueError("a motion track must start at fraction 0.0")
    o_pts, i_pts = EASE[ease]
    keyframes = []
    ordered = sorted(keys)
    for fraction, value in ordered:
        keyframes.append({
            "t": r2(fraction * OP),
            "s": value,
            "o": {"x": [o_pts[0]], "y": [o_pts[1]]},
            "i": {"x": [i_pts[0]], "y": [i_pts[1]]},
        })
    if ordered[-1][0] < 1.0:
        keyframes.append({"t": OP, "s": ordered[0][1]})
    return {"a": 1, "k": keyframes}


def bezier_path(points: list[tuple[float, float]],
                tangents: list[tuple[tuple[float, float], tuple[float, float]]] | None = None,
                closed: bool = True) -> dict:
    """A 'sh' shape from anchor points with (in, out) tangents per point."""
    n = len(points)
    if tangents is None:
        tangents = [((0.0, 0.0), (0.0, 0.0))] * n
    return {
        "ty": "sh",
        "ks": static({
            "c": closed,
            "v": [[r2(x), r2(y)] for x, y in points],
            "i": [[r2(t[0][0]), r2(t[0][1])] for t in tangents],
            "o": [[r2(t[1][0]), r2(t[1][1])] for t in tangents],
        }),
    }


def blob_points(cx: float, cy: float, rx: float, ry: float,
                wobble: float = 0.12) -> tuple[list, list]:
    """Anchor+tangent sets for an organic blob (a rounded silhouette with
    hand-feeling asymmetry, not a perfect ellipse primitive)."""
    pts, tans = [], []
    step = math.pi / 4
    for i in range(8):
        ang = i * step
        rad = 1.0 + (wobble if i % 2 == 0 else -wobble / 2)
        x, y = cx + rx * rad * math.cos(ang), cy + ry * rad * math.sin(ang)
        pts.append((x, y))
        # دسته‌های بزیه در راستای مماس بیضی، با طول تقریب استاندارد کمان
        ox, oy = -rx * math.sin(ang) * (step / 3), ry * math.cos(ang) * (step / 3)
        tans.append(((-ox, -oy), (ox, oy)))
    return pts, tans


def fill(color: str, opacity: float = 100.0) -> dict:
    return {"ty": "fl", "c": static(hex_color(color)), "o": static(opacity)}


def group(name: str, items: list[dict],
          pos: tuple[float, float] = (0.0, 0.0),
          rot: float | dict = 0.0, scale: tuple[float, float] = (100.0, 100.0)) -> dict:
    rot_prop = rot if isinstance(rot, dict) else static(rot)
    return {
        "ty": "gr", "nm": name,
        "it": items + [{
            "ty": "tr",
            "p": static([r2(pos[0]), r2(pos[1])]),
            "a": static([0.0, 0.0]),
            "s": static([r2(scale[0]), r2(scale[1])]),
            "r": rot_prop,
            "o": static(100.0),
        }],
    }


@dataclass
class Part:
    """One rigged body part. Coordinates are in the character's 512 space."""
    name: str
    items: list[dict]                       # shapes (paths + fills)
    pivot: tuple[float, float]              # rotation centre, canvas coords
    pos: tuple[float, float] = (256.0, 256.0)
    parent: str | None = None
    motion: dict[str, dict] = field(default_factory=dict)  # 'r'/'p'/'s' tracks

    def bounds(self) -> tuple[float, float, float, float]:
        xs, ys = [], []
        def scan(node: Any) -> None:
            if isinstance(node, dict):
                if node.get("ty") == "sh":
                    k = node.get("ks", {}).get("k", {})
                    for vtx in k.get("v", []) or []:
                        xs.append(vtx[0]); ys.append(vtx[1])
                for v in node.values():
                    scan(v)
            elif isinstance(node, list):
                for v in node:
                    scan(v)
        scan(self.items)
        if not xs:
            return (0.0, 0.0, 0.0, 0.0)
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass
class Rig:
    name: str
    parts: list[Part]

    def audit(self) -> list[str]:
        """Structural problems that would show up as broken motion later:
        a pivot outside its part, a missing parent, a duplicated name."""
        problems: list[str] = []
        names = [p.name for p in self.parts]
        if len(names) != len(set(names)):
            problems.append("duplicate part names in rig")
        known = set(names)
        for part in self.parts:
            if part.parent and part.parent not in known:
                problems.append(f"part {part.name!r} has unknown parent {part.parent!r}")
            x0, y0, x1, y1 = part.bounds()
            if (x0 or x1) and not (x0 - 40 <= part.pivot[0] <= x1 + 40
                                   and y0 - 40 <= part.pivot[1] <= y1 + 40):
                problems.append(
                    f"part {part.name!r}: pivot {part.pivot} is far outside its "
                    f"silhouette bounds {(x0, y0, x1, y1)} — rotation will swing "
                    "around the wrong point")
        return problems


def build_character(rig: Rig) -> dict[str, Any]:
    """Compile a Rig into a Lottie document (512x512, 60 fps, 3 s loop)."""
    problems = rig.audit()
    if problems:
        raise ValueError("rig audit failed: " + "; ".join(problems))
    layers = []
    for index, part in enumerate(reversed(rig.parts)):  # Lottie draws top-first
        ks: dict[str, Any] = {
            "p": part.motion.get("p", static([r2(part.pos[0]), r2(part.pos[1]), 0.0])),
            "a": static([r2(part.pivot[0]), r2(part.pivot[1]), 0.0]),
            "s": part.motion.get("s", static([100.0, 100.0, 100.0])),
            "r": part.motion.get("r", static(0.0)),
            "o": static(100.0),
        }
        layers.append({
            "ty": 4, "nm": part.name, "ind": index + 1,
            "ip": 0, "op": OP, "st": 0, "ks": ks,
            "shapes": [group(part.name, part.items)],
            "ao": 0, "ddd": 0,
        })
    return {"v": "5.7.4", "fr": FR, "ip": 0, "op": OP, "w": SIZE, "h": SIZE,
            "nm": rig.name, "ddd": 0, "assets": [], "layers": layers}
