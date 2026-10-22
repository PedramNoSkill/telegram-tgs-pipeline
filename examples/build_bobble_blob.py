#!/usr/bin/env python3
"""Example build: 'Bobble' — a one-eyed blob character with a waving arm.

Shows the whole point of the rig system:
  * every part is a bezier silhouette (no ellipse/rect clip-art heroes),
  * the arm rotates around its *shoulder* pivot, not its centre,
  * the squash-and-stretch body track and the wave track are defined on
    the loop, and the compiler closes the loop by construction.

Run:
    python examples/build_bobble_blob.py
    tgspipe validate examples/bobble_blob.tgs
    tgspipe render   examples/bobble_blob.tgs --out preview.png
    tgspipe qa       examples/bobble_blob.tgs
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tgspipe.build import Part, Rig, bezier_path, blob_points, fill, track
from tgspipe.lottieio import dump_tgs

OUT = Path(__file__).with_name("bobble_blob.tgs")


def body_part() -> Part:
    pts, tans = blob_points(0, 0, 118, 104, wobble=0.03)
    return Part(
        name="body",
        items=[bezier_path(pts, tans), fill("#37B24D")],
        pivot=(0, 30),
        pos=(256, 300),
        motion={
            # squash & stretch: wide-flat at the bottom of the bounce,
            # tall-thin at the top; fractions are of the 3 s loop.
            "s": track([(0.0, [100, 100, 100]),
                        (0.25, [108, 88, 100]),
                        (0.5, [100, 100, 100]),
                        (0.75, [94, 108, 100])], ease="smooth"),
            "p": track([(0.0, [256, 300, 0]),
                        (0.25, [256, 314, 0]),
                        (0.5, [256, 300, 0]),
                        (0.75, [256, 278, 0])], ease="smooth"),
        },
    )


def eye_part() -> Part:
    # one big eye: white bezier disc + pupil that looks left, then right
    white_pts, white_tans = blob_points(0, 0, 46, 50, wobble=0.04)
    pupil_pts, pupil_tans = blob_points(0, 6, 19, 22, wobble=0.05)
    return Part(
        name="eye",
        items=[bezier_path(white_pts, white_tans), fill("#FFFFFF"),
               bezier_path(pupil_pts, pupil_tans), fill("#1E272E")],
        pivot=(0, 0),
        pos=(256, 252),
        motion={
            "p": track([(0.0, [256, 252, 0]),
                        (0.25, [256, 262, 0]),
                        (0.5, [256, 252, 0]),
                        (0.75, [256, 238, 0])], ease="smooth"),
        },
    )


def arm_part() -> Part:
    # a simple tapered arm silhouette, drawn pointing up-right from the
    # shoulder at (0, 0) — the pivot IS the shoulder.
    pts = [(-14, 10), (26, -58), (44, -66), (48, -52), (22, 8), (4, 16)]
    tans = [((10, -2), (-10, 2)), ((-4, -12), (6, 10)),
            ((-8, -2), (8, 2)), ((-2, 10), (0, -10)),
            ((10, 4), (-8, -4)), ((-4, 8), (2, -8))]
    return Part(
        name="arm_r",
        items=[bezier_path(pts, tans), fill("#2F9E44")],
        pivot=(0, 0),
        pos=(352, 268),
        motion={
            # the wave: three swings per loop, settling back to 0 degrees
            "r": track([(0.0, 0), (0.125, -22), (0.25, 6), (0.375, -22),
                        (0.5, 6), (0.625, -22), (0.75, 0), (0.875, 0)],
                       ease="smooth"),
            "p": track([(0.0, [352, 268, 0]),
                        (0.25, [352, 280, 0]),
                        (0.5, [352, 268, 0]),
                        (0.75, [352, 250, 0])], ease="smooth"),
        },
    )


def main() -> int:
    rig = Rig(name="bobble_blob", parts=[arm_part(), body_part(), eye_part()])
    problems = rig.audit()
    if problems:
        print("rig audit FAIL:", *problems, sep="\n  ")
        return 1
    from tgspipe.build import build_character
    doc = build_character(rig)
    size = dump_tgs(doc, OUT)
    print(f"built {OUT.name}: {size} bytes (limit 65536)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
