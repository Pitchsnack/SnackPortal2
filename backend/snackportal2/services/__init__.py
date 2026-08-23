"""The fourteen independently-bootable SnackPortal2 FastAPI services (IC-013 §21).

Each service owns its own package, its own ``main.py`` defining its own ``app = FastAPI()``,
its own port, its own liveness/readiness, and its own tests. Services do not import one
another's internal implementation (IC-013 §13); they talk over declared transport ports.
"""
