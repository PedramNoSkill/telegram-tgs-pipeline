"""Visual QA: does the loop actually close, and do frames change sanely?

Two checks that catch what JSON validation cannot:

* ``loop_seam`` — compares the rendered first frame with the rendered
  frame at the loop point. A seamless animation scores ~0; a jump shows
  up as a large mean pixel difference, however clean the JSON looks.
* ``frame_diff`` — mean absolute difference between consecutive frames.
  All-zero means a frozen animation; a single huge spike in the middle
  usually means a glitch frame (a keyframe typo), not a design choice.

Both work on in-memory RGB frames (lists of Pillow images or nested
lists), so they can run in CI without a Telegram client.
"""
from __future__ import annotations

from dataclasses import dataclass


def _mean_abs_diff(frame_a, frame_b) -> float:
    """Mean absolute per-channel difference between two same-size frames.
    Frames are Pillow images in RGB/RGBA mode."""
    if frame_a.size != frame_b.size:
        raise ValueError(f"frame size mismatch: {frame_a.size} vs {frame_b.size}")
    a = frame_a.convert("RGBA")
    b = frame_b.convert("RGBA")
    pa, pb = a.load(), b.load()
    w, h = a.size
    total = 0
    for y in range(h):
        for x in range(w):
            ca, cb = pa[x, y], pb[x, y]
            total += sum(abs(int(ca[i]) - int(cb[i])) for i in range(4))
    return total / (w * h * 4)


@dataclass
class QaReport:
    seam: float
    max_step: float
    mean_step: float
    frozen: bool

    @property
    def ok(self) -> bool:
        return self.seam < 2.0 and not self.frozen


def qa_frames(frames: list) -> QaReport:
    """Run the QA gates on a rendered frame sequence (first..last of loop)."""
    if len(frames) < 3:
        raise ValueError("need at least 3 frames for QA")
    steps = [_mean_abs_diff(frames[i], frames[i + 1]) for i in range(len(frames) - 1)]
    seam = _mean_abs_diff(frames[-1], frames[0])
    return QaReport(
        seam=seam,
        max_step=max(steps),
        mean_step=sum(steps) / len(steps),
        frozen=all(step == 0 for step in steps),
    )
