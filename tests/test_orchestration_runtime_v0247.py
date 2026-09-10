"""Focused v0.24.7 correction tests with real negative paths."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from ugas.orchestration_runtime_v0247 import (
    HARD_GATE_IDS,
    BoundedExecutionStore,
    CircuitBreaker,
    DeterministicBatchScheduler,
    DeterministicClock,
    ExecutionCoordinator,
    FakeExecutor,
    OrchestrationContractError,
    OrchestrationRuntime,
    assert_provider_boundary,
    build_dag,
    build_dependency_ref,
    build_request,
    evaluate_hard_gates,
    provider_spy_targets,
    resolve_dependency_ref,
    resume_from_checkpoint,
    sha256_value,
    sanitize_uads_handoff,
    validate_canonical_correction_history,
    validate_checkpoint,
    validate_concurrency_limits,
    validate_dependency_ref,
    validate_provider_spy_counts,
    validate_request,
)


def make_request(*, request_id: str = "request-0242", project_id: str = "project-0242", timeout: int = 30, idempotency_key: str = "idem-0242") -> dict:
    return build_request(
        request_id=request_id,
        project_id=project_id,
        request_kind="ASSET_OPERATION",
        asset_family="maps_minimap",
        operation="EXECUTE",
        inputs={"fixture": "deterministic"},
        dependency_refs=[],
        outputs={"project_id": project_id, "path": "results/output.json"},
        quality_profile="qa",
        budget_profile="bounded",
        priority=50,
        timeout_seconds=timeout,
        retry_policy={"max_attempts": 2, "retryable_errors": ["TRANSIENT_EXECUTION_ERROR", "REQUEST_DEADLINE_EXCEEDED", "NODE_DEADLINE_EXCEEDED"]},
        idempotency_key=idempotency_key,
        production_intent=False,
        test_only=True,
    )


def make_node(node_id: str, dependencies: list[str] | None = None, *, family: str = "maps_minimap", timeout: int = 20, priority: int = 10) -> dict:
    return {
        "node_id": node_id,
        "dependencies": dependencies or [],
        "operation": "EXECUTE",
        "input_contract_hash": (node_id.encode().hex() * 64)[:64],
        "dependency_hashes": {},
        "timeout_seconds": timeout,
        "retry_policy": {"max_attempts": 2, "retryable_errors": ["TRANSIENT_EXECUTION_ERROR", "REQUEST_DEADLINE_EXCEEDED", "NODE_DEADLINE_EXCEEDED"]},
        "resource_class": "cpu-test",
        "scheduling_key": "orchestration-v0247",
        "priority": priority,
        "asset_family": family,
    }


class OrchestrationRuntimev0247Tests(unittest.TestCase):
    def dag(self, request: dict | None = None, nodes: list[dict] | None = None) -> tuple[dict, dict]:
        req = request or make_request()
        value = nodes or [make_node("root"), make_node("child", ["root"]), make_node("tail", ["child"])]
        return req, build_dag(req, value)

    def reject(self, expected: str, action) -> None:
        with self.assertRaises(OrchestrationContractError) as ctx:
            action()
        self.assertEqual(ctx.exception.rejection_class, expected)

    def test_request_and_dag_hashes_are_forward_bound(self) -> None:
        request, dag = self.dag()
        self.assertEqual(request["request_hash"], validate_request(request)["request_hash"])
        self.assertEqual(dag["dag_hash"], build_dag(request, dag["nodes"])["dag_hash"])

    def test_request_deadline_is_consumed_by_fake_elapsed_input(self) -> None:
        request = make_request(timeout=3)
        request, dag = self.dag(request, [make_node("first", timeout=10), make_node("second", ["first"], timeout=10), make_node("third", ["second"], timeout=10)])
        runtime = OrchestrationRuntime(request, dag, executor=FakeExecutor(durations={"first": 2, "second": 2, "third": 0}))
        snapshot = runtime.run()
        self.assertEqual(snapshot["states"]["first"], "SUCCEEDED")
        self.assertEqual(snapshot["states"]["second"], "FAILED")
        self.assertEqual(snapshot["states"]["third"], "BLOCKED")
        self.assertEqual(snapshot["node_deadlines"]["second"]["error_class"], "REQUEST_DEADLINE_EXCEEDED")
        self.assertEqual(snapshot["clock_elapsed_seconds"], 3.0)

    def test_node_deadline_is_typed_and_parent_bounded(self) -> None:
        request = make_request(timeout=20)
        request, dag = self.dag(request, [make_node("slow", timeout=2)])
        snapshot = OrchestrationRuntime(request, dag, executor=FakeExecutor(durations={"slow": 3})).run()
        self.assertEqual(snapshot["states"]["slow"], "FAILED")
        self.assertEqual(snapshot["node_deadlines"]["slow"]["error_class"], "NODE_DEADLINE_EXCEEDED")
        self.assertLessEqual(snapshot["node_deadlines"]["slow"]["deadline_seconds"], request["timeout_seconds"])
        self.assertLessEqual(snapshot["clock_elapsed_seconds"], request["timeout_seconds"])

    def test_retry_consumes_the_same_parent_deadline(self) -> None:
        request = make_request(timeout=3)
        request, dag = self.dag(request, [make_node("retry", timeout=10)])
        snapshot = OrchestrationRuntime(request, dag, executor=FakeExecutor(durations={"retry": [2, 2]})).run(faults={"retry": "retryable"})
        self.assertEqual(snapshot["states"]["retry"], "FAILED")
        self.assertEqual(snapshot["attempts"]["retry"], 2)
        self.assertEqual(snapshot["node_deadlines"]["retry"]["error_class"], "REQUEST_DEADLINE_EXCEEDED")

    def test_partial_checkpoint_resume_does_not_reexecute_success(self) -> None:
        request, dag = self.dag()
        first = OrchestrationRuntime(request, dag, executor=FakeExecutor())
        partial = first.run(stop_after_nodes=1)
        checkpoint = first.checkpoint()
        self.assertEqual(partial["status"], "PARTIAL")
        self.assertEqual(validate_checkpoint(checkpoint, request, dag)["status"], "PASS")
        second_executor = FakeExecutor()
        resumed = resume_from_checkpoint(request, dag, checkpoint, executor=second_executor)
        final = resumed.run()
        self.assertEqual(final["status"], "COMPLETE")
        self.assertEqual(second_executor.calls_by_node.get("root", 0), 0)
        self.assertEqual(second_executor.executions, 2)

    def test_checkpoint_rejects_extra_node_and_unknown_event(self) -> None:
        request, dag = self.dag()
        runtime = OrchestrationRuntime(request, dag, executor=FakeExecutor())
        runtime.run(stop_after_nodes=1)
        checkpoint = runtime.checkpoint()
        extra = copy.deepcopy(checkpoint)
        extra["states"]["injected"] = "PLANNED"
        extra["checkpoint_hash"] = sha256_value({key: value for key, value in extra.items() if key != "checkpoint_hash"})
        self.reject("ORCH_CHECKPOINT_NODE_SET_MISMATCH", lambda: validate_checkpoint(extra, request, dag))
        unknown = copy.deepcopy(checkpoint)
        unknown["events"][0]["node_id"] = "injected"
        unknown["checkpoint_hash"] = sha256_value({key: value for key, value in unknown.items() if key != "checkpoint_hash"})
        self.reject("ORCH_CHECKPOINT_EVENT_NODE_UNKNOWN", lambda: validate_checkpoint(unknown, request, dag))

    def test_checkpoint_rejects_fake_success_and_state_pair_tamper(self) -> None:
        request, dag = self.dag()
        runtime = OrchestrationRuntime(request, dag, executor=FakeExecutor())
        runtime.run(stop_after_nodes=1)
        fake = runtime.checkpoint()
        fake["states"]["child"] = "SUCCEEDED"
        fake["results"]["child"] = {"status": "SUCCEEDED", "result_hash": "a" * 64}
        fake["completed_result_hashes"]["child"] = "a" * 64
        fake["completed_hash"] = sha256_value(fake["completed_result_hashes"])
        fake["checkpoint_hash"] = sha256_value({key: value for key, value in fake.items() if key != "checkpoint_hash"})
        self.reject("ORCH_CHECKPOINT_EVENT_STATE_MISMATCH", lambda: validate_checkpoint(fake, request, dag))
        changed = copy.deepcopy(runtime.checkpoint())
        changed["execution_identity"]["dag_hash"] = "b" * 64
        changed["checkpoint_hash"] = sha256_value({key: value for key, value in changed.items() if key != "checkpoint_hash"})
        self.reject("ORCH_CHECKPOINT_IDENTITY_MISMATCH", lambda: validate_checkpoint(changed, request, dag))

    def test_cross_runtime_idempotency_reuses_only_success(self) -> None:
        request, dag = self.dag()
        store = BoundedExecutionStore()
        coordinator = ExecutionCoordinator(store)
        first = coordinator.execute(OrchestrationRuntime(request, dag, executor=FakeExecutor()))
        second_executor = FakeExecutor()
        second = coordinator.execute(OrchestrationRuntime(request, dag, executor=second_executor))
        self.assertEqual(first["status"], "EXECUTED")
        self.assertEqual(second["status"], "REUSED")
        self.assertEqual(second_executor.executions, 0)
        changed_request = make_request(idempotency_key=request["idempotency_key"], timeout=31)
        _, changed_dag = self.dag(changed_request)
        self.reject("ORCH_IDEMPOTENCY_CONFLICT", lambda: coordinator.execute(OrchestrationRuntime(changed_request, changed_dag)))

    def test_failed_execution_is_not_reused_as_success(self) -> None:
        request, dag = self.dag(request=make_request(timeout=5), nodes=[make_node("bad")])
        store = BoundedExecutionStore()
        coordinator = ExecutionCoordinator(store)
        failed = coordinator.execute(OrchestrationRuntime(request, dag), faults={"bad": "nonretryable"})
        retry = coordinator.execute(OrchestrationRuntime(request, dag))
        self.assertEqual(failed["status"], "EXECUTED")
        self.assertEqual(retry["status"], "EXECUTED")

    def test_idempotency_store_capacity_fails_closed(self) -> None:
        store = BoundedExecutionStore(max_records=1)
        coordinator = ExecutionCoordinator(store)
        request, dag = self.dag()
        coordinator.execute(OrchestrationRuntime(request, dag))
        second_request = make_request(request_id="request-0242-second", idempotency_key="idem-0242-second")
        _, second_dag = self.dag(second_request)
        self.reject("ORCH_IDEMPOTENCY_STORE_BOUNDS_EXCEEDED", lambda: coordinator.execute(OrchestrationRuntime(second_request, second_dag)))

    def test_circuit_breaker_open_and_single_half_open_probe(self) -> None:
        breaker = CircuitBreaker(failure_threshold=2)
        breaker.record_failure(); breaker.record_failure()
        self.assertEqual(breaker.state, "OPEN")
        self.assertFalse(breaker.allow())
        breaker.half_open()
        self.assertTrue(breaker.allow())
        self.assertFalse(breaker.allow())
        breaker.record_success()
        self.assertEqual(breaker.state, "CLOSED")

    def test_batch_scheduler_proves_global_and_family_peaks(self) -> None:
        request = make_request()
        nodes = [make_node("a", family="maps_minimap"), make_node("b", family="ui_asset_family"), make_node("c", family="maps_minimap"), make_node("d", family="vfx_asset_family")]
        _, dag = self.dag(request, nodes)
        proof = DeterministicBatchScheduler(dag, 3, {"maps_minimap": 1, "ui_asset_family": 2, "vfx_asset_family": 1}).plan()
        self.assertGreater(proof["peak_global"], 1)
        self.assertLessEqual(proof["family_peaks"]["maps_minimap"], 1)
        self.assertEqual(proof["dispatch_count"], 4)
        self.reject("ORCH_FAMILY_LIMIT_INVALID", lambda: validate_concurrency_limits(2, {"maps_minimap": 3}))

    def test_dependency_ref_is_byte_and_revision_bound(self) -> None:
        root = Path(__file__).resolve().parents[1]
        path = "docs/evidence/maps-minimap-runtime-v0213/map-contract-v0213.json"
        ref = build_dependency_ref(root, project_id="project-0242", family="maps_minimap", revision="v0.21.3", path=path, status="MERGED_CLOSED")
        resolved = resolve_dependency_ref(ref, root, expected_project_id="project-0242")
        self.assertEqual(resolved["resolved_content_hash"], ref["content_hash"])
        wrong = copy.deepcopy(ref); wrong["content_hash"] = "0" * 64
        self.reject("ORCH_DEPENDENCY_AUTHORITY_HASH_MISMATCH", lambda: resolve_dependency_ref(wrong, root, expected_project_id="project-0242"))
        unknown = copy.deepcopy(ref); unknown["unexpected"] = True
        self.reject("ORCH_UNKNOWN_FIELD", lambda: validate_dependency_ref(unknown))

    def test_provider_boundary_and_zero_spy_are_real_contracts(self) -> None:
        proof = assert_provider_boundary(Path(__file__).resolve().parents[1] / "src/ugas/orchestration_runtime_v0247.py")
        self.assertEqual(proof["status"], "PASS")
        self.assertEqual(len(provider_spy_targets()), 2)
        self.assertEqual(validate_provider_spy_counts({target: 0 for target in provider_spy_targets()})["status"], "PASS")
        self.reject("ORCH_REAL_PROVIDER_SUBMIT_REJECTED", lambda: validate_provider_spy_counts({provider_spy_targets()[0]: 1}))

    def test_strict_gate_preserves_observed_type(self) -> None:
        observations = {gate_id: True for gate_id in HARD_GATE_IDS}
        evidence = evaluate_hard_gates(observations)
        self.assertTrue(evidence["overall_pass"])
        observations["provider_client_spy_zero"] = "true"
        negative = evaluate_hard_gates(observations)
        self.assertFalse(negative["overall_pass"])
        self.assertEqual(negative["gates"]["provider_client_spy_zero"]["observed_type"], "str")

    def test_f38_git_and_no_git_modes_share_binding_hash(self) -> None:
        from ugas.orchestration_runtime_v0247 import (
            APPROVED_AUTHORITY_REGISTRY,
            FROZEN_REGISTRY_WITNESS,
            GIT_COMMIT_WITNESS,
            build_governed_dependency_refs,
            git_object_witness_available,
            resolve_dependency_refs,
        )

        root = Path(__file__).resolve().parents[1]
        git_resolved = None
        if git_object_witness_available(root):
            git_refs = build_governed_dependency_refs(root, project_id="project-0244")
            git_resolved = resolve_dependency_refs(git_refs, root, expected_project_id="project-0244", require_approved_commit=True)
            self.assertEqual(git_resolved["verification_mode"], GIT_COMMIT_WITNESS)
        with tempfile.TemporaryDirectory(prefix="ugas-f38-nogit-") as directory:
            dest = Path(directory)
            for entry in APPROVED_AUTHORITY_REGISTRY.values():
                source = root / entry["path"]
                target = dest / entry["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            no_git_refs = build_governed_dependency_refs(dest, project_id="project-0244")
            frozen = resolve_dependency_refs(no_git_refs, dest, expected_project_id="project-0244", require_approved_commit=True)
            self.assertEqual(frozen["verification_mode"], FROZEN_REGISTRY_WITNESS)
            self.assertFalse(git_object_witness_available(dest))
            if git_resolved is not None:
                self.assertEqual(frozen["authority_binding_hash"], git_resolved["authority_binding_hash"])

    def test_f38_git_missing_object_does_not_fallback(self) -> None:
        import subprocess
        from ugas.orchestration_runtime_v0247 import (
            APPROVED_AUTHORITY_REGISTRY,
            build_governed_dependency_refs,
            git_object_witness_available,
            resolve_dependency_refs,
        )

        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="ugas-f38-emptygit-") as directory:
            empty = Path(directory)
            subprocess.run(["git", "init"], cwd=empty, check=True, capture_output=True)
            for entry in APPROVED_AUTHORITY_REGISTRY.values():
                source = root / entry["path"]
                target = empty / entry["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            self.assertTrue(git_object_witness_available(empty))
            refs = build_governed_dependency_refs(empty, project_id="project-0244")
            self.reject("ORCH_DEPENDENCY_AUTHORITY_COMMIT_MISSING", lambda: resolve_dependency_refs(refs, empty, expected_project_id="project-0244", require_approved_commit=True))

    def test_f37r_public_historical_validator_rejects_mismatch(self) -> None:
        from ugas.orchestration_runtime_v0247 import compare_historical_evidence_tree

        root = Path(__file__).resolve().parents[1]
        if not (root / ".git").exists():
            self.skipTest("official no-git snapshot has no git metadata; F-37R is proved by the git-backed runner")
        proof = compare_historical_evidence_tree(root, "ed9fa927fd50193130b3e085ef077dea267f2790", ["REVIEW-v0.24.1.md", "docs/evidence/orchestration-runtime-v0241"], label="v0241-positive")
        self.assertEqual(proof["status"], "PASS")
        self.assertEqual(proof["differences"], [])
        self.assertTrue(proof["equality"])
        self.assertEqual(proof["authority_fingerprint"], proof["observed_fingerprint"])
        self.assertNotIn("authority_tree", proof)
        self.assertNotIn("observed_tree", proof)
        self.reject("HISTORICAL_REF_UNRESOLVED", lambda: compare_historical_evidence_tree(root, "0" * 40, ["REVIEW-v0.24.1.md"], label="v0241-unresolved"))
        self.reject("HISTORICAL_ROOT_EMPTY", lambda: compare_historical_evidence_tree(root, "ed9fa927fd50193130b3e085ef077dea267f2790", ["docs/evidence/does-not-exist-v0247"], label="v0241-missing-root"))

    def test_f41_status_must_equal_canonical_registry(self) -> None:
        from ugas.orchestration_runtime_v0247 import (
            APPROVED_AUTHORITY_REGISTRY,
            build_dependency_ref,
            build_governed_dependency_refs,
            resolve_dependency_ref,
        )

        root = Path(__file__).resolve().parents[1]
        maps = APPROVED_AUTHORITY_REGISTRY["maps_minimap"]
        built = build_dependency_ref(root, project_id="project-0245", family="maps_minimap", revision=maps["revision"], path=maps["path"])
        self.assertEqual(built["status"], maps["status"])
        self.assertEqual(maps["status"], "MERGED_CLOSED")
        refs = build_governed_dependency_refs(root, project_id="project-0245")
        mutated = dict(refs[0]); mutated["status"] = "APPROVED_FOUNDATION"
        self.reject("ORCH_DEPENDENCY_AUTHORITY_STATUS_MISMATCH", lambda: resolve_dependency_ref(mutated, root, expected_project_id="project-0245"))
        items = APPROVED_AUTHORITY_REGISTRY["items_props"]
        items_ref = build_dependency_ref(root, project_id="project-0245", family="items_props", revision=items["revision"], path=items["path"])
        self.assertEqual(items_ref["status"], "APPROVED_FOUNDATION")
        items_mutated = dict(items_ref); items_mutated["status"] = "MERGED_CLOSED"
        self.reject("ORCH_DEPENDENCY_AUTHORITY_STATUS_MISMATCH", lambda: resolve_dependency_ref(items_mutated, root, expected_project_id="project-0245"))

    def test_f42_mode_and_type_identity_are_compared(self) -> None:
        from ugas.orchestration_runtime_v0247 import diff_historical_entry_sets

        blob = {"mode": "100644", "type": "blob", "object_id": "a" * 40, "path": "REVIEW-v0.24.1.md"}
        chmod_only = {"mode": "100755", "type": "blob", "object_id": "a" * 40, "path": "REVIEW-v0.24.1.md"}
        symlink = {"mode": "120000", "type": "blob", "object_id": "a" * 40, "path": "REVIEW-v0.24.1.md"}
        tree = {"mode": "040000", "type": "tree", "object_id": "b" * 40, "path": "REVIEW-v0.24.1.md"}
        mode_diff = diff_historical_entry_sets([blob], [chmod_only])
        self.assertEqual(mode_diff[0]["reason"], "mode_mismatch")
        symlink_diff = diff_historical_entry_sets([blob], [symlink])
        self.assertEqual(symlink_diff[0]["reason"], "mode_mismatch")
        type_diff = diff_historical_entry_sets([blob], [tree])
        self.assertEqual(type_diff[0]["reason"], "type_mismatch")

    def test_f39_stale_gate_fails_state_consistency(self) -> None:
        import json
        from ugas.state_consistency_v0247 import CURRENT_GATE, validate_state_consistency

        root = Path(__file__).resolve().parents[1]
        state = json.loads((root / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        checkpoint = (root / "CHECKPOINT.md").read_text(encoding="utf-8")
        roadmap = (root / "docs/roadmap.md").read_text(encoding="utf-8")
        matrix = json.loads((root / "docs/ugas-v1-capability-matrix.json").read_text(encoding="utf-8"))
        binding = {"base_main_sha": "dee98f8cd89ebd83a36ead7a22a184700d6e916f", "reviewed_head": "cdc49dd96e7c683c0426d209e0bef162442a3bbb", "status": "CORRECTION_REQUIRED"}
        self.assertEqual(state["current_gate"], CURRENT_GATE)
        self.assertNotIn("ORCHESTRATION_RUNTIME_HARDENING_F31R_F36_CORRECTION_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED", CURRENT_GATE)
        ok = validate_state_consistency(state, checkpoint, roadmap, matrix, binding, state.get("evidence", {}))
        self.assertEqual(ok["status"], CURRENT_GATE)
        self.assertEqual(ok["failures"], [])
        stale = copy.deepcopy(state)
        stale["current_gate"] = "ORCHESTRATION_RUNTIME_HARDENING_F31R_F36_CORRECTION_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED"
        failed = validate_state_consistency(stale, checkpoint, roadmap, matrix, binding, stale.get("evidence", {}))
        self.assertEqual(failed["status"], "ORCHESTRATION_STATE_FAILED")
        self.assertIn("current_gate_invalid", failed["failures"])
        stale_version = copy.deepcopy(state)
        stale_version["version"] = "0.24.3"
        version_failed = validate_state_consistency(stale_version, checkpoint, roadmap, matrix, binding, stale_version.get("evidence", {}))
        self.assertEqual(version_failed["status"], "ORCHESTRATION_STATE_FAILED")
        self.assertIn("version_invalid", version_failed["failures"])

    def test_f39r_approval_binding_drives_governed_merge_state(self) -> None:
        import json
        from ugas.state_consistency_v0247 import APPROVAL_AUTHORIZATION, APPROVAL_COMMENT_ID, APPROVAL_RECORD, APPROVED_SEMANTIC_HEAD, CURRENT_GATE, validate_state_consistency

        root = Path(__file__).resolve().parents[1]
        state = json.loads((root / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        checkpoint = (root / "CHECKPOINT.md").read_text(encoding="utf-8")
        roadmap = (root / "docs/roadmap.md").read_text(encoding="utf-8")
        matrix = json.loads((root / "docs/ugas-v1-capability-matrix.json").read_text(encoding="utf-8"))
        binding = {"base_main_sha": "dee98f8cd89ebd83a36ead7a22a184700d6e916f", "reviewed_head": "cdc49dd96e7c683c0426d209e0bef162442a3bbb", "status": "CORRECTION_REQUIRED"}
        self.assertEqual(state["review"]["merge_authorization"], APPROVAL_AUTHORIZATION)
        self.assertEqual(state["review"]["approved_semantic_head"], APPROVED_SEMANTIC_HEAD)
        self.assertEqual(state["review"]["approval_comment_id"], APPROVAL_COMMENT_ID)
        self.assertEqual(state["review"]["approval_record"], APPROVAL_RECORD)
        ok = validate_state_consistency(state, checkpoint, roadmap, matrix, binding, state.get("evidence", {}))
        self.assertEqual(ok["status"], CURRENT_GATE)
        self.assertEqual(ok["failures"], [])
        tampered_authorization = copy.deepcopy(state)
        tampered_authorization["review"]["merge_authorization"] = "MERGE_IMMEDIATELY"
        authorization_failed = validate_state_consistency(tampered_authorization, checkpoint, roadmap, matrix, binding, tampered_authorization.get("evidence", {}))
        self.assertEqual(authorization_failed["status"], "ORCHESTRATION_STATE_FAILED")
        self.assertIn("review:merge_authorization", authorization_failed["failures"])
        tampered_binding = copy.deepcopy(state)
        tampered_binding["review"]["approval_comment_id"] = 0
        binding_failed = validate_state_consistency(tampered_binding, checkpoint, roadmap, matrix, binding, tampered_binding.get("evidence", {}))
        self.assertEqual(binding_failed["status"], "ORCHESTRATION_STATE_FAILED")
        self.assertIn("review:approval_binding", binding_failed["failures"])
        tampered_transition = copy.deepcopy(state)
        tampered_transition["evidence"]["approval_transition"] = "docs/evidence/github-governance-v0247/missing.json"
        transition_failed = validate_state_consistency(tampered_transition, checkpoint, roadmap, matrix, binding, tampered_transition.get("evidence", {}))
        self.assertEqual(transition_failed["status"], "ORCHESTRATION_STATE_FAILED")
        self.assertIn("evidence_root_invalid", transition_failed["failures"])

    def test_f43r_sanitize_uads_handoff_is_fail_closed(self) -> None:
        valid = {
            "work_order_id": "wo_22268aa2ff8736ca",
            "run_or_dispatch_id": "er_eda99105fa43d383",
            "route_status": "SELECTED",
            "selected_profile_id": "codex-global-strong-v1",
            "selected_profile_digest_unavailable_reason": "UADS model execution plan does not expose a profile digest",
            "dispatch_status": "DISPATCHED",
            "execution_mode": "GLOBAL_FIRST",
            "project_footprint": "ZERO",
        }
        sanitized = sanitize_uads_handoff(valid)
        self.assertEqual(sanitized["route_status"], "SELECTED")
        self.assertEqual(sanitized["dispatch_status"], "DISPATCHED")
        self.assertEqual(len(HARD_GATE_IDS), 64)
        self.assertIn("uads_global_first_mode", HARD_GATE_IDS)
        self.assertIn("artifact_inventory_consistent", HARD_GATE_IDS)
        self.assertIn("artifact_single_self_attestation", HARD_GATE_IDS)
        blocked = dict(valid)
        blocked["route_status"] = "BLOCKED"
        self.reject("ORCH_UADS_ROUTE_STATUS_REJECTED", lambda: sanitize_uads_handoff(blocked))
        unknown = dict(valid)
        unknown["route_status"] = "UNKNOWN"
        self.reject("ORCH_UADS_ROUTE_STATUS_REJECTED", lambda: sanitize_uads_handoff(unknown))
        not_dispatched = dict(valid)
        not_dispatched["dispatch_status"] = "NOT_DISPATCHED"
        self.reject("ORCH_UADS_DISPATCH_STATUS_REJECTED", lambda: sanitize_uads_handoff(not_dispatched))
        path_like = dict(valid)
        path_like["work_order_id"] = "~/wo_secret"
        self.reject("ORCH_UADS_HANDOFF_PATH_REJECTED", lambda: sanitize_uads_handoff(path_like))
        missing_profile = dict(valid)
        missing_profile.pop("selected_profile_id")
        self.reject("ORCH_UADS_HANDOFF_INVALID", lambda: sanitize_uads_handoff(missing_profile))

    def test_f44r_rejects_malformed_terminal_summary(self) -> None:
        import importlib.util
        path = Path(__file__).resolve().parents[1] / "scripts/validation/record_orchestration_results_v0247.py"
        spec = importlib.util.spec_from_file_location("record_orchestration_results_v0247", path)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
        nested = (
            "PASS snapshot:validation - SUMMARY checks=3044 passed=3044 failed=0\n"
            "PASS snapshot:no-git - SUMMARY checks=3044 passed=3044 failed=0\n"
            "SUMMARY checks=3050 passed=3050 failed=0\n"
        )
        selected = module.select_final_validation_summary(nested)
        self.assertEqual(selected["status"], "PASS")
        self.assertEqual(selected["checks"], 3050)
        self.assertEqual(selected["selected_summary_index"], 0)
        self.assertEqual(selected["summary_prefixed_count"], 1)
        self.assertEqual(selected["canonical_summary_count"], 1)
        self.assertEqual(selected["selected_terminal_line"], 2)
        malformed = module.select_final_validation_summary("SUMMARY checks=100 passed=100 failed=0\nSUMMARY checks=120 passed=120\n")
        self.assertEqual(malformed["status"], "FAIL")
        self.assertEqual(malformed["reason"], "MALFORMED_TERMINAL_SUMMARY")
        self.assertEqual(malformed["selected_summary_index"], 1)
        junk = module.select_final_validation_summary("SUMMARY checks=100 passed=100 failed=0\nSUMMARY checks=120 passed=120 failed=0 trailing\n")
        self.assertEqual(junk["status"], "FAIL")
        self.assertEqual(junk["reason"], "MALFORMED_TERMINAL_SUMMARY")
        embedded = module.select_final_validation_summary("nested text SUMMARY checks=120 passed=120 failed=0 inside a line\n")
        self.assertEqual(embedded["status"], "FAIL")
        self.assertEqual(embedded["reason"], "NO_FINAL_SUMMARY")
        early_fail_final_pass = module.select_final_validation_summary("SUMMARY checks=100 passed=90 failed=10\nSUMMARY checks=120 passed=120 failed=0\n")
        self.assertEqual(early_fail_final_pass["status"], "PASS")
        self.assertEqual(early_fail_final_pass["checks"], 120)
        missing = module.select_final_validation_summary("official validation started\n")
        self.assertEqual(missing["status"], "FAIL")
        self.assertEqual(missing["reason"], "NO_FINAL_SUMMARY")

    def test_f45_canonical_correction_history_mismatch_fails(self) -> None:
        canonical = {
            "status": "CORRECTION_REQUIRED",
            "rejected_reviewed_head": "cdc49dd96e7c683c0426d209e0bef162442a3bbb",
            "findings": ["F-44R", "F-46R"],
            "historical_evidence_unchanged": True,
        }
        matched = validate_canonical_correction_history(canonical, canonical)
        self.assertEqual(matched["status"], "PASS")
        stale = dict(canonical)
        stale["findings"] = ["F-43R", "F-44", "F-45", "F-46"]
        self.reject("ORCH_CORRECTION_HISTORY_MISMATCH", lambda: validate_canonical_correction_history(stale, canonical))
        wrong_head = dict(canonical)
        wrong_head["rejected_reviewed_head"] = "0" * 40
        self.reject("ORCH_CORRECTION_HISTORY_MISMATCH", lambda: validate_canonical_correction_history(wrong_head, canonical))

    def test_f46r_inventory_rejects_post_scan_mutation(self) -> None:
        import importlib.util
        import tempfile
        path = Path(__file__).resolve().parents[1] / "scripts/validation/validate_github_review_security_v0247.py"
        spec = importlib.util.spec_from_file_location("validate_github_review_security_v0247", path)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "REVIEW-v0.24.7.md").write_text("ok\n", encoding="utf-8")
            (root / "logs").mkdir()
            (root / "logs/ugas-tests.log").write_text("ok\n", encoding="utf-8")
            inventory = module.build_artifact_inventory(root, excluded_paths=(module.SELF_ATTESTATION,))
            (root / "logs/injected.txt").write_text("extra\n", encoding="utf-8")
            added = module.verify_artifact_inventory(root, inventory, excluded_paths=(module.SELF_ATTESTATION,))
            self.assertEqual(added["status"], "FAIL")
            self.assertEqual(added["reason"], "ARTIFACT_FILE_ADDED")
            (root / "logs/injected.txt").unlink()
            (root / module.SELF_ATTESTATION).write_text("{}\n", encoding="utf-8")
            positive = module.verify_artifact_inventory(root, inventory, excluded_paths=(module.SELF_ATTESTATION,))
            self.assertEqual(positive["status"], "PASS")
            self.assertEqual(positive["final_staged_file_count"], inventory["scanned_file_count"] + 1)
            multi = module.verify_artifact_inventory(root, inventory, excluded_paths=(module.SELF_ATTESTATION, "REVIEW-v0.24.7.md"))
            self.assertEqual(multi["status"], "FAIL")
            self.assertEqual(multi["reason"], "ARTIFACT_MULTI_SELF_EXCLUSION")


if __name__ == "__main__":
    unittest.main()
