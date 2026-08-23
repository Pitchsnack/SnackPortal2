"""Technical cross-cutting foundation for every SnackPortal2 service.

Strictly technical (3-day plan §Day 1.1): configuration, canonical errors, structured
logging, correlation, security *types*, shared primitive types, and the FastAPI/OpenAPI
application builder.

**Nothing here decides tenant, permission, database, or ownership.** Domain authorization
lives in the Access Control Service (IC-014); tenant routing lives in the Database Router;
neither may be re-implemented, cached, or short-circuited in this package.
"""
