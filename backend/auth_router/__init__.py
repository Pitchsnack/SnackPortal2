"""auth_router — SnackPortal2 Authentication Layer (Build Phase 3).

DB-free OIDC stateless JWT validation + tenant-context establishment (IC-005):
two-stage model (stateless token validation; control-plane-read tenant context),
hybrid identity (D-03), signed-claim tenant carriage + carrier-match (D-06),
membership/role validation (D-04/D-32), disclosure-safe denials, audited. Performs
no database routing, no tenant-DB access, and no permission evaluation. Consumes the
control plane only via a transport ControlPlaneReadPort (no in-process import).
"""
from __future__ import annotations

GOVERNING_CONTRACTS = ["IC-005", "IC-001", "IC-002", "D-03", "D-04", "D-05", "D-06", "D-30", "D-32"]
BUILD_PHASE = 3
IMPLEMENTS_BEHAVIOR = True
