"""Collect v0.12.2 Stage A contracts and Docker runtime evidence."""

from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
from urllib.parse import quote
from urllib.request import Request, urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/observability-v0122"
BASE_URL = os.environ.get("UGAS_OBSERVABILITY_URL", "http://127.0.0.1:8765").rstrip("/")


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_json(name: str, value: object) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def get_json(path: str) -> tuple[int, object, dict[str, str]]:
    try:
        url = path if path.startswith("http://") or path.startswith("https://") else BASE_URL + path
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=5) as response:
            return int(response.status), json.loads(response.read().decode("utf-8")), dict(response.headers.items())
    except Exception as exc:
        return int(getattr(exc, "code", 599)), {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}, {}


def _copy_current_worktree_to_clone(source: Path, destination: Path) -> None:
    """Overlay only the active index and its listed files on a clean clone."""
    index_path = source / "docs/evidence/review-index-v0.12.2.json"
    if not index_path.is_file():
        return
    index = json.loads(index_path.read_text(encoding="utf-8"))
    paths = {item.get("path") for item in index.get("artifact_set", {}).get("artifacts", []) if item.get("path")}
    paths.update({
        "docs/evidence/review-index-v0.12.2.json",
        "docs/evidence/current-state.json",
        "schemas/current-state.json",
        "schemas/review-index-v0122.json",
        "CHECKPOINT.md",
        "REVIEW-v0.12.2.md",
    })
    for relative in paths:
        source_path = source / relative
        if not source_path.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)


def _prepare_clean_fixture(source: Path, destination: Path) -> bool:
    """Create a clean, descendant-capable fixture carrying the active evidence."""
    if not (source / "docs/evidence/review-index-v0.12.2.json").is_file():
        return False
    cloned = subprocess.run(
        ["git", "clone", "--shared", "--no-checkout", "--no-tags", str(source), str(destination)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )
    if cloned.returncode != 0:
        return False
    _copy_current_worktree_to_clone(source, destination)
    subprocess.run(["git", "add", "-A"], cwd=destination, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    committed = subprocess.run(
        ["git", "-c", "user.name=UGAS QA", "-c", "user.email=qa@example.invalid", "commit", "-m", "QA fixture current worktree"],
        cwd=destination,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=30,
    )
    return committed.returncode == 0


@contextmanager
def qa_api(cache):
    from ugas.observability.dashboard_app import build_server
    from ugas.observability.service import ObservabilityService
    service = ObservabilityService(ROOT, sample_interval=60)
    service._qa_cache = cache
    server = build_server(service, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/api/qa", timeout=5) as response:
            yield json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2); service.close()


def collect_qa_cache() -> dict:
    from ugas.observability.qa_integrity import ActiveEvidenceCache, validate_qa_semantics
    fixture_results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="ugas-v0122-qa-") as directory:
        temporary = Path(directory)
        malformed = temporary / "malformed-current-state.json"; malformed.write_text("{ malformed", encoding="utf-8")
        with qa_api(ActiveEvidenceCache(ROOT, state_path=malformed)) as result:
            fixture_results.append({"id": "QA-NC-01", "status": result.get("status"), "reason": result.get("reason"), "rejected": result.get("status") in {"GAP", "ERROR"}})
        invalid = temporary / "schema-invalid-current-state.json"
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8")); state["version"] = "tampered"
        invalid.write_text(json.dumps(state), encoding="utf-8")
        with qa_api(ActiveEvidenceCache(ROOT, state_path=invalid)) as result:
            fixture_results.append({"id": "QA-NC-02", "status": result.get("status"), "reason": result.get("reason"), "rejected": result.get("status") in {"GAP", "ERROR"}})
        good_tests = {"status": "passed", "count": 10, "passed": 10, "failed": 0}; good_validation = {"status": "passed", "checks": 20, "passed": 20, "failed": 0}
        fixture_results.append({"id": "QA-NC-03", "failures": validate_qa_semantics({**good_tests, "failed": 1}, good_validation), "rejected": bool(validate_qa_semantics({**good_tests, "failed": 1}, good_validation))})
        fixture_results.append({"id": "QA-NC-04", "failures": validate_qa_semantics(good_tests, {**good_validation, "passed": 19}), "rejected": bool(validate_qa_semantics(good_tests, {**good_validation, "passed": 19}))})
        index_path = ROOT / "docs/evidence/review-index-v0.12.2.json"
        if index_path.is_file():
            tampered = temporary / "tampered-review-index.json"; index = json.loads(index_path.read_text(encoding="utf-8")); index["artifact_set"]["artifact_set_sha256"] = "0" * 64; tampered.write_text(json.dumps(index), encoding="utf-8")
            with qa_api(ActiveEvidenceCache(ROOT, review_index_path=tampered)) as result:
                fixture_results.append({"id": "QA-NC-05", "status": result.get("status"), "reason": result.get("reason"), "rejected": result.get("status") != "PASS"})
        else:
            fixture_results.append({"id": "QA-NC-05", "status": "GAP", "reason": "REVIEW_INDEX_NOT_BUILT", "rejected": True})
        governance = temporary / "governance-invalid-current-state.json"; state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8")); state["production_approved"] = True; governance.write_text(json.dumps(state), encoding="utf-8")
        with qa_api(ActiveEvidenceCache(ROOT, state_path=governance)) as result:
            fixture_results.append({"id": "QA-NC-06", "status": result.get("status"), "reason": result.get("reason"), "rejected": result.get("status") != "PASS"})
        clean = {"status": "GAP", "reason": "CLEAN_FIXTURE_NOT_READY"}
        dirty = {"status": "GAP", "reason": "CLEAN_FIXTURE_NOT_READY"}
        head_change = {"clean_pass": False, "second_status": "GAP", "rejected": False, "reason": "CLEAN_FIXTURE_NOT_READY"}
        with tempfile.TemporaryDirectory(prefix="ugas-v0122-clean-") as clone_directory:
            clone = Path(clone_directory) / "repo"
            if _prepare_clean_fixture(ROOT, clone):
                clone_cache = ActiveEvidenceCache(clone)
                clean = clone_cache.validate()
                source = clone / "src/ugas/observability/static/dashboard.css"
                original = source.read_bytes()
                try:
                    source.write_bytes(original + b"\n/* QA-NC-07 temporary mutation */\n")
                    dirty = clone_cache.validate()
                finally:
                    source.write_bytes(original)
                fixture_results.append({"id": "QA-NC-07", "clean_status": clean.get("status"), "dirty_status": dirty.get("status"), "reason": dirty.get("reason"), "rejected": clean.get("status") == "PASS" and dirty.get("status") == "GAP"})
                first = clone_cache.validate()
                head_change = {"clean_pass": first.get("status") == "PASS", "second_status": "GAP", "rejected": False}
                target = clone / "README.md"
                target.write_bytes(target.read_bytes() + b"\nQA-NC-08 descendant mutation\n")
                subprocess.run(["git", "add", "README.md"], cwd=clone, check=True, timeout=10)
                subprocess.run(["git", "-c", "user.name=UGAS QA", "-c", "user.email=qa@example.invalid", "commit", "-m", "QA-NC-08 descendant"], cwd=clone, check=True, capture_output=True, timeout=30)
                second = clone_cache.validate()
                head_change.update({"second_status": second.get("status"), "reason": second.get("reason"), "current_head_changed": first.get("current_head") != second.get("current_head"), "rejected": second.get("status") == "GAP" and first.get("current_head") != second.get("current_head")})
            else:
                fixture_results.append({"id": "QA-NC-07", "clean_status": clean.get("status"), "dirty_status": dirty.get("status"), "reason": clean.get("reason"), "rejected": False})
        fixture_results.append({"id": "QA-NC-08", **head_change})
    value = {"captured_at": stamp(), "fixtures": fixture_results, "fixture_ids": [item["id"] for item in fixture_results], "all_exact": [item["id"] for item in fixture_results] == [f"QA-NC-{index:02d}" for index in range(1, 9)], "all_rejected": all(item.get("rejected") is True for item in fixture_results)}
    write_json("qa-negative-controls-v0122.json", value)
    write_json("qa-cache-invalidation-v0122.json", {"captured_at": stamp(), "clean_pass": clean.get("status") == "PASS", "dirty_source_gap": clean.get("status") == "PASS" and dirty.get("status") == "GAP", "head_change_gap": head_change.get("rejected") is True, "source_change_reason": dirty.get("reason"), "head_change_reason": head_change.get("reason")})
    return value


def collect_stale_integration() -> dict:
    import ugas.observability.service as service_module
    from ugas.observability.dashboard_app import build_server
    from ugas.observability.service import ObservabilityService
    good_gpu = {"status": "GPU_AVAILABLE", "capability": "NVIDIA_SMI", "reason": None, "gpu": {"name": "Fixture GPU", "utilization_percent": 63, "vram_used_mb": 1024, "vram_total_mb": 4096}, "timestamp": stamp()}
    good_processes = {"status": "GPU_PROCESS_AVAILABLE", "capability": "NVIDIA_SMI", "reason": None, "processes": [], "timestamp": stamp()}
    good_comfy = {"endpoint": "http://host.docker.internal:8188", "checked_at": stamp(), "status": "UP", "health": "HEALTHY", "reason": None}
    service = ObservabilityService(ROOT, sample_interval=60)
    try:
        with patch.object(service_module, "probe_nvidia_smi", return_value=good_gpu), patch.object(service_module, "probe_nvidia_processes", return_value=good_processes), patch.object(service_module, "probe_endpoint", return_value=good_comfy): service.refresh(include_assets=False)
        def slow(*args, **kwargs): time.sleep(2.0); raise TimeoutError("fixture timeout")
        with patch.object(service_module, "probe_nvidia_smi", side_effect=slow), patch.object(service_module, "probe_nvidia_processes", side_effect=slow), patch.object(service_module, "probe_endpoint", side_effect=slow): service.refresh(include_assets=False)
        system = service.system(); processes = service.processes(); server = build_server(service, "127.0.0.1", 0); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            started = time.monotonic(); code_system, api_system, _ = get_json(f"http://127.0.0.1:{server.server_port}/api/system"); code_process, api_processes, _ = get_json(f"http://127.0.0.1:{server.server_port}/api/processes"); api_elapsed = time.monotonic() - started
        finally: server.shutdown(); server.server_close(); thread.join(timeout=2)
    finally: service.close()
    # The local get_json helper targets the configured dashboard. Read the API
    # directly for the ephemeral integration server used above.
    value = {"captured_at": stamp(), "service_refresh_proof": "stale_last_known" in system.get("gpu", {}) and "stale_last_known" in processes.get("comfyui", {}), "api_proof": code_system == 200 and code_process == 200 and isinstance(api_system, dict) and isinstance(api_processes, dict), "api_system": api_system, "api_processes": api_processes, "api_elapsed_seconds": round(api_elapsed, 4), "no_slow_probe_on_api": api_elapsed < 1.0, "zero_not_fabricated": system.get("gpu", {}).get("stale_last_known", {}).get("gpu", {}).get("utilization_percent") != 0}
    write_json("stale-last-known-integration-v0122.json", value)
    return value


def collect_generation_contract() -> dict:
    from ugas.generation import _run_job
    from ugas.observability.service import ObservabilityService
    from ugas.workflow_registry import load_workflow
    class FakeProvider:
        base_url = "http://fake-provider.invalid"
        def submit_workflow(self, workflow, *, client_id): return {"prompt_id": "fake-prompt-v0122"}
        def poll_history(self, prompt_id, *, on_poll=None):
            if on_poll: on_poll(prompt_id)
            return {"_ugas_prompt_id": prompt_id, "status": {"completed": True, "status_str": "success"}}
        def fetch_history_outputs(self, history):
            output = BytesIO(); Image.new("RGBA", (2, 2), (20, 30, 40, 255)).save(output, format="PNG"); return [{"filename": "output.png", "subfolder": "", "type": "output", "node_id": "1", "data": output.getvalue()}]
    workflow = load_workflow(ROOT, "flux2-klein-4b-distilled-text-to-image"); service = ObservabilityService(ROOT, sample_interval=60)
    instrumented_events: list[dict[str, object]] = []
    original_emit = service.emit
    def recording_emit(*args, **kwargs):
        if kwargs.get("category") == "stage":
            instrumented_events.append({"stage": (kwargs.get("metadata") or {}).get("stage"), "action": kwargs.get("action"), "status": kwargs.get("status"), "job_id": kwargs.get("job_id"), "parent_command_id": (kwargs.get("metadata") or {}).get("parent_command_id")})
        return original_emit(*args, **kwargs)
    service.emit = recording_emit
    try:
        with tempfile.TemporaryDirectory(prefix="ugas-v0122-generation-") as directory:
            with service.command(["generate", "--fake-provider"]) as parent: result, _ = _run_job(ROOT, FakeProvider(), workflow["api"], output_dir=Path(directory), filename="output.png", profile="generic-2d", capability="2d", workflow_id=workflow["id"], model_id="flux2-klein-4b-distilled-nvfp4", prompt="fixture", seed=1, width=2, height=2)
            job = next(item for item in service.jobs()["recent"] if item.get("job_id") == result["job"]["job_id"])
    finally: service.close()
    stages = [str(item.get("stage")) for item in instrumented_events]; parent_bound = any(item.get("parent_command_id") == parent for item in instrumented_events); value = {"captured_at": stamp(), "actual_instrumentation_path": True, "fake_provider": True, "new_generation": 0, "parent_command_id": job.get("parent_command_id") == parent, "parent_command_bound": parent_bound, "real_stage_names": all(name in stages for name in ("validate", "submit", "provider", "output-fetch", "postprocess", "complete")), "job": job, "stage_names": stages, "instrumented_stage_events": instrumented_events}
    write_json("generation-telemetry-contract-v0122.json", value)
    return value


def collect_stage_a() -> dict:
    qa = collect_qa_cache(); stale = collect_stale_integration(); generation = collect_generation_contract()
    result = {"status": "STAGE_A_EVIDENCE_COLLECTED", "qa_negative_controls": qa.get("all_rejected"), "stale_integration": stale.get("service_refresh_proof") and stale.get("api_proof"), "generation_contract": generation.get("real_stage_names")}
    print(json.dumps(result, ensure_ascii=False)); return result


def _run(command: list[str], *, timeout: int = 60, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=timeout, env=env)
    return result.returncode, result.stdout, result.stderr


def _wait_for_api(timeout: int = 45) -> tuple[int, object]:
    deadline = time.monotonic() + timeout
    last: tuple[int, object] = (599, {"status": "ERROR", "reason": "API_NOT_REACHED"})
    while time.monotonic() < deadline:
        code, value, _ = get_json("/api/health")
        last = (code, value)
        if code == 200:
            return last
        time.sleep(1)
    return last


def _wait_for_event(*, category: str, search: str, timeout: int = 45) -> dict[str, object] | None:
    deadline = time.monotonic() + timeout
    path = f"/api/events?category={quote(category)}&search={quote(search)}&limit=100"
    while time.monotonic() < deadline:
        code, value, _ = get_json(path)
        if code == 200 and isinstance(value, dict) and value.get("events"):
            return value
        time.sleep(1)
    return None


def _wait_for_command_argv(argv: list[str], timeout: int = 45) -> dict[str, object] | None:
    """Find a host CLI command by its structured argv metadata."""
    deadline = time.monotonic() + timeout
    path = "/api/events?category=command&limit=100"
    while time.monotonic() < deadline:
        code, value, _ = get_json(path)
        if code == 200 and isinstance(value, dict):
            events = value.get("events", [])
            if any(isinstance(item, dict) and (item.get("metadata") or {}).get("argv") == argv for item in events):
                return value
        time.sleep(1)
    return None


def collect_docker() -> dict:
    import shutil as _shutil
    preflight = {}
    for name, command in (("docker", ["docker", "version", "--format", "{{.Server.Version}}"]), ("compose", ["docker", "compose", "version", "--short"]), ("context", ["docker", "context", "show"]), ("host_gpu", ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])):
        code, out, err = _run(command, timeout=30) if _shutil.which(command[0]) else (127, "", f"{command[0]} not found")
        preflight[name] = {"exit_code": code, "stdout": out.strip(), "stderr": err.strip()[-500:]}
    gpu_probe_code, gpu_probe, gpu_probe_err = _run(["docker", "run", "--rm", "--gpus", "all", "--entrypoint", "nvidia-smi", "ugas-dashboard:0.12.2", "--query-gpu=name", "--format=csv,noheader"], timeout=30)
    gpu_available = gpu_probe_code == 0 and bool(gpu_probe.strip())
    compose_args = ["docker", "compose", "-f", "compose.yaml"] + (["-f", "compose.gpu.yaml"] if gpu_available else [])
    code, config, err = _run([*compose_args, "config", "--format", "json"], timeout=30)
    normalized = {}
    if code == 0:
        try: normalized = json.loads(config)
        except json.JSONDecodeError: normalized = {}
    service = normalized.get("services", {}).get("dashboard", {})
    port_records = service.get("ports", [])
    first_port = port_records[0] if port_records else {}
    if isinstance(first_port, dict):
        host_publication = f"{first_port.get('host_ip', '')}:{first_port.get('published', '')}"
    else:
        host_publication = str(first_port).rsplit(":", 1)[0] if first_port else ""
    compose_value = {"captured_at": stamp(), "compose_config_exit_code": code, "compose_config_error": err[-500:], "compose_files": compose_args[3::2], "gpu_requested": gpu_available, "gpu_probe": gpu_probe.strip(), "gpu_probe_error": gpu_probe_err.strip()[-500:], "host_publication": host_publication, "ports": port_records, "repo_read_only": any(item.get("target") == "/workspace/ugas" and item.get("read_only") is True for item in service.get("volumes", []) if isinstance(item, dict)), "runtime_read_write": any(item.get("target") == "/workspace/ugas/.ugas/runtime" and item.get("read_only") is not True for item in service.get("volumes", []) if isinstance(item, dict)), "restart": service.get("restart"), "non_root": service.get("user") in {"10001:10001", "10001"}, "no_socket": not any("docker.sock" in json.dumps(item) for item in service.get("volumes", [])), "normalized": normalized}
    write_json("docker-preflight-v0122.json", {"captured_at": stamp(), "checks": preflight})
    write_json("docker-compose-config-v0122.json", compose_value)
    code, image, err = _run(["docker", "image", "inspect", "ugas-dashboard:0.12.2", "--format", "{{json .}}"], timeout=20); image_value = json.loads(image) if code == 0 and image.strip() else {}
    write_json("docker-build-v0122.json", {"captured_at": stamp(), "status": "BUILT" if code == 0 else "BUILD_GAP", "exit_code": code, "image": image_value, "error": err[-500:]})
    code, inspect, err = _run(["docker", "inspect", "ugas-dashboard", "--format", "{{json .}}"], timeout=20); runtime = json.loads(inspect) if code == 0 and inspect.strip() else {}
    status_code, status, _ = get_json("/api/status"); health_code, health, _ = get_json("/api/health")
    write_json("docker-runtime-v0122.json", {"captured_at": stamp(), "container": runtime, "container_id": runtime.get("Id"), "container_status": runtime.get("State", {}).get("Status"), "health": runtime.get("State", {}).get("Health", {}).get("Status"), "started_at": runtime.get("State", {}).get("StartedAt"), "local_url": BASE_URL + "/", "api_status_code": status_code, "api_status": status, "api_health_code": health_code, "api_health": health})
    host_env = os.environ.copy(); host_env["PYTHONPATH"] = str(ROOT / "src")
    host_command_started = stamp()
    command_code, command_out, command_err = _run([sys.executable, "-m", "ugas.cli", "models", "list"], timeout=30, env=host_env)
    command_event = _wait_for_command_argv(["models", "list"]) if command_code == 0 else None
    write_json("docker-cross-process-telemetry-v0122.json", {"captured_at": stamp(), "host_command": "python -m ugas.cli models list", "started_at": host_command_started, "exit_code": command_code, "stdout_tail": command_out[-1000:], "stderr_tail": command_err[-500:], "host_command_visible_in_container_api": command_event is not None, "event_payload": command_event})

    watch_path = ROOT / ".ugas/runtime/observability-watch-v0122.txt"
    watch_token = f"watch-{int(time.time())}"
    watch_started = stamp()
    watch_path.write_text(watch_token + "\n", encoding="utf-8")
    try:
        created_event = _wait_for_event(category="file", search="observability-watch-v0122")
        stable_event = None
        stable_deadline = time.monotonic() + 45
        while time.monotonic() < stable_deadline:
            stable_event = _wait_for_event(category="file", search="observability-watch-v0122", timeout=2)
            if stable_event and any(item.get("action") == "stable" or item.get("transition") == "STABILIZING->STABLE" for item in stable_event.get("events", []) if isinstance(item, dict)):
                break
        write_json("docker-file-watch-v0122.json", {"captured_at": stamp(), "path": ".ugas/runtime/observability-watch-v0122.txt", "created_at": watch_started, "created_event_visible": created_event is not None, "stable_event_visible": bool(stable_event and any(item.get("action") == "stable" or item.get("transition") == "STABILIZING->STABLE" for item in stable_event.get("events", []) if isinstance(item, dict))), "created_event": created_event, "stable_event": stable_event})
    finally:
        try: watch_path.unlink()
        except FileNotFoundError: pass

    restart_code, restart_out, restart_err = _run([*compose_args, "restart", "dashboard"], timeout=60)
    restart_health_code, restart_health = _wait_for_api()
    restart_event = _wait_for_command_argv(["models", "list"], timeout=15)
    rebuild_code, rebuild_out, rebuild_err = _run([*compose_args, "up", "-d", "--build"], timeout=360)
    rebuild_health_code, rebuild_health = _wait_for_api()
    rebuild_event = _wait_for_command_argv(["models", "list"], timeout=30)
    write_json("docker-persistence-v0122.json", {"captured_at": stamp(), "restart": {"exit_code": restart_code, "stdout_tail": (restart_out or "")[-500:], "stderr_tail": (restart_err or "")[-500:], "health_code": restart_health_code, "health": restart_health, "event_survived_restart": restart_event is not None}, "rebuild": {"exit_code": rebuild_code, "stdout_tail": (rebuild_out or "")[-500:], "stderr_tail": (rebuild_err or "")[-500:], "health_code": rebuild_health_code, "health": rebuild_health, "event_survived_rebuild": rebuild_event is not None}, "telemetry_db": ".ugas/runtime/telemetry.db"})

    install_code, install_out, install_err = _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts/docker/install-dashboard-autostart.ps1"], timeout=60)
    write_json("docker-autostart-v0122.json", {"captured_at": stamp(), "task_name": "UGAS-Dashboard-AlwaysOn", "install_exit_code": install_code, "install_stdout": install_out[-1000:], "install_stderr": install_err[-500:], "status": "INSTALLED" if install_code == 0 else "AUTOSTART_INSTALL_GAP"})

    code, inspect, err = _run(["docker", "inspect", "ugas-dashboard", "--format", "{{json .}}"], timeout=20); security_runtime = json.loads(inspect) if code == 0 and inspect.strip() else {}
    host_config = security_runtime.get("HostConfig", {})
    security_mounts = security_runtime.get("Mounts", [])
    write_json("docker-security-v0122.json", {"captured_at": stamp(), "container_inspect_exit_code": code, "non_root_user": security_runtime.get("Config", {}).get("User") in {"10001", "10001:10001"}, "read_only_rootfs": host_config.get("ReadonlyRootfs") is True, "no_new_privileges": "no-new-privileges:true" in host_config.get("SecurityOpt", []), "cap_drop_all": "ALL" in host_config.get("CapDrop", []), "docker_socket_mounted": any("docker.sock" in json.dumps(item) for item in security_mounts), "repo_mount_read_only": any(item.get("Destination") == "/workspace/ugas" and item.get("RW") is False for item in security_mounts if isinstance(item, dict)), "runtime_mount_read_write": any(item.get("Destination") == "/workspace/ugas/.ugas/runtime" and item.get("RW") is True for item in security_mounts if isinstance(item, dict)), "host_port_loopback": compose_value.get("host_publication") == "127.0.0.1:8765", "restart_policy": security_runtime.get("HostConfig", {}).get("RestartPolicy", {}).get("Name"), "mounts": security_mounts})

    code, gpu, err = _run(["docker", "exec", "ugas-dashboard", "nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw", "--format=csv,noheader,nounits"], timeout=10); write_json("docker-gpu-v0122.json", {"captured_at": stamp(), "status": "GPU_AVAILABLE" if code == 0 and gpu.strip() else "GPU_CONTAINER_RUNTIME_GAP", "exit_code": code, "output": gpu.strip(), "reason": None if code == 0 and gpu.strip() else (err or gpu).strip()[-500:], "requested_by_compose": gpu_available})
    return compose_value


def main() -> int:
    stage_only = "--stage-a" in sys.argv[1:]
    collect_stage_a()
    if stage_only: return 0
    if not Path(ROOT / "compose.yaml").is_file(): return 2
    collect_docker(); return 0


if __name__ == "__main__": raise SystemExit(main())
