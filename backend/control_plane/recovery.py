"""Recovery compensation + orphan visibility (IC-002 Recovery & Compensation; PRD 07D-2b.2b).

The recovery-core safety layer for the FIRST governed ``DROP DATABASE`` caller:

* ``RecoveryCompensationService`` — the explicit, audited ``DeprovisionTenantDatabase``
  compensation operation. NEVER automatic, never silent: every call emits the IC-002
  ``TenantDeprovisionRequested`` record first and exactly one terminal record
  (``TenantDeprovisionCompleted`` | ``TenantDeprovisionFailed``). A DROP happens ONLY after
  the full ownership-proof quintuple (§7) passes AND the §7.1 pre-DROP re-validation
  (TOCTOU) re-proves the non-content subset immediately before the destructive step.
* ``OrphanScanService`` — the READ-ONLY ``ScanForOrphans`` operation: classifies every
  candidate physical database and registry record into the IC-002 orphan table rows.
  No state change, no audit events, no DROP, no registry write, and a credential-free,
  deterministic report shape.
* ``RecoveryInspectionPort`` — the abstract live-inspection boundary these services consume.
  The concrete PostgreSQL adapter lives under ``adapters/providers/**`` (Driver Containment
  Standard — this module imports NO database driver); ``InMemoryRecoveryInspection`` is the
  pure-stdlib double for the default composition and the unit suite.

Ownership-proof quintuple (PRD 07D-2b.2b §7; Readiness Report §12):

    1. Registry proof        — record exists; state ∈ {Provisioning, Failed, Quarantined}.
    2. Target recomputation  — target derived from tenant_id by ``tenant_database_name``
                               (never caller-supplied), inside the ``sp2_tenant_*``
                               namespace, and ≠ the Control database.
    3. Association-ref proof — the stored association has the canonical
                               ``tenant/<tenant_id>/dsn`` shape for THIS tenant.
    4. Content-safety proof  — the database is EMPTY or BOOTSTRAP-ONLY by the exact R1-3
                               census below; anything beyond bootstrap is evidence and is
                               never dropped.
    5. Ledger non-collision  — no OTHER tenant's distinctness evidence identifies the same
                               physical database; the tenant's OWN recorded evidence (if
                               any) must match the observed physical identity
                               (fingerprint mismatch fails closed).

Failure of any element: NO DROP, a ``TenantDeprovisionFailed`` record, quarantine where
applicable (R1-5: only when the current state ∈ {Provisioning, Failed} — an
already-Quarantined tenant STAYS), and never a registry-record deletion.

References only (D-14): the report and every audit record carry identifiers and category
reasons — never a credential, DSN, or business payload. B5-BLK-4 remains OPEN; the Physical
Multi-Database MVP remains mandatory and is NOT completed by this module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from . import events
from .audit import ControlPlaneAudit
from .distinctness import DistinctnessEvidence, DistinctnessLedger
from .onboarding import tenant_id_from_dsn_ref
from .ports import ControlStore
from .provisioning import DEFAULT_TENANT_DB_PREFIX, ProvisioningOperator, tenant_database_name
from .records import TenantLifecycleState, TenantRecord
from .registry import TenantRegistry


class RecoveryError(Exception):
    """Non-sensitive recovery/compensation error (fail closed; mapped at the edge)."""


# ---------------------------------------------------------------------------------------
# Inspection port + evidence shape (pure domain — no driver import in this module)
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class DatabaseInspection:
    """Reference-only physical inspection of ONE candidate database.

    ``user_tables`` maps fully-qualified ``schema.relation`` names (all non-system schemas)
    to row counts. The postgres adapter surfaces every DATA-BEARING relation (AT-PMV46-1):
    ordinary tables are counted; materialized views and foreign tables surface with ``-1``;
    a synthetic ``pg_catalog.pg_largeobject`` entry marks large-object presence. A count of
    ``-1`` means "not safely countable" (fail-closed: any allowed name carrying ``-1``
    violates its count rule, and any other name is outside the bootstrap set ⇒ evidence).
    Carries identifiers only — never a credential or payload."""

    database_name: str
    system_identifier: str  # PostgreSQL cluster system identifier ("" in the in-memory plane)
    database_identity: str  # database-level identity, e.g. "datname:oid"
    user_tables: Mapping[str, int] = field(default_factory=dict)
    agents_total: int = 0  # rows in public.agents (0 if the table is absent)
    agents_system_primary: int = 0  # rows in public.agents with agent_kind='system_primary'
    schema_versions: Tuple[str, ...] = ()  # distinct version values in public.schema_version

    @property
    def fingerprint(self) -> str:
        """The physical-database fingerprint — same shape as ``DistinctnessEvidence``."""
        return f"{self.system_identifier}::{self.database_identity}"


class RecoveryInspectionPort(ABC):
    """Live-inspection boundary for compensation + orphan scan (fail-closed).

    Every method returns ``None`` on ANY error (a partial census is never treated as safe);
    the concrete PostgreSQL adapter (``adapters/providers/postgres_recovery_inspection.py``)
    connects lazily, short-lived, by secret REFERENCE only, and never writes."""

    @abstractmethod
    def list_candidate_databases(self) -> Optional[Sequence[str]]:
        """Names of physical databases inside the tenant namespace (``sp2_tenant_*``)."""

    @abstractmethod
    def database_exists(self, target: str) -> Optional[bool]:
        """Whether the target database exists (None = could not determine — fail closed)."""

    @abstractmethod
    def inspect_database(self, target: str) -> Optional[DatabaseInspection]:
        """Content census + physical identity of an EXISTING target (None = fail closed)."""

    @abstractmethod
    def control_database_name(self) -> Optional[str]:
        """The Control database's name (None = unavailable — fail closed, never guessed)."""


class InMemoryRecoveryInspection(RecoveryInspectionPort):
    """Pure-stdlib inspection double (default composition + unit suite).

    Databases are either explicitly seeded (``set_database``) or derived from a live view of
    the in-memory operator's provisioned targets (each an EMPTY database). ``on_inspect`` is
    a test seam for the §7.1 TOCTOU proof — it runs DURING inspection, between the first
    ownership proof and the pre-DROP re-validation. The ``fail_*`` switches exercise the
    fail-closed (None) legs."""

    def __init__(
        self,
        *,
        control_database_name: str,
        provisioned_view: Optional[Callable[[], Set[str]]] = None,
    ) -> None:
        self._control_name = control_database_name
        self._provisioned_view: Callable[[], Set[str]] = provisioned_view or (lambda: set())
        self._inspections: Dict[str, DatabaseInspection] = {}
        self._dropped: Set[str] = set()
        self.on_inspect: Optional[Callable[[str], None]] = None  # TOCTOU test seam (R1-9)
        self.fail_inventory = False
        self.fail_exists = False
        self.fail_inspect = False
        self.fail_control_name = False

    def set_database(self, inspection: DatabaseInspection) -> None:
        self._inspections[inspection.database_name] = inspection
        self._dropped.discard(inspection.database_name)

    def remove_database(self, name: str) -> None:
        self._inspections.pop(name, None)
        self._dropped.add(name)

    def _known(self) -> Set[str]:
        return (set(self._inspections) | self._provisioned_view()) - self._dropped

    def list_candidate_databases(self) -> Optional[Sequence[str]]:
        if self.fail_inventory:
            return None
        return sorted(n for n in self._known() if n.startswith(DEFAULT_TENANT_DB_PREFIX))

    def database_exists(self, target: str) -> Optional[bool]:
        if self.fail_exists:
            return None
        return target in self._known()

    def inspect_database(self, target: str) -> Optional[DatabaseInspection]:
        if self.on_inspect is not None:
            self.on_inspect(target)  # test seam: mutate state between proof and re-validation
        if self.fail_inspect:
            return None
        if target in self._inspections:
            return self._inspections[target]
        if target in self._known():
            # A provisioned-but-never-applied target is an EMPTY database (the in-memory
            # operator records intent and creates nothing — mirrored as a table-less census).
            return DatabaseInspection(
                database_name=target,
                system_identifier="",
                database_identity=f"{target}:db",
            )
        return None

    def control_database_name(self) -> Optional[str]:
        if self.fail_control_name:
            return None
        return self._control_name


# ---------------------------------------------------------------------------------------
# Content-safety census (§7 element 4 — the EXACT R1-3 rules; never judgment)
# ---------------------------------------------------------------------------------------

CONTENT_EMPTY = "empty"
CONTENT_BOOTSTRAP_ONLY = "bootstrap_only"
CONTENT_NON_EMPTY = "non_empty"

_SEED_TABLE = "public.agents"
_SENTINEL_TABLE = "dv_sentinel.marker"
_VERSION_TABLE = "public.schema_version"

# The applicator's DDL family — verified against the tenant DDL at execution time
# (infrastructure/db/provisioning/001-002 + lineage/001 + tenant/001-007; the role templates
# create no tables). ANY observed user table outside this set ⇒ non-empty ⇒ evidence.
BOOTSTRAP_TABLE_SET = frozenset(
    {
        # provisioning bootstrap (001_tenant_database.sql, 002_distinctness_sentinel.sql)
        _VERSION_TABLE,
        _SENTINEL_TABLE,
        # lineage family (lineage/001_lineage_schema.sql)
        "public.lineage",
        "public.lineage_segment",
        "public.import_job",
        "public.import_idempotency",
        "public.import_checkpoint",
        # tenant business schema (tenant/001-005)
        _SEED_TABLE,
        "public.ai_agents",
        "public.startups",
        "public.investors",
        "public.deals",
        # ownership tables (tenant/006_ownership.sql)
        "public.startup_ownership",
        "public.investor_ownership",
        "public.deal_ownership",
        "public.startup_ai_ownership",
        "public.investor_ai_ownership",
        "public.deal_ai_ownership",
        # link tables (tenant/007_links.sql)
        "public.startup_contacts",
        "public.investor_contacts",
        "public.startup_investors",
    }
)


def classify_content(inspection: DatabaseInspection, *, supported_schema_versions: Iterable[str]) -> str:
    """The EXACT bootstrap-only census (R1-3; fixes the Readiness §23 R-3 obligation).

    Rules — mechanical, never judgment:
      * zero user tables                                → ``empty``
      * observed user-table set ⊄ BOOTSTRAP_TABLE_SET   → ``non_empty`` (extra table = evidence)
      * ``public.agents``: EXACTLY one row and it is the ``system_primary`` platform seed
      * ``public.schema_version``: platform-applied version rows only (every distinct value
        inside the supported version family)
      * ``dv_sentinel.marker``: UNRESTRICTED row count (verification artifacts are
        bootstrap-compatible — Readiness §23 R-3)
      * every other bootstrap table: ZERO rows
    ANY rule failure ⇒ ``non_empty`` ⇒ evidence ⇒ never dropped (fail closed; an unknowable
    row count of ``-1`` fails every count rule)."""
    tables = dict(inspection.user_tables)
    if not tables:
        return CONTENT_EMPTY
    if not set(tables) <= BOOTSTRAP_TABLE_SET:
        return CONTENT_NON_EMPTY
    supported = frozenset(supported_schema_versions)
    for name, count in tables.items():
        if name == _SENTINEL_TABLE:
            continue  # unrestricted (R1-3): sentinel artifacts are bootstrap-compatible
        if name == _SEED_TABLE:
            if count != 1 or inspection.agents_total != 1 or inspection.agents_system_primary != 1:
                return CONTENT_NON_EMPTY
            continue
        if name == _VERSION_TABLE:
            if count < 0 or not inspection.schema_versions or any(v not in supported for v in inspection.schema_versions):
                return CONTENT_NON_EMPTY
            continue
        if count != 0:
            return CONTENT_NON_EMPTY
    return CONTENT_BOOTSTRAP_ONLY


# ---------------------------------------------------------------------------------------
# DeprovisionTenantDatabase — explicit-only compensation (§7/§8)
# ---------------------------------------------------------------------------------------

# §7 element 1: the ONLY deprovision-eligible lifecycle states.
DEPROVISION_ELIGIBLE_STATES = frozenset(
    {
        TenantLifecycleState.PROVISIONING,
        TenantLifecycleState.FAILED,
        TenantLifecycleState.QUARANTINED,
    }
)

# R1-5: quarantine_tenant's allowed_from — quarantine on proof failure ONLY from these.
_QUARANTINE_ELIGIBLE_STATES = frozenset({TenantLifecycleState.PROVISIONING, TenantLifecycleState.FAILED})

# Non-sensitive refusal/outcome reasons (identifiers/categories only — never secrets).
REASON_DEPROVISIONED = "deprovisioned"
REASON_ABSENT_NOOP = "absent_noop"
REASON_UNKNOWN_TENANT = "unknown_tenant"
REASON_INELIGIBLE_STATE = "ineligible_lifecycle_state"
REASON_OUTSIDE_NAMESPACE = "target_outside_tenant_namespace"
REASON_CONTROL_TARGET = "control_database_target"
REASON_CONTROL_UNAVAILABLE = "control_identity_unavailable"
REASON_NON_CANONICAL_REF = "non_canonical_association_ref"
REASON_CONTENT_NOT_EMPTY = "content_not_empty"
REASON_LEDGER_COLLISION = "ledger_collision"
REASON_FINGERPRINT_MISMATCH = "fingerprint_mismatch"
REASON_INSPECTION_UNAVAILABLE = "inspection_unavailable"
REASON_DEPROVISION_FAILED = "deprovision_failed"

# Isolation/integrity-class proof failures — quarantine where applicable (R1-5). Transient/
# environmental refusals (inspection or control identity unavailable, operator failure,
# concurrent-state re-validation) hold the current state without a quarantine transition.
_ANOMALY_REASONS = frozenset(
    {
        REASON_OUTSIDE_NAMESPACE,
        REASON_CONTROL_TARGET,
        REASON_NON_CANONICAL_REF,
        REASON_CONTENT_NOT_EMPTY,
        REASON_LEDGER_COLLISION,
        REASON_FINGERPRINT_MISMATCH,
    }
)

# The ledger read below needs the FULL evidence inventory; ``evidence_excluding``'s parameter
# is a tenant id to omit, and the empty string is never an admissible tenant id (admission
# guard: ^[a-z0-9_]+$), so excluding it returns everything. The DistinctnessLedger port and
# its write path are UNCHANGED (read-only use).
_NO_TENANT = ""


@dataclass(frozen=True)
class DeprovisionOutcome:
    """Result of one explicit DeprovisionTenantDatabase request (reference-only)."""

    tenant_id: str
    target: str
    dropped: bool  # the operator's DROP ran and succeeded
    completed: bool  # a TenantDeprovisionCompleted terminal was recorded (drop or safe no-op)
    reason: str  # non-sensitive category (REASON_* above)


class RecoveryCompensationService:
    """Explicit-only, ownership-proof-gated tenant-database compensation (IC-002).

    The ONLY authorized caller of ``ProvisioningOperator.deprovision`` (the first governed
    ``DROP DATABASE`` path). Accepts a ``tenant_id`` plus actor/correlation context ONLY —
    never a database name, DSN, or connection string (§7.2). Emits the IC-002
    Requested/Completed/Failed audit trail; quarantines on anomaly-class proof failure where
    the lifecycle state allows (R1-5); never deletes a registry record; never runs
    automatically (no onboarding/verification/recover/scan path calls this)."""

    def __init__(
        self,
        registry: TenantRegistry,
        operator: ProvisioningOperator,
        audit: ControlPlaneAudit,
        inspection: RecoveryInspectionPort,
        ledger: DistinctnessLedger,
        *,
        supported_schema_versions: Iterable[str],
    ) -> None:
        self._registry = registry
        self._operator = operator
        self._audit = audit
        self._inspection = inspection
        self._ledger = ledger
        self._supported = frozenset(supported_schema_versions)

    # -- public operation --------------------------------------------------------------
    def deprovision_tenant_database(self, tenant_id: str, *, actor: str, correlation_id: str) -> DeprovisionOutcome:
        """Explicit DeprovisionTenantDatabase (IC-002 Recovery & Compensation).

        Request-shaped: emits ``TenantDeprovisionRequested`` on entry and EXACTLY ONE
        terminal record. The target is RECOMPUTED from ``tenant_id`` (never accepted from
        the caller). Idempotency is by OUTCOME (§8.3): an absent target under a fully
        proven non-content quintuple is a safe no-op ``Completed``; everything else that
        cannot be proven fails closed with NO DROP."""
        target = tenant_database_name(tenant_id)  # §7.2: recomputed, never caller-supplied
        self._event(tenant_id, events.TENANT_DEPROVISION_REQUESTED, actor, correlation_id)

        # §7 elements 1 + 2 + 5 (name-leg) — the non-content proof.
        failure = self._non_content_proof(tenant_id, target, fingerprint=None)
        if failure is None:
            # §7 element 3 — canonical association-reference shape for THIS tenant.
            record = self._registry.get_tenant_status(tenant_id)
            assert record is not None  # element 1 just proved existence
            if tenant_id_from_dsn_ref(record.database_association_ref.store_ref) != tenant_id:
                failure = REASON_NON_CANONICAL_REF
        if failure is not None:
            return self._fail(tenant_id, target, failure, actor, correlation_id)

        exists = self._inspection.database_exists(target)
        if exists is None:
            return self._fail(tenant_id, target, REASON_INSPECTION_UNAVAILABLE, actor, correlation_id)
        if exists is False:
            # §8.3 idempotency by outcome: the non-content proof identifies the same eligible
            # tenant and the target is already absent — a safe no-op completion (no DROP).
            self._event(tenant_id, events.TENANT_DEPROVISION_COMPLETED, actor, correlation_id)
            return DeprovisionOutcome(tenant_id=tenant_id, target=target, dropped=False, completed=True, reason=REASON_ABSENT_NOOP)

        # §7 element 4 — content-safety census on the live target (the inspection is the slow
        # I/O step — the §7.1 window the pre-DROP re-validation below exists to close).
        inspection = self._inspection.inspect_database(target)
        if inspection is None:
            return self._fail(tenant_id, target, REASON_INSPECTION_UNAVAILABLE, actor, correlation_id)
        own_evidence = dict(self._ledger.evidence_excluding(_NO_TENANT)).get(tenant_id)
        if own_evidence is not None and (own_evidence.fingerprint != inspection.fingerprint or own_evidence.observed_target != target):
            # The tenant's own recorded physical identity disagrees with the observed one —
            # a swapped/restored database is evidence, never a droppable target (§7 element 5).
            return self._fail(tenant_id, target, REASON_FINGERPRINT_MISMATCH, actor, correlation_id)
        if classify_content(inspection, supported_schema_versions=self._supported) == CONTENT_NON_EMPTY:
            return self._fail(tenant_id, target, REASON_CONTENT_NOT_EMPTY, actor, correlation_id)

        # §7.1 TOCTOU rule (R1-9) + §7 element 5 fingerprint legs: ONE final re-validation of
        # the critical non-content proof IMMEDIATELY before the destructive step — re-reads
        # the registry state, the Control-DB identity, and the full ledger inventory fresh
        # (now with the observed fingerprint, covering BOTH the other-tenant loop and the
        # tenant's OWN recorded evidence — AT-PMV46-2). A concurrent state/ledger/identity
        # change between the first proof and this point refuses with NO DROP. MR-13 kill site.
        failure = self._non_content_proof(tenant_id, target, fingerprint=inspection.fingerprint)
        if failure is not None:
            return self._fail(tenant_id, target, failure, actor, correlation_id)

        try:
            self._operator.deprovision(target=target)
        except Exception:
            # Operational failure (not an integrity anomaly): terminal Failed, no quarantine,
            # no state change — never a partial/ambiguous success (fail closed).
            return self._fail(tenant_id, target, REASON_DEPROVISION_FAILED, actor, correlation_id, quarantine=False)
        self._event(tenant_id, events.TENANT_DEPROVISION_COMPLETED, actor, correlation_id)
        return DeprovisionOutcome(tenant_id=tenant_id, target=target, dropped=True, completed=True, reason=REASON_DEPROVISIONED)

    # -- internals -----------------------------------------------------------------------
    def _non_content_proof(self, tenant_id: str, target: str, *, fingerprint: Optional[str]) -> Optional[str]:
        """§7 elements 1, 2 and 5 — the subset the §7.1 re-validation re-proves.

        Element 5 is re-proven on BOTH legs once the observed fingerprint is known
        (``fingerprint is not None``): the other-tenant collision loop AND the tenant's
        OWN recorded identity (AT-PMV46-2). Elements 3 (canonical ref shape) and 4 (the
        content census) are proven once, before the inspection I/O — the content leg is a
        documented residual of the deferred 07D-2c atomic operation. Returns a
        non-sensitive failure reason, or None when every element holds. The target is
        re-derived by the caller from ``tenant_id`` on every call (element 2's
        recomputation); this function re-reads the registry, the Control-DB identity, and
        the ledger inventory fresh each time (nothing is trusted from an earlier pass)."""
        record = self._registry.get_tenant_status(tenant_id)
        if record is None:
            return REASON_UNKNOWN_TENANT
        if record.lifecycle_state not in DEPROVISION_ELIGIBLE_STATES:
            return REASON_INELIGIBLE_STATE
        if not target.startswith(DEFAULT_TENANT_DB_PREFIX):
            return REASON_OUTSIDE_NAMESPACE
        control_name = self._inspection.control_database_name()
        if control_name is None:
            return REASON_CONTROL_UNAVAILABLE  # cannot prove ≠ Control DB -> fail closed
        if target == control_name:
            return REASON_CONTROL_TARGET  # the Control database is never droppable
        for evidence in self._ledger.evidence_excluding(tenant_id).values():
            if evidence.observed_target == target:
                return REASON_LEDGER_COLLISION
            if fingerprint is not None and evidence.fingerprint == fingerprint:
                return REASON_LEDGER_COLLISION
        if fingerprint is not None:
            # AT-PMV46-2 (PR #46 pre-merge V-2): re-prove the OWN-evidence leg of element 5
            # inside the §7.1 window. The loop above deliberately EXCLUDES this tenant's own
            # row, so without this re-check a concurrent write of the tenant's own evidence
            # (e.g. a parallel verifier immediately before its READY commit) landing between
            # the pre-census fingerprint check and the DROP would be invisible to the final
            # re-validation. Fail closed: recorded identity must match the observed one.
            own = dict(self._ledger.evidence_excluding(_NO_TENANT)).get(tenant_id)
            if own is not None and (own.fingerprint != fingerprint or own.observed_target != target):
                return REASON_FINGERPRINT_MISMATCH
        return None

    def _fail(
        self,
        tenant_id: str,
        target: str,
        reason: str,
        actor: str,
        correlation_id: str,
        *,
        quarantine: bool = True,
    ) -> DeprovisionOutcome:
        """Terminal refusal: quarantine where applicable (R1-5), then the Failed record.

        Quarantine fires ONLY for isolation/integrity-class reasons AND only when the
        current state is inside ``quarantine_tenant``'s allowed_from ({Provisioning,
        Failed}); an already-Quarantined tenant STAYS (a re-quarantine would raise) and
        ineligible states keep the Requested→Failed trail with zero state change."""
        if quarantine and reason in _ANOMALY_REASONS:
            record = self._registry.get_tenant_status(tenant_id)
            if record is not None and record.lifecycle_state in _QUARANTINE_ELIGIBLE_STATES:
                self._registry.quarantine_tenant(tenant_id, actor=actor, correlation_id=correlation_id)
                self._event(tenant_id, events.TENANT_QUARANTINED, actor, correlation_id)
        self._event(tenant_id, events.TENANT_DEPROVISION_FAILED, actor, correlation_id)
        return DeprovisionOutcome(tenant_id=tenant_id, target=target, dropped=False, completed=False, reason=reason)

    def _event(self, tenant_id: str, action: str, actor: str, correlation_id: str) -> None:
        """Reference-only operational-audit event (frozen ``events`` vocabulary)."""
        self._audit.record(
            actor=actor,
            tenant_id=tenant_id,
            action=action,
            from_state=None,
            to_state=None,
            correlation_id=correlation_id,
        )


# ---------------------------------------------------------------------------------------
# ScanForOrphans — read-only classification (§9)
# ---------------------------------------------------------------------------------------

# Association-reference status (shape-based ONLY — the scan never resolves a secret).
REF_CANONICAL = "canonical"
REF_NON_CANONICAL = "non_canonical"
REF_NO_RECORD = "no_record"

# Classification rows (§9.2; Readiness §13) — deterministic, non-sensitive labels.
CLASS_ELIGIBLE_EMPTY = "eligible_empty"
CLASS_ELIGIBLE_BOOTSTRAP_ONLY = "eligible_bootstrap_only"
CLASS_NON_EMPTY_EVIDENCE = "non_empty_evidence"
CLASS_ACTIVE_TENANT = "active_tenant"
CLASS_NO_REGISTRY_RECORD = "db_no_registry_record"
CLASS_REGISTRY_NO_DATABASE = "registry_record_database_absent"
CLASS_LEDGER_COLLISION = "ledger_collision"
CLASS_FINGERPRINT_MISMATCH = "fingerprint_mismatch"
CLASS_CONTROL_DB_TARGET = "control_db_targeted"
CLASS_UNINSPECTABLE = "uninspectable"

ACTION_EXPLICIT_DEPROVISION = "explicit_deprovision_eligible"
ACTION_PRESERVE_EVIDENCE = "preserve_evidence"
ACTION_MANUAL_REVIEW = "manual_review"
ACTION_NONE = "no_action"


@dataclass(frozen=True)
class OrphanScanEntry:
    """One row of the read-only orphan report (§9.3) — credential-free, deterministic."""

    tenant_id: Optional[str]
    database_name: str
    registry_state: Optional[str]
    association_ref_status: str  # canonical | non_canonical | no_record
    content_class: Optional[str]  # empty | bootstrap_only | non_empty | None (absent/uninspectable)
    ledger_conflict: bool
    fingerprint_mismatch: bool
    control_db_target: bool
    classification: str
    recommended_action: str
    safe_to_deprovision: bool
    reason: str


class OrphanScanService:
    """Read-only ``ScanForOrphans`` (§9): classification and visibility ONLY.

    Never mutates lifecycle state, never emits an audit event, never calls deprovision,
    never drops or writes anything, and never repairs an association reference. The report
    carries identifiers and category strings only — no credentials (D-14). A failed
    inventory or Control-DB identity read raises ``RecoveryError`` (fail closed) rather
    than returning a partial report."""

    def __init__(
        self,
        store: ControlStore,
        inspection: RecoveryInspectionPort,
        ledger: DistinctnessLedger,
        *,
        supported_schema_versions: Iterable[str],
    ) -> None:
        self._store = store
        self._inspection = inspection
        self._ledger = ledger
        self._supported = frozenset(supported_schema_versions)

    def scan_for_orphans(self) -> List[OrphanScanEntry]:
        names = self._inspection.list_candidate_databases()
        if names is None:
            raise RecoveryError("orphan inventory unavailable (fail closed)")
        control_name = self._inspection.control_database_name()
        if control_name is None:
            raise RecoveryError("control database identity unavailable (fail closed)")
        inventory = sorted(set(names))
        all_evidence = dict(self._ledger.evidence_excluding(_NO_TENANT))
        entries: List[OrphanScanEntry] = []

        for name in inventory:
            entries.append(self._classify_database(name, control_name, all_evidence))

        # Registry sweep: records whose recomputed target has NO physical database.
        for tenant_id in sorted(set(self._store.list_tenant_ids())):
            target = tenant_database_name(tenant_id)
            if target in set(inventory):
                continue  # covered by the database-side row above
            record = self._store.get_tenant(tenant_id)
            if record is None:
                continue
            entries.append(
                OrphanScanEntry(
                    tenant_id=tenant_id,
                    database_name=target,
                    registry_state=record.lifecycle_state.value,
                    association_ref_status=self._ref_status(record),
                    content_class=None,
                    ledger_conflict=False,
                    fingerprint_mismatch=False,
                    control_db_target=target == control_name,
                    classification=CLASS_CONTROL_DB_TARGET if target == control_name else CLASS_REGISTRY_NO_DATABASE,
                    recommended_action=ACTION_MANUAL_REVIEW,
                    safe_to_deprovision=False,
                    reason="registry record present; physical database absent",
                )
            )
        return sorted(entries, key=lambda e: (e.database_name, e.tenant_id or ""))

    # -- internals -----------------------------------------------------------------------
    def _ref_status(self, record: Optional[TenantRecord]) -> str:
        if record is None:
            return REF_NO_RECORD
        if tenant_id_from_dsn_ref(record.database_association_ref.store_ref) == record.tenant_id:
            return REF_CANONICAL
        return REF_NON_CANONICAL

    def _classify_database(
        self,
        name: str,
        control_name: str,
        all_evidence: Mapping[str, DistinctnessEvidence],
    ) -> OrphanScanEntry:
        tenant_id = name[len(DEFAULT_TENANT_DB_PREFIX) :] if name.startswith(DEFAULT_TENANT_DB_PREFIX) else None
        record = self._store.get_tenant(tenant_id) if tenant_id else None
        state = record.lifecycle_state.value if record is not None else None
        ref_status = self._ref_status(record)
        control_target = name == control_name

        inspection = self._inspection.inspect_database(name)
        if inspection is None:
            return OrphanScanEntry(
                tenant_id=record.tenant_id if record is not None else None,
                database_name=name,
                registry_state=state,
                association_ref_status=ref_status,
                content_class=None,
                ledger_conflict=False,
                fingerprint_mismatch=False,
                control_db_target=control_target,
                classification=CLASS_UNINSPECTABLE,
                recommended_action=ACTION_MANUAL_REVIEW,
                safe_to_deprovision=False,
                reason="content census unavailable (fail closed)",
            )

        content = classify_content(inspection, supported_schema_versions=self._supported)
        ledger_conflict = False
        fingerprint_mismatch = False
        for other_id, evidence in all_evidence.items():
            if record is not None and other_id == record.tenant_id:
                if evidence.observed_target != name or evidence.fingerprint != inspection.fingerprint:
                    fingerprint_mismatch = True
                continue
            if evidence.observed_target == name or evidence.fingerprint == inspection.fingerprint:
                ledger_conflict = True

        if control_target:
            classification, action, safe, reason = (
                CLASS_CONTROL_DB_TARGET,
                ACTION_MANUAL_REVIEW,
                False,
                "candidate resolves to the Control database (never droppable)",
            )
        elif record is None:
            classification, action, safe, reason = (
                CLASS_NO_REGISTRY_RECORD,
                ACTION_MANUAL_REVIEW,
                False,
                "physical database has no registry record (report-only; never touched)",
            )
        elif ledger_conflict:
            classification, action, safe, reason = (
                CLASS_LEDGER_COLLISION,
                ACTION_MANUAL_REVIEW,
                False,
                "another tenant's distinctness evidence identifies this database",
            )
        elif fingerprint_mismatch:
            classification, action, safe, reason = (
                CLASS_FINGERPRINT_MISMATCH,
                ACTION_MANUAL_REVIEW,
                False,
                "recorded physical identity disagrees with the observed database",
            )
        elif record.lifecycle_state not in DEPROVISION_ELIGIBLE_STATES:
            classification, action, safe, reason = (
                CLASS_ACTIVE_TENANT,
                ACTION_NONE,
                False,
                "lifecycle state is not compensation-eligible",
            )
        elif content == CONTENT_NON_EMPTY:
            classification, action, safe, reason = (
                CLASS_NON_EMPTY_EVIDENCE,
                ACTION_PRESERVE_EVIDENCE,
                False,
                "content beyond bootstrap is evidence (never dropped)",
            )
        elif ref_status != REF_CANONICAL:
            classification, action, safe, reason = (
                CLASS_UNINSPECTABLE,
                ACTION_MANUAL_REVIEW,
                False,
                "association reference is not canonical for this tenant",
            )
        else:
            eligible_empty = content == CONTENT_EMPTY
            classification = CLASS_ELIGIBLE_EMPTY if eligible_empty else CLASS_ELIGIBLE_BOOTSTRAP_ONLY
            action, safe = ACTION_EXPLICIT_DEPROVISION, True
            reason = "ownership-proof preconditions hold (explicit deprovision only)"

        return OrphanScanEntry(
            tenant_id=record.tenant_id if record is not None else None,
            database_name=name,
            registry_state=state,
            association_ref_status=ref_status,
            content_class=content,
            ledger_conflict=ledger_conflict,
            fingerprint_mismatch=fingerprint_mismatch,
            control_db_target=control_target,
            classification=classification,
            recommended_action=action,
            safe_to_deprovision=safe,
            reason=reason,
        )
