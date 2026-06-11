"""Secret-hygiene checks: env templates are reference-only; no obvious secret literals."""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),
]
SCAN_SUFFIXES = {".py", ".toml", ".template", ".md", ".yml", ".yaml", ".txt", ".cfg", ""}


def _template_files():
    for p in (_scan.REPO_ROOT / "infrastructure").rglob("*.template"):
        yield p


def test_templates_reference_only() -> None:
    for p in _template_files():
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key, _, value = s.partition("=")
            value = value.strip()
            if key.strip().endswith("_REF"):
                assert value == "" or value.startswith("ref:"), (
                    f"{p.name}:{i} *_REF must be empty or a 'ref:' reference, got: {value!r}"
                )


def test_no_obvious_secret_literals() -> None:
    for root in (_scan.BACKEND_ROOT, _scan.REPO_ROOT / "infrastructure"):
        for p in root.rglob("*"):
            if not p.is_file() or (_scan.SKIP_PARTS & set(p.parts)):
                continue
            if p.suffix not in SCAN_SUFFIXES:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for pat in SECRET_PATTERNS:
                assert not pat.search(text), f"possible secret literal in {p}"


if __name__ == "__main__":
    _scan.run([test_templates_reference_only, test_no_obvious_secret_literals])
