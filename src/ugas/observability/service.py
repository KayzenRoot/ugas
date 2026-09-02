"""Application service joining the local event store, collectors and API data."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
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
from .process_metrics import collect_process_metrics
from .store import TelemetryStore
from .system_metrics import CpuSampler, collect_system_metrics

_CURRENT: ContextVar["ObservabilityService | None"] = ContextVar("ugas_observability_service", default=None)


def current_service() -> "ObservabilityService | None":
    return _CURRENT.get()


@contextmanager
def bind_service(service: "ObservabilityService") -> Iterator["ObservabilityService"]:
    token = _CURRENT.set(service)
    try:
        yield service
    finally:
        _CURRENT.reset(token)


def record_event(repo_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Write a single event for short-lived scripts without starting workers."""

    service = ObservabilityService(repo_root)
    try:
        return service.emit(**kwargs).to_dict()
    finally:
        service.close()


class ObservabilityService:
    def __init__(self, repo_root: Path, *, max_events: int = 5000, sample_interval: float = 1.0) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.runtime_dir = self.repo_root / ".ugas" / "runtime"
        self.telemetry_db = self.runtime_dir / "telemetry.db"
        self.store = TelemetryStore(self.telemetry_db, max_events=max_events)
        self.assets = AssetActivityTracker(self.repo_root)
        self.sample_interval = max(0.4, float(sample_interval))
        self.started_at = time.monotonic()
        self.pid = os.getpid()
        self.cpu_sampler = CpuSampler()
        self._latest_system: dict[str, Any] = {}
        self._latest_processes: dict[str, Any] = {}
        self._subscribers: set[queue.Queue[dict[str, Any]]] = set()
        self._subscriber_lock = threading.Lock()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._closed = False
        self._finished_commands: set[str] = set()
        self._asset_lock = threading.Lock()

    def start(self) -> "ObservabilityService":
        if self._worker and self._worker.is_alive():
            return self
        # Establish a baseline before background activity events are emitted.
        try:
            self.assets.scan()
        except Exception as exc:
            self.emit(category="error", severity="warning", source="asset_activity", action="baseline", status="DEGRADED", message="file activity baseline unavailable", metadata={"reason": type(exc).__name__})
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

    def refresh(self, *, include_assets: bool = True) -> None:
        self._latest_system = collect_system_metrics(self.repo_root, pid=self.pid, cpu_sampler=self.cpu_sampler)
        self._latest_processes = collect_process_metrics(self.pid, comfyui_endpoint=os.environ.get("UGAS_COMFYUI_URL", "http://127.0.0.1:8188"))
        self.emit(category="system", severity="info", source="system_metrics", action="sample", status="SAMPLED", message="system telemetry sampled", metadata=self._latest_system)
        comfy_status = self._latest_processes.get("comfyui", {}).get("health", "UNAVAILABLE")
        self.emit(category="provider", severity="info" if comfy_status == "HEALTHY" else "warning", source="comfyui", action="health", status=comfy_status, message=f"ComfyUI endpoint {comfy_status.casefold()}", metadata=self._latest_processes.get("comfyui", {}))
        with self._asset_lock:
            changes = self.assets.scan() if include_assets else []
        for item in changes:
            self.emit(category="file", severity="info", source="asset_activity", action=item["action"], status=item["status"], message=f"{item['action']} {item['path']}", asset_id=item.get("safe_id"), metadata=item)

    def emit(self, *, category: str, severity: str = "info", source: str, action: str, status: str, message: str, job_id: str | None = None, asset_id: str | None = None, metadata: Mapping[str, Any] | None = None) -> TelemetryEvent:
        event = TelemetryEvent.create(category=category, severity=severity, source=source, action=action, status=status, message=message, job_id=job_id, asset_id=asset_id, metadata=metadata)
        try:
            self.store.insert(event)
        except Exception:
            # Telemetry is explicitly non-critical. TelemetryStore itself also
            # has a fallback, but this boundary protects unusual failures.
            pass
        with self._subscriber_lock:
            subscribers = tuple(self._subscribers)
        payload = event.to_dict()
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(payload)
            except queue.Full:
                try:
                    subscriber.get_nowait()
                    subscriber.put_nowait(payload)
                except (queue.Empty, queue.Full):
                    pass
        return event

    @contextmanager
    def command(self, argv: list[str] | tuple[str, ...], *, source: str = "ugas.cli") -> Iterator[str]:
        job_id = f"cmd-{uuid.uuid4().hex}"
        safe_argv = [str(item) for item in argv]
        self.emit(category="command", source=source, action="started", status="RUNNING", message="UGAS command started", job_id=job_id, metadata={"argv": safe_argv})
        token = _CURRENT.set(self)
        try:
            yield job_id
        except Exception as exc:
            self.emit(category="command", severity="error", source=source, action="failed", status="FAILED", message="UGAS command failed", job_id=job_id, metadata={"error_type": type(exc).__name__})
            self._finished_commands.add(job_id)
            raise
        else:
            if job_id not in self._finished_commands:
                self.finish_command(job_id, success=True, source=source)
        finally:
            _CURRENT.reset(token)

    def finish_command(self, job_id: str, *, success: bool, source: str = "ugas.cli") -> None:
        if job_id in self._finished_commands:
            return
        self._finished_commands.add(job_id)
        self.emit(category="command", severity="info" if success else "error", source=source, action="completed" if success else "failed", status="SUCCEEDED" if success else "FAILED", message="UGAS command completed" if success else "UGAS command failed", job_id=job_id)

    def status(self) -> dict[str, Any]:
        state, state_error = self._read_json(self.repo_root / "docs" / "evidence" / "current-state.json")
        branch = self._git_value(["branch", "--show-current"]) or "UNKNOWN"
        head = self._git_value(["rev-parse", "HEAD"]) or "UNKNOWN"
        state_status = "OK" if state is not None else "GAP"
        return {
            "timestamp": _now(), "status": "OK" if state is not None else "GAP", "version": state.get("version") if state else UGAS_VERSION,
            "branch": branch, "head": head, "phase": state.get("phase") if state else "UNKNOWN", "current_gate": state.get("current_gate") if state else "UNKNOWN",
            "production_routing": state.get("state_consistency", {}).get("production_routing") if state else "UNKNOWN",
            "production_approved": state.get("production_approved", False) if state else False,
            "external_visual_review": self._external_review(state), "uptime_seconds": round(time.monotonic() - self.started_at, 2),
            "active_job": self.jobs().get("active_job"), "provider_health": self._latest_processes.get("comfyui", {}),
            "state_status": state_status, "state_error": state_error,
        }

    @staticmethod
    def _external_review(state: dict[str, Any] | None) -> dict[str, Any]:
        if not state:
            return {"status": "GAP"}
        nested = state.get("state_consistency") if isinstance(state.get("state_consistency"), dict) else {}
        return {"attack_front_v2": nested.get("attack_front_v2_external_visual", "UNKNOWN"), "status": "APPROVED_PILOT" if nested.get("attack_front_v2_external_visual") == "APPROVED_PILOT" else nested.get("attack_front_v2_external_visual", "UNKNOWN")}

    def system(self) -> dict[str, Any]:
        if not self._latest_system:
            try: self.refresh(include_assets=False)
            except Exception as exc: return {"timestamp": _now(), "status": "GAP", "error": type(exc).__name__}
        return self._latest_system

    def processes(self) -> dict[str, Any]:
        if not self._latest_processes:
            try: self.refresh(include_assets=False)
            except Exception as exc: return {"timestamp": _now(), "status": "GAP", "error": type(exc).__name__}
        return self._latest_processes

    def jobs(self) -> dict[str, Any]:
        events = self.store.query(limit=300)
        records: dict[str, dict[str, Any]] = {}
        for item in reversed(events):
            job_id = item.get("job_id")
            if not job_id:
                continue
            current = records.setdefault(job_id, {"job_id": job_id, "command": item.get("metadata", {}).get("argv", []), "started_at": item.get("timestamp"), "status": "UNKNOWN", "event_count": 0})
            current["event_count"] += 1
            if item.get("action") == "started": current.update({"status": "RUNNING", "started_at": item.get("timestamp")})
            if item.get("action") == "completed": current.update({"status": "SUCCEEDED", "finished_at": item.get("timestamp")})
            if item.get("action") == "failed": current.update({"status": "FAILED", "finished_at": item.get("timestamp")})
        values = sorted(records.values(), key=lambda item: item.get("started_at", ""), reverse=True)
        active = next((item for item in values if item.get("status") == "RUNNING"), None)
        return {"timestamp": _now(), "active_job": active, "recent": values[:20]}

    def assets_recent(self, limit: int = 100) -> dict[str, Any]:
        with self._asset_lock:
            values = self.assets.recent(limit)
        return {"timestamp": _now(), "status": "OK", "items": values}

    def qa(self) -> dict[str, Any]:
        state, state_error = self._read_json(self.repo_root / "docs" / "evidence" / "current-state.json")
        index, index_error = self._read_json(self.repo_root / "docs" / "evidence" / "review-index-v0.12.0.json")
        errors = [item for item in (state_error, index_error) if item]
        if errors:
            return {"timestamp": _now(), "status": "GAP", "errors": errors, "current_state": state, "review_index": None}
        return {"timestamp": _now(), "status": "PASS" if state and index else "GAP", "current_state": {"version": state.get("version"), "gate": state.get("current_gate"), "production_routing": state.get("state_consistency", {}).get("production_routing"), "external_visual": self._external_review(state)}, "tests": index.get("tests", {}), "validation": index.get("validation", {}), "review_index": {"status": "PRESENT", "path": "docs/evidence/review-index-v0.12.0.json", "artifact_count": index.get("artifact_set", {}).get("evidence_count"), "visual_count": index.get("artifact_set", {}).get("visual_count")}}

    def events(self, *, limit: int = 100, category: str | None = None, severity: str | None = None, search: str | None = None) -> dict[str, Any]:
        return {"timestamp": _now(), "status": "OK" if self.store.available else "DEGRADED", "store": {"available": self.store.available, "path": str(self.telemetry_db), "reason": self.store.reason, "count": self.store.count()}, "events": self.store.query(limit=limit, category=category, severity=severity, search=search)}

    def health(self) -> dict[str, Any]:
        system = self.system(); processes = self.processes(); status = self.status(); alerts: list[dict[str, Any]] = []
        gpu = system.get("gpu", {})
        if gpu.get("status") != "GPU_AVAILABLE": alerts.append({"severity": "info", "code": "GPU_UNAVAILABLE", "message": gpu.get("reason") or "GPU capability unavailable"})
        if processes.get("comfyui", {}).get("health") != "HEALTHY": alerts.append({"severity": "warning", "code": "COMFYUI_DOWN", "message": processes.get("comfyui", {}).get("reason") or "ComfyUI endpoint unavailable"})
        if system.get("disk", {}).get("percent") is not None and system["disk"]["percent"] >= 90: alerts.append({"severity": "warning", "code": "LOW_DISK", "message": "repository volume has less than 10% free"})
        if system.get("memory", {}).get("percent") is not None and system["memory"]["percent"] >= 90: alerts.append({"severity": "warning", "code": "HIGH_RAM", "message": "RAM pressure is high"})
        if status.get("state_status") != "OK": alerts.append({"severity": "error", "code": "INVALID_STATE_EVIDENCE", "message": status.get("state_error") or "current-state.json is not valid"})
        return {"timestamp": _now(), "status": "DEGRADED" if alerts else "HEALTHY", "alerts": alerts}

    def snapshot(self) -> dict[str, Any]:
        # Keep the first SSE frame bounded so a slow client cannot deadlock the
        # producer while waiting for the terminating newline of one JSON line.
        events = self.events(limit=35)
        assets = self.assets_recent(limit=50)
        return {"timestamp": _now(), "status": self.status(), "system": self.system(), "processes": self.processes(), "jobs": self.jobs(), "assets": assets, "qa": self.qa(), "events": events, "health": self.health()}

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        subscriber: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=200)
        with self._subscriber_lock:
            self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[dict[str, Any]]) -> None:
        with self._subscriber_lock:
            self._subscribers.discard(subscriber)

    def preview(self, safe_id: str) -> tuple[Path, str] | None:
        with self._asset_lock:
            return self.assets.resolve_preview(safe_id)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=2)
        self.store.close()

    def _read_json(self, path: Path) -> tuple[dict[str, Any] | None, str | None]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                return None, f"{path.name}: expected JSON object"
            return value, None
        except FileNotFoundError:
            return None, f"{path.name}: missing"
        except (OSError, json.JSONDecodeError) as exc:
            return None, f"{path.name}: {type(exc).__name__}"

    def _git_value(self, args: list[str]) -> str | None:
        try:
            result = subprocess.run(["git", *args], cwd=self.repo_root, capture_output=True, text=True, timeout=0.8, check=False, shell=False)
            return result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
