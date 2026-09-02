"""Local read-only HTTP/SSE dashboard for UGAS."""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import webbrowser
from typing import Any
from urllib.parse import parse_qs, urlsplit

from ..constants import UGAS_VERSION
from .service import ObservabilityService

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class DashboardHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], service: ObservabilityService):
        self.service = service
        super().__init__(server_address, DashboardRequestHandler)


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server: DashboardHTTPServer
    protocol_version = "HTTP/1.1"

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
            # A browser closing an SSE connection is a normal reconnect path.
            return

    def log_message(self, format: str, *args: object) -> None:
        return

    def _security_headers(self) -> None:
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")

    def _send_json(self, value: object, status: int = 200) -> None:
        payload = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except OSError:
            pass

    def _send_static(self, path: Path, content_type: str) -> None:
        try:
            data = path.read_bytes()
        except OSError:
            self._send_json({"status": "NOT_FOUND"}, HTTPStatus.NOT_FOUND); return
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except OSError:
            pass

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        path = parsed.path
        service = self.server.service
        if path == "/" or path == "/index.html":
            self._send_static(Path(__file__).parent / "static" / "index.html", "text/html; charset=utf-8"); return
        if path == "/static/dashboard.css":
            self._send_static(Path(__file__).parent / "static" / "dashboard.css", "text/css; charset=utf-8"); return
        if path == "/static/dashboard.js":
            self._send_static(Path(__file__).parent / "static" / "dashboard.js", "text/javascript; charset=utf-8"); return
        if path == "/api/status": self._send_json(service.status()); return
        if path == "/api/system": self._send_json(service.system()); return
        if path == "/api/processes": self._send_json(service.processes()); return
        if path == "/api/jobs": self._send_json(service.jobs()); return
        if path == "/api/assets/recent":
            limit = _query_int(parsed.query, "limit", 100); self._send_json(service.assets_recent(limit)); return
        if path == "/api/qa": self._send_json(service.qa()); return
        if path == "/api/events":
            query = parse_qs(parsed.query); self._send_json(service.events(limit=_query_int(parsed.query, "limit", 100), category=_query_value(query, "category"), severity=_query_value(query, "severity"), search=_query_value(query, "search"))); return
        if path == "/api/health": self._send_json(service.health()); return
        if path == "/api/stream": self._stream(service); return
        if path.startswith("/api/preview/"):
            safe_id = path.removeprefix("/api/preview/")
            if "/" in safe_id or not safe_id:
                self._send_json({"status": "REJECTED", "reason": "invalid safe preview id"}, HTTPStatus.NOT_FOUND); return
            resolved = service.preview(safe_id)
            if resolved is None:
                self._send_json({"status": "REJECTED", "reason": "preview id is not allowlisted"}, HTTPStatus.NOT_FOUND); return
            file_path, content_type = resolved
            try: data = file_path.read_bytes()
            except OSError: self._send_json({"status": "NOT_FOUND"}, HTTPStatus.NOT_FOUND); return
            self.send_response(HTTPStatus.OK); self._security_headers(); self.send_header("Content-Type", content_type); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(data))); self.end_headers()
            try: self.wfile.write(data)
            except OSError: pass
            return
        self._send_json({"status": "NOT_FOUND"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        self._read_only_rejection()

    def do_PUT(self) -> None:  # noqa: N802
        self._read_only_rejection()

    def do_PATCH(self) -> None:  # noqa: N802
        self._read_only_rejection()

    def do_DELETE(self) -> None:  # noqa: N802
        self._read_only_rejection()

    def _read_only_rejection(self) -> None:
        self._send_json({"status": "READ_ONLY", "error": "dashboard API is read-only in v0.12.2"}, HTTPStatus.METHOD_NOT_ALLOWED)

    def _stream(self, service: ObservabilityService) -> None:
        subscriber = service.subscribe()
        try:
            self.send_response(HTTPStatus.OK)
            self._security_headers()
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self._sse("snapshot", service.stream_snapshot())
            while True:
                try:
                    event = subscriber.get(timeout=15)
                    self._sse("telemetry", event)
                except Exception as exc:
                    if type(exc).__name__ == "Empty":
                        try: self.wfile.write(b": heartbeat\n\n"); self.wfile.flush()
                        except OSError: break
                    elif isinstance(exc, (BrokenPipeError, ConnectionResetError, OSError)):
                        break
                    else:
                        break
        finally:
            service.unsubscribe(subscriber)

    def _sse(self, name: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        self.wfile.write(f"event: {name}\ndata: {payload}\n\n".encode("utf-8")); self.wfile.flush()


def _query_int(query: str, name: str, default: int) -> int:
    values = parse_qs(query).get(name, [])
    try: return int(values[0]) if values else default
    except ValueError: return default


def _query_value(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name, [])
    return values[0] if values and values[0] else None


def build_server(service: ObservabilityService, host: str = "127.0.0.1", port: int = 8765) -> DashboardHTTPServer:
    normalized = host.casefold()
    if normalized not in LOOPBACK_HOSTS:
        if not (normalized == "0.0.0.0" and os.environ.get("UGAS_CONTAINERIZED") == "1"):
            raise ValueError("UGAS dashboard is local-only; non-loopback bind requires trusted UGAS_CONTAINERIZED=1")
    return DashboardHTTPServer((host, int(port)), service)


def startup_record(service: ObservabilityService, server: DashboardHTTPServer) -> dict[str, Any]:
    host, port = server.server_address[:2]
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    gpu = service.system().get("gpu", {})
    gpu_summary = {key: gpu.get(key) for key in ("status", "capability", "reason", "timestamp")}
    if isinstance(gpu.get("gpu"), dict):
        gpu_summary["device"] = {key: gpu["gpu"].get(key) for key in ("name", "utilization_percent", "vram_used_mb", "vram_total_mb", "temperature_c", "power_draw_w")}
    comfy = service.processes().get("comfyui", {})
    provider_summary = {key: comfy.get(key) for key in ("endpoint", "status", "health", "reason", "checked_at")}
    # Startup is a supervisor contract, not a full health sample. Avoid Git
    # and provider probes here so an ephemeral-port launch is immediate even
    # on a slow Windows/Docker Desktop bind mount.
    return {"status": "DASHBOARD_STARTED", "dashboard_url": f"http://{display_host}:{port}/", "version": UGAS_VERSION, "pid": service.pid, "telemetry_db": str(service.telemetry_db), "gpu": gpu_summary, "provider": provider_summary, "shutdown": "CTRL+C"}


def run_dashboard(repo_root: Path, *, host: str = "127.0.0.1", port: int = 8765, no_open: bool = False, service: ObservabilityService | None = None) -> int:
    own_service = service is None
    service = service or ObservabilityService(repo_root)
    server: DashboardHTTPServer | None = None
    try:
        # Bind validation happens before any collector work. The long-running
        # dashboard should publish its startup record immediately and let the
        # worker produce the first complete snapshot asynchronously, keeping
        # CLI/supervisor startup deterministic on slow bind mounts.
        server = build_server(service, host, port)
        service.start(prime=False)
        record = startup_record(service, server)
        (service.runtime_dir / "dashboard-startup.json").write_text(json.dumps(record, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        # Keep startup evidence a single machine-readable line so a supervisor
        # can consume it without guessing where nested JSON ends.
        print(json.dumps(record, ensure_ascii=True, separators=(",", ":")), flush=True)
        if not no_open:
            webbrowser.open(record["dashboard_url"])
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print(json.dumps({"status": "DASHBOARD_STOPPING", "shutdown": "CTRL+C"}), flush=True)
    finally:
        if server is not None:
            server.server_close()
        if own_service:
            service.close()
    return 0
