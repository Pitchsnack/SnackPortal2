-- SnackPortal2 — control-plane provisioning identity (D15; D-15).
-- Least-privilege, control-plane-scoped provisioning role. D-15: provisioning is an
-- automated, audited control-plane workflow (manual runbook = break-glass only) and the
-- provisioning identity is least-privilege. NOLOGIN group role — the actual LOGIN credential
-- is resolved from the D-14 secret store at connect time and is NEVER stored here (no
-- passwords in IaC). The role is granted only what it needs to provision and bootstrap
-- physically distinct tenant databases in a controlled non-production environment.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sp2_provisioner') THEN
        CREATE ROLE sp2_provisioner NOLOGIN;
    END IF;
END
$$;

-- Capability to create a physically distinct tenant database (CREATE DATABASE). Scoped to
-- the provisioning workflow; not granted to tenant login roles or to any serving path.
ALTER ROLE sp2_provisioner CREATEDB;

COMMENT ON ROLE sp2_provisioner IS
    'D15/D-15 least-privilege control-plane provisioning identity (NOLOGIN group role; '
    'login credential via D-14 secret store; controlled non-production only).';
