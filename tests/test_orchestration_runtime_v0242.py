"""Focused v0.24.2 correction tests with real negative paths."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from ugas.orchestration_runtime_v0242 import (
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
        "scheduling_key": "orchestration-v0242",
        "priority": priority,
        "asset_family": family,
    }


class OrchestrationRuntimeV0242Tests(unittest.TestCase):
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
        proof = assert_provider_boundary(Path(__file__).resolve().parents[1] / "src/ugas/orchestration_runtime_v0242.py")
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


if __name__ == "__main__":
    unittest.main()
