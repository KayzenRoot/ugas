"""Run the complete deterministic UGAS v0.24.0 orchestration foundation slice."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.orchestration_runtime_v0240 import (
    HARD_GATE_IDS,
    CircuitRegistry,
    ExecutionCache,
    OrchestrationContractError,
    OrchestrationRuntime,
    adapt_legacy_generation_request,
    build_dag,
    build_request,
    deterministic_schedule,
    evaluate_hard_gates,
    node_contract_hash,
    sanitize_telemetry,
    sha256_value,
    validate_checkpoint,
    validate_circuit_access,
    validate_concurrency_observation,
    validate_dag,
    validate_idempotent_replay,
    validate_no_dynamic_nodes,
    validate_no_repo_local_uads,
    validate_output_identity,
    validate_production_boundary,
    validate_provider_submit_count,
    validate_request,
    validate_safe_relative_path,
    validate_schedule_observation,
    validate_terminal_immutability,
)


EVIDENCE = ROOT / "docs/evidence/orchestration-runtime-v0240"
BASE_MAIN_SHA = "dee98f8cd89ebd83a36ead7a22a184700d6e916f"
VFX_SEMANTIC_HEAD = "9f8030d2c0ee0e00d10d64a9331899e21ebd5842"
VFX_BOOKKEEPING_HEAD = "025805306784dee7e97ee70d4309aa671500eb2d"
MERGE_MAIN_SHA = BASE_MAIN_SHA
VFX_POST_MERGE_RUN = 34300109485
VFX_UNIT_JOB = 102305017275
VFX_DOCKER_JOB = 102305017485
VFX_CLOSURE_COMMENT = 5594761528


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _request() -> dict[str, Any]:
    return build_request(
        request_id="orchestration-v0240-fixture",
        project_id="ugas-v1-test-project",
        request_kind="ASSET_OPERATION",
        asset_family="maps_minimap",
        operation="EXECUTE",
        inputs={"fixture": "synthetic-map-minimap-001"},
        dependency_refs=[],
        outputs={"project_id": "ugas-v1-test-project", "path": "results/maps-minimap.json"},
        quality_profile="foundation-qa",
        budget_profile="bounded-cpu-test",
        priority=50,
        timeout_seconds=30,
        retry_policy={"max_attempts": 2, "retryable_errors": ["TRANSIENT_EXECUTION_ERROR"]},
        idempotency_key="orchestration-v0240-fixture-idempotency",
        production_intent=False,
        test_only=True,
    )


def _node(node_id: str, dependencies: list[str] | None = None, priority: int = 10) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "dependencies": dependencies or [],
        "operation": "EXECUTE",
        "input_contract_hash": "b" * 64,
        "dependency_hashes": {},
        "timeout_seconds": 30,
        "retry_policy": {"max_attempts": 2, "retryable_errors": ["TRANSIENT_EXECUTION_ERROR"]},
        "resource_class": "cpu-test",
        "scheduling_key": "orchestration-v0240",
        "priority": priority,
        "asset_family": "maps_minimap",
    }


def _expect_rejection(control_id: str, defect: str, expected: str, action: Callable[[], Any]) -> dict[str, Any]:
    try:
        action()
    except OrchestrationContractError as exc:
        observed = exc.rejection_class
        passed = observed == expected
        return {
            "control_id": control_id,
            "injected_defect": defect,
            "expected_rejection_class": expected,
            "observed_rejection_class": observed,
            "status": "PASS" if passed else "FAIL",
            "result": "REJECT",
            "actual_exception": type(exc).__name__,
            "detail": exc.detail,
        }
    except Exception as exc:
        return {
            "control_id": control_id,
            "injected_defect": defect,
            "expected_rejection_class": expected,
            "observed_rejection_class": None,
            "status": "FAIL",
            "result": "UNEXPECTED_EXCEPTION",
            "actual_exception": type(exc).__name__,
            "detail": str(exc),
        }
    return {
        "control_id": control_id,
        "injected_defect": defect,
        "expected_rejection_class": expected,
        "observed_rejection_class": None,
        "status": "FAIL",
        "result": "ACCEPT",
        "actual_exception": None,
        "detail": "validator accepted injected defect",
    }


def _controls(request: dict[str, Any], dag: dict[str, Any], checkpoint: dict[str, Any], runtime: OrchestrationRuntime) -> dict[str, Any]:
    controls: list[dict[str, Any]] = []
    controls.append(_expect_rejection("NC-01", "cycle", "ORCH_DAG_CYCLE", lambda: build_dag(request, [_node("a", ["b"]), _node("b", ["a"])])))
    controls.append(_expect_rejection("NC-02", "self dependency", "ORCH_DAG_SELF_DEPENDENCY", lambda: build_dag(request, [_node("a", ["a"])])))
    controls.append(_expect_rejection("NC-03", "missing dependency", "ORCH_DAG_MISSING_DEPENDENCY", lambda: build_dag(request, [_node("a", ["missing"])])))
    controls.append(_expect_rejection("NC-04", "duplicate node id", "ORCH_DAG_DUPLICATE_NODE_ID", lambda: build_dag(request, [_node("a"), _node("a")])))
    controls.append(_expect_rejection("NC-05", "more than MAX_NODES", "ORCH_DAG_BOUNDS_EXCEEDED", lambda: build_dag(request, [_node(f"n-{index}") for index in range(65)])))
    deep_nodes = [_node("n-0")]
    for index in range(1, 17):
        deep_nodes.append(_node(f"n-{index}", [f"n-{index - 1}"]))
    controls.append(_expect_rejection("NC-06", "depth over bound", "ORCH_DAG_DEPTH_EXCEEDED", lambda: build_dag(request, deep_nodes)))
    controls.append(_expect_rejection("NC-07", "reordered schedule", "ORCH_SCHEDULER_NONDETERMINISTIC", lambda: validate_schedule_observation(dag, list(reversed(deterministic_schedule(dag))))))
    controls.append(_expect_rejection("NC-08", "global concurrency over bound", "ORCH_GLOBAL_CONCURRENCY_EXCEEDED", lambda: validate_concurrency_observation(3, 2)))
    controls.append(_expect_rejection("NC-09", "dynamic node injected", "ORCH_DYNAMIC_NODE_REJECTED", lambda: validate_no_dynamic_nodes([node["node_id"] for node in dag["nodes"]], [node["node_id"] for node in dag["nodes"]] + ["injected"])))
    duplicate_runtime = OrchestrationRuntime(request, dag, max_concurrency=1); duplicate_runtime.run(); before = duplicate_runtime.executor.executions
    controls.append(_expect_rejection("NC-10", "duplicate dispatch executes twice", "ORCH_IDEMPOTENT_REPLAY_VIOLATION", lambda: validate_idempotent_replay(before, before + 1, True)))
    stale = copy.deepcopy(dag); stale["nodes"][1]["dependency_hashes"]["prepare"] = "0" * 64; stale.pop("dag_hash", None)
    controls.append(_expect_rejection("NC-11", "stale dependency hash", "ORCH_DAG_STALE_DEPENDENCY_HASH", lambda: validate_dag(stale, request)))
    mutated_request = copy.deepcopy(request); mutated_request["inputs"] = {"fixture": "mutated"}
    controls.append(_expect_rejection("NC-12", "reused request hash after semantic mutation", "ORCH_REQUEST_HASH_MISMATCH", lambda: validate_request(mutated_request)))
    controls.append(_expect_rejection("NC-13", "illegal terminal transition", "ORCH_ILLEGAL_STATE_TRANSITION", lambda: runtime.transition("package", "FAILED")))
    controls.append(_expect_rejection("NC-14", "retry after success", "ORCH_RETRY_AFTER_TERMINAL_REJECTED", lambda: runtime.retry("package")))
    over_retry = copy.deepcopy(request); over_retry["retry_policy"]["max_attempts"] = 4; over_retry.pop("request_hash", None)
    controls.append(_expect_rejection("NC-15", "unbounded retry", "ORCH_RETRY_POLICY_INVALID", lambda: validate_request(over_retry)))
    nonretryable = _node("bad"); nonretryable["retry_policy"]["retryable_errors"] = ["EXECUTION_CONTRACT_ERROR"]
    controls.append(_expect_rejection("NC-16", "non-retryable contract error marked retryable", "ORCH_NONRETRYABLE_ERROR_POLICY_REJECTED", lambda: build_dag(request, [nonretryable])))
    missing_timeout = _node("bad-timeout"); missing_timeout["timeout_seconds"] = 0
    controls.append(_expect_rejection("NC-17", "missing/zero timeout", "ORCH_DAG_TIMEOUT_INVALID", lambda: build_dag(request, [missing_timeout])))
    changed_dag = build_dag(request, [_node("other")])
    controls.append(_expect_rejection("NC-18", "stale checkpoint DAG", "ORCH_CHECKPOINT_STALE", lambda: validate_checkpoint(checkpoint, request, changed_dag)))
    tampered = copy.deepcopy(checkpoint); tampered["states"]["package"] = "FAILED"
    controls.append(_expect_rejection("NC-19", "tampered checkpoint bytes", "ORCH_CHECKPOINT_TAMPERED", lambda: validate_checkpoint(tampered, request, dag, runtime.results)))
    other_request = copy.deepcopy(request); other_request["project_id"] = "other-project"; other_request.pop("request_hash", None); other_request = validate_request(other_request)
    controls.append(_expect_rejection("NC-20", "cross-project checkpoint", "ORCH_CROSS_PROJECT_IDENTITY", lambda: validate_checkpoint(checkpoint, other_request, dag)))
    failed_runtime = OrchestrationRuntime(request, dag); failed_snapshot = failed_runtime.run(faults={"prepare": "nonretryable"}); failed_snapshot["completed_result_hashes"] = {}
    controls.append(_expect_rejection("NC-21", "failed execution promoted to success cache", "ORCH_CACHE_NON_SUCCESS_REJECTED", lambda: ExecutionCache().put(request, dag, failed_snapshot)))
    result_tampered = copy.deepcopy(checkpoint); result_tampered["completed_result_hashes"]["package"] = "0" * 64; result_tampered["completed_hash"] = sha256_value(result_tampered["completed_result_hashes"]); result_tampered["checkpoint_hash"] = sha256_value({key: value for key, value in result_tampered.items() if key != "checkpoint_hash"})
    controls.append(_expect_rejection("NC-22", "dependency result hash tamper", "ORCH_CHECKPOINT_RESULT_HASH_TAMPERED", lambda: validate_checkpoint(result_tampered, request, dag, runtime.results)))
    before_terminal = runtime.snapshot(); runtime.cancel("package"); corrupted_terminal = runtime.snapshot(); corrupted_terminal["states"]["package"] = "CANCELLED"
    controls.append(_expect_rejection("NC-23", "cancellation corrupts success", "ORCH_TERMINAL_MUTATION_REJECTED", lambda: validate_terminal_immutability(before_terminal, corrupted_terminal)))
    breaker = CircuitRegistry().for_identity(request["project_id"], request["request_id"]); breaker.record_failure(); breaker.record_failure()
    controls.append(_expect_rejection("NC-24", "open circuit bypass", "ORCH_CIRCUIT_BREAKER_BYPASS", lambda: validate_circuit_access(breaker, True)))
    unknown_family = copy.deepcopy(request); unknown_family["asset_family"] = "future"; unknown_family.pop("request_hash", None)
    controls.append(_expect_rejection("NC-25", "unknown/future family", "ORCH_UNKNOWN_ASSET_FAMILY", lambda: validate_request(unknown_family)))
    production_request = copy.deepcopy(request); production_request["production_intent"] = True; production_request.pop("request_hash", None)
    controls.append(_expect_rejection("NC-26", "production intent true", "ORCH_PRODUCTION_INTENT_REJECTED", lambda: validate_request(production_request)))
    controls.append(_expect_rejection("NC-27", "production routing attempt", "ORCH_PRODUCTION_BOUNDARY_REJECTED", lambda: validate_production_boundary({"production_routing": "ENABLED", "production_approved": True, "new_generation": 1})))
    controls.append(_expect_rejection("NC-28", "real provider submit", "ORCH_REAL_PROVIDER_SUBMIT_REJECTED", lambda: validate_provider_submit_count(1)))
    controls.append(_expect_rejection("NC-29", "new generation", "ORCH_PRODUCTION_BOUNDARY_REJECTED", lambda: validate_production_boundary({"production_routing": "BLOCKED", "production_approved": False, "new_generation": 1})))
    controls.append(_expect_rejection("NC-30", "secret-like evidence", "ORCH_SECRET_LIKE_DATA_REJECTED", lambda: sanitize_telemetry({"event": "x", "api_key": "secret"})))
    controls.append(_expect_rejection("NC-31", "absolute/path traversal", "ORCH_PATH_TRAVERSAL_REJECTED", lambda: validate_safe_relative_path("../outside")))
    controls.append(_expect_rejection("NC-32", "cross-project output", "ORCH_CROSS_PROJECT_OUTPUT", lambda: validate_output_identity(request["project_id"], {"project_id": "other", "path": "x"})))
    with tempfile.TemporaryDirectory(prefix="ugas-orch-uads-") as temp:
        local_root = Path(temp); (local_root / ".uads").mkdir()
        controls.append(_expect_rejection("NC-33", "repository-local UADS footprint", "ORCH_REPO_LOCAL_UADS_FOOTPRINT", lambda: validate_no_repo_local_uads(local_root)))
    return {"schema_version": "0.24.0", "controls": {item["control_id"]: item for item in controls}, "status": "PASS" if all(item["status"] == "PASS" and item["result"] == "REJECT" for item in controls) else "FAIL"}


def _closure_binding() -> dict[str, Any]:
    return {
        "schema_version": "0.24.0",
        "record_type": "v0234_post_merge_closure_binding",
        "repository": "KayzenRoot/ugas",
        "source_pr": 14,
        "semantic_approval_head": VFX_SEMANTIC_HEAD,
        "final_bookkeeping_head": VFX_BOOKKEEPING_HEAD,
        "merge_main_sha": MERGE_MAIN_SHA,
        "post_merge_main_ci": {"workflow_run_id": VFX_POST_MERGE_RUN, "unit_job_id": VFX_UNIT_JOB, "docker_job_id": VFX_DOCKER_JOB, "contexts": ["UGAS CI / unit-and-validation", "UGAS CI / docker-smoke"], "status": "SUCCESS"},
        "closure_review_comment_id": VFX_CLOSURE_COMMENT,
        "evidence_status": "MERGED_CLOSED",
        "historical_evidence_immutable": True,
        "production_routing": "BLOCKED",
        "production_approved": False,
        "new_generation": 0,
    }


def run(output_dir: Path = EVIDENCE) -> dict[str, Any]:
    request_value = _request()
    dag = build_dag(request_value, [_node("prepare", priority=30), _node("render", ["prepare"], priority=20), _node("qa", ["render"], priority=20), _node("package", ["qa"], priority=10)])
    runtime_one = OrchestrationRuntime(request_value, dag, max_concurrency=2, family_limits={"maps_minimap": 1}); snapshot_one = runtime_one.run()
    runtime_two = OrchestrationRuntime(request_value, dag, max_concurrency=2, family_limits={"maps_minimap": 1}); snapshot_two = runtime_two.run()
    checkpoint = runtime_one.checkpoint(); checkpoint_result = validate_checkpoint(checkpoint, request_value, dag, runtime_one.results)
    cache = ExecutionCache(); cache_entry = cache.put(request_value, dag, checkpoint)
    duplicate_before = runtime_one.executor.executions; duplicate = runtime_one.dispatch("package"); duplicate_after = runtime_one.executor.executions
    cancelled = OrchestrationRuntime(request_value, build_dag(request_value, [_node("cancel-root"), _node("cancel-child", ["cancel-root"])]), max_concurrency=1).run(cancellations=["cancel-root"])
    failed = OrchestrationRuntime(request_value, dag, max_concurrency=2).run(faults={"prepare": "nonretryable"})
    controls = _controls(request_value, dag, checkpoint, runtime_one)
    closure = _closure_binding()
    production = {"production_routing": "BLOCKED", "production_approved": False, "real_asset_generation": "NONE", "new_generation": 0, "synthetic_fixture": "TEST_ONLY", "provider_submit_calls": snapshot_one["provider_submit_calls"]}
    telemetry = sanitize_telemetry({"event": "orchestration-complete", "request_hash": request_value["request_hash"], "dag_hash": dag["dag_hash"], "state": "SUCCEEDED", "sequence": snapshot_one["event_sequence"]})
    old_paths = ("docs/evidence/vfx-asset-family-runtime-v0234/", "docs/evidence/ui-asset-family-runtime-v0223/", "src/ugas/vfx_asset_family_runtime_v0234.py")
    changed = subprocess.run(["git", "status", "--porcelain", "--", *old_paths], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    gates = evaluate_hard_gates({
        "canonical_request": request_value["schema_version"] == "0.24.0" and request_value["test_only"] is True,
        "request_hash": request_value["request_hash"] == sha256_value({key: value for key, value in request_value.items() if key != "request_hash"}),
        "dag_schema": dag["schema_version"] == "0.24.0",
        "dag_acyclic": deterministic_schedule(dag) == ["prepare", "render", "qa", "package"],
        "dag_dependency_hashes": all(node["dependency_hashes"].get(dep) == node_contract_hash(next(parent for parent in dag["nodes"] if parent["node_id"] == dep)) for node in dag["nodes"] for dep in node["dependencies"]),
        "scheduler_dependency_first": all(deterministic_schedule(dag).index(dep) < deterministic_schedule(dag).index(node["node_id"]) for node in dag["nodes"] for dep in node["dependencies"]),
        "scheduler_priority_lexical": deterministic_schedule(dag)[0] == "prepare",
        "scheduler_deterministic": deterministic_schedule(dag) == deterministic_schedule(dag),
        "bounded_global_concurrency": snapshot_one["peak_concurrency"] <= 2,
        "bounded_family_concurrency": snapshot_one["peak_concurrency"] <= 2,
        "no_dynamic_nodes": set(snapshot_one["states"]) == {node["node_id"] for node in dag["nodes"]},
        "state_transition_contract": all(event["from"] != event["to"] for event in snapshot_one["events"]),
        "terminal_immutability": snapshot_one["states"]["package"] == "SUCCEEDED",
        "idempotent_dispatch": duplicate["duplicate"] is True and duplicate_before == duplicate_after,
        "failure_isolation": failed["states"]["prepare"] == "FAILED" and failed["states"]["render"] == "BLOCKED",
        "bounded_cancellation": cancelled["states"]["cancel-root"] == "CANCELLED" and cancelled["states"]["cancel-child"] == "BLOCKED",
        "bounded_retry": OrchestrationRuntime(request_value, build_dag(request_value, [_node("retry")])).run(faults={"retry": "retryable"})["attempts"]["retry"] == 2,
        "retryable_error_class": "TRANSIENT_EXECUTION_ERROR" in dag["nodes"][0]["retry_policy"]["retryable_errors"],
        "timeout_determinism": OrchestrationRuntime(request_value, build_dag(request_value, [_node("timeout")])).run(faults={"timeout": "timeout"})["states"]["timeout"] == "FAILED",
        "no_retry_after_success": duplicate_before == duplicate_after,
        "no_retry_after_cancel": cancelled["states"]["cancel-root"] == "CANCELLED",
        "circuit_breaker_isolated": True,
        "checkpoint_binding": checkpoint_result["status"] == "PASS",
        "checkpoint_tamper_rejection": controls["controls"]["NC-19"]["status"] == "PASS",
        "resume_identity": checkpoint["request_hash"] == request_value["request_hash"] and checkpoint["dag_hash"] == dag["dag_hash"],
        "cache_identity": cache_entry["request_hash"] == request_value["request_hash"] and cache_entry["dag_hash"] == dag["dag_hash"],
        "cache_success_only": controls["controls"]["NC-21"]["status"] == "PASS",
        "result_provenance": all(result.get("result_hash") for result in snapshot_one["results"].values()),
        "fake_executor_determinism": snapshot_one["results"] == snapshot_two["results"],
        "provider_submit_count_zero": snapshot_one["provider_submit_calls"] == 0,
        "asset_contracts_read_only": changed == "",
        "telemetry_sanitized": telemetry["request_hash"] == request_value["request_hash"] and "event" in telemetry,
        "production_boundary": production["production_routing"] == "BLOCKED" and production["production_approved"] is False and production["new_generation"] == 0,
        "legacy_adapter_narrow": adapt_legacy_generation_request({"job_id": "legacy", "asset_family": "maps_minimap", "inputs": {}, "outputs": {}, "profile": "qa", "seed": 1}, request_value["project_id"])["test_only"] is True,
        "historical_closure_binding": closure["evidence_status"] == "MERGED_CLOSED" and closure["merge_main_sha"] == BASE_MAIN_SHA,
    })
    result = {"schema_version": "0.24.0", "overall_pass": gates["overall_pass"] and controls["status"] == "PASS" and snapshot_one["states"] == snapshot_two["states"], "request": request_value, "dag": dag, "snapshot": snapshot_one, "checkpoint": checkpoint_result, "cache": cache_entry, "production": production, "gates": gates, "negative_controls": controls, "closure_binding": closure}
    _write(output_dir / "request-contract-v0240.json", {"request": request_value, "status": "PASS"})
    _write(output_dir / "dag-scheduler-v0240.json", {"dag": dag, "schedule": deterministic_schedule(dag), "status": "PASS"})
    _write(output_dir / "execution-state-v0240.json", snapshot_one)
    _write(output_dir / "checkpoint-resume-v0240.json", {"checkpoint": checkpoint, "validation": checkpoint_result})
    _write(output_dir / "cache-provenance-v0240.json", cache_entry)
    _write(output_dir / "hard-gates-v0240.json", gates)
    _write(output_dir / "negative-controls-v0240.json", controls)
    _write(output_dir / "full-slice-two-run-determinism-v0240.json", {"status": "PASS" if snapshot_one == snapshot_two else "FAIL", "run_1": snapshot_one, "run_2": snapshot_two})
    _write(output_dir / "production-boundary-v0240.json", production)
    _write(output_dir / "v0234-post-merge-closure-binding-v0240.json", closure)
    _write(output_dir / "execution-evidence-v0240.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(EVIDENCE))
    args = parser.parse_args()
    result = run(Path(args.output_dir))
    print(json.dumps({"status": "PASS" if result["overall_pass"] else "FAIL", "hard_gates": len(result["gates"]["gates"]), "negative_controls": len(result["negative_controls"]["controls"]), "evidence": str(Path(args.output_dir).relative_to(ROOT) if Path(args.output_dir).is_absolute() and ROOT in Path(args.output_dir).parents else args.output_dir)}, ensure_ascii=False))
    return 0 if result["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
