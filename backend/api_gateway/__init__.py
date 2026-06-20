"""api_gateway — SnackPortal2 API Gateway (Build Phase 7).

The single approved ingress (IC-010 §A; D-37 §5). An enforcement boundary, not a
decision-maker: it authenticates (consumes IC-005 output), validates carriers,
constructs the canonical RequestContext exclusively from AuthContext, dispatches by
path/operation, hands the context to the Database Router over a transport port, and
emits the §J audit set — it never resolves a database, decides ownership, or runs
business logic. Framework-agnostic core (no web framework dependency); the concrete
HTTP binding is a transport detail. Imports only `shared` + stdlib (DAG independence).
"""

from __future__ import annotations

GOVERNING_CONTRACTS = ["IC-010", "IC-005", "IC-002", "IC-001"]
BUILD_PHASE = 7
IMPLEMENTS_BEHAVIOR = True
