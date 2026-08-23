"""SnackPortal2 — Option A clean FastAPI rebuild (D-46).

The target runtime is ``Frontend -> FastAPI BFF -> FastAPI Services -> Database Router ->
Control DB / Tenant DBs``, with **zero API Gateway** (IC-013 §2). Every backend HTTP
service in this package is FastAPI, and the document produced by ``app.openapi()`` is the
hard implementation contract for that service — never a hand-maintained second spec.

Governed by IC-013 (BFF Ingress) and IC-014 (Access Control), which jointly supersede
IC-010. The flat legacy packages beside this one (``api_gateway``, ``auth_router``, ...)
are Phase-0 category D — old architecture, retained on disk, never imported from here.
"""
