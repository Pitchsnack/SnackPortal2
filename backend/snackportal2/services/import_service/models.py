"""Import Service wire models (IC-003).

**Import ≠ Synchronization.** An import is a discrete, user-initiated act that produces an
**independent tenant copy** of a global record, carrying a *soft reference* to its source. It is
not a link, not a subscription, and not a mirror: nothing here re-reads the global record later,
and there is no scheduled, background, event-triggered or timer-driven re-import (D-34).

**Global Record ≠ Tenant Record.** After import the two records have separate lives. Editing
the tenant copy never touches the global record, and a later change to the global record never
propagates.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from ...shared.security import RequestContext


class ImportOutcome(str, Enum):
    """What an import attempt actually did.

    ``REPLAYED`` is what makes the operation idempotent: the same source imported twice into the
    same tenant returns the first result rather than producing a second copy. Without it, a
    retried request — a client timeout, a proxy retry — would silently duplicate the record.
    """

    CREATED = "created"
    REPLAYED = "replayed"


class ImportInitiationRequest(BaseModel):
    """Import one global directory record into the caller's single active tenant."""

    context: RequestContext = Field(description="The canonical RequestContext naming the single active tenant.")
    source_ref: str = Field(
        min_length=1,
        max_length=256,
        description="Reference to the global directory record to copy. Carried by reference only; never a payload.",
    )


class ImportResult(BaseModel):
    """The completion envelope of a real, recorded import — references only (IC-009 §D).

    Never carries a tenant row, the source record's content, a database name, a secret, or any
    router detail.
    """

    source_ref: str = Field(description="The global source reference this copy came from.")
    target_tenant_ref: str = Field(description="The signed active tenant the copy was written into.")
    tenant_record_ref: str = Field(description="Reference to the created tenant record. Never a raw row primary key.")
    lineage_ref: str = Field(description="Reference to the lineage row recording this derivation (IC-004).")
    import_id: str = Field(description="Identifier of the import job. Stable across a replay of the same import.")
    outcome: ImportOutcome = Field(description="Whether this call created the copy or replayed an existing import.")


__all__ = ["ImportInitiationRequest", "ImportOutcome", "ImportResult"]
