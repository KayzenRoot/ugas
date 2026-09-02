"""Contract tests for the v0.12.0 local observability MVP."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image

from ugas.observability.asset_activity import AssetActivityTracker
from ugas.observability.dashboard_app import build_server
from ugas.observability.events import TelemetryEvent
from ugas.observability.service import ObservabilityService
from ugas.observability.store import TelemetryStore
from ugas.observability.system_metrics import probe_nvidia_smi
from ugas.state_consistency_v0120 import validate_state_consistency


class EventAndStoreTests(unittest.TestCase):
    def test_event_serialization_is_structured_monotonic_and_redacted(self) -> None:
        first = TelemetryEvent.create(category="command", source="test", action="started", status="RUNNING", message="token=secret-value", metadata={"api_key": "secret", "nested": {"value": 1}})
        second = TelemetryEvent.create(category="command", source="test", action="completed", status="SUCCEEDED", message="done")
        self.assertLess(first.timestamp, second.timestamp)
        self.assertEqual("[REDACTED]", first.metadata["api_key"])
        self.assertNotIn("secret-value", first.message)
        self.assertEqual(first.to_dict(), json.loads(first.to_json()))

    def test_sqlite_insert_query_restart_and_retention(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.db"
            store = TelemetryStore(path, max_events=100)
            for index in range(110):
                store.insert(TelemetryEvent.create(category="qa", source="test", action="sample", status="PASS", message=str(index)))
            self.assertTrue(store.available)
            self.assertEqual(100, store.count())
            self.assertEqual("109", store.query(limit=1)[0]["message"])
            store.close()
            restarted = TelemetryStore(path, max_events=100)
            self.assertEqual(100, restarted.count())
            self.assertEqual("qa", restarted.query(limit=1, category="qa")[0]["category"])
            restarted.close()


class CollectorAndActivityTests(unittest.TestCase):
    def test_nvidia_missing_timeout_and_supported_paths_are_explicit(self) -> None:
        def missing(args, **kwargs): raise FileNotFoundError()
        def timeout(args, **kwargs): raise subprocess.TimeoutExpired(args, kwargs.get("timeout", 1))
        supported = subprocess.CompletedProcess([], 0, "RTX 5050, 42, 100, 4096, 55, 80\n", "")
        with patch("ugas.observability.system_metrics._run", side_effect=missing):
            self.assertEqual("GPU_UNAVAILABLE", probe_nvidia_smi()["status"])
        with patch("ugas.observability.system_metrics._run", side_effect=timeout):
            self.assertEqual("TIMEOUT", probe_nvidia_smi()["capability"])
        with patch("ugas.observability.system_metrics._run", side_effect=[supported, subprocess.CompletedProcess([], 0, "123, python, 100\n", "")]):
            value = probe_nvidia_smi()
        self.assertEqual("GPU_AVAILABLE", value["status"])
        self.assertEqual("RTX 5050", value["gpu"]["name"])
        self.assertEqual(1, len(value["gpu"]["processes"]))

    def test_activity_detects_create_update_and_stable_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); evidence = root / "docs" / "evidence"; evidence.mkdir(parents=True)
            tracker = AssetActivityTracker(root)
            self.assertEqual([], tracker.scan())
            target = evidence / "test-activity.png"; Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(target)
            created = tracker.scan()
            self.assertEqual("created", created[0]["action"])
            self.assertIsNone(created[0]["sha256"])
            tracker.scan()
            self.assertEqual(64, tracker.recent()[0]["sha256"].__len__())
            target.write_bytes(target.read_bytes() + b"x")
            updated = tracker.scan()
            self.assertEqual("updated", updated[0]["action"])

    def test_preview_allowlist_and_traversal_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); evidence = root / "docs" / "evidence"; evidence.mkdir(parents=True)
            media = evidence / "safe.png"; Image.new("RGBA", (2, 2), (0, 255, 0, 255)).save(media)
            tracker = AssetActivityTracker(root); tracker.scan()
            safe_id = tracker.recent()[0]["safe_id"]
            resolved = tracker.resolve_preview(safe_id)
            self.assertIsNotNone(resolved); self.assertEqual(media.resolve(), resolved[0])
            self.assertIsNone(tracker.resolve_preview("Li4vLi4vLmVudi"))
            self.assertIsNone(tracker.resolve_preview("not-a-valid-id"))
            secret = evidence / ".env.png"; Image.new("RGBA", (1, 1)).save(secret)
            self.assertIsNone(tracker.resolve_preview(tracker._record(tracker.roots[3], secret, action="observed", stat=secret.stat(), sha256=None)["safe_id"]))

    def test_runtime_root_is_allowlisted_without_broad_repository_leak(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); runtime = root / ".ugas" / "runtime"; runtime.mkdir(parents=True); probe = runtime / "probe.png"; Image.new("RGBA", (2, 2), (1, 2, 3, 255)).save(probe)
            tracker = AssetActivityTracker(root); tracker.scan()
            self.assertTrue(any(item["path"] == ".ugas/runtime/probe.png" for item in tracker.recent()))


class DashboardApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ObservabilityService(ROOT, sample_interval=60).start()
        self.server = build_server(self.service, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown(); self.server.server_close(); self.service.close(); self.thread.join(timeout=2)

    def get_json(self, path: str) -> tuple[int, dict]:
        with urlopen(self.base + path, timeout=5) as response:
            return response.status, json.loads(response.read())

    def test_read_only_api_and_snapshot_endpoints(self) -> None:
        for path in ("/api/status", "/api/system", "/api/processes", "/api/jobs", "/api/assets/recent", "/api/qa", "/api/events?limit=3", "/api/health"):
            status, value = self.get_json(path); self.assertEqual(200, status); self.assertIn("timestamp", value)
        request = Request(self.base + "/api/status", method="POST")
        with self.assertRaises(Exception) as context:
            urlopen(request, timeout=5)
        self.assertIn("405", str(context.exception))

    def test_sse_snapshot_reconnect_and_preview_traversal(self) -> None:
        for _ in range(2):
            connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5); connection.request("GET", "/api/stream"); response = connection.getresponse(); self.assertEqual(200, response.status); self.assertIn("text/event-stream", response.getheader("Content-Type")); self.assertIn(b"event: snapshot", response.readline() + response.readline()); connection.close()
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5); connection.request("GET", "/api/preview/../../.env"); response = connection.getresponse(); self.assertIn(response.status, (400, 404)); connection.close()


class GovernanceAndCliTests(unittest.TestCase):
    def test_current_state_cannot_promote_production(self) -> None:
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        result = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.12.0.md").read_text(encoding="utf-8"))
        self.assertEqual("LOCAL_REALTIME_OBSERVABILITY_DASHBOARD_MVP_TECHNICALLY_QUALIFIED", result["status"])
        mutant = dict(state); mutant["production_approved"] = True
        self.assertIn("production_approved_must_remain_false", validate_state_consistency(mutant, "", "")["failures"])

    def test_dashboard_cli_startup_smoke_on_ephemeral_port(self) -> None:
        environment = dict(os.environ); environment["PYTHONPATH"] = str(ROOT / "src")
        startup_path = ROOT / ".ugas" / "runtime" / "dashboard-startup.json"; startup_path.unlink(missing_ok=True)
        process = subprocess.Popen([sys.executable, "-m", "ugas.cli", "dashboard", "--port", "0", "--no-open"], cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        try:
            payload = None
            deadline = time.time() + 12
            while time.time() < deadline:
                if startup_path.is_file():
                    try: payload = json.loads(startup_path.read_text(encoding="utf-8")); break
                    except json.JSONDecodeError: pass
                time.sleep(0.05)
            self.assertIsNotNone(payload)
            self.assertEqual("DASHBOARD_STARTED", payload["status"]); self.assertTrue(payload["dashboard_url"].startswith("http://127.0.0.1:")); self.assertTrue(payload["telemetry_db"].endswith("telemetry.db"))
        finally:
            process.terminate(); process.wait(timeout=10)


if __name__ == "__main__": unittest.main()
