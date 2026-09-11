"""Focused v0.25.1 canonical-state reconciliation tests with real negative paths."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ugas.acceptance_v0250 import (
    APPROVAL_RECORD_PATH,
    APPROVED_SEMANTIC_HEAD,
    observability_binding,
    validate_external_approval,
)
from ugas.schema_validation import validate_instance, validate_schema_document
from ugas.state_consistency_v0251 import (
    ACCEPTANCE_VERDICT,
    BASELINE_MAIN_SHA,
    BRANCH,
    CLOSURE_EVIDENCE_ROOT,
    CURRENT_GATE,
    FROZEN_ACCEPTANCE_ROOT,
    HARD_GATE_COUNT,
    NEGATIVE_CONTROL_IDS,
    NEXT_ACTION,
    NEXT_CANDIDATE,
    ORCHESTRATION_EVIDENCE_ROOT,
    STOP_REASON,
    V1_AUDIT_COMMENT_ID,
    V1_BOOKKEEPING_HEAD,
    V1_CLOSURE_COMMENT_ID,
    V1_DOCKER_JOB,
    V1_POST_MERGE_CI_RUN,
    V1_SEMANTIC_HEAD,
    V1_STATE_SNAPSHOT,
    V1_UNIT_JOB,
    VERSION,
    closure_binding_failures,
    definition_of_done_hard_gate_count,
    immutability_failures,
    negative_control_failures,
    validate_state_consistency,
)

SNAPSHOT_SHA256 = "f843e21c378dbc7bd6eca02fb580bb3a995d1513ed126f897ebeff7fc99ad1a9"
STALE_PENDING_GATE = "V1_TECHNICAL_BASELINE_EXTERNALLY_APPROVED_PENDING_GOVERNED_MERGE"


def load_script(name: str):
    path = ROOT / "scripts" / "validation" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def read_json(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def normalized_digest(path: Path) -> str:
    data = path.read_bytes().replace(bytes([13, 10]), bytes([10]))
    return hashlib.sha256(data).hexdigest()


def live_inputs() -> tuple[dict, str, str, dict]:
    return (
        read_json("docs/evidence/current-state.json"),
        (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"),
        (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"),
        read_json("docs/ugas-v1-capability-matrix.json"),
    )


def audit_input(state: dict) -> dict:
    audit = read_json("docs/evidence/v1-final-acceptance/capability-matrix-audit.json")
    return {
        "capability_count": audit.get("capability_count"),
        "production_routing": state.get("production_routing"),
        "new_generation": state.get("new_generation"),
        "status": audit.get("status"),
        "observability": {"visual_review_status": observability_binding(ROOT).get("visual_review_status")},
    }


class CanonicalStateReconciliationv0251Tests(unittest.TestCase):
    def test_b01_constants_bind_the_authorized_reconciliation(self) -> None:
        self.assertEqual(VERSION, "0.25.1")
        self.assertEqual(BASELINE_MAIN_SHA, "02fa44f2173aca46b4484209abccf218fe688a63")
        self.assertEqual(BRANCH, "codex/ugas-wo-0253-v1-canonical-state-reconciliation")
        self.assertEqual(CURRENT_GATE, "V1_TECHNICAL_BASELINE_MERGED_CLOSED")
        self.assertEqual(STOP_REASON, "V1_TECHNICAL_BASELINE_CLOSED_PRODUCTION_READINESS_NOT_STARTED")
        self.assertEqual(ACCEPTANCE_VERDICT, "V1_TECHNICAL_BASELINE_ACCEPTED")
        self.assertEqual(NEXT_CANDIDATE, "PRODUCTION_READINESS")
        self.assertEqual(NEXT_ACTION, "define_and_review_production_readiness_work_order")
        self.assertEqual(HARD_GATE_COUNT, 30)
        self.assertEqual(len(NEGATIVE_CONTROL_IDS), 14)
        self.assertEqual(V1_SEMANTIC_HEAD, "66db255fdb2483da4bae08e418c904f24d215ebb")
        self.assertEqual(V1_BOOKKEEPING_HEAD, "5046b3ed8c626540fa8258d25afc9a2abbf0a182")
        self.assertEqual(V1_POST_MERGE_CI_RUN, 34610394648)
        self.assertEqual(V1_UNIT_JOB, 103299136405)
        self.assertEqual(V1_DOCKER_JOB, 103299136059)
        self.assertEqual(V1_CLOSURE_COMMENT_ID, 5636295417)
        self.assertEqual(V1_AUDIT_COMMENT_ID, 5637818972)

    def test_b02_active_state_schema_and_frozen_snapshot_identity(self) -> None:
        schema = read_json("schemas/current-state-v0251.json")
        validate_schema_document(schema)
        self.assertEqual(schema["properties"]["version"]["const"], VERSION)
        state = read_json("docs/evidence/current-state.json")
        validate_instance(state, schema)
        self.assertEqual(state["version"], VERSION)
        self.assertEqual(state["schema_version"], VERSION)
        snapshot_path = ROOT / V1_STATE_SNAPSHOT
        self.assertEqual(normalized_digest(snapshot_path), SNAPSHOT_SHA256)
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertEqual(snapshot["version"], "0.25.0")
        self.assertEqual(snapshot["current_gate"], STALE_PENDING_GATE)
        self.assertEqual(snapshot["acceptance_verdict"], "V1_ACCEPTANCE_CANDIDATE")
        binding = read_json(CLOSURE_EVIDENCE_ROOT + "closure-binding-v0251.json")["v0250_state_snapshot"]
        self.assertEqual(binding["sha256"], SNAPSHOT_SHA256)
        self.assertEqual(binding["source_commit"], BASELINE_MAIN_SHA)

    def test_b03_state_consistency_accepts_the_active_state(self) -> None:
        state, checkpoint, roadmap, matrix = live_inputs()
        result = validate_state_consistency(state, checkpoint, roadmap, matrix, audit_input(state))
        self.assertEqual(result["status"], CURRENT_GATE)
        self.assertEqual(result["failures"], [])

    def test_b04_active_documents_carry_the_merged_closure(self) -> None:
        checkpoint = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8")
        roadmap = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")
        for document in (checkpoint, roadmap):
            self.assertIn(CURRENT_GATE, document)
            self.assertIn(V1_SEMANTIC_HEAD, document)
            self.assertIn(V1_BOOKKEEPING_HEAD, document)
            self.assertIn(str(V1_POST_MERGE_CI_RUN), document)
            self.assertIn(str(V1_CLOSURE_COMMENT_ID), document)
            self.assertIn("production_routing=BLOCKED", document)
            self.assertIn("production_approved=false", document)
            self.assertNotIn(STALE_PENDING_GATE, document.split("## Historical", 1)[0])

    def test_b05_state_consistency_rejects_the_stale_pending_merge_gate(self) -> None:
        state, checkpoint, roadmap, matrix = live_inputs()
        stale = copy.deepcopy(state)
        stale["current_gate"] = STALE_PENDING_GATE
        result = validate_state_consistency(stale, checkpoint, roadmap, matrix, audit_input(state))
        self.assertEqual(result["status"], "V1_CANONICAL_STATE_FAILED")
        self.assertIn("current_gate_invalid", result["failures"])
        legacy = copy.deepcopy(state)
        legacy["main_sha"] = BASELINE_MAIN_SHA
        result = validate_state_consistency(legacy, checkpoint, roadmap, matrix, audit_input(state))
        self.assertIn("main_sha_forbidden", result["failures"])

    def test_b06_state_consistency_rejects_closure_identity_drift(self) -> None:
        state, checkpoint, roadmap, matrix = live_inputs()
        drifts = {
            "merge_main_sha": "6c6d53dab5a95226bf9578a6099d755d51327d8e",
            "post_merge_ci_run": 34523428088,
            "unit_job": 103026362729,
            "docker_job": 103026362968,
            "closure_comment_id": 5625161567,
            "audit_verdict": "REJECTED",
            "semantic_head": "0" * 40,
            "bookkeeping_head": "1" * 40,
        }
        for key, wrong in drifts.items():
            mutated = copy.deepcopy(state)
            mutated["v1_closure"][key] = wrong
            result = validate_state_consistency(mutated, checkpoint, roadmap, matrix, audit_input(state))
            self.assertIn(f"v1_closure:{key}", result["failures"], key)
        history = copy.deepcopy(state)
        history["correction_history"]["v0.25.0"]["semantic_head"] = "0" * 40
        result = validate_state_consistency(history, checkpoint, roadmap, matrix, audit_input(state))
        self.assertIn("correction_history:0.25.0_closure_invalid", result["failures"])

    def test_b07_state_consistency_rejects_production_boundary_drift(self) -> None:
        state, checkpoint, roadmap, matrix = live_inputs()
        drifts = {
            "production_approved": True,
            "production_routing": "ENABLED",
            "new_generation": 1,
            "provider_submit_calls": 1,
            "real_asset_generation": "REAL",
            "production_readiness_workstream": "STARTED",
        }
        for key, wrong in drifts.items():
            mutated = copy.deepcopy(state)
            mutated[key] = wrong
            result = validate_state_consistency(mutated, checkpoint, roadmap, matrix, audit_input(state))
            self.assertIn(f"{key}_invalid", result["failures"], key)

    def test_b08_state_consistency_rejects_next_candidate_and_unsafe_action_drift(self) -> None:
        state, checkpoint, roadmap, matrix = live_inputs()
        drifted = copy.deepcopy(state)
        drifted["next_candidate"] = "V1_FINAL_ACCEPTANCE"
        result = validate_state_consistency(drifted, checkpoint, roadmap, matrix, audit_input(state))
        self.assertIn("next_candidate_invalid", result["failures"])
        unsafe = copy.deepcopy(state)
        unsafe["allowed_next_actions"] = ["start_production_readiness"]
        result = validate_state_consistency(unsafe, checkpoint, roadmap, matrix, audit_input(state))
        self.assertIn("unsafe_next_action", result["failures"])
        self.assertIn("allowed_action_forbidden_contradiction", result["failures"])

    def test_b09_closure_binding_evidence_accepts_and_rejects_drift(self) -> None:
        evidence = read_json(CLOSURE_EVIDENCE_ROOT + "closure-binding-v0251.json")
        self.assertEqual(closure_binding_failures(evidence), [])
        semantic = copy.deepcopy(evidence)
        semantic["binding"]["semantic_head"] = "0" * 40
        self.assertIn("binding:semantic_head", closure_binding_failures(semantic))
        snapshot = copy.deepcopy(evidence)
        snapshot["v0250_state_snapshot"]["sha256"] = "short"
        self.assertIn("v0250_state_snapshot:invalid", closure_binding_failures(snapshot))
        status = copy.deepcopy(evidence)
        status["status"] = "FAIL"
        self.assertIn("status_or_version_invalid", closure_binding_failures(status))

    def test_b10_immutability_proof_accepts_and_rejects_tampering(self) -> None:
        evidence = read_json(CLOSURE_EVIDENCE_ROOT + "immutability-proof-v0251.json")
        self.assertEqual(immutability_failures(evidence, ROOT), [])
        unguarded = copy.deepcopy(evidence)
        unguarded["git_guarded"] = False
        self.assertIn("git_guarded", immutability_failures(unguarded, ROOT))
        count = copy.deepcopy(evidence)
        count["frozen_roots"][FROZEN_ACCEPTANCE_ROOT]["file_count"] += 1
        self.assertIn(f"{FROZEN_ACCEPTANCE_ROOT}:file_count", immutability_failures(count, ROOT))
        recorded = copy.deepcopy(evidence)
        first = recorded["frozen_roots"][ORCHESTRATION_EVIDENCE_ROOT]["files"][0]
        first["sha256"] = "0" * 64
        self.assertIn(f"{ORCHESTRATION_EVIDENCE_ROOT}:{first['path']}:sha256", immutability_failures(recorded, ROOT))

    def test_b11_negative_control_evidence_accepts_and_rejects_failed_controls(self) -> None:
        evidence = read_json(CLOSURE_EVIDENCE_ROOT + "negative-controls-v0251.json")
        self.assertEqual(negative_control_failures(evidence), [])
        self.assertEqual(evidence["control_count"], len(NEGATIVE_CONTROL_IDS))
        drifted = copy.deepcopy(evidence)
        drifted["controls"]["NEG-0253-01-STALE-PENDING-MERGE"]["observed_rejection_class"] = "NONE"
        self.assertIn("NEG-0253-01-STALE-PENDING-MERGE:rejection_class", negative_control_failures(drifted))
        missing = copy.deepcopy(evidence)
        del missing["controls"]["NEG-0253-14-NEXT-CANDIDATE-DRIFT"]
        self.assertIn("control_count", negative_control_failures(missing))

    def test_b12_generator_negative_controls_execute_real_rejection_paths(self) -> None:
        runner = load_script("run_canonical_state_reconciliation_v0251")
        payload = runner.negative_controls()
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["control_count"], len(NEGATIVE_CONTROL_IDS))
        self.assertEqual(set(payload["controls"]), set(NEGATIVE_CONTROL_IDS))
        for control_id, record in payload["controls"].items():
            self.assertEqual(record["status"], "PASS", control_id)
            self.assertEqual(record["result"], "REJECT", control_id)
            self.assertEqual(record["expected_rejection_class"], record["observed_rejection_class"], control_id)
            self.assertNotEqual(record["expected_rejection_class"], "NONE", control_id)

    def test_b13_closure_binding_regeneration_matches_tracked_evidence(self) -> None:
        runner = load_script("run_canonical_state_reconciliation_v0251")
        regenerated = runner.closure_binding()
        self.assertEqual(runner._canonical_digest(regenerated), runner._canonical_digest(runner.closure_binding()))
        tracked = read_json(CLOSURE_EVIDENCE_ROOT + "closure-binding-v0251.json")
        for key in ("schema_version", "version", "status", "work_order", "issue", "binding", "v0250_state_snapshot", "tracked_state_binding", "historical_evidence_unchanged"):
            self.assertEqual(regenerated[key], tracked[key], key)

    def test_b14_closure_validator_reports_pass_end_to_end(self) -> None:
        validator = load_script("validate_v1_closure_v0251")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "closure-v0251.json"
            with patch.object(sys, "argv", ["validate_v1_closure_v0251.py", "--output", str(output)]):
                code = validator.main()
            self.assertEqual(code, 0)
            result = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["failures"], [])

    def test_b15_definition_of_done_declares_the_accepted_hard_gate_count(self) -> None:
        definition = (ROOT / "docs/definition-of-done.md").read_text(encoding="utf-8")
        self.assertEqual(definition_of_done_hard_gate_count(definition), HARD_GATE_COUNT)
        self.assertEqual(definition_of_done_hard_gate_count("each of the 28 hard gates"), 28)
        self.assertIsNone(definition_of_done_hard_gate_count("no gate count declared here"))
        gates = read_json("docs/evidence/v1-final-acceptance/hard-gates.json")
        self.assertEqual(len(gates["gates"]), HARD_GATE_COUNT)
        self.assertTrue(gates["overall_pass"])

    def test_b16_historical_v0250_acceptance_stays_reproducible(self) -> None:
        schema = read_json("schemas/current-state-v0250.json")
        validate_schema_document(schema)
        snapshot = json.loads((ROOT / V1_STATE_SNAPSHOT).read_text(encoding="utf-8"))
        validate_instance(snapshot, schema)
        approval = validate_external_approval(read_json(APPROVAL_RECORD_PATH), candidate_head=APPROVED_SEMANTIC_HEAD, root=ROOT)
        self.assertEqual(approval["status"], "PASS")
        self.assertIs(approval["production_approved"], False)
        self.assertEqual(approval["production_routing"], "BLOCKED")
