"""Focused v0.25.0 V1 final acceptance tests with real negative paths."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ugas.acceptance_v0250 import (
    ACCEPTANCE_COMPUTATION_GATE_IDS,
    BASE_MAIN_SHA,
    BRANCH,
    CAPABILITY_RECORDS,
    ENVIRONMENT_GATE_IDS,
    HARD_GATE_IDS,
    OBSERVABILITY_ROW_STATUS,
    PR_TITLE,
    REQUIRED_CAPABILITY_IDS,
    VERSION,
    WORK_ORDER_ID,
    AcceptanceContractError,
    acceptance_status,
    audit_architecture,
    audit_capability_matrix,
    audit_security,
    canonical_acceptance_digest,
    evaluate_acceptance_gates,
    observability_binding,
    strict_gate_observation,
)
from ugas.state_consistency_v0250 import CURRENT_GATE, validate_state_consistency


def load_script(name: str):
    path = ROOT / "scripts" / "validation" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def read_json(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def matrix_closure() -> dict:
    return dict(read_json("docs/evidence/current-state.json")["orchestration_closure"])


def audit_input() -> dict:
    return {
        "capability_count": 16,
        "production_routing": "BLOCKED",
        "new_generation": 0,
        "status": "PASS",
        "observability": {"visual_review_status": "PASS"},
    }


def tampered_matrix(mutator) -> dict:
    matrix = copy.deepcopy(read_json("docs/ugas-v1-capability-matrix.json"))
    mutator(matrix)
    return matrix


class FinalAcceptancev0250Tests(unittest.TestCase):
    def reject(self, expected: str, action) -> None:
        with self.assertRaises(AcceptanceContractError) as ctx:
            action()
        self.assertEqual(ctx.exception.code, expected)

    def test_a01_constants_bind_the_authorized_candidate(self) -> None:
        self.assertEqual(VERSION, "0.25.0")
        self.assertEqual(WORK_ORDER_ID, "UGAS-WO-V1-FINAL-ACCEPTANCE-001")
        self.assertEqual(BASE_MAIN_SHA, "6c6d53dab5a95226bf9578a6099d755d51327d8e")
        self.assertEqual(BRANCH, "codex/v1-final-acceptance")
        self.assertEqual(PR_TITLE, "UGAS V1 Final Acceptance")
        self.assertEqual(len(HARD_GATE_IDS), 28)
        self.assertEqual(len(set(HARD_GATE_IDS)), 28)
        self.assertEqual(set(ENVIRONMENT_GATE_IDS) | set(ACCEPTANCE_COMPUTATION_GATE_IDS), set(HARD_GATE_IDS))
        self.assertEqual(REQUIRED_CAPABILITY_IDS, tuple(record["id"] for record in CAPABILITY_RECORDS))
        self.assertEqual(len(REQUIRED_CAPABILITY_IDS), 16)

    def test_a02_strict_gate_observation_rejects_non_booleans(self) -> None:
        rejected = strict_gate_observation("unit_suite_pass", "true")
        self.assertEqual(rejected["status"], "FAIL")
        self.assertEqual(rejected["reason"], "OBSERVED_VALUE_NOT_STRICT_BOOLEAN")
        self.assertEqual(rejected["observed_type"], "str")
        self.assertEqual(strict_gate_observation("unit_suite_pass", True)["status"], "PASS")
        false_gate = strict_gate_observation("unit_suite_pass", False)
        self.assertEqual(false_gate["status"], "FAIL")
        self.assertEqual(false_gate["reason"], "OBSERVED_FALSE")

    def test_a03_acceptance_gates_are_observed_not_assumed(self) -> None:
        empty = evaluate_acceptance_gates({})
        self.assertFalse(empty["overall_pass"])
        self.assertEqual(tuple(empty["missing_observations"]), tuple(sorted(HARD_GATE_IDS)))
        literal = evaluate_acceptance_gates({gate_id: "true" for gate_id in HARD_GATE_IDS})
        self.assertFalse(literal["overall_pass"])
        self.assertTrue(all(item["reason"] == "OBSERVED_VALUE_NOT_STRICT_BOOLEAN" for item in literal["gates"].values()))
        full = evaluate_acceptance_gates({gate_id: True for gate_id in HARD_GATE_IDS})
        self.assertTrue(full["overall_pass"])

    def test_a04_capability_matrix_audit_passes_the_tracked_matrix(self) -> None:
        result = audit_capability_matrix(ROOT, read_json("docs/ugas-v1-capability-matrix.json"), matrix_closure())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["capability_count"], 16)
        self.assertEqual(result["accepted_or_preserved"], 16)
        self.assertEqual(result["blocked"], 0)
        self.assertEqual(result["orchestration_merge_sha"], BASE_MAIN_SHA)
        observability = next(row for row in result["capabilities"] if row["id"] == "local_always_on_observability")
        self.assertEqual(observability["claimed_status"], OBSERVABILITY_ROW_STATUS)

    def test_a05_capability_matrix_audit_rejects_matrix_defects(self) -> None:
        closure = matrix_closure()
        promoted = tampered_matrix(lambda value: next(item for item in value["capabilities"] if item["id"] == "core_2d_generation").update({"status": "APPROVED_PRODUCTION"}))
        self.reject("CAPABILITY_STATUS_UNSUPPORTED", lambda: audit_capability_matrix(ROOT, promoted, closure))
        duplicate = tampered_matrix(lambda value: value["capabilities"].insert(0, copy.deepcopy(value["capabilities"][0])))
        self.reject("CAPABILITY_DUPLICATE_ID", lambda: audit_capability_matrix(ROOT, duplicate, closure))
        dropped = tampered_matrix(lambda value: value["capabilities"].pop())
        self.reject("CAPABILITY_SET_MISMATCH", lambda: audit_capability_matrix(ROOT, dropped, closure))
        extra = tampered_matrix(lambda value: value["capabilities"].append({"id": "v0250_extra", "status": "APPROVED_PILOT"}))
        self.reject("CAPABILITY_SET_MISMATCH", lambda: audit_capability_matrix(ROOT, extra, closure))

    def test_a06_capability_matrix_audit_rejects_record_defects(self) -> None:
        closure = matrix_closure()
        records = tuple(copy.deepcopy(dict(item)) for item in CAPABILITY_RECORDS)
        pointer_records = tuple(dict(item) for item in records)
        for item in pointer_records:
            if item["id"] == "core_2d_generation":
                item["pointers"] = tuple(item["pointers"]) + ("docs/evidence/v0250-unwritten-pointer",)
        with patch("ugas.acceptance_v0250.CAPABILITY_RECORDS", pointer_records):
            self.reject("CAPABILITY_EVIDENCE_MISSING", lambda: audit_capability_matrix(ROOT, read_json("docs/ugas-v1-capability-matrix.json"), closure))
        authority_records = tuple(dict(item) for item in records)
        for item in authority_records:
            if item["id"] == "ui_asset_family":
                item["merge_sha"] = None
        with patch("ugas.acceptance_v0250.CAPABILITY_RECORDS", authority_records):
            self.reject("ORCHESTRATION_CLOSURE_AUTHORITY_MISSING", lambda: audit_capability_matrix(ROOT, read_json("docs/ugas-v1-capability-matrix.json"), closure))

    def test_a07_observability_binding_is_external_and_unpromoted(self) -> None:
        result = observability_binding(ROOT)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["visual_review_status"], "PASS")
        self.assertFalse(result["self_approval"])
        self.assertEqual(result["failures"], [])

    def test_a08_architecture_audit_is_provider_neutral(self) -> None:
        result = audit_architecture(ROOT)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["gates_observed_not_hardcoded"])
        self.assertTrue(result["orchestration_provider_neutral"])
        self.assertEqual(result["cycles"], [])

    def test_a09_security_audit_is_clean(self) -> None:
        result = audit_security(ROOT)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["secrets_included"])
        self.assertEqual(result["repo_local_uads"], [])

    def test_a10_state_consistency_accepts_the_active_state(self) -> None:
        state = read_json("docs/evidence/current-state.json")
        result = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"), read_json("docs/ugas-v1-capability-matrix.json"), audit_input())
        self.assertEqual(result["status"], CURRENT_GATE)
        self.assertEqual(result["failures"], [])

    def test_a11_state_consistency_rejects_production_and_lifecycle_drift(self) -> None:
        base = read_json("docs/evidence/current-state.json")
        checkpoint = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8")
        roadmap = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")
        matrix = read_json("docs/ugas-v1-capability-matrix.json")
        approved = copy.deepcopy(base)
        approved["production_approved"] = True
        self.assertIn("production_approved_invalid", validate_state_consistency(approved, checkpoint, roadmap, matrix, None)["failures"])
        lifecycle = copy.deepcopy(base)
        lifecycle["orchestration_lifecycle"] = "AWAITING_MERGE"
        self.assertIn("orchestration_lifecycle_invalid", validate_state_consistency(lifecycle, checkpoint, roadmap, matrix, None)["failures"])
        stale = copy.deepcopy(base)
        stale["version"] = "0.24.6"
        self.assertIn("version_invalid", validate_state_consistency(stale, checkpoint, roadmap, matrix, None)["failures"])
        self.assertIn("documents_missing:0.25.0", validate_state_consistency(base, "", "", matrix, None)["failures"])

    def test_a12_uads_handoff_accepts_and_rejects_sanitized_states(self) -> None:
        runner = load_script("run_v1_final_acceptance_v0250")
        self.assertEqual(runner.validate_uads_handoff(runner._uads_handoff_with())["status"], "PASS")
        dispatched = runner._uads_handoff_with(dispatch_status="DISPATCHED", run_or_dispatch_id="er_0000000000000000")
        self.assertIs(runner.validate_uads_handoff(dispatched)["dispatch_id_present"], True)
        self.reject("UADS_ROUTE_STATUS_REJECTED", lambda: runner.validate_uads_handoff(runner._uads_handoff_with(route_status="REJECTED")))
        self.reject("UADS_DISPATCH_STATUS_REJECTED", lambda: runner.validate_uads_handoff(runner._uads_handoff_with(dispatch_status="FAILED")))
        self.reject("UADS_HANDOFF_ID_INVALID", lambda: runner.validate_uads_handoff(runner._uads_handoff_with(work_order_id="wo_BAD")))
        self.reject("UADS_HANDOFF_UNSAFE", lambda: runner.validate_uads_handoff(runner._uads_handoff_with(selected_profile_id="profile-" + "." + "uads")))

    def test_a13_acceptance_verdicts_cover_every_stop_condition(self) -> None:
        gates_ok = {"overall_pass": True, "gates": {gate_id: {"status": "PASS"} for gate_id in HARD_GATE_IDS}}
        gates_bad = {"overall_pass": False, "gates": {gate_id: {"status": "FAIL"} for gate_id in HARD_GATE_IDS}}
        high = [{"id": "NC-HIGH", "severity": "HIGH", "status": "OPEN"}]
        self.assertEqual(acceptance_status(findings=high, gates=gates_ok, observability={"status": "PASS"}, evidence_complete=True)["status"], "CORRECTION_REQUIRED")
        blocking = [{"id": "NC-MED", "severity": "MEDIUM", "status": "OPEN", "blocks_acceptance": True}]
        self.assertEqual(acceptance_status(findings=blocking, gates=gates_ok, observability={"status": "PASS"}, evidence_complete=True)["status"], "CORRECTION_REQUIRED")
        self.assertEqual(acceptance_status(findings=[], gates=gates_ok, observability={"status": "FAIL"}, evidence_complete=True)["status"], "BLOCKED_PENDING_OBSERVABILITY_VISUAL_REVIEW")
        self.assertEqual(acceptance_status(findings=[], gates=gates_bad, observability={"status": "PASS"}, evidence_complete=False)["status"], "INCOMPLETE_ACCEPTANCE_EVIDENCE")
        candidate = acceptance_status(findings=[], gates=gates_ok, observability={"status": "PASS"}, evidence_complete=True)
        self.assertEqual(candidate["status"], "V1_ACCEPTANCE_CANDIDATE")
        self.assertTrue(candidate["acceptance_claim_allowed"])

    def test_a14_controls_payload_enforces_the_acceptance_floor(self) -> None:
        runner = load_script("run_v1_final_acceptance_v0250")
        empty = runner._controls_payload([])
        self.assertEqual(empty["status"], "FAIL")
        self.assertIn(f"control_floor_not_met:0<{runner.ACCEPTANCE_CONTROL_FLOOR}", empty["failures"])
        passing = runner._controls_payload([{"control_id": f"NC-{index:02d}", "status": "PASS"} for index in range(runner.ACCEPTANCE_CONTROL_FLOOR)])
        self.assertEqual(passing["status"], "PASS")
        self.assertEqual(passing["control_count"], runner.ACCEPTANCE_CONTROL_FLOOR)
        duplicated = runner._controls_payload([{"control_id": "NC-DUP", "status": "PASS"}] * runner.ACCEPTANCE_CONTROL_FLOOR)
        self.assertIn("duplicate_control_id", duplicated["failures"])

    def test_a15_determinism_view_normalizes_self_attestation(self) -> None:
        runner = load_script("run_v1_final_acceptance_v0250")
        value = runner._determinism_view({
            "generated_at": "stamp",
            "evidence_inventory": [
                {"name": runner.SUMMARY_EVIDENCE_FILE, "status": "PRESENT", "size": 100, "sha256": "a" * 64},
                {"name": "hard-gates.json", "status": "PRESENT", "size": 7, "sha256": "b" * 64},
            ],
            "security": {"evidence_root_bytes": 999},
        })
        self.assertNotIn("generated_at", value)
        summary_entry = value["evidence_inventory"][0]
        self.assertEqual(summary_entry["status"], "SELF_ATTESTATION")
        self.assertIsNone(summary_entry["sha256"])
        self.assertEqual(value["security"]["evidence_root_bytes"], 7)

    def test_a16_negative_controls_all_pass(self) -> None:
        runner = load_script("run_v1_final_acceptance_v0250")
        payload = runner._controls_payload(runner._negative_controls())
        self.assertEqual(payload["failures"], [])
        self.assertEqual(payload["status"], "PASS")
        self.assertGreaterEqual(payload["control_count"], payload["minimum_required"])
        self.assertTrue(all(item["status"] == "PASS" for item in payload["controls"].values()))

    def test_a17_acceptance_core_is_deterministic_and_strict(self) -> None:
        runner = load_script("run_v1_final_acceptance_v0250")
        first = runner.compute_core(determinism_pass=True)
        second = runner.compute_core(determinism_pass=True)
        self.assertEqual(canonical_acceptance_digest(runner._determinism_view(first)), canonical_acceptance_digest(runner._determinism_view(second)))
        self.assertEqual(len(first["gates"]["gates"]), 28)
        self.assertTrue(all(type(value) is bool for value in first["observations"].values()))
        self.assertEqual(first["controls"]["status"], "PASS")
        self.assertEqual(first["snapshot_binding"]["status"], "PASS")

    def test_a18_definition_of_done_separates_production(self) -> None:
        runner = load_script("run_v1_final_acceptance_v0250")
        self.assertTrue(runner._definition_of_done_binding(ROOT))
        self.assertEqual(runner._production_claim_hits(ROOT), [])