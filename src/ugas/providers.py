"""Provider readiness probes that avoid credentials and heavy model downloads."""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path


def comfyui_healthcheck(
    local_endpoint: str = "http://127.0.0.1:8188",
    timeout: float = 2.0,
    dry_run: bool = False,
) -> dict:
    """Probe only the local ComfyUI endpoint; never infer remote GPU state."""
    base = local_endpoint.rstrip("/")
    if dry_run:
        return {
            "provider": "provider-comfyui",
            "scope": "local",
            "status": "dry-run-ready",
            "endpoint": base,
            "simulation": True,
            "checks": ["HTTP endpoint contract", "system_stats probe", "no credentials persisted"],
        }
    try:
        with urllib.request.urlopen(f"{base}/system_stats", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {"provider": "provider-comfyui", "scope": "local", "status": "healthy", "endpoint": base, "system_stats": payload}
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return {"provider": "provider-comfyui", "scope": "local", "status": "unavailable", "endpoint": base, "error": str(exc)}


def detect_local_gpu_capability(dry_run: bool = False) -> dict:
    """Inspect this machine's GPU only; it says nothing about a remote render node."""
    if dry_run:
        return {
            "provider": "local-gpu",
            "scope": "local",
            "status": "dry-run-ready",
            "simulation": True,
            "probe": "nvidia-smi (local machine only)",
        }
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return {"provider": "local-gpu", "scope": "local", "status": "unavailable", "reason": "nvidia-smi unavailable"}
    try:
        result = subprocess.run(
            [nvidia_smi, "--query-gpu=name,driver_version,memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        devices = []
        for line in result.stdout.splitlines():
            values = [value.strip() for value in line.split(",")]
            if len(values) >= 5:
                devices.append({"name": values[0], "driver": values[1], "memory_total_mb": values[2], "memory_used_mb": values[3], "memory_free_mb": values[4]})
        return {"provider": "local-gpu", "scope": "local", "status": "available" if result.returncode == 0 else "error", "gpus": devices}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"provider": "local-gpu", "scope": "local", "status": "error", "error": str(exc)}


def remote_render_node_healthcheck(
    remote_endpoint: str | None = None,
    timeout: float = 3.0,
    dry_run: bool = False,
) -> dict:
    """Probe the remote node's own health endpoint, without local GPU probing."""
    base = (remote_endpoint or "").rstrip("/")
    if dry_run:
        return {
            "provider": "provider-remote-render-node",
            "scope": "remote",
            "status": "dry-run-ready",
            "simulation": True,
            "endpoint": base or None,
            "checks": ["remote /system_stats contract", "private endpoint required", "no local nvidia-smi"],
        }
    if not base:
        return {
            "provider": "provider-remote-render-node",
            "scope": "remote",
            "status": "unknown",
            "reason": "remote endpoint not configured",
        }
    try:
        with urllib.request.urlopen(f"{base}/system_stats", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {"provider": "provider-remote-render-node", "scope": "remote", "status": "healthy", "endpoint": base, "system_stats": payload}
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return {"provider": "provider-remote-render-node", "scope": "remote", "status": "unavailable", "endpoint": base, "error": str(exc)}


# Compatibility for callers from v0.2.0. The corrected name makes the scope explicit.
detect_render_capability = detect_local_gpu_capability


def load_provider_manifest(repo_root: Path, provider_id: str) -> dict:
    path = repo_root / "providers" / "manifests" / f"{provider_id}.json"
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)
