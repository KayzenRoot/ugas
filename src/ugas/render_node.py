"""Windows/NVIDIA render-node lifecycle helpers using official comfy-cli commands."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from .comfyui_client import ComfyUIClient


def default_config_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "UGAS" / "render-node.json"


def default_workspace() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "UGAS" / "comfyui"


def validate_endpoint(endpoint: str, allow_remote: bool = False) -> None:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("endpoint must be an http(s) URL")
    if not allow_remote and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("local render node must bind to localhost")


def load_config(path: Path | None = None) -> dict:
    path = path or default_config_path()
    if not path.exists():
        return {"endpoint": "http://127.0.0.1:8188", "workspace": str(default_workspace()), "comfy_executable": shutil.which("comfy") or "comfy", "bind": "127.0.0.1", "port": 8188}
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(config: dict, path: Path | None = None) -> Path:
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _run(args: list[str], timeout: float = 30.0) -> dict:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return {"command": args, "returncode": result.returncode, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"command": args, "returncode": 127, "stdout": "", "stderr": str(exc)}


def cli_help(executable: str = "comfy") -> dict:
    return {"comfy": _run([executable, "--help"]), "install": _run([executable, "install", "--help"])}


def doctor(config: dict | None = None, *, timeout: float = 3.0) -> dict:
    config = config or load_config()
    gpu = _gpu_probe()
    endpoint = config.get("endpoint", "http://127.0.0.1:8188")
    try:
        validate_endpoint(endpoint, allow_remote=config.get("allow_remote", False))
        endpoint_ok = True
    except ValueError as exc:
        endpoint_ok = False
        endpoint_error = str(exc)
    client = ComfyUIClient(endpoint, timeout=timeout)
    health = client.safe_health()
    workspace = Path(config.get("workspace", default_workspace()))
    free = shutil.disk_usage(workspace.anchor or workspace).free if workspace.anchor else 0
    result = {"status": "ready" if endpoint_ok and health.get("status") == "healthy" else "not-ready", "os": sys.platform, "python": sys.version.split()[0], "gpu": gpu, "comfyui": {"endpoint": endpoint, "health": health, "workspace": str(workspace), "workspace_exists": workspace.exists()}, "disk_free_bytes": free, "endpoint_valid": endpoint_ok}
    if not endpoint_ok:
        result["endpoint_error"] = endpoint_error
    return result


def _gpu_probe() -> dict:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"status": "unavailable", "reason": "nvidia-smi unavailable"}
    query = "name,driver_version,memory.total,memory.used,memory.free"
    result = _run([executable, f"--query-gpu={query}", "--format=csv,noheader,nounits"], timeout=5)
    devices = []
    for line in result["stdout"].splitlines():
        values = [item.strip() for item in line.split(",")]
        if len(values) >= 5:
            devices.append({"name": values[0], "driver": values[1], "memory_total_mb": values[2], "memory_used_mb": values[3], "memory_free_mb": values[4]})
    version = _run([executable], timeout=5)
    import re
    match = re.search(r"CUDA Version:\s*([0-9.]+)", version["stdout"])
    return {"status": "available" if result["returncode"] == 0 else "error", "devices": devices, "cuda_version": match.group(1) if match else None, "nvidia_smi": executable}


def setup(config: dict | None = None, *, executable: str | None = None) -> dict:
    config = dict(config or load_config())
    config.setdefault("workspace", str(default_workspace()))
    config.setdefault("endpoint", "http://127.0.0.1:8188")
    config.setdefault("bind", "127.0.0.1")
    config.setdefault("port", 8188)
    config["comfy_executable"] = executable or config.get("comfy_executable") or shutil.which("comfy") or "comfy"
    validate_endpoint(config["endpoint"], allow_remote=config.get("allow_remote", False))
    workspace = Path(config["workspace"]).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    help_result = cli_help(config["comfy_executable"])
    if help_result["comfy"]["returncode"] not in {0, 1}:
        return {"status": "blocked", "config": config, "help": help_result, "reason": "comfy-cli is not available; install it separately and rerun setup"}
    saved = save_config(config)
    return {"status": "configured", "config_path": str(saved), "config": config, "help": help_result, "next": ["comfy install", "comfy launch --background"]}


def lifecycle(action: str, config: dict | None = None) -> dict:
    config = config or load_config()
    executable = config.get("comfy_executable", "comfy")
    workspace = config.get("workspace", str(default_workspace()))
    commands = {"start": [executable, f"--workspace={workspace}", "launch", "--background", "--", "--listen", config.get("bind", "127.0.0.1"), "--port", str(config.get("port", 8188))], "stop": [executable, f"--workspace={workspace}", "stop"], "status": [executable, f"--workspace={workspace}", "status"]}
    if action not in commands:
        raise ValueError(f"unknown lifecycle action: {action}")
    return _run(commands[action])


def probe(config: dict | None = None) -> dict:
    config = config or load_config()
    client = ComfyUIClient(config.get("endpoint", "http://127.0.0.1:8188"))
    return {"health": client.safe_health(), "features": client.safe_call(client.features), "nodes": client.safe_call(client.node_info)}
