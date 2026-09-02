"""v0.12.2 QA-cache and runtime-boundary correction tests."""

from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image

from ugas.generation import _run_job
from ugas.observability.dashboard_app import build_server
import ugas.observability.service as service_module
from ugas.observability.qa_integrity import ActiveEvidenceCache, validate_qa_semantics
from ugas.observability.service import ObservabilityService
from ugas.workflow_registry import load_workflow


def _json_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGBA", (2, 2), (20, 30, 40, 255)).save(output, format="PNG")
    return output.getvalue()


@contextmanager
def _qa_api(cache: ActiveEvidenceCache):
    service = ObservabilityService(ROOT, sample_interval=60)
    service._qa_cache = cache
    server = build_server(service, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(Request(f"http://127.0.0.1:{server.server_port}/api/qa", headers={"Accept": "application/json"}), timeout=5) as response:
            yield json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2); service.close()


class QaCacheBindingTests(unittest.TestCase):
    def test_api_exposes_repository_binding_and_dirty_worktree_is_not_pass(self) -> None:
        value = ActiveEvidenceCache(ROOT).validate()
        self.assertIn("current_head", value)
        self.assertIn("validated_head", value)
        self.assertIn("worktree_clean", value)
        self.assertIn("cache_checked_at", value)
        self.assertIn("cache_generation", value)
        self.assertIn("cache_fingerprint", value)
        self.assertIn("stale", value)
        self.assertIn("reason", value)
        if not value["worktree_clean"]:
            self.assertNotEqual("PASS", value["status"])
            self.assertEqual("WORKTREE_DIRTY_UNBOUND", value["reason"])

    def test_source_change_invalidates_previous_pass_without_touching_state_or_index(self) -> None:
        cache = ActiveEvidenceCache(ROOT)
        first = cache.validate()
        if first["status"] != "PASS":
            self.skipTest(f"requires clean active review baseline: {first.get('reason')}")
        source = ROOT / "src/ugas/observability/static/dashboard.css"
        original = source.read_bytes()
        try:
            source.write_bytes(original + b"\n/* QA-NC-07 temporary source mutation */\n")
            second = cache.validate()
        finally:
            source.write_bytes(original)
        self.assertEqual("PASS", first["status"])
        self.assertNotEqual(first["cache_fingerprint"], second["cache_fingerprint"])
        self.assertEqual("GAP", second["status"])
        self.assertEqual("WORKTREE_DIRTY_UNBOUND", second["reason"])
        self.assertFalse(second["worktree_clean"])

    def test_descendant_head_revalidates_against_old_index(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ugas-v0122-head-") as directory:
            clone = Path(directory) / "repo"
            cloned = subprocess.run(["git", "clone", "--no-local", str(ROOT), str(clone)], capture_output=True, text=True, check=False, timeout=60)
            if cloned.returncode != 0:
                self.skipTest(f"local git clone unavailable: {cloned.stderr[-200:]}")
            first_cache = ActiveEvidenceCache(clone)
            first = first_cache.validate()
            if first["status"] != "PASS":
                self.skipTest(f"requires clean active review baseline: {first.get('reason')}")
            source = clone / "README.md"
            source.write_bytes(source.read_bytes() + b"\nQA-NC-08 descendant mutation\n")
            subprocess.run(["git", "add", "README.md"], cwd=clone, check=True, timeout=10)
            committed = subprocess.run(["git", "-c", "user.name=UGAS QA", "-c", "user.email=qa@example.invalid", "commit", "-m", "QA-NC-08 descendant"], cwd=clone, capture_output=True, text=True, check=False, timeout=30)
            self.assertEqual(0, committed.returncode, committed.stderr)
            second = first_cache.validate()
        self.assertNotEqual(first["current_head"], second["current_head"])
        self.assertNotEqual(first["cache_fingerprint"], second["cache_fingerprint"])
        self.assertEqual("GAP", second["status"])
        self.assertEqual("REVIEW_INDEX_INVALID", second["reason"])

    def test_exact_qa_nc_01_02_and_05_are_api_gaps(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ugas-v0122-fixtures-") as directory:
            temporary = Path(directory)
            malformed = temporary / "malformed-current-state.json"
            malformed.write_text("{ malformed", encoding="utf-8")
            with _qa_api(ActiveEvidenceCache(ROOT, state_path=malformed)) as result:
                self.assertEqual("GAP", result["status"])
                self.assertEqual("STATE_EVIDENCE_INVALID", result["reason"])
            schema_invalid = temporary / "schema-invalid-current-state.json"
            state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
            state["version"] = "tampered"
            schema_invalid.write_text(json.dumps(state), encoding="utf-8")
            with _qa_api(ActiveEvidenceCache(ROOT, state_path=schema_invalid)) as result:
                self.assertEqual("GAP", result["status"])
                self.assertEqual("STATE_EVIDENCE_INVALID", result["reason"])
            tampered_index = temporary / "tampered-review-index.json"
            index_path = ROOT / "docs/evidence/review-index-v0.12.2.json"
            if not index_path.is_file():
                self.skipTest("active v0.12.2 index not built yet")
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["artifact_set"]["artifact_set_sha256"] = "0" * 64
            tampered_index.write_text(json.dumps(index), encoding="utf-8")
            with _qa_api(ActiveEvidenceCache(ROOT, review_index_path=tampered_index)) as result:
                self.assertEqual("GAP", result["status"])
                self.assertEqual("REVIEW_INDEX_INVALID", result["reason"])

    def test_exact_qa_nc_03_04_06_reject_contradictory_counts_and_governance(self) -> None:
        tests = {"status": "passed", "count": 10, "passed": 10, "failed": 0}
        validation = {"status": "passed", "checks": 20, "passed": 20, "failed": 0}
        self.assertTrue(validate_qa_semantics({**tests, "failed": 1}, validation))
        self.assertTrue(validate_qa_semantics(tests, {**validation, "passed": 19}))
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        state["production_approved"] = True
        from ugas.state_consistency_v0122 import validate_state_consistency
        result = validate_state_consistency(state, "", "")
        self.assertIn("production_approved_must_remain_false", result["failures"])


class CollectorAndGenerationContractTests(unittest.TestCase):
    def test_stale_last_known_flows_through_refresh_and_http_api(self) -> None:
        good_gpu = {"status": "GPU_AVAILABLE", "capability": "NVIDIA_SMI", "reason": None, "gpu": {"name": "Test GPU", "utilization_percent": 63, "vram_used_mb": 1024, "vram_total_mb": 4096}, "timestamp": "2026-09-02T00:00:00Z"}
        good_processes = {"status": "GPU_PROCESS_AVAILABLE", "capability": "NVIDIA_SMI", "reason": None, "processes": [], "timestamp": "2026-09-02T00:00:00Z"}
        good_comfy = {"endpoint": "http://host.docker.internal:8188", "checked_at": "2026-09-02T00:00:00Z", "status": "UP", "health": "HEALTHY", "reason": None}
        with patch.object(service_module, "probe_nvidia_smi", return_value=good_gpu), patch.object(service_module, "probe_nvidia_processes", return_value=good_processes), patch.object(service_module, "probe_endpoint", return_value=good_comfy):
            service = ObservabilityService(ROOT, sample_interval=60)
            service.refresh(include_assets=False)
        try:
            def slow(*args, **kwargs):
                time.sleep(2.0)
                raise TimeoutError("probe timeout fixture")
            with patch.object(service_module, "probe_nvidia_smi", side_effect=slow), patch.object(service_module, "probe_nvidia_processes", side_effect=slow), patch.object(service_module, "probe_endpoint", side_effect=slow):
                service.refresh(include_assets=False)
            system = service.system()
            processes = service.processes()
            self.assertEqual(63, system["gpu"]["stale_last_known"]["gpu"]["utilization_percent"])
            self.assertGreaterEqual(system["gpu"]["stale_last_known_age_seconds"], 0)
            self.assertNotEqual(0, system["gpu"]["stale_last_known"]["gpu"]["utilization_percent"])
            server = build_server(service, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                before = time.monotonic()
                with urlopen(f"http://127.0.0.1:{server.server_port}/api/system", timeout=2) as response:
                    api_system = json.loads(response.read().decode("utf-8"))
                with urlopen(f"http://127.0.0.1:{server.server_port}/api/processes", timeout=2) as response:
                    api_processes = json.loads(response.read().decode("utf-8"))
                self.assertLess(time.monotonic() - before, 1.0)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)
            self.assertIn("stale_last_known", api_system["gpu"])
            self.assertIn("stale_last_known", api_processes["comfyui"])
        finally:
            service.close()

    def test_generation_instrumentation_emits_real_stages_with_fake_provider(self) -> None:
        class FakeProvider:
            base_url = "http://fake-provider.invalid"

            def submit_workflow(self, workflow, *, client_id):
                return {"prompt_id": "fake-prompt-v0122"}

            def poll_history(self, prompt_id, *, on_poll=None):
                if on_poll:
                    on_poll(prompt_id)
                return {"_ugas_prompt_id": prompt_id, "status": {"completed": True, "status_str": "success"}}

            def fetch_history_outputs(self, history):
                return [{"filename": "output.png", "subfolder": "", "type": "output", "node_id": "1", "data": _json_bytes()}]

        workflow = load_workflow(ROOT, "flux2-klein-4b-distilled-text-to-image")
        service = ObservabilityService(ROOT, sample_interval=60)
        try:
            with tempfile.TemporaryDirectory(prefix="ugas-v0122-generation-") as directory:
                with service.command(["generate", "--fake-provider"]) as parent:
                    result, _ = _run_job(ROOT, FakeProvider(), workflow["api"], output_dir=Path(directory), filename="output.png", profile="generic-2d", capability="2d", workflow_id=workflow["id"], model_id="flux2-klein-4b-distilled-nvfp4", prompt="fixture", seed=1, width=2, height=2)
                job_id = result["job"]["job_id"]
                job = next(item for item in service.jobs()["recent"] if item.get("job_id") == job_id)
        finally:
            service.close()
        self.assertEqual(parent, job["parent_command_id"])
        self.assertEqual("complete", job["current_stage"])
        self.assertEqual("SUCCEEDED", job["status"])
        self.assertIn("provider", [item["stage"] for item in job["recent_stages"]])
        self.assertIsNotNone(job["elapsed_seconds"])

    def test_native_non_loopback_rejected_and_trusted_container_bind_allowed(self) -> None:
        service = ObservabilityService(ROOT, sample_interval=60)
        try:
            with self.assertRaises(ValueError):
                build_server(service, "0.0.0.0", 0)
            with patch.dict(os.environ, {"UGAS_CONTAINERIZED": "1"}):
                server = build_server(service, "0.0.0.0", 0)
                server.server_close()
        finally:
            service.close()


if __name__ == "__main__":
    unittest.main()
