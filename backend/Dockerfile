# SnackPortal2 — Option A rebuild (D-46): the ONE image the fourteen FastAPI services run from.
#
# One image, fourteen services. Each service is independently bootable (IC-013 §21) — its own
# `main.py`, its own `app = FastAPI()`, its own port — and independence is a property of the
# *process*, not of the filesystem it was copied from. Fourteen near-identical images would
# make the build slower and the drift harder to see, without making any service more separate
# than the import-linter contract already makes it.
#
# The service a container runs is chosen by the `command:` the deployment manifest supplies.
# There is no default service and no entrypoint that picks one: a container started without a
# command fails loudly rather than quietly becoming whichever service happened to be first.
#
# BIND vs PUBLISH (IC-013 §21.1 E-3): this image sets no bind address. Binding 0.0.0.0 inside a
# container namespace is permitted and is supplied per service by the manifest; publishing is a
# manifest decision this file cannot make and must not pre-empt.

FROM python:3.12-slim

# Bytecode files and a stdout buffer both make container logs lie about when something happened.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependency metadata first, so a source edit does not invalidate the dependency layer.
# `psycopg[binary]` ships prebuilt wheels, so no compiler toolchain is installed here — the
# image stays slim and has no build-time C dependency to keep patched.
COPY pyproject.toml /app/pyproject.toml

# The packages setuptools is configured to find. The retired flat packages are copied because
# `[tool.setuptools.packages.find]` still enumerates them (D-46 keeps them on disk as the
# historical record); nothing in `snackportal2/` may import them, and import-linter proves it.
COPY snackportal2 /app/snackportal2
COPY shared /app/shared
COPY api_gateway /app/api_gateway
COPY auth_router /app/auth_router
COPY database_router /app/database_router
COPY control_plane /app/control_plane
COPY import_service /app/import_service
COPY lineage_service /app/lineage_service
COPY deployment /app/deployment

RUN pip install --no-cache-dir .

# Unprivileged by default. A service that never needs to write to its own filesystem should not
# be able to, and root inside a container is one namespace escape away from root outside it.
RUN useradd --create-home --uid 10001 snackportal2
USER snackportal2

# No service is the default. `command:` in the deployment manifest names one explicitly.
CMD ["python", "-c", "raise SystemExit('SnackPortal2: no service command supplied. The deployment manifest must name one, e.g. uvicorn snackportal2.services.bff.main:app --host 0.0.0.0 --port 8000')"]
