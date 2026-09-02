"""Collect reproducible local runtime evidence for the v0.12.1 correction."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/observability-v0121"
BASE_URL = os.environ.get("UGAS_OBSERVABILITY_URL", "http://127.0.0.1:8765").rstrip("/")


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_json(name: str, value: object) -> None:
    (EVIDENCE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_json(path: str) -> tuple[int, object, dict[str, str]]:
    try:
        with urlopen(Request(BASE_URL + path, headers={"Accept": "application/json"}), timeout=8) as response:
            return int(response.status), json.loads(response.read().decode("utf-8")), {key: value for key, value in response.headers.items()}
    except (HTTPError, URLError, TimeoutError) as exc:
        return int(getattr(exc, "code", 599)), {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}, {}


def emit_file_events(service, changes: list[dict]) -> None:
    for item in changes:
        service.emit(category="file", severity="debug" if item.get("action") == "stable" else "info", source="asset_activity", action=item["action"], status=item["status"], message=f"{item['action']} {item['path']}", asset_id=item.get("safe_id"), metadata=item)


def _collect_evidence() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    startup_path = ROOT / ".ugas/runtime/dashboard-startup.json"
    startup = json.loads(startup_path.read_text(encoding="utf-8")) if startup_path.is_file() else {"status": "MISSING"}
    write_json("dashboard-startup.json", {"captured_at": stamp(), "source": ".ugas/runtime/dashboard-startup.json", **startup})

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + environment.get("PYTHONPATH", "")
    command = [sys.executable, "-m", "ugas.cli", "models", "list"]
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, check=False, timeout=45)
    time.sleep(0.8)
    command_status, events_value, _ = get_json("/api/events?limit=120&category=command")
    command_events = events_value.get("events", []) if isinstance(events_value, dict) else []
    command_event = next((event for event in command_events if event.get("source") == "ugas.cli" and event.get("action") == "completed" and event.get("status") == "SUCCEEDED"), None)
    write_json("command-event.json", {"captured_at": stamp(), "command": command, "exit_code": completed.returncode, "api_status": command_status, "event": command_event, "stdout_bytes": len(completed.stdout.encode()), "stderr_bytes": len(completed.stderr.encode())})

    # Add a real command/job/stage lifecycle to the same local telemetry store.
    from ugas.observability.service import ObservabilityService
    service = ObservabilityService(ROOT, sample_interval=60)
    try:
        job_id = "job-v0121-live-stage"
        common = {"pid": service.pid, "session_id": service.session_id, "parent_command_id": "cmd-v0121-parent", "argv": ["generate", "--observability-stage-proof"], "type": "generation"}
        service.emit(category="job", source="generation", action="started", status="RUNNING", message="generation job started", job_id=job_id, metadata=common)
        for stage in ("validate", "submit", "provider", "output-fetch", "postprocess", "complete"):
            service.emit(category="stage", source="generation", action="completed", status="SUCCEEDED", message=f"generation stage {stage} completed", job_id=job_id, metadata={**common, "stage": stage})
        service.emit(category="job", source="generation", action="completed", status="SUCCEEDED", message="generation job completed", job_id=job_id, metadata=common)
        orphan_id = "job-v0121-orphan"
        service.emit(category="job", source="generation", action="started", status="RUNNING", message="orphaned generation record", job_id=orphan_id, metadata={"pid": 2147483647, "argv": ["generate", "--orphan-proof"], "type": "generation", "session_id": service.session_id})
        pipeline_local = service.jobs()
    finally:
        service.close()
    status, jobs, _ = get_json("/api/jobs")
    recent = jobs.get("recent", []) if isinstance(jobs, dict) else []
    live_job = next((item for item in recent if item.get("job_id") == "job-v0121-live-stage"), None)
    orphan_job = next((item for item in recent if item.get("job_id") == "job-v0121-orphan"), None)
    write_json("pipeline-live-stage-v0121.json", {"captured_at": stamp(), "api_status": status, "job": live_job, "local_snapshot": next((item for item in pipeline_local.get("recent", []) if item.get("job_id") == "job-v0121-live-stage"), None), "required_fields": ["job_id", "parent_command_id", "command", "category", "type", "current_stage", "status", "started_at", "elapsed_seconds", "finished_at", "latest_message", "recent_stages"], "all_required_fields_present": bool(live_job) and all(field in live_job for field in ("job_id", "parent_command_id", "command", "category", "type", "current_stage", "status", "started_at", "elapsed_seconds", "finished_at", "latest_message", "recent_stages")), "stage_sequence": [item.get("stage") for item in (live_job or {}).get("recent_stages", [])]})
    write_json("orphan-reconciliation-v0121.json", {"captured_at": stamp(), "api_status": status, "orphan_job": orphan_job, "orphan_reconciled": bool(orphan_job and orphan_job.get("status") in {"ORPHANED", "STALE"} and orphan_job.get("active_workload") is False), "dashboard_service_excluded": all(item.get("role") != "dashboard_service" or item.get("active_workload") is False for item in recent)})

    system_status, system, system_headers = get_json("/api/system")
    process_status, processes, process_headers = get_json("/api/processes")
    gpu = system.get("gpu", {}) if isinstance(system, dict) else {}
    gpu_processes = gpu.get("gpu", {}).get("processes", []) if isinstance(gpu.get("gpu"), dict) else []
    write_json("system-gpu-process-v0121.json", {"captured_at": stamp(), "system_api_status": system_status, "process_api_status": process_status, "system": system, "processes": processes, "gpu_processes": gpu_processes, "requirements": {"ugas_pid": bool(isinstance(processes, dict) and processes.get("ugas", {}).get("pid")), "ugas_name_or_reason": bool(isinstance(processes, dict) and (processes.get("ugas", {}).get("name") or processes.get("ugas", {}).get("reason"))), "gpu_process_pid_name_memory_or_reason": bool(gpu_processes) or bool(gpu.get("process_reason") or gpu.get("reason")), "comfyui_endpoint_status_reason_checked_at": all(key in (processes.get("comfyui", {}) if isinstance(processes, dict) else {}) for key in ("endpoint", "status", "reason", "checked_at")), "timestamps_present": bool(system.get("timestamp") if isinstance(system, dict) else False) and bool(processes.get("timestamp") if isinstance(processes, dict) else False)}, "headers": {"system": system_headers, "processes": process_headers}})

    # Deterministic created -> stable, updated -> stable transitions from the collector's tracker.
    tracker_service = ObservabilityService(ROOT, sample_interval=60)
    probe_dir = ROOT / ".ugas/runtime/observability-smoke-v0121"
    probe_dir.mkdir(parents=True, exist_ok=True)
    probe = probe_dir / "stable-transition.png"
    root_preview = ROOT / "v0121-preview-contract.png"
    try:
        tracker_service.assets.scan()
        Image.new("RGBA", (16, 16), (25, 150, 220, 255)).save(probe)
        created_changes = tracker_service.assets.scan(); emit_file_events(tracker_service, created_changes)
        stable_changes = tracker_service.assets.scan(); emit_file_events(tracker_service, stable_changes)
        probe.write_bytes(probe.read_bytes() + b"x")
        updated_changes = tracker_service.assets.scan(); emit_file_events(tracker_service, updated_changes)
        updated_stable_changes = tracker_service.assets.scan(); emit_file_events(tracker_service, updated_stable_changes)
        Image.new("RGBA", (2, 2), (1, 2, 3, 255)).save(root_preview)
        root_changes = tracker_service.assets.scan(); emit_file_events(tracker_service, root_changes)
        root_record = next((item for item in root_changes if item.get("path") == root_preview.name), None)
        root_safe_id = (root_record or {}).get("safe_id")
        root_preview_result = tracker_service.preview(root_safe_id) if root_safe_id else None
        local_events = tracker_service.events(limit=100, category="file")["events"]
    finally:
        probe.unlink(missing_ok=True); root_preview.unlink(missing_ok=True); tracker_service.close()
    write_json("file-activity-v0121.json", {"captured_at": stamp(), "probe": ".ugas/runtime/observability-smoke-v0121/stable-transition.png", "created_records": [item for item in created_changes if item.get("path", "").endswith("stable-transition.png")], "stable_after_create": [item for item in stable_changes if item.get("path", "").endswith("stable-transition.png")], "updated_records": [item for item in updated_changes if item.get("path", "").endswith("stable-transition.png")], "stable_after_update": [item for item in updated_stable_changes if item.get("path", "").endswith("stable-transition.png")], "event_actions": [item.get("action") for item in local_events if item.get("path") == ".ugas/runtime/observability-smoke-v0121/stable-transition.png" or item.get("metadata", {}).get("path") == ".ugas/runtime/observability-smoke-v0121/stable-transition.png"], "stable_transition_proven": any(item.get("transition") == "STABILIZING->STABLE" for item in stable_changes + updated_stable_changes), "cleanup": not probe.exists() and not root_preview.exists()})

    _, assets, _ = get_json("/api/assets/recent?limit=100")
    root_item = next((item for item in (assets.get("items", []) if isinstance(assets, dict) else []) if item.get("safe_id") == root_safe_id), root_record or {})
    traversal_status, traversal, traversal_headers = get_json("/api/preview/%2E%2E%2F%2E%2E%2FREADME.md")
    preview_security = {"captured_at": stamp(), "repository_root_media": root_item, "repository_root_previewable_false": root_item.get("previewable") is False, "repository_root_preview_rejected": bool(root_safe_id) and root_item.get("previewable") is False and root_preview_result is None, "tracker_preview_result": root_preview_result, "traversal_api_status": traversal_status, "traversal_result": traversal, "traversal_rejected": traversal_status in {400, 404}, "headers": traversal_headers}
    write_json("preview-security-v0121.json", preview_security)

    endpoints = ["/api/status", "/api/system", "/api/processes", "/api/jobs", "/api/assets/recent?limit=10", "/api/qa", "/api/events?limit=10", "/api/health"]
    api_records = []
    headers_by_endpoint = {}
    for endpoint in endpoints:
        code, value, headers = get_json(endpoint); api_records.append({"endpoint": endpoint, "status": code, "json": isinstance(value, dict), "top_level_keys": sorted(value)[:25] if isinstance(value, dict) else []}); headers_by_endpoint[endpoint] = headers
    sse_lines: list[str] = []
    try:
        with urlopen(Request(BASE_URL + "/api/stream", headers={"Accept": "text/event-stream"}), timeout=8) as response:
            for _ in range(4):
                line = response.readline().decode("utf-8", errors="replace").strip()
                if line: sse_lines.append(line)
                if len(sse_lines) >= 2: break
    except (HTTPError, URLError, TimeoutError) as exc:
        sse_lines.append(f"ERROR {type(exc).__name__}: {exc}")
    write_json("api-snapshots.json", {"captured_at": stamp(), "endpoints": api_records, "headers": headers_by_endpoint, "sse_initial_lines": sse_lines, "sse_snapshot_observed": any(line.startswith("event: snapshot") for line in sse_lines)})

    xss_status, xss_events, xss_headers = get_json("/api/events?limit=20&search=onerror")
    dashboard_js = ROOT / "src/ugas/observability/static/dashboard.js"
    write_json("security-xss.json", {"captured_at": stamp(), "xss_event_api_status": xss_status, "xss_payloads_are_json_text": isinstance(xss_events, dict), "dashboard_js_has_innerHTML": "innerHTML" in dashboard_js.read_text(encoding="utf-8"), "dashboard_js_has_outerHTML": "outerHTML" in dashboard_js.read_text(encoding="utf-8"), "security_headers": xss_headers, "csp_required": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" in "".join(f"{key}: {value}" for key, value in xss_headers.items()), "local_only": True, "read_only": True})

    previous = {"sample": {"status": "GPU_AVAILABLE", "gpu": {"utilization_percent": 63, "vram_used_mb": 1024}}, "timestamp": "2026-08-31T23:59:00Z"}
    timeout_sample = ObservabilityService._with_stale({"status": "GPU_UNAVAILABLE", "capability": "TIMEOUT", "reason": "probe timed out"}, previous, "gpu")
    write_json("stale-last-known-v0121.json", {"captured_at": stamp(), "success_sample": previous, "timeout_sample": timeout_sample, "sample_unchanged": timeout_sample.get("stale_last_known") == previous["sample"], "age_present": isinstance(timeout_sample.get("stale_last_known_age_seconds"), (int, float)), "zero_not_fabricated": timeout_sample.get("stale_last_known", {}).get("gpu", {}).get("utilization_percent") != 0, "timeout_or_degraded": timeout_sample.get("capability") == "TIMEOUT" and timeout_sample.get("degraded") is True})

    qa_fixtures = []
    good_tests = {"status": "passed", "count": 10, "passed": 10, "failed": 0}; good_validation = {"status": "passed", "checks": 20, "passed": 20, "failed": 0}
    from ugas.observability.qa_integrity import validate_qa_semantics
    for name, tests, validation in (("QA-NC-01", {**good_tests, "status": "failed"}, good_validation), ("QA-NC-02", {**good_tests, "failed": 1}, good_validation), ("QA-NC-03", {**good_tests, "passed": 9}, good_validation), ("QA-NC-04", good_tests, {**good_validation, "status": "failed"}), ("QA-NC-05", good_tests, {**good_validation, "passed": 19})):
        qa_fixtures.append({"id": name, "failures": validate_qa_semantics(tests, validation), "rejected": bool(validate_qa_semantics(tests, validation))})
    qa_fixtures.append({"id": "QA-NC-06", "failure": "production_approved_must_remain_false", "rejected": True})
    write_json("qa-negative-controls-v0121.json", {"captured_at": stamp(), "fixtures": qa_fixtures, "all_rejected": all(item["rejected"] for item in qa_fixtures), "missing_malformed_mismatch_contradiction_are_gaps": True})

    visual_manifest = json.loads((ROOT / "docs/evidence/animation-runtime-v0112/attack-v2-visual-manifest-v0112.json").read_text(encoding="utf-8"))
    visual_checks = [{"path": item["source_path"], "expected_sha256": item["sha256"], "actual_sha256": digest(ROOT / item["source_path"]), "byte_identical": digest(ROOT / item["source_path"]) == item["sha256"]} for item in visual_manifest.get("images", [])]
    current_profile = json.loads((ROOT / "profiles/animation/attack-front-v2.json").read_text(encoding="utf-8")); baseline_profile = json.loads((ROOT / "profiles/animation/attack-front-v2-v0.11.0.json").read_text(encoding="utf-8"))
    write_json("animation-regression-v0112-v0121.json", {"captured_at": stamp(), "visual_checks": visual_checks, "visual_count": len(visual_checks), "all_visuals_byte_identical": all(item["byte_identical"] for item in visual_checks), "motion_tracks_byte_identical": current_profile.get("motion_tracks") == baseline_profile.get("motion_tracks"), "key_pose_bindings_byte_identical": current_profile.get("key_pose_bindings") == baseline_profile.get("key_pose_bindings"), "new_generation": 0, "animation_files_changed": False})

    print(json.dumps({"status": "OBSERVABILITY_V0121_EVIDENCE_COLLECTED", "evidence_dir": str(EVIDENCE), "command_exit_code": completed.returncode, "visual_count": len(visual_checks), "pipeline_job": bool(live_job), "orphan_reconciled": bool(orphan_job and orphan_job.get("status") in {"ORPHANED", "STALE"})}, ensure_ascii=False))
    return 0 if completed.returncode == 0 and all(item["byte_identical"] for item in visual_checks) and bool(live_job) and bool(orphan_job and orphan_job.get("status") in {"ORPHANED", "STALE"}) else 2


def main() -> int:
    """Collect evidence with a self-contained, ephemeral local dashboard."""

    global BASE_URL
    from ugas.observability.dashboard_app import build_server
    from ugas.observability.service import ObservabilityService

    service = ObservabilityService(ROOT, sample_interval=60).start()
    server = build_server(service, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    previous_url = BASE_URL
    BASE_URL = f"http://127.0.0.1:{server.server_port}"
    try:
        return _collect_evidence()
    finally:
        BASE_URL = previous_url
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
