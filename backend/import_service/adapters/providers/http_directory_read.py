"""Production DirectoryReadPort over HTTP (stdlib urllib) — Control Plane Read API.

Transport-only access to the Global Discovery Platform directory reads; NO in-process
import of control_plane (DAG). Returns None on 404 (consistent denial). Not exercised by
the stdlib unit suite by default; a best-effort loopback test exercises the real path.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from import_service.ports import DirectoryPage, DirectoryReadPort, GlobalDirectoryRecordView


class HttpDirectoryRead(DirectoryReadPort):
    def __init__(self, base_url: str, timeout: float = 2.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def _get(self, path: str) -> Optional[dict]:
        req = urllib.request.Request(self._base + path, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # internal control-plane URL
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    @staticmethod
    def _view(data: dict) -> GlobalDirectoryRecordView:
        return GlobalDirectoryRecordView(
            directory=data["directory"], record_id=data["record_id"],
            display_name=data["display_name"], attributes=dict(data.get("attributes") or {}),
        )

    def get_record(self, kind: str, record_id: str) -> Optional[GlobalDirectoryRecordView]:
        data = self._get(f"/directory/{urllib.parse.quote(kind)}/{urllib.parse.quote(record_id)}")
        return self._view(data) if data else None

    def page(self, kind: str, cursor: Optional[str], limit: int) -> DirectoryPage:
        q = "?limit=" + str(limit) + (("&cursor=" + urllib.parse.quote(cursor)) if cursor else "")
        data = self._get(f"/directory/{urllib.parse.quote(kind)}{q}")
        if not data:
            return DirectoryPage(records=[], next_cursor=None)
        return DirectoryPage(
            records=[self._view(r) for r in data.get("records", [])],
            next_cursor=data.get("next_cursor"),
        )
