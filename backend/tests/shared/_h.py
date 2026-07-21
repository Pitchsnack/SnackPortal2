"""Path/runner bootstrap for shared-package behavior tests (stdlib; pytest or standalone).

NOTE: every tests/<dir>/_h.py shares the module name `_h`, so in a full-suite run the
first one imported wins the sys.modules cache. This module therefore carries ONLY the
interface every `_h` provides (backend/arch path bootstrap + `run`); portability-specific
constants live in the uniquely-named `_portability_paths` module.
"""

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
