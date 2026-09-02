"""Safe process and ComfyUI endpoint probes."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import socket
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from .system_metrics import process_resource_metrics


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def probe_endpoint(endpoint: str, *, timeout: float = 0.7) -> dict[str, Any]:
    """Check ComfyUI's read-only system_stats endpoint only."""

    endpoint = endpoint.rstrip("/")
    url = f"{endpoint}/system_stats"
    result: dict[str, Any] = {"endpoint": endpoint, "checked_at": _now(), "status": "DOWN", "health": "UNAVAILABLE", "reason": None}
    try:
        request = Request(url, headers={"Accept": "application/json"}, method="GET")
        with urlopen(request, timeout=timeout) as response:
            result["http_status"] = int(response.status)
            if 200 <= response.status < 300:
                result["status"] = "UP"; result["health"] = "HEALTHY"
                # The dashboard only needs provider health. Keep the response
                # bounded and do not persist provider payloads or credentials.
                result["provider_summary"] = {"response_bytes": int(response.headers.get("Content-Length") or 0)}
            else:
                result["reason"] = f"HTTP {response.status}"
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        result["reason"] = f"{type(exc).__name__}: local endpoint unavailable"[:300]
    return result


def _process_name(pid: int) -> str | None:
    if os.name == "posix":
        try:
            return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return None


def collect_process_metrics(pid: int | None, *, comfyui_endpoint: str = "http://127.0.0.1:8188") -> dict[str, Any]:
    process = process_resource_metrics(pid)
    if pid and not process.get("name"):
        process["name"] = _process_name(pid)
    comfy = probe_endpoint(comfyui_endpoint)
    return {"timestamp": _now(), "ugas": process, "comfyui": comfy}
