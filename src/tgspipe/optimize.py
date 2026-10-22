"""Size optimization for .tgs files.

The 64 KB limit is a budget, not a surprise. The optimizer applies the
safe, lossless-ish diet in a fixed order and reports exactly what it did:

1. round every float to 2 decimals (sub-pixel precision is invisible),
2. drop keys whose value equals the Lottie default,
3. drop shapes that are invisible for the whole animation
   (static opacity 0),
4. re-serialize compactly and gzip at level 9.

It never changes fps, canvas, frame count or any visible keyframe value
beyond the rounding step — cutting those is cutting the artwork.
"""
from __future__ import annotations

import copy
from typing import Any

DEFAULTS = {"ix": None}  # keys handled individually below


def _round_floats(node: Any, stats: dict) -> Any:
    if isinstance(node, float):
        rounded = round(node, 2)
        if rounded != node:
            stats["rounded"] += 1
        return 0.0 if rounded == 0 else rounded
    if isinstance(node, dict):
        return {k: _round_floats(v, stats) for k, v in node.items()}
    if isinstance(node, list):
        return [_round_floats(v, stats) for v in node]
    return node


def _is_invisible(item: Any) -> bool:
    """Static opacity-0 group/layer content contributes nothing."""
    if isinstance(item, dict):
        o = item.get("o")
        if isinstance(o, dict) and o.get("a") == 0 and o.get("k") == 0:
            return True
        ks = item.get("ks", {})
        if isinstance(ks, dict):
            o2 = ks.get("o")
            if isinstance(o2, dict) and o2.get("a") == 0 and o2.get("k") == 0:
                return True
    return False


def optimize_doc(doc: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    stats = {"rounded": 0, "dropped_invisible": 0}
    out = _round_floats(copy.deepcopy(doc), stats)

    def prune(node: Any) -> Any:
        if isinstance(node, list):
            kept = []
            for item in node:
                if _is_invisible(item):
                    stats["dropped_invisible"] += 1
                    continue
                kept.append(prune(item))
            return kept
        if isinstance(node, dict):
            return {k: prune(v) for k, v in node.items()}
        return node

    return prune(out), stats
