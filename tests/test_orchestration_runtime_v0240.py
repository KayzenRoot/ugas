"""Focused v0.24.0 orchestration contract and hardening tests."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from ugas.orchestration_runtime_v0240 import (
    HARD_GATE_IDS,
    CircuitRegistry,
    ExecutionCache,
    OrchestrationContractError,
    OrchestrationRuntime,
    adapt_legacy_generation_request,
    atomic_write_checkpoint,
    build_dag,
    build_request,
    deterministic_schedule,
    evaluate_hard_gates,
    sanitize_telemetry,
    strict_boolean_observation,
    validate_checkpoint,
    validate_dag,
    validate_output_identity,
    validate_request,
    validate_safe_relative_path,
)


def request() -> dict:
    return build_request(
        request_id="request-001",
        project_id="project-ugas-test",
        request_kind="ASSET_OPERATION",
        asset_family="maps_minimap",
        operation="EXECUTE",
        inputs={"fixture": "map-001"},
        dependency_refs=[],
        outputs={"path": "results/map.json", "project_id": "project-ugas-test"},
        quality_profile="qa",
        budget_profile="bounded",
        priority=50,
        timeout_seconds=30,
        retry_policy={"max_attempts": 2, "retryable_errors": ["TRANSIENT_EXECUTION_ERROR"]},
        idempotency_key="idem-001",
        production_intent=False,
        test_only=True,
    )


def raw_node(node_id: str, dependencies: list[str] | None = None, priority: int = 10) -> dict:
    return {
        "node_id": node_id,
        "dependencies": dependencies or [],
        "operation": "EXECUTE",
        "input_contract_hash": "a" * 64,
        "dependency_hashes": {},
        "timeout_seconds": 30,
        "retry_policy": {"max_attempts": 2, "retryable_errors": ["TRANSIENT_EXECUTION_ERROR", "TRANSIENT_EXECUTION_ERROR"]},
        "resource_class": "cpu-test",
        "scheduling_key": "maps-minimap",
        "priority": priority,
        "asset_family": "maps_minimap",
    }


class OrchestrationRuntimeV0240Tests(unittest.TestCase):
    def test_request_is_canonical_and_hash_bound(self) -> None:
        value = request()
        self.assertEqual(len(value["request_hash"]), 64)
        self.assertEqual(validate_request(value)["request_hash"], value["request_hash"])

    def test_request_rejects_unknown_field(self) -> None:
        value = request(); value["unexpected"] = True
        self._reject("ORCH_UNKNOWN_FIELD", lambda: validate_request(value))

    def test_request_rejects_production_intent(self) -> None:
        value = request(); value["production_intent"] = True
        self._reject("ORCH_PRODUCTION_INTENT_REJECTED", lambda: validate_request(value))

    def test_request_rejects_future_family(self) -> None:
        value = request(); value["asset_family"] = "future_family"
        self._reject("ORCH_UNKNOWN_ASSET_FAMILY", lambda: validate_request(value))

    def test_request_rejects_cross_project_reference(self) -> None:
        value = request(); value["dependency_refs"] = [{"project_id": "other", "ref_id": "x", "content_hash": "a" * 64}]
        self._reject("ORCH_CROSS_PROJECT_IDENTITY", lambda: validate_request(value))

    def test_dag_is_acyclic_and_dependency_hash_bound(self) -> None:
        dag = build_dag(request(), [raw_node("root"), raw_node("child", ["root"], priority=90)])
        self.assertEqual(deterministic_schedule(dag), ["root", "child"])
        self.assertEqual(validate_dag(dag, request())["dag_hash"], dag["dag_hash"])

    def test_dag_rejects_cycle(self) -> None:
        nodes = [raw_node("a", ["b"]), raw_node("b", ["a"])]
        self._reject("ORCH_DAG_CYCLE", lambda: build_dag(request(), nodes))

    def test_dag_rejects_self_dependency(self) -> None:
        self._reject("ORCH_DAG_SELF_DEPENDENCY", lambda: build_dag(request(), [raw_node("a", ["a"])]))

    def test_dag_rejects_missing_dependency(self) -> None:
        self._reject("ORCH_DAG_MISSING_DEPENDENCY", lambda: build_dag(request(), [raw_node("a", ["missing"])]))

    def test_dag_rejects_duplicate_node(self) -> None:
        self._reject("ORCH_DAG_DUPLICATE_NODE_ID", lambda: build_dag(request(), [raw_node("a"), raw_node("a")]))

    def test_dag_rejects_stale_dependency_hash(self) -> None:
        dag = build_dag(request(), [raw_node("root"), raw_node("child", ["root"])])
        dag["nodes"][1]["dependency_hashes"]["root"] = "0" * 64
        dag.pop("dag_hash", None)
        self._reject("ORCH_DAG_STALE_DEPENDENCY_HASH", lambda: validate_dag(dag, request()))

    def test_priority_and_lexical_tie_break_are_deterministic(self) -> None:
        dag = build_dag(request(), [raw_node("z", priority=10), raw_node("a", priority=10)])
        self.assertEqual(deterministic_schedule(dag), ["a", "z"])
        self.assertEqual(deterministic_schedule(dag), deterministic_schedule(dag))

    def test_runtime_success_is_provider_neutral_and_bounded(self) -> None:
        dag = build_dag(request(), [raw_node("root"), raw_node("child", ["root"])])
        runtime = OrchestrationRuntime(request(), dag, max_concurrency=1, family_limits={"maps_minimap": 1})
        snapshot = runtime.run()
        self.assertEqual(snapshot["states"], {"root": "SUCCEEDED", "child": "SUCCEEDED"})
        self.assertLessEqual(snapshot["peak_concurrency"], 1)
        self.assertEqual(snapshot["provider_submit_calls"], 0)

    def test_dispatch_is_idempotent_after_success(self) -> None:
        dag = build_dag(request(), [raw_node("root")])
        runtime = OrchestrationRuntime(request(), dag)
        runtime.run(); executions = runtime.executor.executions
        result = runtime.dispatch("root")
        self.assertTrue(result["duplicate"])
        self.assertEqual(runtime.executor.executions, executions)

    def test_failed_dependency_blocks_dependents(self) -> None:
        dag = build_dag(request(), [raw_node("root"), raw_node("child", ["root"])])
        runtime = OrchestrationRuntime(request(), dag)
        snapshot = runtime.run(faults={"root": "nonretryable"})
        self.assertEqual(snapshot["states"]["root"], "FAILED")
        self.assertEqual(snapshot["states"]["child"], "BLOCKED")

    def test_cancellation_is_bounded_and_blocks_dependents(self) -> None:
        dag = build_dag(request(), [raw_node("root"), raw_node("child", ["root"])])
        snapshot = OrchestrationRuntime(request(), dag).run(cancellations=["root"])
        self.assertEqual(snapshot["states"], {"root": "CANCELLED", "child": "BLOCKED"})

    def test_retry_is_bounded_and_timeout_is_typed(self) -> None:
        dag = build_dag(request(), [raw_node("root")])
        runtime = OrchestrationRuntime(request(), dag)
        snapshot = runtime.run(faults={"root": "retryable"})
        self.assertEqual(snapshot["states"]["root"], "SUCCEEDED")
        self.assertEqual(snapshot["attempts"]["root"], 2)
        timeout_runtime = OrchestrationRuntime(request(), dag)
        timeout_snapshot = timeout_runtime.run(faults={"root": "timeout"})
        self.assertEqual(timeout_snapshot["states"]["root"], "FAILED")

    def test_terminal_state_cannot_be_mutated_or_retried(self) -> None:
        dag = build_dag(request(), [raw_node("root")])
        runtime = OrchestrationRuntime(request(), dag); runtime.run()
        self._reject("ORCH_ILLEGAL_STATE_TRANSITION", lambda: runtime.transition("root", "FAILED"))

    def test_checkpoint_round_trip_and_atomic_write(self) -> None:
        dag = build_dag(request(), [raw_node("root")])
        runtime = OrchestrationRuntime(request(), dag); runtime.run()
        checkpoint = runtime.checkpoint()
        self.assertEqual(validate_checkpoint(checkpoint, request(), dag, runtime.results)["status"], "PASS")
        with tempfile.TemporaryDirectory() as directory:
            target = atomic_write_checkpoint(Path(directory) / "checkpoint.json", checkpoint)
            self.assertTrue(target.is_file())

    def test_checkpoint_rejects_tamper_and_stale_dag(self) -> None:
        dag = build_dag(request(), [raw_node("root")])
        runtime = OrchestrationRuntime(request(), dag); runtime.run()
        checkpoint = runtime.checkpoint(); checkpoint["states"]["root"] = "FAILED"
        self._reject("ORCH_CHECKPOINT_TAMPERED", lambda: validate_checkpoint(checkpoint, request(), dag, runtime.results))
        fresh = runtime.checkpoint(); changed = build_dag(request(), [raw_node("other")])
        self._reject("ORCH_CHECKPOINT_STALE", lambda: validate_checkpoint(fresh, request(), changed))

    def test_cache_accepts_only_success_and_preserves_source_identity(self) -> None:
        dag = build_dag(request(), [raw_node("root")])
        runtime = OrchestrationRuntime(request(), dag); runtime.run()
        cache = ExecutionCache(); entry = cache.put(request(), dag, runtime.checkpoint())
        self.assertEqual(cache.get(request(), dag)["source_execution_id"], entry["source_execution_id"])
        failed = OrchestrationRuntime(request(), dag).run(faults={"root": "nonretryable"})
        failed["completed_result_hashes"] = {}
        self._reject("ORCH_CACHE_NON_SUCCESS_REJECTED", lambda: cache.put(request(), dag, failed))

    def test_circuit_breakers_are_isolated_by_project_and_request(self) -> None:
        registry = CircuitRegistry(); first = registry.for_identity("p1", "r1"); second = registry.for_identity("p1", "r2")
        first.record_failure(); first.record_failure()
        self.assertEqual(first.state, "OPEN"); self.assertEqual(second.state, "CLOSED")

    def test_security_paths_outputs_and_telemetry_fail_closed(self) -> None:
        self._reject("ORCH_PATH_TRAVERSAL_REJECTED", lambda: validate_safe_relative_path("../secret"))
        self._reject("ORCH_ABSOLUTE_PATH_REJECTED", lambda: validate_safe_relative_path("C:\\secret\\file"))
        self._reject("ORCH_CROSS_PROJECT_OUTPUT", lambda: validate_output_identity("p1", {"project_id": "p2", "path": "x"}))
        self._reject("ORCH_SECRET_LIKE_DATA_REJECTED", lambda: sanitize_telemetry({"event": "x", "token": "bad"}))
        self._reject("ORCH_TELEMETRY_PATH_REJECTED", lambda: sanitize_telemetry({"event": "x", "request_hash": "C:\\secret"}))

    def test_legacy_adapter_is_narrow_and_test_only(self) -> None:
        value = adapt_legacy_generation_request({"job_id": "old-1", "asset_family": "maps_minimap", "inputs": {}, "outputs": {}, "profile": "qa", "seed": 1}, "p1")
        self.assertTrue(value["test_only"]); self.assertFalse(value["production_intent"])
        self._reject("ORCH_UNKNOWN_FIELD", lambda: adapt_legacy_generation_request({"provider_endpoint": "x"}, "p1"))

    def test_strict_gate_rejects_every_non_boolean_observation(self) -> None:
        for observed in (False, None, 0, 1, "", "true", [], [True], {}, {"ok": True}, object()):
            self.assertFalse(strict_boolean_observation(observed))
        self.assertTrue(strict_boolean_observation(True))

    def test_hard_gate_evidence_preserves_actual_types(self) -> None:
        evidence = evaluate_hard_gates({gate_id: True for gate_id in HARD_GATE_IDS})
        self.assertTrue(evidence["overall_pass"])
        self.assertEqual(len(evidence["gates"]), len(HARD_GATE_IDS))
        negative = evaluate_hard_gates({gate_id: (True if gate_id != "production_boundary" else "true") for gate_id in HARD_GATE_IDS})
        self.assertFalse(negative["overall_pass"])
        self.assertEqual(negative["gates"]["production_boundary"]["observed_type"], "str")

    def _reject(self, rejection_class: str, action) -> None:
        with self.assertRaises(OrchestrationContractError) as context:
            action()
        self.assertEqual(context.exception.rejection_class, rejection_class)


if __name__ == "__main__":
    unittest.main()
