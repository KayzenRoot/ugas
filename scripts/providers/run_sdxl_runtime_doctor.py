"""Capture the live ComfyUI/RTX 5050 prerequisites for v0.6.0."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
COMFY_ROOT = Path.home() / "AppData" / "Local" / "UGAS" / "comfyui"
EVIDENCE = ROOT / "docs" / "evidence" / "runtime-doctor-v0.6.0.json"
ENDPOINT = "http://127.0.0.1:8188"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stats() -> dict[str, Any]:
    import urllib.request
    with urllib.request.urlopen(f"{ENDPOINT}/system_stats", timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _nodes() -> dict[str, Any]:
    import urllib.request
    with urllib.request.urlopen(f"{ENDPOINT}/object_info", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _git_revision() -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=COMFY_ROOT, capture_output=True, text=True, check=False, timeout=10)
    return result.stdout.strip() if result.returncode == 0 else None


def _nvidia_smi() -> dict[str, Any]:
    command = shutil.which("nvidia-smi")
    if not command:
        return {"status": "unavailable", "reason": "nvidia-smi not on PATH"}
    result = subprocess.run([command, "--query-gpu=name,driver_version,memory.total,memory.free", "--format=csv,noheader,nounits"], capture_output=True, text=True, check=False, timeout=10)
    rows = []
    for line in result.stdout.splitlines():
        values = [part.strip() for part in line.split(",")]
        if len(values) >= 4:
            rows.append({"name": values[0], "driver": values[1], "memory_total_mb": values[2], "memory_free_mb": values[3]})
    return {"status": "available" if result.returncode == 0 else "error", "gpus": rows, "stderr": result.stderr[-500:]}


def _inventory(folder: str) -> list[str]:
    import urllib.request
    with urllib.request.urlopen(f"{ENDPOINT}/models/{folder}", timeout=20) as response:
        value = json.loads(response.read().decode("utf-8"))
    return value if isinstance(value, list) else []


def run() -> dict[str, Any]:
    failures: list[str] = []
    try:
        stats = _stats()
        nodes = _nodes()
        system = stats.get("system", {})
        devices = stats.get("devices", [])
        gpu = devices[0] if devices else {}
        required_nodes = ["CheckpointLoaderSimple", "CLIPTextEncode", "ControlNetLoader", "ControlNetApplyAdvanced", "CLIPVisionLoader", "CLIPVisionEncode", "IPAdapterModelLoader", "IPAdapterAdvanced", "KSampler", "VAEDecode", "SaveImage"]
        node_checks = {node: node in nodes for node in required_nodes}
        failures.extend(f"missing_node:{node}" for node, present in node_checks.items() if not present)
        if "RTX 5050" not in str(gpu.get("name", "")):
            failures.append("gpu_is_not_rtx_5050")
        if int(gpu.get("vram_total", 0)) < 512 * 1024 * 1024:
            failures.append("vram_below_512mb")
        inventory = {folder: _inventory(folder) for folder in ("checkpoints", "controlnet", "ipadapter", "clip_vision")}
        return {
            "schema_version": "0.6.0",
            "status": "RUNTIME_DOCTOR_PASSED" if not failures else "SDXL_CONTROL_PROVIDER_HARDWARE_GAP",
            "checked_at": _now(),
            "endpoint": ENDPOINT,
            "comfyui": {"version": system.get("comfyui_version"), "git_revision": _git_revision(), "python": system.get("python_version"), "pytorch": system.get("pytorch_version")},
            "gpu": gpu,
            "nvidia_smi": _nvidia_smi(),
            "required_nodes": node_checks,
            "inventory": inventory,
            "runtime_strategy": ["512x512 FP16-compatible attempt", "low-VRAM/offload fallback", "sequential model unload/offload"],
            "resolution_minimum": [512, 512],
            "failures": failures,
            "smoke_generation_run": False,
        }
    except Exception as exc:
        return {"schema_version": "0.6.0", "status": "SDXL_CONTROL_PROVIDER_HARDWARE_GAP", "checked_at": _now(), "endpoint": ENDPOINT, "failures": [f"doctor_error:{type(exc).__name__}: {exc}"], "smoke_generation_run": False}


def main() -> int:
    result = run()
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "RUNTIME_DOCTOR_PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
