"""Provider readiness probes that avoid credentials and heavy model downloads."""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path


def comfyui_healthcheck(url: str = "http://127.0.0.1:8188", timeout: float = 2.0, dry_run: bool = False) -> dict:
    base = url.rstrip("/")
    if dry_run:
        return {
            "provider": "provider-comfyui",
            "status": "dry-run-ready",
            "endpoint": base,
            "checks": ["HTTP endpoint contract", "system_stats probe", "no credentials persisted"],
        }
    try:
        with urllib.request.urlopen(f"{base}/system_stats", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {"provider": "provider-comfyui", "status": "healthy", "endpoint": base, "system_stats": payload}
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return {"provider": "provider-comfyui", "status": "unavailable", "endpoint": base, "error": str(exc)}


def detect_render_capability(dry_run: bool = False) -> dict:
    if dry_run:
        return {
            "provider": "provider-remote-render-node",
            "status": "contract-ready",
            "gpu": "RTX 5050 expected on the remote node; not asserted on this machine",
            "network": "private-network endpoint required",
        }
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return {"provider": "provider-remote-render-node", "status": "not-detected", "reason": "nvidia-smi unavailable"}
    try:
        result = subprocess.run([nvidia_smi, "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True, timeout=3)
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return {"provider": "provider-remote-render-node", "status": "detected" if result.returncode == 0 else "error", "gpus": names}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"provider": "provider-remote-render-node", "status": "error", "error": str(exc)}


def load_provider_manifest(repo_root: Path, provider_id: str) -> dict:
    path = repo_root / "providers" / "manifests" / f"{provider_id}.json"
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)
