"""Focused v0.24.4 correction tests with real negative paths."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from ugas.orchestration_runtime_v0244 import (
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
        "scheduling_key": "orchestration-v0244",
        "priority": priority,
        "asset_family": family,
    }


class OrchestrationRuntimev0244Tests(unittest.TestCase):
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
        proof = assert_provider_boundary(Path(__file__).resolve().parents[1] / "src/ugas/orchestration_runtime_v0244.py")
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
        from ugas.orchestration_runtime_v0244 import (
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
        from ugas.orchestration_runtime_v0244 import (
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
        from ugas.orchestration_runtime_v0244 import compare_historical_evidence_tree

        root = Path(__file__).resolve().parents[1]
        if not (root / ".git").exists():
            self.skipTest("official no-git snapshot has no git metadata; F-37R is proved by the git-backed runner")
        proof = compare_historical_evidence_tree(root, "ed9fa927fd50193130b3e085ef077dea267f2790", ["REVIEW-v0.24.1.md", "docs/evidence/orchestration-runtime-v0241"], label="v0241-positive")
        self.assertEqual(proof["status"], "PASS")
        self.assertEqual(proof["differences"], [])
        empty_tree = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        self.reject("HISTORICAL_TREE_MISMATCH", lambda: compare_historical_evidence_tree(root, empty_tree, ["REVIEW-v0.24.1.md"], label="v0241-empty-tree"))

    def test_f39_stale_gate_fails_state_consistency(self) -> None:
        import json
        import subprocess
        from ugas.state_consistency_v0244 import CURRENT_GATE, validate_state_consistency

        root = Path(__file__).resolve().parents[1]
        state = json.loads((root / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        checkpoint = (root / "CHECKPOINT.md").read_text(encoding="utf-8")
        roadmap = (root / "docs/roadmap.md").read_text(encoding="utf-8")
        matrix = json.loads((root / "docs/ugas-v1-capability-matrix.json").read_text(encoding="utf-8"))
        if state.get("version") != "0.24.4":
            if not (root / ".git").exists():
                self.skipTest("official no-git snapshot has no frozen v0.24.4 tree; F-39 live proof is v0.24.5")
            frozen_ref = "0c5226fcaaf90e0ddc5131749976afb6d6dd3153"

            def _frozen(path: str) -> str:
                result = subprocess.run(["git", "show", f"{frozen_ref}:{path}"], cwd=root, check=True, capture_output=True)
                return result.stdout.decode("utf-8")

            state = json.loads(_frozen("docs/evidence/current-state.json"))
            checkpoint = _frozen("CHECKPOINT.md")
            roadmap = _frozen("docs/roadmap.md")
            matrix = json.loads(_frozen("docs/ugas-v1-capability-matrix.json"))
        binding = {"base_main_sha": "dee98f8cd89ebd83a36ead7a22a184700d6e916f", "reviewed_head": "5a619c0b98ced7e4c09afd9ca117a039f0d5d068", "status": "CORRECTION_REQUIRED"}
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


if __name__ == "__main__":
    unittest.main()
