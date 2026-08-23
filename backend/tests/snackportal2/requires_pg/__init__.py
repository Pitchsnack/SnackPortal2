"""Stage 4 live-PostgreSQL verification for the Option A rebuild.

Excluded from the default ``pytest`` run by ``addopts`` — the same convention the two
pre-existing ``requires_pg`` harnesses follow — and run explicitly:

    python -m pytest tests/snackportal2/requires_pg -q

Every module here clean-skips when no Stage 4 DSNs are configured, so an unconfigured
machine reports *skipped* rather than *failed*. A skipped run is never a Stage 4 pass.
"""
