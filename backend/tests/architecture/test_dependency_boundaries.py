"""Dependency-boundary checks: shared is a leaf; services are independent."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402


def test_shared_is_leaf() -> None:
    shared_dir = _scan.BACKEND_ROOT / "shared"
    for f in _scan.py_files(shared_dir):
        for mod in _scan.imported_modules(f):
            top = mod.split(".")[0]
            assert top not in _scan.SERVICE_PACKAGES, f"{_scan.relposix(f)} imports service '{mod}' — shared must be a dependency leaf"


def test_services_are_independent() -> None:
    for svc in _scan.SERVICE_PACKAGES:
        for f in _scan.py_files(_scan.BACKEND_ROOT / svc):
            for mod in _scan.imported_modules(f):
                top = mod.split(".")[0]
                assert not (top in _scan.SERVICE_PACKAGES and top != svc), (
                    f"{_scan.relposix(f)} imports another service '{mod}' — services must be independent"
                )


if __name__ == "__main__":
    _scan.run([test_shared_is_leaf, test_services_are_independent])
