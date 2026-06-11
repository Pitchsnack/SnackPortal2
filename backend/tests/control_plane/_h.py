"""Path/runner bootstrap for control-plane behavior tests (stdlib; pytest or standalone)."""
from __future__ import annotations

import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

_ARCH = BACKEND / "tests" / "architecture"
if str(_ARCH) not in sys.path:
    sys.path.insert(0, str(_ARCH))

import _scan  # noqa: E402

run = _scan.run
