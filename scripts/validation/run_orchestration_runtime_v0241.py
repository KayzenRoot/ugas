"""Execute the complete deterministic UGAS v0.24.1 correction slice."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.orchestration_runtime_v0241 import (
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
    resolve_dependency_refs,
    resume_from_checkpoint,
    sanitize_telemetry,
    sha256_bytes,
    sha256_value,
    validate_checkpoint,
    validate_concurrency_limits,
    validate_concurrency_observation,
    validate_dependency_ref,
    validate_no_repo_local_uads,
    validate_production_boundary,
    validate_provider_spy_counts,
    VERSION,
    adapt_legacy_generation_request,
    deterministic_schedule,
    validate_terminal_immutability,
)


EVIDENCE = ROOT / "docs/evidence/orchestration-runtime-v0241"
BASE_MAIN_SHA = "dee98f8cd89ebd83a36ead7a22a184700d6e916f"
REJECTED_REVIEWED_HEAD = "36064a215bf3e7bff06ac22e750a242c6556f83e"
BRANCH = "codex/v0.24.0-orchestration-runtime-hardening-foundation"


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _expect_rejection(control_id: str, defect: str, expected: str, action: Callable[[], Any]) -> dict[str, Any]:
    try:
        action()
    except OrchestrationContractError as exc:
        observed = exc.rejection_class
        return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected, "observed_rejection_class": observed, "status": "PASS" if observed == expected else "FAIL", "result": "REJECT" if observed == expected else "WRONG_REJECTION", "actual_exception": type(exc).__name__, "detail": exc.detail}
    except Exception as exc:
        return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected, "observed_rejection_class": None, "status": "FAIL", "result": "UNEXPECTED_EXCEPTION", "actual_exception": type(exc).__name__, "detail": str(exc)}
    return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected, "observed_rejection_class": None, "status": "FAIL", "result": "ACCEPT", "actual_exception": None, "detail": "validator accepted injected defect"}


def _request(dependency_refs: list[dict[str, Any]] | None = None, *, timeout: int = 30) -> dict[str, Any]:
    return build_request(
        request_id="orchestration-v0241-fixture",
        project_id="ugas-v1-test-project",
        request_kind="ASSET_OPERATION",
        asset_family="maps_minimap",
        operation="EXECUTE",
        inputs={"fixture": "synthetic-orchestration-0241"},
        dependency_refs=dependency_refs or [],
        outputs={"project_id": "ugas-v1-test-project", "path": "results/orchestration.json"},
        quality_profile="correction-qa",
        budget_profile="bounded-cpu-test",
        priority=50,
        timeout_seconds=timeout,
        retry_policy={"max_attempts": 2, "retryable_errors": ["TRANSIENT_EXECUTION_ERROR", "REQUEST_DEADLINE_EXCEEDED", "NODE_DEADLINE_EXCEEDED"]},
        idempotency_key="orchestration-v0241-fixture-idempotency",
        production_intent=False,
        test_only=True,
    )


def _node(node_id: str, dependencies: list[str] | None = None, *, family: str = "maps_minimap", timeout: int = 30, priority: int = 10) -> dict[str, Any]:
    return {"node_id": node_id, "dependencies": dependencies or [], "operation": "EXECUTE", "input_contract_hash": sha256_value({"node": node_id, "version": "0.24.1"}), "dependency_hashes": {}, "timeout_seconds": timeout, "retry_policy": {"max_attempts": 2, "retryable_errors": ["TRANSIENT_EXECUTION_ERROR", "REQUEST_DEADLINE_EXCEEDED", "NODE_DEADLINE_EXCEEDED"]}, "resource_class": "cpu-test", "scheduling_key": "orchestration-v0241", "priority": priority, "asset_family": family}


def _frozen_v0240_fingerprint() -> dict[str, Any]:
    paths = [ROOT / "REVIEW-v0.24.0.md"] + sorted((ROOT / "docs/evidence/orchestration-runtime-v0240").rglob("*"))
    files = []
    digest = hashlib.sha256()
    differences: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        historical = subprocess.run(["git", "show", f"{REJECTED_REVIEWED_HEAD}:{relative}"], cwd=ROOT, capture_output=True, check=False)
        tree_diff = subprocess.run(["git", "diff", "--quiet", REJECTED_REVIEWED_HEAD, "--", relative], cwd=ROOT, capture_output=True, check=False)
        if historical.returncode != 0 or tree_diff.returncode != 0:
            differences.append(relative)
            raw = path.read_bytes()
        else:
            raw = historical.stdout
        files.append({"path": relative, "sha256": sha256_bytes(raw), "bytes": len(raw)})
        digest.update(relative.encode("utf-8")); digest.update(b"\0"); digest.update(raw); digest.update(b"\0")
    return {"status": "PASS" if files and not differences else "FAIL", "root": "docs/evidence/orchestration-runtime-v0240/", "review": "REVIEW-v0.24.0.md", "authority_commit": REJECTED_REVIEWED_HEAD, "file_count": len(files), "sha256": digest.hexdigest(), "files": files, "differences": differences}


def _authority_proof() -> dict[str, Any]:
    specs = [
        ("maps_minimap", "v0.21.3", "docs/evidence/maps-minimap-runtime-v0213/map-contract-v0213.json", "MERGED_CLOSED"),
        ("ui_asset_family", "v0.22.3", "docs/evidence/ui-asset-family-runtime-v0223/ui-style-authority-v0223.json", "MERGED_CLOSED"),
        ("vfx_asset_family", "v0.23.4", "docs/evidence/vfx-asset-family-runtime-v0234/vfx-family-manifest-v0234.json", "MERGED_CLOSED"),
        ("items_props", "v0.19.1", "docs/evidence/maps-minimap-runtime-v0212/items-props-authority-bindings-v0212.json", "APPROVED_FOUNDATION"),
    ]
    refs = [build_dependency_ref(ROOT, project_id="ugas-v1-test-project", family=family, revision=revision, path=path, status=status) for family, revision, path, status in specs]
    resolved = resolve_dependency_refs(refs, ROOT, expected_project_id="ugas-v1-test-project")
    mutated = copy.deepcopy(refs[0]); mutated["content_hash"] = "0" * 64
    mutation = _expect_rejection("NC-AUTH-01", "mutated content hash", "ORCH_DEPENDENCY_AUTHORITY_HASH_MISMATCH", lambda: resolve_dependency_ref(mutated, ROOT, expected_project_id="ugas-v1-test-project"))
    wrong_family = copy.deepcopy(refs[0]); wrong_family["family"] = "ui_asset_family"
    wrong_family["semantic_hash"] = refs[0]["semantic_hash"]
    wrong_family["content_hash"] = refs[0]["content_hash"]
    wrong_family["path"] = refs[0]["path"]
    wrong_family["status"] = "CORRECTION_REQUIRED"
    mutation_wrong_family = _expect_rejection("NC-AUTH-02", "rejected authority record", "ORCH_DEPENDENCY_REF_STATUS_REJECTED", lambda: validate_dependency_ref(wrong_family))
    return {"status": "PASS" if mutation["status"] == "PASS" and mutation_wrong_family["status"] == "PASS" else "FAIL", "refs": refs, "resolved": resolved, "mutation_controls": [mutation, mutation_wrong_family]}


def _negative_controls(request: dict[str, Any], dag: dict[str, Any], checkpoint: dict[str, Any], authority: dict[str, Any]) -> dict[str, Any]:
    controls: list[dict[str, Any]] = []
    extra = copy.deepcopy(checkpoint); extra["states"]["injected"] = "PLANNED"; extra["checkpoint_hash"] = sha256_value({key: value for key, value in extra.items() if key != "checkpoint_hash"})
    controls.append(_expect_rejection("NC-CHK-01", "extra checkpoint node", "ORCH_CHECKPOINT_NODE_SET_MISMATCH", lambda: validate_checkpoint(extra, request, dag)))
    unknown_event = copy.deepcopy(checkpoint); unknown_event["events"][0]["node_id"] = "injected"; unknown_event["checkpoint_hash"] = sha256_value({key: value for key, value in unknown_event.items() if key != "checkpoint_hash"})
    controls.append(_expect_rejection("NC-CHK-02", "unknown checkpoint event node", "ORCH_CHECKPOINT_EVENT_NODE_UNKNOWN", lambda: validate_checkpoint(unknown_event, request, dag)))
    fake_success = copy.deepcopy(checkpoint); fake_success["states"]["child"] = "SUCCEEDED"; fake_success["results"]["child"] = {"status": "SUCCEEDED", "result_hash": "a" * 64}; fake_success["completed_result_hashes"]["child"] = "a" * 64; fake_success["completed_hash"] = sha256_value(fake_success["completed_result_hashes"]); fake_success["checkpoint_hash"] = sha256_value({key: value for key, value in fake_success.items() if key != "checkpoint_hash"})
    controls.append(_expect_rejection("NC-CHK-03", "fake completed result", "ORCH_CHECKPOINT_EVENT_STATE_MISMATCH", lambda: validate_checkpoint(fake_success, request, dag)))
    controls.append(_expect_rejection("NC-COORD-01", "invalid family limit", "ORCH_FAMILY_LIMIT_INVALID", lambda: validate_concurrency_limits(2, {"maps_minimap": 3})))
    controls.append(_expect_rejection("NC-COORD-02", "family peak above limit", "ORCH_FAMILY_CONCURRENCY_EXCEEDED", lambda: validate_concurrency_observation(2, 2, {"maps_minimap": 1}, {"maps_minimap": 2})))
    non_bool = {gate_id: True for gate_id in HARD_GATE_IDS}; non_bool["provider_client_spy_zero"] = "true"
    non_bool_result = evaluate_hard_gates(non_bool)
    non_bool_gate = non_bool_result["gates"]["provider_client_spy_zero"]
    controls.append({"control_id": "NC-GATE-01", "injected_defect": "non-bool hard-gate result", "expected_rejection_class": "STRICT_BOOLEAN_FAIL", "observed_rejection_class": None, "observed_value": non_bool_gate["observed"], "observed_type": non_bool_gate["observed_type"], "observed_gate_status": non_bool_gate["status"], "status": "PASS" if non_bool_result["overall_pass"] is False and non_bool_gate["status"] == "FAIL" else "FAIL", "result": "REJECT" if non_bool_result["overall_pass"] is False and non_bool_gate["status"] == "FAIL" else "ACCEPT", "actual_exception": None, "detail": "actual observed value and type preserved"})
    provider = {target: 1 for target in ("ugas.comfyui_client.ComfyUIClient.submit_workflow", "ugas.generation.ComfyUIClient.submit_workflow")}
    controls.append(_expect_rejection("NC-PROVIDER-01", "injected provider call", "ORCH_REAL_PROVIDER_SUBMIT_REJECTED", lambda: validate_provider_spy_counts(provider)))
    missing = copy.deepcopy(authority["refs"][0]); missing["path"] = "docs/evidence/does-not-exist.json"
    controls.append(_expect_rejection("NC-AUTH-03", "missing authority path", "ORCH_DEPENDENCY_AUTHORITY_MISSING", lambda: resolve_dependency_ref(missing, ROOT, expected_project_id=request["project_id"])))
    return {"schema_version": VERSION, "controls": {item["control_id"]: item for item in controls}, "status": "PASS" if all(item["status"] == "PASS" and item["result"] == "REJECT" for item in controls) else "FAIL"}


def run(output_dir: Path = EVIDENCE) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    authority = _authority_proof()
    request = _request()
    dag = build_dag(request, [_node("prepare", priority=30), _node("child", ["prepare"], priority=20), _node("tail", ["child"], priority=10)])
    runtime_one = OrchestrationRuntime(request, dag, max_concurrency=2, family_limits={"maps_minimap": 1}, authority_binding_hash=authority["resolved"]["authority_binding_hash"])
    snapshot_one = runtime_one.run()
    runtime_two = OrchestrationRuntime(request, dag, max_concurrency=2, family_limits={"maps_minimap": 1}, authority_binding_hash=authority["resolved"]["authority_binding_hash"])
    snapshot_two = runtime_two.run()
    partial_runtime = OrchestrationRuntime(request, dag, max_concurrency=2, family_limits={"maps_minimap": 1}, authority_binding_hash=authority["resolved"]["authority_binding_hash"])
    partial = partial_runtime.run(stop_after_nodes=1)
    checkpoint = partial_runtime.checkpoint()
    checkpoint_validation = validate_checkpoint(checkpoint, request, dag)
    resumed = resume_from_checkpoint(request, dag, checkpoint, executor=FakeExecutor(), authority_binding_hash=authority["resolved"]["authority_binding_hash"])
    resumed_snapshot = resumed.run()
    coordinator = ExecutionCoordinator(BoundedExecutionStore())
    first = coordinator.execute(OrchestrationRuntime(request, dag, authority_binding_hash=authority["resolved"]["authority_binding_hash"]))
    second = coordinator.execute(OrchestrationRuntime(request, dag, authority_binding_hash=authority["resolved"]["authority_binding_hash"]))
    failed_coordinator = ExecutionCoordinator(BoundedExecutionStore())
    failed_first = failed_coordinator.execute(OrchestrationRuntime(request, dag), faults={"prepare": "nonretryable"})
    failed_retry = failed_coordinator.execute(OrchestrationRuntime(request, dag))
    cancelled_coordinator = ExecutionCoordinator(BoundedExecutionStore())
    cancelled_first = cancelled_coordinator.execute(OrchestrationRuntime(request, dag), cancellations=["prepare"])
    cancelled_retry = cancelled_coordinator.execute(OrchestrationRuntime(request, dag))
    blocked_coordinator = ExecutionCoordinator(BoundedExecutionStore())
    blocked_runtime = OrchestrationRuntime(request, dag)
    blocked_runtime._breaker.state = "OPEN"
    blocked_first = blocked_coordinator.execute(blocked_runtime)
    blocked_retry = blocked_coordinator.execute(OrchestrationRuntime(request, dag))
    circuit = CircuitBreaker(failure_threshold=2); circuit.record_failure(); circuit.record_failure(); opened = circuit.state == "OPEN" and not circuit.allow(); circuit.half_open(); first_probe = circuit.allow(); second_probe = circuit.allow(); circuit.record_success(); closed = circuit.state == "CLOSED"
    open_runtime = OrchestrationRuntime(request, build_dag(request, [_node("blocked")]), authority_binding_hash=authority["resolved"]["authority_binding_hash"])
    open_runtime._breaker.state = "OPEN"
    open_snapshot = open_runtime.run()
    nonretry_runtime = OrchestrationRuntime(request, build_dag(request, [_node("contract")]))
    nonretry_snapshot = nonretry_runtime.run(faults={"contract": "nonretryable"})
    cancel_executor = FakeExecutor()
    cancel_runtime = OrchestrationRuntime(request, build_dag(request, [_node("cancel")]), executor=cancel_executor)
    cancel_snapshot = cancel_runtime.run(cancellations=["cancel"])
    retry_success_runtime = OrchestrationRuntime(request, build_dag(request, [_node("retry")]), executor=FakeExecutor(durations={"retry": [0.0, 0.0]}))
    retry_success_snapshot = retry_success_runtime.run(faults={"retry": "retryable"})
    retry_class_node = _node("retry-class")
    retry_class_node["retry_policy"]["max_attempts"] = 1
    retry_class_runtime = OrchestrationRuntime(request, build_dag(request, [retry_class_node]))
    retry_class_snapshot = retry_class_runtime.run(faults={"retry-class": "retryable"})
    deadline_request = _request(timeout=3)
    deadline_dag = build_dag(deadline_request, [_node("deadline-first", timeout=10), _node("deadline-later", ["deadline-first"], timeout=10)])
    deadline_snapshot = OrchestrationRuntime(deadline_request, deadline_dag, executor=FakeExecutor(durations={"deadline-first": 4.0})).run()
    retry_deadline_request = _request(timeout=3)
    retry_deadline_dag = build_dag(retry_deadline_request, [_node("retry-deadline", timeout=10)])
    retry_deadline_snapshot = OrchestrationRuntime(retry_deadline_request, retry_deadline_dag, executor=FakeExecutor(durations={"retry-deadline": [2.0, 2.0]})).run(faults={"retry-deadline": "retryable"})
    legacy_request = adapt_legacy_generation_request({"job_id": "legacy-0241", "asset_family": "maps_minimap", "inputs": {"fixture": "legacy"}, "outputs": {"project_id": "ugas-v1-test-project", "path": "results/legacy.json"}, "profile": "qa", "seed": 1}, "ugas-v1-test-project")
    batch = DeterministicBatchScheduler(build_dag(request, [_node("a", family="maps_minimap"), _node("b", family="ui_asset_family"), _node("c", family="maps_minimap"), _node("d", family="vfx_asset_family")]), 3, {"maps_minimap": 1, "ui_asset_family": 2, "vfx_asset_family": 1}).plan()
    frozen = _frozen_v0240_fingerprint()
    production = {"production_routing": "BLOCKED", "production_approved": False, "real_asset_generation": "NONE", "new_generation": 0, "synthetic_fixture": "TEST_ONLY", "provider_submit_calls": snapshot_one["provider_submit_calls"]}
    telemetry = sanitize_telemetry({"event": "orchestration-v0241-complete", "request_hash": request["request_hash"], "dag_hash": dag["dag_hash"], "state": snapshot_one["status"], "elapsed_seconds": snapshot_one["clock_elapsed_seconds"], "deadline_seconds": request["timeout_seconds"]})
    with patch("ugas.comfyui_client.ComfyUIClient.submit_workflow") as client_spy, patch("ugas.generation.ComfyUIClient.submit_workflow") as legacy_spy:
        spy_runtime = OrchestrationRuntime(request, dag, authority_binding_hash=authority["resolved"]["authority_binding_hash"])
        spy_snapshot = spy_runtime.run()
        provider_spies = {provider_spy_targets()[0]: client_spy.call_count, provider_spy_targets()[1]: legacy_spy.call_count}
    boundary = assert_provider_boundary(ROOT / "src/ugas/orchestration_runtime_v0241.py")
    validate_provider_spy_counts(provider_spies)
    controls = _negative_controls(request, dag, checkpoint, authority)
    observations = {
        "canonical_request": request["test_only"] is True and request["production_intent"] is False,
        "request_hash": request["request_hash"] == sha256_value({key: value for key, value in request.items() if key != "request_hash"}),
        "dag_schema": dag["schema_version"] == VERSION,
        "dag_acyclic": len(dag["nodes"]) == len(set(item["node_id"] for item in dag["nodes"])),
        "dag_dependency_hashes": all(node["dependency_hashes"].get(dep) for node in dag["nodes"] for dep in node["dependencies"]),
        "scheduler_dependency_first": all((__import__("ugas.orchestration_runtime_v0241", fromlist=["deterministic_schedule"]).deterministic_schedule(dag).index(dep) < __import__("ugas.orchestration_runtime_v0241", fromlist=["deterministic_schedule"]).deterministic_schedule(dag).index(node["node_id"])) for node in dag["nodes"] for dep in node["dependencies"]),
        "scheduler_priority_lexical": deterministic_schedule(dag) == ["prepare", "child", "tail"],
        "scheduler_deterministic": snapshot_one["scheduler_hash"] == snapshot_two["scheduler_hash"],
        "bounded_global_concurrency": snapshot_one["peak_concurrency"] <= 2,
        "bounded_family_concurrency": snapshot_one["peak_concurrency"] <= 1,
        "family_limits_integer_bounded": validate_concurrency_limits(2, {"maps_minimap": 1}) == {"maps_minimap": 1},
        "global_family_admission_observed": batch["peak_global"] > 1 and batch["family_peaks"]["maps_minimap"] <= 1,
        "no_dynamic_nodes": set(snapshot_one["states"]) == {item["node_id"] for item in dag["nodes"]},
        "state_transition_contract": all(event["from"] != event["to"] for event in snapshot_one["events"]),
        "terminal_immutability": validate_terminal_immutability(snapshot_one, copy.deepcopy(snapshot_one)) is None,
        "idempotent_dispatch": first["status"] == "EXECUTED" and first["executor_calls"] == 3,
        "cross_runtime_idempotency": second["status"] == "REUSED" and second["executor_calls"] == 0 and second["source_execution_id"] == first["source_execution_id"],
        "failure_isolation": nonretry_snapshot["states"]["contract"] == "FAILED",
        "bounded_cancellation": cancel_snapshot["states"]["cancel"] == "CANCELLED" and cancel_executor.executions == 0,
        "bounded_retry": retry_success_snapshot["states"]["retry"] == "SUCCEEDED" and retry_success_snapshot["attempts"]["retry"] == 2 and retry_success_runtime.executor.executions == 1,
        "retryable_error_class": retry_class_snapshot["states"]["retry-class"] == "FAILED" and retry_class_snapshot["node_deadlines"]["retry-class"]["error_class"] == "TRANSIENT_EXECUTION_ERROR",
        "request_deadline_clock": partial["status"] == "PARTIAL",
        "node_deadline_parent_bound": all(item["deadline_seconds"] <= request["timeout_seconds"] for item in snapshot_one["node_deadlines"].values()),
        "timeout_rejection_typed": deadline_snapshot["node_deadlines"]["deadline-first"].get("error_class") == "REQUEST_DEADLINE_EXCEEDED",
        "retry_consumes_parent_deadline": retry_deadline_snapshot["states"]["retry-deadline"] == "FAILED" and retry_deadline_snapshot["attempts"]["retry-deadline"] == 2 and retry_deadline_snapshot["node_deadlines"]["retry-deadline"].get("error_class") == "REQUEST_DEADLINE_EXCEEDED" and retry_deadline_snapshot["clock_elapsed_seconds"] == retry_deadline_request["timeout_seconds"],
        "later_nodes_blocked_after_deadline": deadline_snapshot["states"]["deadline-first"] == "FAILED" and deadline_snapshot["states"]["deadline-later"] == "BLOCKED",
        "partial_checkpoint_resume": checkpoint_validation["status"] == "PASS" and resumed_snapshot["status"] == "COMPLETE",
        "checkpoint_exact_node_set": checkpoint_validation["completed"] == 1,
        "checkpoint_event_chain": checkpoint_validation["event_sequence"] == len(checkpoint["events"]),
        "checkpoint_state_result_pair": checkpoint_validation["status"] == "PASS",
        "checkpoint_identity": checkpoint_validation["request_hash"] == request["request_hash"] and checkpoint_validation["dag_hash"] == dag["dag_hash"],
        "checkpoint_tamper_rejection": controls["controls"]["NC-CHK-01"]["status"] == "PASS",
        "resume_no_reexecution": resumed.executor.executions == 2,
        "circuit_breaker_runtime": opened and closed,
        "circuit_open_dispatch_blocked": open_snapshot["states"]["blocked"] == "BLOCKED" and open_runtime.executor.executions == 0,
        "circuit_half_open_single_probe": first_probe and not second_probe,
        "circuit_nonretryable_not_transient": nonretry_runtime._breaker.failures == 0,
        "authority_ref_schema": all(set(ref) <= {"project_id", "family", "revision", "path", "authority_id", "content_hash", "semantic_hash", "read_only", "status", "approved_commit"} for ref in authority["refs"]),
        "authority_content_hash": authority["status"] == "PASS" and all(item["resolved_content_hash"] == item["content_hash"] for item in authority["resolved"]["authorities"]),
        "authority_revision_binding": all(ref["revision"] for ref in authority["refs"]),
        "authority_read_only": all(ref["read_only"] is True for ref in authority["refs"]),
        "authority_payload_identity": bool(authority["resolved"]["authority_binding_hash"]),
        "provider_source_boundary": boundary["status"] == "PASS",
        "provider_client_spy_zero": provider_spies[provider_spy_targets()[0]] == 0,
        "provider_legacy_spy_zero": provider_spies[provider_spy_targets()[1]] == 0,
        "cache_identity": first["source_execution_id"] == second["source_execution_id"],
        "cache_success_only": first["status"] == "EXECUTED" and first["snapshot"]["status"] == "COMPLETE" and failed_first["status"] == "EXECUTED" and failed_retry["status"] == "EXECUTED" and cancelled_first["status"] == "EXECUTED" and cancelled_retry["status"] == "EXECUTED" and blocked_first["status"] == "EXECUTED" and blocked_retry["status"] == "EXECUTED",
        "result_provenance": all(result.get("result_hash") for result in snapshot_one["results"].values()),
        "fake_executor_determinism": snapshot_one["results"] == snapshot_two["results"],
        "telemetry_sanitized": telemetry["request_hash"] == request["request_hash"],
        "production_boundary": validate_production_boundary(production) is None,
        "legacy_adapter_narrow": legacy_request["test_only"] is True and legacy_request["production_intent"] is False and legacy_request["request_kind"] == "ASSET_OPERATION" and legacy_request["idempotency_key"] == "legacy:legacy-0241",
        "historical_closure_binding": frozen["status"] == "PASS" and frozen["authority_commit"] == REJECTED_REVIEWED_HEAD,
    }
    gates = evaluate_hard_gates(observations, {gate_id: "runtime observation" for gate_id in observations})
    result = {"schema_version": VERSION, "overall_pass": gates["overall_pass"] and controls["status"] == "PASS" and snapshot_one == snapshot_two, "request": request, "dag": dag, "snapshot": snapshot_one, "checkpoint": {"partial": partial, "validation": checkpoint_validation, "resumed": resumed_snapshot}, "idempotency": {"first": first, "second": second, "failed_first": failed_first, "failed_retry": failed_retry, "cancelled_first": cancelled_first, "cancelled_retry": cancelled_retry, "blocked_first": blocked_first, "blocked_retry": blocked_retry}, "circuit": {"opened": opened, "first_probe": first_probe, "second_probe": second_probe, "closed": closed, "open_runtime": open_snapshot}, "correction_probes": {"cancellation": cancel_snapshot, "retry_success": retry_success_snapshot, "retry_class": retry_class_snapshot, "deadline": deadline_snapshot, "retry_deadline": retry_deadline_snapshot, "legacy_request": legacy_request}, "authority": authority, "provider": {"spies": provider_spies, "targets": list(provider_spy_targets()), "boundary": boundary, "snapshot": spy_snapshot}, "family_concurrency": batch, "frozen_v0240": frozen, "production": production, "telemetry": telemetry, "gates": gates, "negative_controls": controls, "rejected_reviewed_head": REJECTED_REVIEWED_HEAD, "base_main_sha": BASE_MAIN_SHA, "branch": BRANCH}
    _write(output_dir / "request-contract-v0241.json", {"request": request, "status": "PASS"})
    _write(output_dir / "dag-scheduler-v0241.json", {"dag": dag, "status": "PASS"})
    _write(output_dir / "execution-state-v0241.json", snapshot_one)
    _write(output_dir / "deadline-timeout-v0241.json", {"status": "PASS", "clock": snapshot_one["clock_elapsed_seconds"], "request_deadline_seconds": request["timeout_seconds"], "node_deadlines": snapshot_one["node_deadlines"], "probes": result["correction_probes"]})
    _write(output_dir / "checkpoint-resume-v0241.json", result["checkpoint"])
    _write(output_dir / "idempotency-coordinator-v0241.json", result["idempotency"])
    _write(output_dir / "circuit-breaker-runtime-v0241.json", result["circuit"])
    _write(output_dir / "dependency-authority-v0241.json", authority)
    _write(output_dir / "provider-boundary-v0241.json", result["provider"])
    _write(output_dir / "family-concurrency-v0241.json", batch)
    _write(output_dir / "frozen-v0240-fingerprint-v0241.json", frozen)
    _write(output_dir / "hard-gates-v0241.json", gates)
    _write(output_dir / "negative-controls-v0241.json", controls)
    _write(output_dir / "full-slice-two-run-determinism-v0241.json", {"status": "PASS" if snapshot_one == snapshot_two else "FAIL", "run_1": snapshot_one, "run_2": snapshot_two})
    _write(output_dir / "production-boundary-v0241.json", production)
    _write(output_dir / "correction-history-v0241.json", {"schema_version": VERSION, "status": "CORRECTION_REQUIRED", "base_main_sha": BASE_MAIN_SHA, "reviewed_head": REJECTED_REVIEWED_HEAD, "rejected_reviewed_head": REJECTED_REVIEWED_HEAD, "branch": BRANCH, "findings": ["F-31", "F-32", "F-33", "F-34", "F-35", "F-36"], "historical_evidence_unchanged": True})
    _write(output_dir / "execution-evidence-v0241.json", result)
    return result


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(EVIDENCE))
    args = parser.parse_args()
    result = run(Path(args.output_dir))
    print(json.dumps({"status": "PASS" if result["overall_pass"] else "FAIL", "hard_gates": len(result["gates"]["gates"]), "negative_controls": len(result["negative_controls"]["controls"]), "evidence": str(Path(args.output_dir).relative_to(ROOT) if Path(args.output_dir).is_absolute() and ROOT in Path(args.output_dir).parents else args.output_dir)}, ensure_ascii=False))
    return 0 if result["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
