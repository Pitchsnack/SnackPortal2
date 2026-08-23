"""The enumerated BFF operation surface (IC-013 §16).

**The BFF surface is enumerated, not generic.** Every operation the frontend can reach is
named here, mapped to exactly one operation category, and through that category to exactly
one database domain. Adding an operation is a contract change, not a configuration change
— and because this enumeration is what the Access Control Service validates against, an
operation absent from it cannot be authorized at all (IC-014 §5.2, closed permission set).

This module is a **taxonomy**, not a policy. It says which database domain an operation
belongs to; it says nothing about who may perform it. That question lives entirely in the
Access Control Service, which is the only place a permission is evaluated.
"""

from __future__ import annotations

from enum import Enum

from .types import CATEGORY_DOMAIN, DatabaseDomain, OperationCategory


class BffOperation(str, Enum):
    """Every named frontend use case the BFF exposes.

    Grouped by category below. Names are stable identifiers, not route paths: the route is
    never a client-controlled routing channel (IC-013 §16), so an operation's identity is
    deliberately decoupled from the URL that reaches it.
    """

    # MembershipsForPrincipal — CONTROL
    LIST_MEMBERSHIPS = "list_memberships"

    # Global Directory Read — CONTROL
    READ_GLOBAL_STARTUP_DIRECTORY = "read_global_startup_directory"
    READ_GLOBAL_INVESTOR_DIRECTORY = "read_global_investor_directory"

    # Import Initiation — TENANT
    INITIATE_STARTUP_IMPORT = "initiate_startup_import"

    # Tenant Operations — TENANT
    LIST_TENANT_STARTUPS = "list_tenant_startups"
    CREATE_TENANT_STARTUP = "create_tenant_startup"
    READ_TENANT_STARTUP = "read_tenant_startup"
    UPDATE_TENANT_STARTUP = "update_tenant_startup"
    LIST_TENANT_INVESTORS = "list_tenant_investors"
    CREATE_TENANT_INVESTOR = "create_tenant_investor"
    READ_TENANT_INVESTOR = "read_tenant_investor"
    UPDATE_TENANT_INVESTOR = "update_tenant_investor"
    LIST_TENANT_DEALS = "list_tenant_deals"
    CREATE_TENANT_DEAL = "create_tenant_deal"
    READ_TENANT_DEAL = "read_tenant_deal"
    UPDATE_TENANT_DEAL = "update_tenant_deal"
    LIST_TENANT_CONTACTS = "list_tenant_contacts"
    CREATE_TENANT_CONTACT = "create_tenant_contact"
    READ_TENANT_CONTACT = "read_tenant_contact"
    READ_TENANT_LINEAGE = "read_tenant_lineage"

    # Governed Sharing — CONTROL. Authored-but-inert until IC-007 is Final (IC-013 §18).
    PROPOSE_DEAL_SHARE = "propose_deal_share"
    READ_DEAL_SHARE = "read_deal_share"


#: Operation -> category. Exhaustive: :func:`category_of` refuses an unmapped operation
#: rather than guessing one, so a newly added operation is unusable until it is classified.
OPERATION_CATEGORY: dict[BffOperation, OperationCategory] = {
    BffOperation.LIST_MEMBERSHIPS: OperationCategory.MEMBERSHIPS_FOR_PRINCIPAL,
    BffOperation.READ_GLOBAL_STARTUP_DIRECTORY: OperationCategory.GLOBAL_DIRECTORY_READ,
    BffOperation.READ_GLOBAL_INVESTOR_DIRECTORY: OperationCategory.GLOBAL_DIRECTORY_READ,
    BffOperation.INITIATE_STARTUP_IMPORT: OperationCategory.IMPORT_INITIATION,
    BffOperation.LIST_TENANT_STARTUPS: OperationCategory.TENANT_OPERATION,
    BffOperation.CREATE_TENANT_STARTUP: OperationCategory.TENANT_OPERATION,
    BffOperation.READ_TENANT_STARTUP: OperationCategory.TENANT_OPERATION,
    BffOperation.UPDATE_TENANT_STARTUP: OperationCategory.TENANT_OPERATION,
    BffOperation.LIST_TENANT_INVESTORS: OperationCategory.TENANT_OPERATION,
    BffOperation.CREATE_TENANT_INVESTOR: OperationCategory.TENANT_OPERATION,
    BffOperation.READ_TENANT_INVESTOR: OperationCategory.TENANT_OPERATION,
    BffOperation.UPDATE_TENANT_INVESTOR: OperationCategory.TENANT_OPERATION,
    BffOperation.LIST_TENANT_DEALS: OperationCategory.TENANT_OPERATION,
    BffOperation.CREATE_TENANT_DEAL: OperationCategory.TENANT_OPERATION,
    BffOperation.READ_TENANT_DEAL: OperationCategory.TENANT_OPERATION,
    BffOperation.UPDATE_TENANT_DEAL: OperationCategory.TENANT_OPERATION,
    BffOperation.LIST_TENANT_CONTACTS: OperationCategory.TENANT_OPERATION,
    BffOperation.CREATE_TENANT_CONTACT: OperationCategory.TENANT_OPERATION,
    BffOperation.READ_TENANT_CONTACT: OperationCategory.TENANT_OPERATION,
    BffOperation.READ_TENANT_LINEAGE: OperationCategory.TENANT_OPERATION,
    BffOperation.PROPOSE_DEAL_SHARE: OperationCategory.GOVERNED_SHARING,
    BffOperation.READ_DEAL_SHARE: OperationCategory.GOVERNED_SHARING,
}

#: The IC-013 §18 inert set. These operations are authored so the taxonomy is complete and
#: so their denial is deliberate and tested — not so they can be performed. They stay denied
#: until IC-007 is promoted from ``Draft / Proposed`` to ``Final``.
SHARING_INERT_OPERATIONS = frozenset(op for op, category in OPERATION_CATEGORY.items() if category is OperationCategory.GOVERNED_SHARING)


class UnknownOperation(Exception):
    """The operation is not in the enumerated surface. Callers MUST fail closed."""


def category_of(operation: BffOperation) -> OperationCategory:
    """The single category this operation resolves to."""
    category = OPERATION_CATEGORY.get(operation)
    if category is None:
        raise UnknownOperation(operation.value)
    return category


def domain_of(operation: BffOperation) -> DatabaseDomain:
    """The single database domain this operation resolves to.

    One request -> one category -> one domain (IC-013 §16). The mapping is derived, never
    written twice, so a category can never mean CONTROL in one place and TENANT in another.
    """
    return CATEGORY_DOMAIN[category_of(operation)]


def unmapped_operations() -> list[BffOperation]:
    """Operations missing from :data:`OPERATION_CATEGORY`. Must always be empty."""
    return [operation for operation in BffOperation if operation not in OPERATION_CATEGORY]


__all__ = [
    "OPERATION_CATEGORY",
    "SHARING_INERT_OPERATIONS",
    "BffOperation",
    "UnknownOperation",
    "category_of",
    "domain_of",
    "unmapped_operations",
]
