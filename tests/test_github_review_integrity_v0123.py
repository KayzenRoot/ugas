"""R1 regression tests for truthful GitHub review evidence transport."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/validation"))
sys.path.insert(0, str(ROOT / "src"))

from build_github_review_manifest import _known_gaps, build
from build_review_visual_transport_v0123 import detect_media_type
from record_v0123_results import _test_result, _validation_result
from validate_github_review_manifest import validate, validate_declared_media_type, validate_visual_manifest
from ugas.schema_validation import validate_instance


VISUAL_MANIFEST_PATH = ROOT / "docs/evidence/github-review-v0123/visual-manifest.json"
EXPECTED_SOURCE_HASHES = {
    "dashboard-docker-overview-v0122.png": "08fed596faeeeef8803006dfe38c0635405ec7399097d40508a73a415b732f23",
    "dashboard-docker-live-activity-v0122.png": "5f8ad61744942a00300b92816913c1e8fc970e1f716a33f3962df0918c47338a",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class GithubReviewIntegrityTests(unittest.TestCase):
    def test_visual_transport_is_true_png_and_pixel_equivalent(self) -> None:
        manifest = read_json(VISUAL_MANIFEST_PATH)
        result = validate_visual_manifest(manifest, ROOT)
        self.assertEqual("PASS", result["status"], result["failures"])
        for item in manifest["visuals"]:
            source = ROOT / item["source_path"]
            transport = ROOT / item["transport_path"]
            self.assertEqual(EXPECTED_SOURCE_HASHES[source.name], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual("image/jpeg", detect_media_type(source.read_bytes()))
            self.assertEqual("image/png", detect_media_type(transport.read_bytes()))
            self.assertEqual("89504E470D0A1A0A", transport.read_bytes()[:8].hex().upper())
            self.assertTrue(item["decoded_pixel_equal"])

    def test_negative_control_rejects_jpeg_renamed_to_png(self) -> None:
        source = ROOT / "docs/evidence/observability-v0122/dashboard-docker-overview-v0122.png"
        with tempfile.TemporaryDirectory() as directory:
            spoofed = Path(directory) / "spoofed.png"
            spoofed.write_bytes(source.read_bytes())
            self.assertEqual("image/jpeg", detect_media_type(spoofed.read_bytes()))
            self.assertIsNotNone(validate_declared_media_type(spoofed, "image/png"))

    def test_failure_logs_preserve_exit_codes_and_do_not_invent_totals(self) -> None:
        failed_tests = _test_result("Ran 3 tests in 0.01s\n\nFAILED (failures=1)\n", 1)
        failed_validation = _validation_result("SUMMARY checks=4 passed=3 failed=1\n", 1)
        self.assertEqual({"count": 3, "passed": None, "failed": 1, "status": "failed", "exit_code": 1}, {key: failed_tests[key] for key in ("count", "passed", "failed", "status", "exit_code")})
        self.assertEqual({"checks": 4, "passed": 3, "failed": 1, "status": "failed", "exit_code": 1}, {key: failed_validation[key] for key in ("checks", "passed", "failed", "status", "exit_code")})
        malformed = _test_result("Traceback: interrupted before unittest summary\n", 1)
        self.assertEqual("parse_failed", malformed["status"])
        self.assertIsNone(malformed["count"])
        self.assertIsNone(malformed["failed"])

    def test_failed_gate_produces_schema_valid_fail_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            tests_path = temp / "tests.json"
            validation_path = temp / "validation.json"
            gates_path = temp / "gates.json"
            tests_path.write_text(json.dumps(_test_result("Ran 3 tests in 0.01s\nFAILED (failures=1)\n", 1)), encoding="utf-8")
            validation_path.write_text(json.dumps(_validation_result("SUMMARY checks=4 passed=3 failed=1\n", 1)), encoding="utf-8")
            gates = [
                {"id": "unit_tests", "status": "FAIL", "exit_code": 1, "detail": "failed"},
                {"id": "official_validation", "status": "FAIL", "exit_code": 1, "detail": "failed"},
            ]
            gates.extend(
                {"id": gate_id, "status": "PASS", "exit_code": 0, "detail": "fixture"}
                for gate_id in ("state_consistency", "capability_matrix", "visual_transport", "manifest_validation", "security")
            )
            gates_path.write_text(json.dumps({"schema_version": "0.12.3", "overall_status": "FAIL", "gates": gates}), encoding="utf-8")
            args = argparse.Namespace(
                base_ref="6b956b9299f3a2f75280f17706c38c59e3714034",
                head_ref="HEAD",
                head_branch="codex/v0.12.3-github-native-review",
                pr_number=0,
                tests_json=str(tests_path),
                validation_json=str(validation_path),
                gates_json=str(gates_path),
                visual_manifest=str(VISUAL_MANIFEST_PATH),
                preflight_json=None,
                known_gap=None,
            )
            manifest, _ = build(args)
            self.assertEqual("FAIL", manifest["overall_status"])
            schema = read_json(ROOT / "schemas/github-review-manifest-v1.json")
            validate_instance(manifest, schema)
            manifest_path = temp / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            validation = validate(manifest_path, VISUAL_MANIFEST_PATH)
            self.assertEqual("GITHUB_REVIEW_MANIFEST_PASSED", validation["status"], validation["failures"])
            self.assertIn("FAIL", {gate["status"] for gate in manifest["gates"]})

    def test_gap_context_is_event_derived_and_pr_gap_is_rejected(self) -> None:
        args = argparse.Namespace(known_gap=["GITHUB_RULESET_GAP", "GITHUB_PR_CREATE_GAP"], preflight_json=None)
        gaps, context = _known_gaps(args, {}, 0)
        self.assertIn("LOCAL_REHEARSAL_PR_NOT_AVAILABLE", gaps)
        self.assertIn("GITHUB_RULESET_GAP", gaps)
        self.assertNotIn("GITHUB_PR_CREATE_GAP", gaps)
        self.assertEqual("local_rehearsal", context["source"])

        base_args = argparse.Namespace(
            base_ref="6b956b9299f3a2f75280f17706c38c59e3714034",
            head_ref="HEAD",
            head_branch="codex/v0.12.3-github-native-review",
            pr_number=0,
            tests_json=None,
            validation_json=None,
            gates_json=None,
            visual_manifest=str(VISUAL_MANIFEST_PATH),
            preflight_json=None,
            known_gap=None,
        )
        manifest, _ = build(base_args)
        invalid = copy.deepcopy(manifest)
        invalid["pull_request"]["number"] = 12
        invalid["gap_context"]["pr_number"] = 12
        invalid["gap_context"]["pr_available"] = True
        invalid["known_gaps"].append("GITHUB_PR_CREATE_GAP")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            result = validate(path, VISUAL_MANIFEST_PATH)
        self.assertIn("pr-number-positive-cannot-have-github-pr-create-gap", result["failures"])

    def test_review_workflow_uses_immutable_action_pins_and_always_upload(self) -> None:
        workflow = (ROOT / ".github/workflows/ugas-review.yml").read_text(encoding="utf-8")
        for pin in (
            "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2",
            "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0",
            "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2",
        ):
            self.assertIn(pin, workflow)
        self.assertIn("Assemble bounded evidence artifact\n        if: always()", workflow)
        self.assertIn("Upload bounded GitHub review artifact\n        if: always()", workflow)
        self.assertIn("Enforce final review result after artifact upload", workflow)


if __name__ == "__main__":
    unittest.main()
