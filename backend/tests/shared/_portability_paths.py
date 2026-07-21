"""Committed-profile locations for the portability tests (uniquely named — see _h.py note)."""

from __future__ import annotations

import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND.parent
PROFILES_DIR = REPO_ROOT / "infrastructure" / "env" / "profiles"
LOCAL_PROFILE_PATH = PROFILES_DIR / "sp2-local-mvp.profile.json"
CLOUD_TEMPLATE_PROFILE_PATH = PROFILES_DIR / "sp2-cloud-template.profile.json"
