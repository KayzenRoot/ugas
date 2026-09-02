"""Correction gates for the v0.12.1 observability integrity slice."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image

from ugas.observability.asset_activity import AssetActivityTracker, classify_file
from ugas.observability.dashboard_app import build_server
from ugas.observability.process_metrics import collect_process_metrics
from ugas.observability.qa_integrity import ActiveEvidenceCache, validate_qa_semantics
from ugas.observability.service import ObservabilityService
from ugas.state_consistency_v0121 import validate_state_consistency


class SecurityAndQaTests(unittest.TestCase):
    def test_xss_payload_is_structured_text_and_dashboard_has_no_unsafe_sink(self) -> None:
        source = (ROOT / "src/ugas/observability/static/dashboard.js").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", source)
        self.assertNotIn("outerHTML", source)
        event = ObservabilityService(ROOT, sample_interval=60)
        try:
            event.emit(category="error", source="test", action="payload", status="GAP", message="<img src=x onerror=alert(1)>", metadata={"payload": "<script>alert(1)</script>"})
            record = event.events(limit=1)["events"][0]
        finally:
            event.close()
        self.assertIn("<img", record["message"])
        self.assertEqual("<script>alert(1)</script>", record["metadata"]["payload"])

    def test_qa_negative_controls_reject_false_green_counts(self) -> None:
        good_tests = {"status": "passed", "count": 10, "passed": 10, "failed": 0}
        good_validation = {"status": "passed", "checks": 20, "passed": 20, "failed": 0}
        fixtures = [
            ("QA-NC-01", {**good_tests, "status": "failed"}, good_validation),
            ("QA-NC-02", {**good_tests, "failed": 1}, good_validation),
            ("QA-NC-03", {**good_tests, "passed": 9}, good_validation),
            ("QA-NC-04", good_tests, {**good_validation, "status": "failed"}),
            ("QA-NC-05", good_tests, {**good_validation, "passed": 19}),
        ]
        for name, tests, validation in fixtures:
            with self.subTest(name=name):
                self.assertTrue(validate_qa_semantics(tests, validation))
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        mutant = dict(state); mutant["production_approved"] = True
        self.assertIn("production_approved_must_remain_false", validate_state_consistency(mutant, "", "")["failures"])
        self.assertTrue(ActiveEvidenceCache(ROOT)._key())


class PipelineAndResourceTests(unittest.TestCase):
    def test_stage_aggregation_has_real_metadata_and_dashboard_is_not_workload(self) -> None:
        service = ObservabilityService(ROOT, sample_interval=60)
        try:
            job_id = f"job-v0121-stage-{uuid.uuid4().hex}"
            service.emit(category="job", source="test", action="started", status="RUNNING", message="job started", job_id=job_id, metadata={"pid": service.pid, "session_id": service.session_id, "parent_command_id": "cmd-parent", "argv": ["generate", "--stage-test"], "type": "generation"})
            service.emit(category="stage", source="test", action="provider", status="RUNNING", message="provider selected", job_id=job_id, metadata={"pid": service.pid, "session_id": service.session_id, "parent_command_id": "cmd-parent", "stage": "provider"})
            dashboard_id = f"cmd-dashboard-v0121-{uuid.uuid4().hex}"
            service.emit(category="command", source="test", action="started", status="RUNNING", message="dashboard service", job_id=dashboard_id, metadata={"pid": service.pid, "session_id": service.session_id, "argv": ["dashboard", "--port", "0"], "role": "dashboard_service"})
            result = service.jobs()
        finally:
            service.close()
        job = next(item for item in result["recent"] if item["job_id"] == job_id)
        daemon = next(item for item in result["recent"] if item["job_id"] == dashboard_id)
        self.assertEqual("provider", job["current_stage"])
        self.assertEqual("cmd-parent", job["parent_command_id"])
        self.assertEqual("generation", job["type"])
        self.assertEqual("RUNNING", job["status"])
        self.assertIsNotNone(job["elapsed_seconds"])
        self.assertTrue(job["active_workload"])
        self.assertFalse(daemon["active_workload"])
        self.assertEqual("RUNNING", daemon["service_status"])

    def test_orphan_running_job_is_not_active(self) -> None:
        service = ObservabilityService(ROOT, sample_interval=60)
        try:
            orphan_id = f"job-orphan-v0121-{uuid.uuid4().hex}"
            service.emit(category="job", source="test", action="started", status="RUNNING", message="orphan", job_id=orphan_id, metadata={"pid": 2147483647, "argv": ["generate"], "type": "generation"})
            record = next(item for item in service.jobs()["recent"] if item["job_id"] == orphan_id)
        finally:
            service.close()
        self.assertEqual("ORPHANED", record["status"])
        self.assertFalse(record["active_workload"])

    def test_process_contract_has_ugas_and_comfyui_fields(self) -> None:
        value = collect_process_metrics(1, comfyui_probe={"endpoint": "http://127.0.0.1:8188", "status": "DOWN", "health": "UNAVAILABLE", "reason": "offline", "checked_at": "2026-09-01T00:00:00Z"})
        self.assertIn("pid", value["ugas"])
        self.assertIn("rss_bytes", value["ugas"])
        self.assertEqual("UNAVAILABLE", value["comfyui"]["health"])
        self.assertIn("checked_at", value["comfyui"])


class ActivityAndPreviewTests(unittest.TestCase):
    def test_spritesheet_precedes_image_and_stable_transition_is_emitted(self) -> None:
        self.assertEqual("spritesheet", classify_file(Path("attack-front-v2-spritesheet.png")))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "docs/evidence").mkdir(parents=True)
            tracker = AssetActivityTracker(root)
            tracker.scan()
            target = root / "docs/evidence" / "attack-front-v0121.png"
            Image.new("RGBA", (2, 2), (20, 30, 40, 255)).save(target)
            created = tracker.scan()
            self.assertEqual("created", created[0]["action"])
            self.assertEqual("image", created[0]["file_kind"])
            stable = tracker.scan()
            self.assertEqual("stable", stable[0]["action"])
            self.assertEqual("STABILIZING->STABLE", stable[0]["transition"])
            target.write_bytes(target.read_bytes() + b"x")
            updated = tracker.scan()
            self.assertEqual("updated", updated[0]["action"])
            self.assertTrue(updated[0]["previewable"])

    def test_stale_last_known_preserves_sample_without_zero(self) -> None:
        previous = {"sample": {"status": "GPU_AVAILABLE", "gpu": {"utilization_percent": 63, "vram_used_mb": 1024}}, "timestamp": "2026-08-31T23:59:00Z"}
        current = {"status": "GPU_UNAVAILABLE", "capability": "TIMEOUT", "reason": "probe timed out"}
        value = ObservabilityService._with_stale(current, previous, "gpu")
        self.assertEqual(63, value["stale_last_known"]["gpu"]["utilization_percent"])
        self.assertNotEqual(0, value["stale_last_known"]["gpu"]["utilization_percent"])
        self.assertTrue(value["degraded"])
        self.assertGreater(value["stale_last_known_age_seconds"], 0)

    def test_api_security_headers_and_read_only_method(self) -> None:
        service = ObservabilityService(ROOT, sample_interval=60)
        server = build_server(service, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/status", timeout=5) as response:
                self.assertEqual("nosniff", response.headers["X-Content-Type-Options"])
                self.assertEqual("no-referrer", response.headers["Referrer-Policy"])
                self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        finally:
            server.shutdown(); server.server_close(); service.close(); thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
