"""tgspipe command line: one entry point for the whole pipeline.

    tgspipe validate file.tgs [--json]
    tgspipe optimize in.tgs -o out.tgs
    tgspipe render   file.tgs --frames 12 --out preview.png
    tgspipe qa       file.tgs
    tgspipe audit    (runs inside the example builder, see examples/)

Exit codes: 0 = gates pass, 1 = a gate failed, 2 = usage/IO error.
"""
from __future__ import annotations

import argparse
import json
import sys

from .lottieio import TgsError, dump_tgs, load_any, load_tgs
from .optimize import optimize_doc
from .validate import validate_file


def _cmd_validate(args) -> int:
    try:
        report = validate_file(args.file)
    except (TgsError, OSError) as exc:
        print(f"FAIL: {exc}")
        return 1
    if args.json:
        print(json.dumps({
            "ok": report.ok,
            "stats": report.stats,
            "findings": [f.__dict__ for f in report.findings],
        }, indent=2))
    else:
        for finding in report.findings:
            print(f"{finding.level:5} [{finding.rule}] {finding.detail}")
        verdict = "PASS" if report.ok else "FAIL"
        print(f"{verdict}: {args.file} "
              f"({report.stats.get('size_bytes', '?')} bytes, "
              f"{report.stats.get('frames', '?')} frames @ {report.stats.get('fps', '?')} fps)")
    return 0 if report.ok else 1


def _cmd_optimize(args) -> int:
    try:
        doc, before = load_tgs(args.file)
    except (TgsError, OSError) as exc:
        print(f"FAIL: {exc}")
        return 2
    optimized, stats = optimize_doc(doc)
    after = dump_tgs(optimized, args.output)
    print(f"optimized: {before} -> {after} bytes "
          f"({stats['rounded']} floats rounded, "
          f"{stats['dropped_invisible']} invisible node(s) dropped)")
    report = validate_file(args.output)
    print("PASS" if report.ok else "FAIL", "after optimize")
    return 0 if report.ok else 1


def _cmd_render(args) -> int:
    try:
        from .render import contact_sheet, render_frames
        doc, _ = load_any(args.file)
        frames = render_frames(doc, count=args.frames, size=args.size)
        contact_sheet(frames, cols=args.cols).convert("RGB").save(args.out)
    except (TgsError, OSError, ImportError) as exc:
        print(f"FAIL: {exc}")
        return 2
    print(f"preview: {args.out} ({args.frames} frames @ {args.size}px)")
    return 0


def _cmd_qa(args) -> int:
    try:
        from .qa import qa_frames
        from .render import render_frames
        doc, _ = load_any(args.file)
        frames = render_frames(doc, count=args.frames, size=args.size)
        report = qa_frames(frames)
    except (TgsError, OSError, ImportError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 2
    print(f"loop seam diff : {report.seam:.3f}  (gate < 2.0)")
    print(f"max frame step : {report.max_step:.3f}")
    print(f"mean frame step: {report.mean_step:.3f}")
    print(f"frozen         : {report.frozen}")
    print("PASS" if report.ok else "FAIL")
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tgspipe", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="run the hard spec gates on a .tgs")
    p.add_argument("file")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_validate)

    p = sub.add_parser("optimize", help="apply the size diet and re-validate")
    p.add_argument("file")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=_cmd_optimize)

    p = sub.add_parser("render", help="render a contact-sheet preview PNG")
    p.add_argument("file")
    p.add_argument("--frames", type=int, default=12)
    p.add_argument("--size", type=int, default=100)
    p.add_argument("--cols", type=int, default=6)
    p.add_argument("--out", default="preview.png")
    p.set_defaults(fn=_cmd_render)

    p = sub.add_parser("qa", help="visual QA: loop seam + frame motion gates")
    p.add_argument("file")
    p.add_argument("--frames", type=int, default=24)
    p.add_argument("--size", type=int, default=100)
    p.set_defaults(fn=_cmd_qa)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
