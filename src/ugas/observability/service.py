"""Application service joining local telemetry, collectors and API data."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid
from typing import Any, Iterator, Mapping

from ..constants import UGAS_VERSION
from .asset_activity import AssetActivityTracker
from .events import TelemetryEvent
from .process_metrics import collect_process_metrics, probe_endpoint
from .qa_integrity import ActiveEvidenceCache
from .store import TelemetryStore
from .system_metrics import CpuSampler, collect_system_metrics, probe_nvidia_processes, probe_nvidia_smi

_CURRENT: ContextVar["ObservabilityService | None"] = ContextVar("ugas_observability_service", default=None)
_CURRENT_COMMAND: ContextVar[str | None] = ContextVar("ugas_observability_command", default=None)


def current_service() -> "ObservabilityService | None":
    return _CURRENT.get()


def current_command_id() -> str | None:
    return _CURRENT_COMMAND.get()


@contextmanager
def bind_service(service: "ObservabilityService") -> Iterator["ObservabilityService"]:
    token = _CURRENT.set(service)
    try:
        yield service
    finally:
        _CURRENT.reset(token)


def record_event(repo_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Write one bounded event for short-lived scripts without workers."""

    service = ObservabilityService(repo_root)
    try:
        return service.emit(**kwargs).to_dict()
    finally:
        service.close()


class ObservabilityService:
    """Read-only observation service with non-blocking request snapshots."""

    def __init__(self, repo_root: Path, *, max_events: int = 5000, sample_interval: float = 1.0) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.runtime_dir = self.repo_root / ".ugas" / "runtime"
        self.telemetry_db = self.runtime_dir / "telemetry.db"
        self.store = TelemetryStore(self.telemetry_db, max_events=max_events)
        self.assets = AssetActivityTracker(self.repo_root)
        self.sample_interval = max(0.4, float(sample_interval))
        self.started_at = time.monotonic()
        self.started_at_iso = _now()
        self.pid = os.getpid()
        self.session_id = f"sess-{uuid.uuid4().hex}"
        self.cpu_sampler = CpuSampler()
        self._latest_system: dict[str, Any] = {}
        self._latest_processes: dict[str, Any] = {}
        self._last_good_gpu: dict[str, Any] | None = None
        self._last_good_comfyui: dict[str, Any] | None = None
        self._probe_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ugas-probe")
        self._subscribers: set[queue.Queue[dict[str, Any]]] = set()
        self._subscriber_lock = threading.Lock()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._closed = False
        self._finished_commands: set[str] = set()
        self._asset_lock = threading.Lock()
        self._qa_cache = ActiveEvidenceCache(self.repo_root)
        self._latest_qa: dict[str, Any] | None = None
        self._latest_stream_snapshot: dict[str, Any] | None = None

    def start(self, *, prime: bool = True) -> "ObservabilityService":
        if self._worker and self._worker.is_alive():
            return self
        if prime:
            try:
                self.assets.scan()
                # Prime the snapshot outside the HTTP request path. Slow probes are
                # parallel and later requests only read the latest collected value.
                self.refresh()
            except Exception as exc:  # pragma: no cover - platform dependent
                self.emit(category="error", severity="warning", source="observability", action="startup", status="DEGRADED", message="initial telemetry sample unavailable", metadata={"reason": type(exc).__name__})
        self._stop.clear()
        self._worker = threading.Thread(target=self._collect_loop, name="ugas-observability", daemon=True)
        self._worker.start()
        return self

    def _collect_loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.refresh()
            except Exception as exc:  # observability must never escape the worker
                self.emit(category="error", severity="warning", source="observability", action="collector", status="DEGRADED", message="telemetry collector failed safely", metadata={"reason": type(exc).__name__})
            self._stop.wait(max(0.05, self.sample_interval - (time.monotonic() - started)))

    def _collect_resources(self) -> tuple[dict[str, Any], dict[str, Any]]:
        endpoint = os.environ.get("UGAS_COMFYUI_URL", "http://127.0.0.1:8188")
        gpu_future = self._probe_executor.submit(probe_nvidia_smi, include_processes=False)
        process_future = self._probe_executor.submit(probe_nvidia_processes)
        comfy_future = self._probe_executor.submit(probe_endpoint, endpoint)
        pending_gpu = {"status": "GPU_PENDING", "capability": "COLLECTING", "reason": "collector is warming up", "timestamp": _now()}
        system = collect_system_metrics(self.repo_root, pid=self.pid, cpu_sampler=self.cpu_sampler, gpu_probe=pending_gpu)
        gpu = self._future_value(gpu_future, pending_gpu, "GPU probe")
        processes = self._future_value(process_future, {"status": "GPU_PROCESS_UNAVAILABLE", "capability": "ERROR", "reason": "GPU process probe failed", "processes": [], "timestamp": _now()}, "GPU process probe")
        if gpu.get("status") == "GPU_AVAILABLE":
            gpu.setdefault("gpu", {})["processes"] = processes.get("processes", [])
            gpu.setdefault("gpu", {})["process_status"] = processes.get("status")
            gpu.setdefault("gpu", {})["process_reason"] = processes.get("reason")
            self._last_good_gpu = {"sample": deepcopy(gpu), "timestamp": gpu.get("timestamp", _now())}
        else:
            gpu = self._with_stale(gpu, self._last_good_gpu, "gpu")
        system["gpu"] = gpu
        comfy = self._future_value(comfy_future, {"endpoint": endpoint, "checked_at": _now(), "status": "UNAVAILABLE", "health": "UNAVAILABLE", "reason": "ComfyUI probe did not complete", "probe_status": "TIMEOUT"}, "ComfyUI probe")
        if comfy.get("health") == "HEALTHY":
            self._last_good_comfyui = {"sample": deepcopy(comfy), "timestamp": comfy.get("checked_at", _now())}
        else:
            comfy = self._with_stale(comfy, self._last_good_comfyui, "comfyui")
        process_snapshot = collect_process_metrics(self.pid, comfyui_endpoint=endpoint, comfyui_probe=comfy)
        return system, process_snapshot

    @staticmethod
    def _future_value(future: Future, fallback: dict[str, Any], label: str) -> dict[str, Any]:
        try:
            return future.result(timeout=1.5)
        except FutureTimeoutError:
            value = deepcopy(fallback); value["probe_status"] = "TIMEOUT"; value["degraded"] = True; value["reason"] = f"{label} timed out"; return value
        except Exception as exc:  # pragma: no cover - platform dependent
            value = deepcopy(fallback); value["probe_status"] = "ERROR"; value["degraded"] = True; value["reason"] = f"{label} failed: {type(exc).__name__}"; return value

    @staticmethod
    def _with_stale(current: dict[str, Any], previous: dict[str, Any] | None, key: str) -> dict[str, Any]:
        if not previous:
            current.setdefault("degraded", True)
            return current
        previous_sample = deepcopy(previous.get("sample", {}))
        timestamp = previous.get("timestamp")
        current["stale_last_known"] = previous_sample
        current["stale_last_known_timestamp"] = timestamp
        current["stale_last_known_age_seconds"] = _age_seconds(timestamp)
        current["degraded"] = True
        current["stale_metric"] = key
        current.setdefault("probe_status", "DEGRADED")
        return current

    def refresh(self, *, include_assets: bool = True) -> None:
        self._latest_system, self._latest_processes = self._collect_resources()
        self.emit(category="system", severity="info", source="system_metrics", action="sample", status="SAMPLED", message="system telemetry sampled", metadata=self._latest_system)
        comfy_status = self._latest_processes.get("comfyui", {}).get("health", "UNAVAILABLE")
        self.emit(category="provider", severity="info" if comfy_status == "HEALTHY" else "warning", source="comfyui", action="health", status=comfy_status, message=f"ComfyUI endpoint {comfy_status.casefold()}", metadata=self._latest_processes.get("comfyui", {}))
        if not include_assets:
            return
        with self._asset_lock:
            changes = self.assets.scan()
        for item in changes:
            severity = "info" if item.get("action") != "stable" else "debug"
            self.emit(category="file", severity=severity, source="asset_activity", action=item["action"], status=item["status"], message=f"{item['action']} {item['path']}", asset_id=item.get("safe_id"), metadata=item)
        # QA integrity can hash a large, immutable review index. Keep it on the
        # collector path so SSE/JSON requests only read the latest result and
        # never wait for filesystem validation.
        self._latest_qa = self._qa_cache.validate()
        self._latest_stream_snapshot = self._build_snapshot()

    def emit(self, *, category: str, severity: str = "info", source: str, action: str, status: str, message: str, job_id: str | None = None, asset_id: str | None = None, metadata: Mapping[str, Any] | None = None) -> TelemetryEvent:
        event = TelemetryEvent.create(category=category, severity=severity, source=source, action=action, status=status, message=message, job_id=job_id, asset_id=asset_id, metadata=metadata)
        try:
            self.store.insert(event)
        except Exception:
            pass
        with self._subscriber_lock:
            subscribers = tuple(self._subscribers)
        payload = event.to_dict()
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(payload)
            except queue.Full:
                try:
                    subscriber.get_nowait(); subscriber.put_nowait(payload)
                except (queue.Empty, queue.Full):
                    pass
        return event

    @contextmanager
    def command(self, argv: list[str] | tuple[str, ...], *, source: str = "ugas.cli") -> Iterator[str]:
        job_id = f"cmd-{uuid.uuid4().hex}"
        safe_argv = [str(item) for item in argv]
        is_dashboard = bool(safe_argv and safe_argv[0].casefold() == "dashboard")
        metadata = {"argv": safe_argv, "session_id": self.session_id, "service_id": self.session_id, "pid": self.pid, "role": "dashboard_service" if is_dashboard else "workload"}
        self.emit(category="command", source=source, action="started", status="RUNNING", message="UGAS command started", job_id=job_id, metadata=metadata)
        service_token = _CURRENT.set(self)
        command_token = _CURRENT_COMMAND.set(job_id)
        try:
            yield job_id
        except Exception as exc:
            self.emit(category="command", severity="error", source=source, action="failed", status="FAILED", message="UGAS command failed", job_id=job_id, metadata={"error_type": type(exc).__name__, "session_id": self.session_id, "pid": self.pid})
            self._finished_commands.add(job_id)
            raise
        else:
            if job_id not in self._finished_commands:
                self.finish_command(job_id, success=True, source=source)
        finally:
            _CURRENT_COMMAND.reset(command_token); _CURRENT.reset(service_token)

    def finish_command(self, job_id: str, *, success: bool, source: str = "ugas.cli") -> None:
        if job_id in self._finished_commands:
            return
        self._finished_commands.add(job_id)
        self.emit(category="command", severity="info" if success else "error", source=source, action="completed" if success else "failed", status="SUCCEEDED" if success else "FAILED", message="UGAS command completed" if success else "UGAS command failed", job_id=job_id, metadata={"session_id": self.session_id, "pid": self.pid})

    def status(self) -> dict[str, Any]:
        state, state_error = self._read_json(self.repo_root / "docs" / "evidence" / "current-state.json")
        branch = self._git_value(["branch", "--show-current"]) or "UNKNOWN"
        head = self._git_value(["rev-parse", "HEAD"]) or "UNKNOWN"
        return {"timestamp": _now(), "status": "OK" if state is not None else "GAP", "version": state.get("version") if state else UGAS_VERSION, "branch": branch, "head": head, "phase": state.get("phase") if state else "UNKNOWN", "current_gate": state.get("current_gate") if state else "UNKNOWN", "production_routing": state.get("production_routing") if state else "UNKNOWN", "production_approved": state.get("production_approved", False) if state else False, "external_visual_review": self._external_review(state), "uptime_seconds": round(time.monotonic() - self.started_at, 2), "active_job": self.jobs().get("active_job"), "provider_health": self._latest_processes.get("comfyui", {}), "state_status": "OK" if state is not None else "GAP", "state_error": state_error, "service": {"session_id": self.session_id, "pid": self.pid, "started_at": self.started_at_iso}}

    @staticmethod
    def _external_review(state: dict[str, Any] | None) -> dict[str, Any]:
        if not state: return {"status": "GAP", "attack_front_v2": "GAP", "observability_dashboard": "GAP"}
        nested = state.get("external_visual_review") if isinstance(state.get("external_visual_review"), dict) else {}
        return {"status": nested.get("observability_dashboard", "UNKNOWN"), "attack_front_v2": nested.get("attack_front_v2", "UNKNOWN"), "observability_dashboard": nested.get("observability_dashboard", "UNKNOWN")}

    def system(self) -> dict[str, Any]:
        return self._latest_system or {"timestamp": _now(), "status": "STARTING", "reason": "collector has not produced a sample yet"}

    def processes(self) -> dict[str, Any]:
        return self._latest_processes or {"timestamp": _now(), "status": "STARTING", "reason": "collector has not produced a sample yet"}

    def jobs(self) -> dict[str, Any]:
        events = self.store.query(limit=1000)
        records: dict[str, dict[str, Any]] = {}
        for item in reversed(events):
            if item.get("category") not in {"command", "job", "stage"}: continue
            job_id = item.get("job_id")
            if not job_id: continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            record = records.setdefault(job_id, {"job_id": job_id, "parent_command_id": metadata.get("parent_command_id"), "command": metadata.get("argv") or metadata.get("command") or metadata.get("workflow") or [], "category": item.get("category"), "type": metadata.get("type") or item.get("category"), "current_stage": "UNKNOWN", "status": "UNKNOWN", "started_at": item.get("timestamp"), "elapsed_seconds": None, "finished_at": None, "latest_message": "", "recent_stages": [], "pid": metadata.get("pid"), "session_id": metadata.get("session_id") or metadata.get("service_id"), "role": metadata.get("role", "workload")})
            record["latest_message"] = item.get("message") or record["latest_message"]
            record["last_event_at"] = item.get("timestamp")
            record["parent_command_id"] = record.get("parent_command_id") or metadata.get("parent_command_id")
            record["pid"] = record.get("pid") or metadata.get("pid")
            if item.get("category") == "command" and isinstance(metadata.get("argv"), list): record["command"] = metadata["argv"]
            if item.get("action") == "started": record["status"] = "RUNNING"; record["started_at"] = item.get("timestamp")
            elif item.get("action") in {"completed", "succeeded"} or item.get("status") == "SUCCEEDED": record["status"] = "SUCCEEDED"; record["finished_at"] = item.get("timestamp")
            elif item.get("action") in {"failed", "error"} or item.get("status") == "FAILED": record["status"] = "FAILED"; record["finished_at"] = item.get("timestamp")
            if item.get("category") == "stage":
                stage = str(metadata.get("stage") or item.get("action") or "UNKNOWN")
                record["current_stage"] = stage
                record["recent_stages"].append({"stage": stage, "action": item.get("action"), "status": item.get("status"), "timestamp": item.get("timestamp"), "message": item.get("message")})
                record["recent_stages"] = record["recent_stages"][-12:]
        values = sorted(records.values(), key=lambda value: value.get("started_at") or "", reverse=True)
        active_candidates: list[dict[str, Any]] = []
        pid_alive_cache: dict[int, bool] = {}
        for record in values:
            # A successful terminal job is authoritative even if the separate
            # stage event was briefly buffered during a shared SQLite lock.
            # Keep the live dashboard from reporting a permanently unfinished
            # postprocess stage after the job completion event was persisted.
            if record.get("status") == "SUCCEEDED" and record.get("current_stage") not in {"complete", "error"}:
                record["current_stage"] = "complete"
            if record.get("status") != "RUNNING":
                record["elapsed_seconds"] = _elapsed(record.get("started_at"), record.get("finished_at")); continue
            command = record.get("command")
            dashboard_role = record.get("role") == "dashboard_service" or (isinstance(command, list) and command and str(command[0]).casefold() == "dashboard")
            if dashboard_role:
                record["service_status"] = "RUNNING"; record["active_workload"] = False
            elif not _pid_alive(record.get("pid"), pid_alive_cache):
                record["status"] = "ORPHANED"; record["stale_reason"] = "recorded process is no longer alive"; record["active_workload"] = False
            elif record.get("pid") is None and _age_seconds(record.get("started_at")) > 10:
                record["status"] = "STALE"; record["stale_reason"] = "running record has no live process binding"; record["active_workload"] = False
            else:
                record["active_workload"] = True; active_candidates.append(record)
            record["elapsed_seconds"] = _elapsed(record.get("started_at"), None)
        return {"timestamp": _now(), "active_job": active_candidates[0] if active_candidates else None, "recent": values[:30], "service": {"session_id": self.session_id, "pid": self.pid}}

    def assets_recent(self, limit: int = 100) -> dict[str, Any]:
        with self._asset_lock: values = self.assets.recent(limit)
        return {"timestamp": _now(), "status": "OK", "items": values}

    def qa(self) -> dict[str, Any]:
        result = self._latest_qa if self._latest_qa is not None else self._qa_cache.validate(); index = result.get("review_index", {}); state = result.get("current_state") or {}
        return {"timestamp": _now(), "status": result.get("status", "GAP"), "current_head": result.get("current_head"), "validated_head": result.get("validated_head"), "worktree_clean": result.get("worktree_clean"), "cache_checked_at": result.get("cache_checked_at"), "cache_generation": result.get("cache_generation"), "cache_fingerprint": result.get("cache_fingerprint"), "stale": result.get("stale"), "reason": result.get("reason"), "integrity": result, "current_state": {"version": state.get("version", "GAP"), "gate": state.get("current_gate", "GAP"), "production_routing": state.get("production_routing", "GAP"), "production_approved": state.get("production_approved", False), "external_visual": {"attack_front_v2": (state.get("external_visual_review") or {}).get("attack_front_v2", "GAP"), "observability_dashboard": (state.get("external_visual_review") or {}).get("observability_dashboard", "GAP")}}, "tests": result.get("tests", {}), "validation": result.get("validation", {}), "review_index": {"status": "PASS" if index.get("status") == "PASS" else "GAP", "path": "docs/evidence/review-index-v0.12.2.json", "artifact_count": index.get("artifact_count"), "visual_count": index.get("visual_count"), "checked_at": index.get("checked_at"), "head": index.get("head")}, "errors": result.get("failures", [])}

    def events(self, *, limit: int = 100, category: str | None = None, severity: str | None = None, search: str | None = None) -> dict[str, Any]:
        return {"timestamp": _now(), "status": "OK" if self.store.available else "DEGRADED", "store": {"available": self.store.available, "path": str(self.telemetry_db), "reason": self.store.reason, "count": self.store.count()}, "events": self.store.query(limit=limit, category=category, severity=severity, search=search)}

    def health(self) -> dict[str, Any]:
        system = self.system(); processes = self.processes(); status = self.status(); qa = self.qa(); alerts: list[dict[str, Any]] = []
        gpu = system.get("gpu", {})
        if gpu.get("status") != "GPU_AVAILABLE": alerts.append({"severity": "info", "code": "GPU_UNAVAILABLE", "message": gpu.get("reason") or "GPU capability unavailable"})
        if gpu.get("degraded") or processes.get("comfyui", {}).get("degraded"): alerts.append({"severity": "warning", "code": "STALE_LAST_KNOWN", "message": "a provider/resource sample is degraded; stale-last-known data is shown"})
        if processes.get("comfyui", {}).get("health") != "HEALTHY": alerts.append({"severity": "warning", "code": "COMFYUI_DOWN", "message": processes.get("comfyui", {}).get("reason") or "ComfyUI endpoint unavailable"})
        if system.get("disk", {}).get("percent") is not None and system["disk"]["percent"] >= 90: alerts.append({"severity": "warning", "code": "LOW_DISK", "message": "repository volume has less than 10% free"})
        if system.get("memory", {}).get("percent") is not None and system["memory"]["percent"] >= 90: alerts.append({"severity": "warning", "code": "HIGH_RAM", "message": "RAM pressure is high"})
        if status.get("state_status") != "OK": alerts.append({"severity": "error", "code": "INVALID_STATE_EVIDENCE", "message": status.get("state_error") or "current-state.json is not valid"})
        if qa.get("status") != "PASS": alerts.append({"severity": "error", "code": "QA_GAP", "message": "canonical QA evidence did not pass fail-closed validation"})
        return {"timestamp": _now(), "status": "DEGRADED" if alerts else "HEALTHY", "alerts": alerts}

    def snapshot(self) -> dict[str, Any]:
        return self._build_snapshot()

    def _build_snapshot(self) -> dict[str, Any]:
        return {"timestamp": _now(), "status": self.status(), "system": self.system(), "processes": self.processes(), "jobs": self.jobs(), "assets": self.assets_recent(limit=50), "qa": self.qa(), "events": self.events(limit=35), "health": self.health()}

    def stream_snapshot(self) -> dict[str, Any]:
        """Return the collector's last complete snapshot without blocking SSE."""

        if self._latest_stream_snapshot is not None:
            value = deepcopy(self._latest_stream_snapshot)
            value["timestamp"] = _now()
            return value
        return self._build_snapshot()

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        subscriber: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=200)
        with self._subscriber_lock: self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[dict[str, Any]]) -> None:
        with self._subscriber_lock: self._subscribers.discard(subscriber)

    def preview(self, safe_id: str) -> tuple[Path, str] | None:
        with self._asset_lock: return self.assets.resolve_preview(safe_id)

    def close(self) -> None:
        if self._closed: return
        self._closed = True; self._stop.set()
        if self._worker and self._worker.is_alive(): self._worker.join(timeout=2)
        self._probe_executor.shutdown(wait=True, cancel_futures=True)
        self.store.close()
        self._probe_executor.shutdown(wait=False, cancel_futures=True); self.store.close()

    def _read_json(self, path: Path) -> tuple[dict[str, Any] | None, str | None]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict): return None, f"{path.name}: expected JSON object"
            return value, None
        except FileNotFoundError: return None, f"{path.name}: missing"
        except (OSError, json.JSONDecodeError) as exc: return None, f"{path.name}: {type(exc).__name__}"

    def _git_value(self, args: list[str]) -> str | None:
        try:
            result = subprocess.run(["git", *args], cwd=self.repo_root, capture_output=True, text=True, timeout=0.8, check=False, shell=False)
            return result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired): return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _age_seconds(value: object) -> float:
    if not value: return 0.0
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")); return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())
    except (TypeError, ValueError): return 0.0


def _elapsed(started: object, finished: object) -> float | None:
    if not started: return None
    if finished:
        try:
            left = datetime.fromisoformat(str(started).replace("Z", "+00:00")); right = datetime.fromisoformat(str(finished).replace("Z", "+00:00")); return round(max(0.0, (right - left).total_seconds()), 3)
        except (TypeError, ValueError): return None
    return round(_age_seconds(started), 3)


def _pid_alive(pid: object, cache: dict[int, bool] | None = None) -> bool:
    if pid in (None, "", 0): return False
    try:
        normalized = int(pid)
    except (TypeError, ValueError):
        return False
    if normalized <= 0:
        return False
    if cache is not None and normalized in cache:
        return cache[normalized]
    if os.name == "nt":
        # os.kill(pid, 0) can block on Windows for a live console process.
        # Querying a limited process handle is read-only and does not signal
        # or suspend the process, so persisted-job reconciliation stays
        # bounded on the dashboard request path.
        try:
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
            kernel32.GetExitCodeProcess.restype = ctypes.c_int
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle.restype = ctypes.c_int
            handle = kernel32.OpenProcess(0x1000, 0, normalized)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                alive = ctypes.get_last_error() == 5  # ERROR_ACCESS_DENIED means the process exists.
            else:
                exit_code = ctypes.c_uint32()
                try:
                    alive = bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) and exit_code.value == 259)  # STILL_ACTIVE
                finally:
                    kernel32.CloseHandle(handle)
        except (AttributeError, OSError, TypeError, ValueError):
            alive = False
    else:
        try:
            os.kill(normalized, 0); alive = True
        except PermissionError:
            alive = True
        except OSError:
            alive = False
    if cache is not None:
        cache[normalized] = alive
    return alive
