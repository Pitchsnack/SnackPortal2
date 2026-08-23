"""The BFF's enumerated operation surface (IC-013 §16).

Every route here is a **named frontend use case**, declared in the operation taxonomy, backed by
its own Pydantic request and response models, and composed from typed service results. None of
them relays a downstream body: a surface that did would be a gateway route and is forbidden
(§19). Adding an operation is a contract change, not a configuration change.

Each route runs the one approved flow, in order:

    authenticate -> validate carrier -> build RequestContext -> ask Access Control
                 -> resolve one database -> invoke the service -> compose the DTO

**No client request model on this surface carries identity, tenancy, role, or permission.**
Those are all server-derived (3-day plan §10): the tenant comes from the signed claim and
nowhere else, so there is no field a caller could set to reach a different one.

Audit emission uses **only** the classes IC-013 §10 names. The three success-access classes are
``workspace_memberships_read``, ``tenant_startup_read`` and ``tenant_startup_update``; no new
success class is invented for the operations that have none.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Mapping, Optional

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, Field

from ...shared.correlation import CORRELATION_HEADER, current_correlation_id, sanitize_correlation_id
from ...shared.errors import error_responses, not_found
from ...shared.operations import BffOperation
from ...shared.security import RequestContext
from ...shared.types import PlatformRole
from .dtos import (
    DirectoryEntryDTO,
    GlobalInvestorSummaryDTO,
    GlobalStartupSummaryDTO,
    ImportOutcomeDTO,
    ImportResultDTO,
    LineageSummaryDTO,
    MembershipEntryDTO,
    TenantDealDetailDTO,
    TenantDealListDTO,
    TenantInvestorDetailDTO,
    TenantInvestorListDTO,
    TenantStartupDetailDTO,
    TenantStartupListDTO,
    WorkspaceMembershipDTO,
    compose,
    compose_display_ref,
)
from .pipeline import OUTCOME_ALLOWED, EstablishedContext, IngressPipeline
from .ports import ControlReadPort, DomainServicePort

STARTUP_DIRECTORY = "GlobalStartupDirectory"
INVESTOR_DIRECTORY = "GlobalInvestorDirectory"

SHORT_DESCRIPTION_MAX_CHARS = 500

#: The three success-access audit classes IC-013 §10 carries forward. Nothing else is emitted
#: on success, because inventing a fourth would add a class the contract does not name.
ACTION_MEMBERSHIPS_READ = "workspace_memberships_read"
ACTION_STARTUP_READ = "tenant_startup_read"
ACTION_STARTUP_UPDATE = "tenant_startup_update"

RecordRef = Annotated[str, Path(min_length=1, max_length=256, description="Opaque reference to the addressed record.")]
SourceRef = Annotated[str, Path(min_length=1, max_length=256, description="Reference to the global directory record to import.")]
PageLimit = Annotated[int, Query(ge=1, le=500, description="Maximum records to return.")]


# --- Client request models (no identity, no tenancy, no role — all server-derived) -----------

class CreateStartupRequest(BaseModel):
    """Create a Startup in the caller's active tenant. The tenant is never a field here."""

    display_name: str = Field(min_length=1, max_length=256, description="Organization display name. Required.")
    short_description: Optional[str] = Field(
        default=None, max_length=SHORT_DESCRIPTION_MAX_CHARS, description="Bounded free text, at most 500 characters."
    )
    investment_stage: Optional[str] = Field(default=None, max_length=128, description="Investment-stage label.")
    company_url: Optional[str] = Field(default=None, max_length=512, description="Company website. Normalized on write.")
    industry: Optional[str] = Field(default=None, max_length=128, description="Industry label.")
    headquarters_country: Optional[str] = Field(default=None, max_length=128, description="Headquarters country label.")
    headquarters_city: Optional[str] = Field(default=None, max_length=128, description="Headquarters city label.")


class UpdateStartupRequest(BaseModel):
    """Update the one mutable Startup field (IC-009 CLM section, adopted under D-42)."""

    short_description: Optional[str] = Field(
        default=None,
        max_length=SHORT_DESCRIPTION_MAX_CHARS,
        description="Bounded free text at most 500 characters, or null to clear. The only mutable field.",
    )


class CreateInvestorRequest(BaseModel):
    """Create an Investor in the caller's active tenant — the Add My Investor field set."""

    display_name: str = Field(min_length=1, max_length=256, description="Organization display name. Required.")
    investor_type: Optional[str] = Field(default=None, max_length=128, description="Investor type label.")
    website_url: Optional[str] = Field(default=None, max_length=512, description="Investor website. Normalized on write.")
    short_description: Optional[str] = Field(
        default=None, max_length=SHORT_DESCRIPTION_MAX_CHARS, description="Bounded free text, at most 500 characters."
    )
    investment_stage_focus: List[str] = Field(
        default_factory=list, max_length=32, description="Investment stages this investor focuses on."
    )
    industry_focus: List[str] = Field(default_factory=list, max_length=32, description="Industries this investor focuses on.")
    headquarters_country: Optional[str] = Field(default=None, max_length=128, description="Headquarters country label.")
    headquarters_city: Optional[str] = Field(default=None, max_length=128, description="Headquarters city label.")


class UpdateInvestorRequest(BaseModel):
    """Update the one mutable Investor field."""

    short_description: Optional[str] = Field(
        default=None,
        max_length=SHORT_DESCRIPTION_MAX_CHARS,
        description="Bounded free text at most 500 characters, or null to clear. The only mutable field.",
    )


class CreateDealRequest(BaseModel):
    """Create a Deal between two records of the caller's active tenant."""

    deal_name: str = Field(min_length=1, max_length=256, description="Deal display name. Required.")
    startup_ref: str = Field(min_length=1, max_length=256, description="Reference to the tenant Startup this deal concerns.")
    investor_ref: Optional[str] = Field(
        default=None, max_length=256, description="Reference to the tenant Investor, or null for an unmatched deal."
    )
    stage: Optional[str] = Field(default=None, max_length=128, description="Deal stage label.")
    amount: Optional[str] = Field(default=None, max_length=64, description="Deal amount.")
    currency: Optional[str] = Field(default=None, max_length=8, description="ISO currency code.")


class UpdateDealRequest(BaseModel):
    """Update a Deal's stage or status. The parties are never mutable through this operation."""

    stage: Optional[str] = Field(default=None, max_length=128, description="New deal stage label, or null to leave unchanged.")
    status: Optional[str] = Field(default=None, max_length=64, description="New deal status, or null to leave unchanged.")


# --- Composition helpers ------------------------------------------------------------------------

def _startup_detail(record: Mapping[str, Any]) -> TenantStartupDetailDTO:
    """Compose the contract-pinned Startup DTO field by field.

    Field by field on purpose. Passing the service result through — even filtered — would mean a
    new column added downstream could reach the frontend without anyone deciding it should.
    """
    return TenantStartupDetailDTO(
        record_ref=str(record["record_ref"]),
        display_name=str(record.get("company_name") or ""),
        short_description=record.get("short_description"),
        investment_stage=record.get("investment_stage"),
        lineage_reference=record.get("lineage_reference"),
    )


def _investor_detail(record: Mapping[str, Any]) -> TenantInvestorDetailDTO:
    return TenantInvestorDetailDTO(
        record_ref=str(record["record_ref"]),
        display_name=str(record.get("investor_name") or ""),
        short_description=record.get("short_description"),
        investor_type=record.get("investor_type"),
        lineage_reference=record.get("lineage_reference"),
    )


def _deal_detail(record: Mapping[str, Any]) -> TenantDealDetailDTO:
    return TenantDealDetailDTO(
        record_ref=str(record["record_ref"]),
        deal_name=str(record.get("deal_name") or ""),
        startup_ref=str(record.get("startup_ref") or ""),
        investor_ref=record.get("investor_ref"),
        stage=record.get("stage"),
        status=record.get("status"),
    )


def build_router(
    pipeline: IngressPipeline,
    control_read: ControlReadPort,
    domains: Mapping[str, DomainServicePort],
) -> APIRouter:
    """Build the enumerated operation surface over the supplied dependencies."""
    router = APIRouter()

    def bearer(request: Request) -> Optional[str]:
        """Read the client credential.

        Read directly rather than through a security dependency so that a missing credential and
        a malformed one are indistinguishable: both are "no credential", and both produce the
        same canonical 401.
        """
        header = request.headers.get("Authorization", "")
        scheme, _, value = header.partition(" ")
        if scheme.casefold() != "bearer":
            return None
        return value.strip() or None

    def establish(request: Request) -> EstablishedContext:
        # The correlation id comes from the middleware, not from the raw header. Two reasons,
        # both of which the header read got wrong:
        #
        #   * the middleware **mints** one when the client sends none, and reading the header
        #     directly yields "" instead. An empty correlation id is a malformed context, and
        #     the Access Control Service denies malformed contexts on its first line — so every
        #     request without the optional header was answered 403 access_denied; and
        #   * the middleware **sanitizes** what the client did send. The raw value is forwarded
        #     to three services and stored in the audit trail, so an unbounded or
        #     newline-bearing header was a log-injection channel straight through the ingress.
        #
        # ``sanitize_correlation_id`` is the fallback for a router mounted on an application
        # built without the middleware; it mints a fresh id rather than returning nothing.
        correlation_id = current_correlation_id() or sanitize_correlation_id(request.headers.get(CORRELATION_HEADER))
        return pipeline.establish(
            credential=bearer(request),
            headers=dict(request.headers),
            host=request.headers.get("host", ""),
            correlation_id=correlation_id,
        )

    def authorized(request: Request, operation: BffOperation, record_ref: Optional[str] = None) -> RequestContext:
        """Run stages 1-4 and return the context, or raise the canonical denial."""
        established = establish(request)
        pipeline.authorize(established.context, operation, record_ref)
        return established.context

    def routed(context: RequestContext) -> None:
        """Stage 5. Resolve exactly one database before any service is invoked.

        The resolution result is deliberately discarded: the BFF is not permitted to hold a
        connection (D-48 C-1), so what it needs from the router is the *fact* that exactly one
        database bound, not a handle to it.
        """
        pipeline.routing.resolve(context)

    def payload(context: RequestContext, **extra: Any) -> Dict[str, Any]:
        return {"context": context.model_dump(mode="json"), **extra}

    # --- MembershipsForPrincipal (CONTROL) ---------------------------------------------------

    @router.get(
        "/memberships",
        response_model=WorkspaceMembershipDTO,
        summary="List the caller's workspace memberships",
        description=(
            "Return every tenant membership the authenticated principal holds, for the workspace switcher. "
            "Self-scoped: a principal can only ever read its own memberships, because the principal is taken "
            "from the signed claim and there is no parameter to name another. An empty list is a lawful "
            "success. Emits exactly one references-only audit event, including for an empty result."
        ),
        tags=["Workspace"],
        operation_id="listWorkspaceMemberships",
        response_description="The principal's memberships, each carrying tenant, role and a composed display reference.",
        responses=error_responses(401, 403, 503),
    )
    async def list_memberships(request: Request) -> WorkspaceMembershipDTO:
        context = authorized(request, BffOperation.LIST_MEMBERSHIPS)
        raw = control_read.list_memberships(context.principal_ref)
        dto = WorkspaceMembershipDTO(
            memberships=[
                MembershipEntryDTO(
                    tenant_id=str(entry["tenant_ref"]),
                    role=PlatformRole(entry["role"]),
                    display_ref=compose_display_ref(str(entry["tenant_ref"])),
                )
                for entry in raw
            ]
        )
        # The event records the operation, not how many records it returned: never zero, never
        # two, never one per row.
        pipeline.audit.emit(
            action=ACTION_MEMBERSHIPS_READ,
            outcome=OUTCOME_ALLOWED,
            correlation_id=context.correlation_id,
            actor_ref=context.principal_ref,
            subject_ref=context.principal_ref,
        )
        result = compose(dto)
        assert isinstance(result, WorkspaceMembershipDTO)
        return result

    # --- Global Directory Read (CONTROL) -----------------------------------------------------

    @router.get(
        "/directories/startups",
        response_model=GlobalStartupSummaryDTO,
        summary="Read the Global Startup Directory",
        description=(
            "Return the Control-resident Global Startup Directory, in the Control Plane's deterministic "
            "order. Entries are tenant-anonymous: they carry no tenant reference, no membership reference "
            "and no lineage reference, because a global record has no tenant to disclose."
        ),
        tags=["Directory"],
        operation_id="readGlobalStartupDirectory",
        response_description="Tenant-anonymous global startup directory entries with their provenance markers.",
        responses=error_responses(401, 403, 503),
    )
    async def read_startup_directory(request: Request) -> GlobalStartupSummaryDTO:
        context = authorized(request, BffOperation.READ_GLOBAL_STARTUP_DIRECTORY)
        del context
        records = control_read.list_directory(STARTUP_DIRECTORY)
        dto = GlobalStartupSummaryDTO(
            records=[
                DirectoryEntryDTO(record_ref=str(entry["record_ref"]), display_name=str(entry["display_name"]))
                for entry in records
            ]
        )
        result = compose(dto)
        assert isinstance(result, GlobalStartupSummaryDTO)
        return result

    @router.get(
        "/directories/investors",
        response_model=GlobalInvestorSummaryDTO,
        summary="Read the Global Investor Directory",
        description=(
            "Return the Control-resident Global Investor Directory, in the Control Plane's deterministic "
            "order. Entries are tenant-anonymous, on the same terms as the startup directory."
        ),
        tags=["Directory"],
        operation_id="readGlobalInvestorDirectory",
        response_description="Tenant-anonymous global investor directory entries with their provenance markers.",
        responses=error_responses(401, 403, 503),
    )
    async def read_investor_directory(request: Request) -> GlobalInvestorSummaryDTO:
        context = authorized(request, BffOperation.READ_GLOBAL_INVESTOR_DIRECTORY)
        del context
        records = control_read.list_directory(INVESTOR_DIRECTORY)
        dto = GlobalInvestorSummaryDTO(
            records=[
                DirectoryEntryDTO(record_ref=str(entry["record_ref"]), display_name=str(entry["display_name"]))
                for entry in records
            ]
        )
        result = compose(dto)
        assert isinstance(result, GlobalInvestorSummaryDTO)
        return result

    # --- Import Initiation (TENANT) ------------------------------------------------------------

    @router.post(
        "/import/startups/{source_ref}",
        response_model=ImportResultDTO,
        status_code=201,
        summary="Import a global Startup into the active tenant",
        description=(
            "Copy one global directory Startup into the caller's single active tenant, producing an "
            "independent tenant record with a soft reference to its source and one lineage row. The "
            "operation is idempotent per source and tenant: a repeat returns the first result with outcome "
            "'replayed' rather than making a second copy. Import is never synchronization — nothing links, "
            "subscribes, mirrors, or re-reads the global record afterwards."
        ),
        tags=["Import"],
        operation_id="importGlobalStartupIntoTenant",
        response_description="The import completion envelope: source, tenant, record, lineage, job and outcome.",
        responses=error_responses(401, 403, 404, 409, 422, 503),
    )
    async def import_startup(request: Request, source_ref: SourceRef) -> ImportResultDTO:
        context = authorized(request, BffOperation.INITIATE_STARTUP_IMPORT)
        routed(context)
        result = domains["import_service"].call("/internal/import/startup", payload(context, source_ref=source_ref))
        dto = ImportResultDTO(
            source_ref=str(result["source_ref"]),
            target_tenant_ref=str(result["target_tenant_ref"]),
            tenant_record_ref=str(result["tenant_record_ref"]),
            lineage_ref=str(result["lineage_ref"]),
            import_id=str(result["import_id"]),
            outcome=ImportOutcomeDTO(result["outcome"]),
        )
        composed = compose(dto)
        assert isinstance(composed, ImportResultDTO)
        return composed

    # --- Tenant Operations: Startups (TENANT) ---------------------------------------------------

    @router.get(
        "/tenant/startups",
        response_model=TenantStartupListDTO,
        summary="List the active tenant's Startups",
        description=(
            "Return Startup records from the caller's single active tenant, in the service's deterministic "
            "order. The tenant is the signed claim; there is no parameter through which another could be named."
        ),
        tags=["Startups"],
        operation_id="listActiveTenantStartups",
        response_description="Startup details from exactly one tenant database.",
        responses=error_responses(401, 403, 404, 409, 422, 503),
    )
    async def list_startups(request: Request, limit: PageLimit = 100) -> TenantStartupListDTO:
        context = authorized(request, BffOperation.LIST_TENANT_STARTUPS)
        routed(context)
        body = domains["startups"].call("/internal/startups/list", payload(context, limit=limit))
        dto = TenantStartupListDTO(records=[_startup_detail(record) for record in body["records"]])
        composed = compose(dto)
        assert isinstance(composed, TenantStartupListDTO)
        return composed

    @router.get(
        "/tenant/startups/{record_ref}",
        response_model=TenantStartupDetailDTO,
        summary="Read one of the active tenant's Startups",
        description=(
            "Return one Startup record from the caller's single active tenant. A record reference minted "
            "for a different tenant is not found here. Emits one references-only success-access audit event."
        ),
        tags=["Startups"],
        operation_id="readActiveTenantStartup",
        response_description="The contract-pinned tenant Startup detail.",
        responses=error_responses(401, 403, 404, 409, 422, 503),
    )
    async def read_startup(request: Request, record_ref: RecordRef) -> TenantStartupDetailDTO:
        context = authorized(request, BffOperation.READ_TENANT_STARTUP, record_ref)
        routed(context)
        record = domains["startups"].call("/internal/startups/read", payload(context, record_ref=record_ref))
        if record is None:
            raise not_found()
        pipeline.audit.emit(
            action=ACTION_STARTUP_READ,
            outcome=OUTCOME_ALLOWED,
            correlation_id=context.correlation_id,
            actor_ref=context.principal_ref,
            tenant_ref=context.tenant_context,
            record_ref=record_ref,
        )
        composed = compose(_startup_detail(record))
        assert isinstance(composed, TenantStartupDetailDTO)
        return composed

    @router.post(
        "/tenant/startups",
        response_model=TenantStartupDetailDTO,
        status_code=201,
        summary="Create a Startup in the active tenant",
        description=(
            "Create one Startup in the caller's single active tenant. The website is normalized on write "
            "and a malformed URL is rejected. The request carries no tenant, principal, role or permission: "
            "all of those are server-derived from the signed claim."
        ),
        tags=["Startups"],
        operation_id="createActiveTenantStartup",
        response_description="The created Startup, as the contract-pinned tenant detail shape.",
        responses=error_responses(401, 403, 404, 409, 422, 503),
    )
    async def create_startup(request: Request, body: CreateStartupRequest) -> TenantStartupDetailDTO:
        context = authorized(request, BffOperation.CREATE_TENANT_STARTUP)
        routed(context)
        record = domains["startups"].call(
            "/internal/startups/create",
            payload(
                context,
                company_name=body.display_name,
                short_description=body.short_description,
                investment_stage=body.investment_stage,
                company_url=body.company_url,
                industry=body.industry,
                headquarters_country=body.headquarters_country,
                headquarters_city=body.headquarters_city,
            ),
        )
        composed = compose(_startup_detail(record))
        assert isinstance(composed, TenantStartupDetailDTO)
        return composed

    @router.patch(
        "/tenant/startups/{record_ref}",
        response_model=TenantStartupDetailDTO,
        summary="Update one of the active tenant's Startups",
        description=(
            "Update the one mutable Startup field: 'short_description', bounded at 500 characters, or null "
            "to clear. A request carrying any other field is rejected with no partial write. Emits one "
            "references-only success-access audit event."
        ),
        tags=["Startups"],
        operation_id="updateActiveTenantStartup",
        response_description="The updated Startup, as the contract-pinned tenant detail shape.",
        responses=error_responses(401, 403, 404, 409, 422, 503),
    )
    async def update_startup(request: Request, record_ref: RecordRef, body: UpdateStartupRequest) -> TenantStartupDetailDTO:
        context = authorized(request, BffOperation.UPDATE_TENANT_STARTUP, record_ref)
        routed(context)
        record = domains["startups"].call(
            "/internal/startups/update",
            payload(context, record_ref=record_ref, short_description=body.short_description),
        )
        pipeline.audit.emit(
            action=ACTION_STARTUP_UPDATE,
            outcome=OUTCOME_ALLOWED,
            correlation_id=context.correlation_id,
            actor_ref=context.principal_ref,
            tenant_ref=context.tenant_context,
            record_ref=record_ref,
        )
        composed = compose(_startup_detail(record))
        assert isinstance(composed, TenantStartupDetailDTO)
        return composed

    # --- Tenant Operations: Investors (TENANT) --------------------------------------------------

    @router.get(
        "/tenant/investors",
        response_model=TenantInvestorListDTO,
        summary="List the active tenant's Investors",
        description="Return Investor records from the caller's single active tenant, in deterministic order.",
        tags=["Investors"],
        operation_id="listActiveTenantInvestors",
        response_description="Investor details from exactly one tenant database.",
        responses=error_responses(401, 403, 404, 409, 422, 503),
    )
    async def list_investors(request: Request, limit: PageLimit = 100) -> TenantInvestorListDTO:
        context = authorized(request, BffOperation.LIST_TENANT_INVESTORS)
        routed(context)
        body = domains["investors"].call("/internal/investors/list", payload(context, limit=limit))
        composed = compose(TenantInvestorListDTO(records=[_investor_detail(record) for record in body["records"]]))
        assert isinstance(composed, TenantInvestorListDTO)
        return composed

    @router.get(
        "/tenant/investors/{record_ref}",
        response_model=TenantInvestorDetailDTO,
        summary="Read one of the active tenant's Investors",
        description="Return one Investor record from the caller's single active tenant.",
        tags=["Investors"],
        operation_id="readActiveTenantInvestor",
        response_description="The tenant Investor detail.",
        responses=error_responses(401, 403, 404, 409, 422, 503),
    )
    async def read_investor(request: Request, record_ref: RecordRef) -> TenantInvestorDetailDTO:
        context = authorized(request, BffOperation.READ_TENANT_INVESTOR, record_ref)
        routed(context)
        record = domains["investors"].call("/internal/investors/read", payload(context, record_ref=record_ref))
        if record is None:
            raise not_found()
        composed = compose(_investor_detail(record))
        assert isinstance(composed, TenantInvestorDetailDTO)
        return composed

    @router.post(
        "/tenant/investors",
        response_model=TenantInvestorDetailDTO,
        status_code=201,
        summary="Create an Investor in the active tenant",
        description=(
            "Create one Investor in the caller's single active tenant, from the approved Add My Investor "
            "field set. The website is normalized on write and a malformed URL is rejected."
        ),
        tags=["Investors"],
        operation_id="createActiveTenantInvestor",
        response_description="The created Investor, as the tenant detail shape.",
        responses=error_responses(401, 403, 404, 409, 422, 503),
    )
    async def create_investor(request: Request, body: CreateInvestorRequest) -> TenantInvestorDetailDTO:
        context = authorized(request, BffOperation.CREATE_TENANT_INVESTOR)
        routed(context)
        record = domains["investors"].call(
            "/internal/investors/create",
            payload(
                context,
                investor_name=body.display_name,
                investor_type=body.investor_type,
                website_url=body.website_url,
                short_description=body.short_description,
                investment_stage_focus=body.investment_stage_focus,
                industry_focus=body.industry_focus,
                headquarters_country=body.headquarters_country,
                headquarters_city=body.headquarters_city,
            ),
        )
        composed = compose(_investor_detail(record))
        assert isinstance(composed, TenantInvestorDetailDTO)
        return composed

    @router.patch(
        "/tenant/investors/{record_ref}",
        response_model=TenantInvestorDetailDTO,
        summary="Update one of the active tenant's Investors",
        description="Update the one mutable Investor field: 'short_description', bounded at 500 characters.",
        tags=["Investors"],
        operation_id="updateActiveTenantInvestor",
        response_description="The updated Investor, as the tenant detail shape.",
        responses=error_responses(401, 403, 404, 409, 422, 503),
    )
    async def update_investor(request: Request, record_ref: RecordRef, body: UpdateInvestorRequest) -> TenantInvestorDetailDTO:
        context = authorized(request, BffOperation.UPDATE_TENANT_INVESTOR, record_ref)
        routed(context)
        record = domains["investors"].call(
            "/internal/investors/update",
            payload(context, record_ref=record_ref, short_description=body.short_description),
        )
        composed = compose(_investor_detail(record))
        assert isinstance(composed, TenantInvestorDetailDTO)
        return composed

    # --- Tenant Operations: Deals (TENANT) --------------------------------------------------------

    @router.get(
        "/tenant/deals",
        response_model=TenantDealListDTO,
        summary="List the active tenant's Deals",
        description="Return Deal records from the caller's single active tenant, in deterministic order.",
        tags=["Deals"],
        operation_id="listActiveTenantDeals",
        response_description="Deal details from exactly one tenant database.",
        responses=error_responses(401, 403, 404, 409, 422, 503),
    )
    async def list_deals(request: Request, limit: PageLimit = 100) -> TenantDealListDTO:
        context = authorized(request, BffOperation.LIST_TENANT_DEALS)
        routed(context)
        body = domains["deals"].call("/internal/deals/list", payload(context, limit=limit))
        composed = compose(TenantDealListDTO(records=[_deal_detail(record) for record in body["records"]]))
        assert isinstance(composed, TenantDealListDTO)
        return composed

    @router.get(
        "/tenant/deals/{record_ref}",
        response_model=TenantDealDetailDTO,
        summary="Read one of the active tenant's Deals",
        description="Return one Deal record from the caller's single active tenant.",
        tags=["Deals"],
        operation_id="readActiveTenantDeal",
        response_description="The tenant Deal detail.",
        responses=error_responses(401, 403, 404, 409, 422, 503),
    )
    async def read_deal(request: Request, record_ref: RecordRef) -> TenantDealDetailDTO:
        context = authorized(request, BffOperation.READ_TENANT_DEAL, record_ref)
        routed(context)
        record = domains["deals"].call("/internal/deals/read", payload(context, record_ref=record_ref))
        if record is None:
            raise not_found()
        composed = compose(_deal_detail(record))
        assert isinstance(composed, TenantDealDetailDTO)
        return composed

    @router.post(
        "/tenant/deals",
        response_model=TenantDealDetailDTO,
        status_code=201,
        summary="Create a Deal in the active tenant",
        description=(
            "Create one Deal between records of the caller's single active tenant. Both party references "
            "are verified to belong to that tenant; a reference minted elsewhere is rejected. Sharing is "
            "never duplication, and no operation here copies an existing deal."
        ),
        tags=["Deals"],
        operation_id="createActiveTenantDeal",
        response_description="The created Deal, as the tenant detail shape.",
        responses=error_responses(401, 403, 404, 409, 422, 503),
    )
    async def create_deal(request: Request, body: CreateDealRequest) -> TenantDealDetailDTO:
        context = authorized(request, BffOperation.CREATE_TENANT_DEAL)
        routed(context)
        record = domains["deals"].call(
            "/internal/deals/create",
            payload(
                context,
                deal_name=body.deal_name,
                startup_ref=body.startup_ref,
                investor_ref=body.investor_ref,
                stage=body.stage,
                amount=body.amount,
                currency=body.currency,
            ),
        )
        composed = compose(_deal_detail(record))
        assert isinstance(composed, TenantDealDetailDTO)
        return composed

    @router.patch(
        "/tenant/deals/{record_ref}",
        response_model=TenantDealDetailDTO,
        summary="Update one of the active tenant's Deals",
        description=(
            "Update a Deal's stage or status. The party references are immutable through this operation: "
            "re-pointing a deal at a different startup is a different deal, not an edit."
        ),
        tags=["Deals"],
        operation_id="updateActiveTenantDeal",
        response_description="The updated Deal, as the tenant detail shape.",
        responses=error_responses(401, 403, 404, 409, 422, 503),
    )
    async def update_deal(request: Request, record_ref: RecordRef, body: UpdateDealRequest) -> TenantDealDetailDTO:
        context = authorized(request, BffOperation.UPDATE_TENANT_DEAL, record_ref)
        routed(context)
        record = domains["deals"].call(
            "/internal/deals/update",
            payload(context, record_ref=record_ref, stage=body.stage, status=body.status),
        )
        composed = compose(_deal_detail(record))
        assert isinstance(composed, TenantDealDetailDTO)
        return composed

    # --- Tenant Operations: Lineage (TENANT) --------------------------------------------------------

    @router.get(
        "/tenant/records/{record_ref}/lineage",
        response_model=LineageSummaryDTO,
        summary="Read a tenant record's provenance",
        description=(
            "Return where a tenant record came from (IC-004). Provenance is tenant-resident and references "
            "only: it names the origin, never reproduces it, and reading it never re-reads the source."
        ),
        tags=["Lineage"],
        operation_id="readActiveTenantRecordLineage",
        response_description="The record's lineage and source references, in deterministic order.",
        responses=error_responses(401, 403, 404, 409, 422, 503),
    )
    async def read_lineage(request: Request, record_ref: RecordRef) -> LineageSummaryDTO:
        context = authorized(request, BffOperation.READ_TENANT_LINEAGE, record_ref)
        routed(context)
        body = domains["lineage"].call("/internal/lineage/for-record", payload(context, target_ref=record_ref))
        entries = body["entries"]
        composed = compose(
            LineageSummaryDTO(
                target_ref=record_ref,
                lineage_references=[str(entry["lineage_ref"]) for entry in entries],
                source_references=[str(entry["source_ref"]) for entry in entries],
            )
        )
        assert isinstance(composed, LineageSummaryDTO)
        return composed

    return router


__all__ = [
    "ACTION_MEMBERSHIPS_READ",
    "ACTION_STARTUP_READ",
    "ACTION_STARTUP_UPDATE",
    "CreateDealRequest",
    "CreateInvestorRequest",
    "CreateStartupRequest",
    "UpdateDealRequest",
    "UpdateInvestorRequest",
    "UpdateStartupRequest",
    "build_router",
]
