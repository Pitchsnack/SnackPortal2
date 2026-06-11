"""auth_router adapters. `providers/` holds concrete bindings (JWT crypto, control-plane
read transport, audit sink); it is the only place a runtime library may be imported."""

from __future__ import annotations
