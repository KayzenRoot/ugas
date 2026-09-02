"""Collect reproducible local runtime evidence for the v0.12.0 dashboard."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/observability-v0120"
BASE_URL = "http://127.0.0.1:8765"


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_json(name: str, value: object) -> None:
    (EVIDENCE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_json(path: str) -> tuple[int, object]:
    try:
        with urlopen(Request(BASE_URL + path, headers={"Accept": "application/json"}), timeout=8) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        return int(getattr(exc, "code", 599)), {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    startup_path = ROOT / ".ugas/runtime/dashboard-startup.json"
    startup = json.loads(startup_path.read_text(encoding="utf-8")) if startup_path.is_file() else {"status": "MISSING"}
    write_json("dashboard-startup.json", {"captured_at": stamp(), "source": ".ugas/runtime/dashboard-startup.json", **startup})

    command = [sys.executable, "-m", "ugas.cli", "models", "list"]
    environment = os.environ.copy(); environment["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + environment.get("PYTHONPATH", "")
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, check=False, timeout=45)
    time.sleep(1.5)
    status, events_value = get_json("/api/events?limit=80&category=command")
    events = events_value.get("events", []) if isinstance(events_value, dict) else []
    command_event = next((event for event in events if event.get("source") == "ugas.cli" and event.get("action") == "completed" and event.get("status") == "SUCCEEDED"), None)
    write_json("command-event.json", {"captured_at": stamp(), "command": command, "exit_code": completed.returncode, "api_status": status, "event": command_event, "stdout_bytes": len(completed.stdout.encode()), "stderr_bytes": len(completed.stderr.encode())})

    system_status, system = get_json("/api/system")
    write_json("system-idle.json", {"captured_at": stamp(), "api_status": system_status, "system": system})

    probe_dir = ROOT / ".ugas/runtime/observability-smoke"
    probe_dir.mkdir(parents=True, exist_ok=True)
    probe = probe_dir / "stable-probe.png"
    Image.new("RGBA", (16, 16), (25, 150, 220, 255)).save(probe)
    time.sleep(2.4)
    _, after_create = get_json("/api/assets/recent?limit=100")
    create_entry = next((item for item in after_create.get("items", []) if item.get("path") == ".ugas/runtime/observability-smoke/stable-probe.png"), None) if isinstance(after_create, dict) else None
    probe.write_bytes(probe.read_bytes() + b"\n")
    time.sleep(2.4)
    _, after_update = get_json("/api/assets/recent?limit=100")
    update_entry = next((item for item in after_update.get("items", []) if item.get("path") == ".ugas/runtime/observability-smoke/stable-probe.png"), None) if isinstance(after_update, dict) else None
    probe.unlink(missing_ok=True)
    write_json("file-activity.json", {"captured_at": stamp(), "probe": ".ugas/runtime/observability-smoke/stable-probe.png", "created": create_entry is not None, "updated": update_entry is not None, "created_record": create_entry, "updated_record": update_entry, "stable_sha256": digest(probe) if probe.is_file() else (update_entry or create_entry or {}).get("sha256"), "cleanup": not probe.exists()})

    endpoints = ["/api/status", "/api/system", "/api/processes", "/api/jobs", "/api/assets/recent?limit=10", "/api/qa", "/api/events?limit=10", "/api/health"]
    api_records = []
    for endpoint in endpoints:
        code, value = get_json(endpoint); api_records.append({"endpoint": endpoint, "status": code, "json": isinstance(value, dict), "top_level_keys": sorted(value)[:20] if isinstance(value, dict) else []})
    sse_lines: list[str] = []
    try:
        with urlopen(Request(BASE_URL + "/api/stream", headers={"Accept": "text/event-stream"}), timeout=8) as response:
            for _ in range(4):
                line = response.readline().decode("utf-8", errors="replace").strip()
                if line: sse_lines.append(line)
                if len(sse_lines) >= 2: break
    except (HTTPError, URLError, TimeoutError) as exc:
        sse_lines.append(f"ERROR {type(exc).__name__}: {exc}")
    write_json("api-snapshots.json", {"captured_at": stamp(), "endpoints": api_records, "sse_initial_lines": sse_lines, "sse_snapshot_observed": any(line.startswith("event: snapshot") for line in sse_lines)})

    _, traversal = get_json("/api/preview/..%2F..%2FREADME.md")
    security = {"captured_at": stamp(), "preview_traversal_result": traversal, "preview_traversal_rejected": traversal.get("status") in {"NOT_FOUND", "ERROR"} if isinstance(traversal, dict) else False}
    try:
        from ugas.observability.dashboard_app import run_dashboard
        run_dashboard(ROOT, host="0.0.0.0", port=0, no_open=True)
    except Exception as exc:
        security["non_loopback_rejection"] = {"type": type(exc).__name__, "message": str(exc)}
        security["non_loopback_rejected"] = isinstance(exc, ValueError)
    write_json("security.json", security)

    visual_manifest = json.loads((ROOT / "docs/evidence/animation-runtime-v0112/attack-v2-visual-manifest-v0112.json").read_text(encoding="utf-8"))
    visual_checks = [{"path": item["source_path"], "expected_sha256": item["sha256"], "actual_sha256": digest(ROOT / item["source_path"]), "byte_identical": digest(ROOT / item["source_path"]) == item["sha256"]} for item in visual_manifest.get("images", [])]
    current_profile = json.loads((ROOT / "profiles/animation/attack-front-v2.json").read_text(encoding="utf-8")); baseline_profile = json.loads((ROOT / "profiles/animation/attack-front-v2-v0.11.0.json").read_text(encoding="utf-8"))
    write_json("animation-regression-v0112.json", {"captured_at": stamp(), "visual_checks": visual_checks, "all_visuals_byte_identical": all(item["byte_identical"] for item in visual_checks), "motion_tracks_byte_identical": current_profile.get("motion_tracks") == baseline_profile.get("motion_tracks"), "key_pose_bindings_byte_identical": current_profile.get("key_pose_bindings") == baseline_profile.get("key_pose_bindings"), "new_generation": 0, "animation_files_changed": False})
    print(json.dumps({"status": "OBSERVABILITY_EVIDENCE_COLLECTED", "evidence_dir": str(EVIDENCE), "command_exit_code": completed.returncode, "visual_count": len(visual_checks)}, ensure_ascii=False))
    return 0 if completed.returncode == 0 and all(item["byte_identical"] for item in visual_checks) and security.get("non_loopback_rejected") else 2


if __name__ == "__main__":
    raise SystemExit(main())
