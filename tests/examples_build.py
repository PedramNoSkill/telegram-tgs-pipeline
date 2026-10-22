"""Shared fixture: builds the example rig without touching the disk."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))

from build_bobble_blob import arm_part, body_part, eye_part  # noqa: E402
from tgspipe.build import Rig  # noqa: E402


def make_rig() -> Rig:
    return Rig(name="bobble_blob", parts=[arm_part(), body_part(), eye_part()])
