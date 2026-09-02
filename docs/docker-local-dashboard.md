# UGAS Docker always-on local dashboard

The historical v0.12.2 observer is the only component containerized in this v0.12.3 slice. ComfyUI and its model storage remain on the host and are never migrated, started or mutated by Compose.

## Runtime contract

- URL: `http://127.0.0.1:8765/` (override with `UGAS_DASHBOARD_PORT`). The host publication is loopback-only.
- `compose.yaml` uses `restart: unless-stopped`, bounded JSON log rotation, a non-root user, `read_only: true`, `no-new-privileges`, all Linux capabilities dropped, and no Docker socket.
- The repository is mounted at `/workspace/ugas` read-only. Only the dedicated host `.ugas/runtime` directory is mounted read-write for the SQLite WAL telemetry store.
- `UGAS_COMFYUI_URL` defaults inside the container to `http://host.docker.internal:8188`; endpoint health is reported as unavailable/down when the host provider is absent.
- `compose.gpu.yaml` is an optional override. The up script selects it only when an actual container `nvidia-smi` preflight succeeds; otherwise the dashboard remains online and evidence records `GPU_CONTAINER_RUNTIME_GAP` with the observed reason.
- The application binds to `0.0.0.0` only inside a container with `UGAS_CONTAINERIZED=1`. Native invocations reject non-loopback binds.

## Start, inspect and stop

From the repository root:

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/docker/ugas-dashboard-up.ps1
pwsh -ExecutionPolicy Bypass -File scripts/docker/ugas-dashboard-status.ps1
pwsh -ExecutionPolicy Bypass -File scripts/docker/ugas-dashboard-logs.ps1
```

The start script builds `ugas-dashboard:0.12.3`, probes GPU passthrough, starts the service and does not call `docker compose down`. The executor final state must keep `ugas-dashboard` running and healthy. Stop only when intentionally shutting down this local observer:

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/docker/ugas-dashboard-down.ps1
```

## Always-on Windows policy

Install a reversible per-user logon task named `UGAS-Dashboard-AlwaysOn`:

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/docker/install-dashboard-autostart.ps1
pwsh -ExecutionPolicy Bypass -File scripts/docker/uninstall-dashboard-autostart.ps1
```

The task runs `ensure-dashboard-online.ps1`, waits a bounded time for Docker Engine, starts Docker Desktop when it is installed but not ready, then invokes the idempotent up script. It does not require administrator rights for the normal per-user registration and never removes unrelated tasks or services. If Task Scheduler denies registration, the installer automatically creates exactly one UGAS-owned `UGAS-Dashboard-AlwaysOn.cmd` in the signed-in user's Startup folder and returns `AUTOSTART_INSTALLED_FALLBACK`. Uninstall removes only that exact task and/or Startup entry.

## Shared telemetry proof

The host CLI and the container use the same `.ugas/runtime/telemetry.db`. Native UGAS commands are the single SQLite writer; the container opens that bind-mounted database read-only (`UGAS_TELEMETRY_READ_ONLY=1`) and keeps only its live collector tail in memory. This avoids SQLite journal corruption across the Docker Desktop Windows/VM boundary while preserving cross-process visibility and persistence. With the container online, run a harmless host command with `PYTHONPATH=src`, query `/api/events` and `/api/jobs`, then create an allowlisted file and query the file activity stream. Restart/rebuild with Compose and confirm the old event remains queryable. These checks are recorded in `docs/evidence/observability-v0122/`.

## Security and limitations

The dashboard is a read-only observer. It has no mutating HTTP endpoints, public binding, wildcard CORS, remote analytics, CDN or external fonts. GPU passthrough is capability-dependent on Docker Desktop; an unsupported NVIDIA container runtime is a recorded operational gap, not a fabricated zero-valued GPU result. External visual review remains required and production routing remains blocked.
