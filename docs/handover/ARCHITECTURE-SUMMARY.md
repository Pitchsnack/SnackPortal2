# ARCHITECTURE-SUMMARY

**Authoritative architecture summary (PRD-HO-03). Every core invariant verified PASS by PRD-SP2-SESSION-V2 (A1–A10).**

## Core Invariants

- **Authentication ≠ Routing**
- **Authentication ≠ Authorization**
- **Workspace ≠ Routing**
- **Global Record ≠ Tenant Record**
- **One Request → One Active Tenant → One Database**
- **Gateway Never Chooses a Database** (the Database Router is the sole selector)
- **Database Router Never Authenticates**
- **Portal Never Routes**
- **Portal Never Selects a Database**

Also binding: Ownership ≠ Authorization/Routing/Residency · Import ≠ Synchronization · Lineage is tenant-resident & append-only · Audit is reference-only (Global Audit Representation Rule) · cloud-portable standard PostgreSQL only · no Supabase/Lovable coupling.

## Core flow

```text
clients / portals
      │   (channel-agnostic; bind to identical gateway rules — D-37 §6)
      ▼
  API GATEWAY          sole governed ingress; authenticates (consumes IC-005), validates
      │                carriers against the signed claim, builds RequestContext from AuthContext,
      ▼                dispatches; NEVER selects a database.
 AUTHENTICATION ROUTER  OIDC stateless JWT; signed tenant claim authoritative; never routes a DB.
      ▼
 DATABASE ROUTER       resolves exactly one physical DB from the signed claim; SOLE selector;
      │                "never re-derived"; never authenticates.
   ┌──┴───────────┐
   ▼              ▼
 CONTROL DB    one TENANT DB     physically separate; one request → Control DB OR one tenant DB,
                                 never both, never several.
```

## MVP Requirement

**The Physical Multi-Database MVP is mandatory. Not future. Not optional. Not configurable. Not subject to downgrade.**

One Control Database + one physically separate PostgreSQL database per tenant. Never a shared database, never a shared schema, never `tenant_id` row-filtering as isolation, never logical isolation in place of physical isolation. The API Gateway Architecture Specification (`AGW-ARCH-SPEC-R2 §22`) preserves it; PRD-SP2-SESSION-V2 verified it intact (P1–P7 PASS; the only open item, P8 tenant-DB physical-distinctness detection, is the governed D-15 / Phase-3B requirement — see DRIFT-ASSESSMENT and NEXT-PHASE).
