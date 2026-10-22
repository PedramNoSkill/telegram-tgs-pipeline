"""Loading, saving and walking .tgs / Lottie documents.

A .tgs file is exactly one thing: gzip-compressed Lottie JSON.
No wrapper, no extra framing. Everything in tgspipe goes through
here so that rule is enforced in a single place.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any, Iterator


class TgsError(ValueError):
    """Raised when a file is not a well-formed .tgs / Lottie document."""


def load_tgs(path: str | Path) -> tuple[dict[str, Any], int]:
    """Load a .tgs file. Returns (document, compressed_size_bytes)."""
    raw = Path(path).read_bytes()
    if raw[:2] != b"\x1f\x8b":
        raise TgsError("not gzip: a .tgs must be gzipped Lottie JSON")
    try:
        doc = json.loads(gzip.decompress(raw))
    except Exception as exc:  # corrupt gzip or non-JSON payload
        raise TgsError(f"cannot decode .tgs payload: {exc}") from exc
    if not isinstance(doc, dict) or "layers" not in doc:
        raise TgsError("payload is JSON but not a Lottie document (no 'layers')")
    return doc, len(raw)


def load_any(path: str | Path) -> tuple[dict[str, Any], int | None]:
    """Load a .tgs (gzipped) or a plain .json Lottie document."""
    raw = Path(path).read_bytes()
    if raw[:2] == b"\x1f\x8b":
        doc, size = load_tgs(path)
        return doc, size
    try:
        doc = json.loads(raw)
    except Exception as exc:
        raise TgsError(f"cannot parse Lottie JSON: {exc}") from exc
    if not isinstance(doc, dict) or "layers" not in doc:
        raise TgsError("not a Lottie document (no 'layers')")
    return doc, None


def dump_tgs(doc: dict[str, Any], path: str | Path) -> int:
    """Write a document as .tgs. Returns the compressed size in bytes."""
    payload = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    blob = gzip.compress(payload, compresslevel=9, mtime=0)
    Path(path).write_bytes(blob)
    return len(blob)


def walk(obj: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Yield (json-path, value) for every node in a Lottie document."""
    yield path, obj
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from walk(value, f"{path}/{key}")
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from walk(value, f"{path}[{index}]")


def animated_properties(doc: dict[str, Any]) -> Iterator[tuple[str, dict]]:
    """Yield (path, property) for every animated property (``a == 1``)."""
    for path, node in walk(doc):
        if isinstance(node, dict) and node.get("a") == 1 and isinstance(node.get("k"), list):
            yield path, node
