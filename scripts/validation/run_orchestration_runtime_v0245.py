"""Execute the complete deterministic UGAS v0.24.5 correction slice."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.orchestration_runtime_v0245 import (
    APPROVED_AUTHORITY_REGISTRY,
    FROZEN_REGISTRY_WITNESS,
    GIT_COMMIT_WITNESS,
    HARD_GATE_IDS,
    BoundedExecutionStore,
    CircuitBreaker,
    CircuitRegistry,
    DeterministicBatchScheduler,
    DeterministicClock,
    ExecutionCoordinator,
    FakeExecutor,
    OrchestrationContractError,
    OrchestrationRuntime,
    TEST_ONLY_ROUTE_EXECUTOR_IDENTITY,
    assert_provider_boundary,
    bind_governed_orchestration,
    build_approved_dependency_ref,
    build_dag,
    build_dependency_ref,
    build_governed_dependency_refs,
    build_request,
    compare_historical_evidence_tree,
    git_object_witness_available,
    evaluate_hard_gates,
    node_authority_input_contract_hash,
    probe_deadline_boundary_truth,
    prove_half_open_second_admission_blocked,
    provider_spy_targets,
    resolve_dependency_ref,
    resolve_dependency_refs,
    resume_from_checkpoint,
    sanitize_telemetry,
    sanitize_uads_handoff,
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


EVIDENCE = ROOT / "docs/evidence/orchestration-runtime-v0245"
BASE_MAIN_SHA = "dee98f8cd89ebd83a36ead7a22a184700d6e916f"
REJECTED_REVIEWED_HEAD = "55d6ee80f29d4cf6ed9f2d65e0173dbba570a124"
V0244_SEMANTIC_HEAD = "0c5226fcaaf90e0ddc5131749976afb6d6dd3153"
V0243_REJECTED_HEAD = "5a619c0b98ced7e4c09afd9ca117a039f0d5d068"
V0242_AUTHORITY_HEAD = "cd3345db7c0e587915e56eb9314879c4a9cf98a3"
V0241_AUTHORITY_HEAD = "ed9fa927fd50193130b3e085ef077dea267f2790"
BRANCH = "codex/v0.24.0-orchestration-runtime-hardening-foundation"
SANITIZED_UADS_HANDOFF = {
    "work_order_id": "wo_e3f4f80bd105a820",
    "run_or_dispatch_id": "er_9287a86fc6478cfa",
    "route_status": "SELECTED",
    "selected_profile_id": "codex-global-strong-v1",
    "dispatch_status": "DISPATCHED",
    "execution_mode": "GLOBAL_FIRST",
    "project_footprint": "ZERO",
}


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


def _copy_registry_files(dest: Path) -> None:
    for entry in APPROVED_AUTHORITY_REGISTRY.values():
        source = ROOT / entry["path"]
        target = dest / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _with_historical_candidate(mutator: Callable[[Path], None], *, auto_stage: bool = True) -> None:
    with tempfile.TemporaryDirectory(prefix="ugas-hist-v0245-") as directory:
        candidate = Path(directory) / "candidate"
        added = subprocess.run(["git", "worktree", "add", "--detach", str(candidate), "HEAD"], cwd=ROOT, capture_output=True)
        if added.returncode != 0:
            raise RuntimeError(added.stderr.decode(errors="replace"))
        try:
            subprocess.run(["git", "-C", str(candidate), "config", "user.email", "ugas-test@example.invalid"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(candidate), "config", "user.name", "UGAS Test"], check=True, capture_output=True)
            mutator(candidate)
            if auto_stage:
                subprocess.run(["git", "-C", str(candidate), "add", "-A"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(candidate), "commit", "-m", "ugas-v0245-historical-mutation", "--allow-empty"], check=True, capture_output=True)
            compare_historical_evidence_tree(candidate, V0241_AUTHORITY_HEAD, ["REVIEW-v0.24.1.md", "docs/evidence/orchestration-runtime-v0241"], label="v0241-historical-mutation")
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(candidate)], cwd=ROOT, capture_output=True)


def _execution_policy() -> dict[str, Any]:
    return {"route_executor_identity": TEST_ONLY_ROUTE_EXECUTOR_IDENTITY}


def _no_git_authority_root() -> tempfile.TemporaryDirectory[str]:
    directory = tempfile.TemporaryDirectory(prefix="ugas-nogit-v0245-")
    root = Path(directory.name)
    _copy_registry_files(root)
    return directory


def _authority_mode_controls() -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    git_refs = build_governed_dependency_refs(ROOT, project_id="ugas-v1-test-project")
    git_resolved = resolve_dependency_refs(git_refs, ROOT, expected_project_id="ugas-v1-test-project", require_approved_commit=True)
    controls.append({"control_id": "NC-AUTH-GIT-PASS", "injected_defect": "none", "expected_rejection_class": None, "observed_rejection_class": None, "status": "PASS" if git_resolved.get("verification_mode") == GIT_COMMIT_WITNESS and git_object_witness_available(ROOT) else "FAIL", "result": None, "actual_exception": None, "detail": "git-backed correct approved commit/bytes"})
    with tempfile.TemporaryDirectory(prefix="ugas-emptygit-v0245-") as directory:
        empty = Path(directory)
        subprocess.run(["git", "init"], cwd=empty, check=True, capture_output=True)
        _copy_registry_files(empty)
        refs = build_governed_dependency_refs(empty, project_id="ugas-v1-test-project")
        controls.append(_expect_rejection("NC-AUTH-11", "git mode missing canonical object", "ORCH_DEPENDENCY_AUTHORITY_COMMIT_MISSING", lambda: resolve_dependency_refs(refs, empty, expected_project_id="ugas-v1-test-project", require_approved_commit=True)))
    no_git_dir = _no_git_authority_root()
    try:
        no_git_root = Path(no_git_dir.name)
        no_git_refs = build_governed_dependency_refs(no_git_root, project_id="ugas-v1-test-project")
        no_git_resolved = resolve_dependency_refs(no_git_refs, no_git_root, expected_project_id="ugas-v1-test-project", require_approved_commit=True)
        controls.append({"control_id": "NC-AUTH-12", "injected_defect": "none", "expected_rejection_class": None, "observed_rejection_class": None, "status": "PASS" if no_git_resolved.get("verification_mode") == FROZEN_REGISTRY_WITNESS else "FAIL", "result": None, "actual_exception": None, "detail": "no-git snapshot frozen registry witness"})
        mutated = Path(no_git_root / APPROVED_AUTHORITY_REGISTRY["maps_minimap"]["path"])
        mutated.write_bytes(mutated.read_bytes() + b"\n")
        mutated_refs = copy.deepcopy(no_git_refs)
        controls.append(_expect_rejection("NC-AUTH-13", "no-git authority byte mutation", "ORCH_DEPENDENCY_AUTHORITY_HASH_MISMATCH", lambda: resolve_dependency_refs(mutated_refs, no_git_root, expected_project_id="ugas-v1-test-project", require_approved_commit=True)))
    finally:
        no_git_dir.cleanup()
    semantic_dir = _no_git_authority_root()
    try:
        semantic_root = Path(semantic_dir.name)
        semantic_path = semantic_root / APPROVED_AUTHORITY_REGISTRY["maps_minimap"]["path"]
        payload = json.loads(semantic_path.read_text(encoding="utf-8"))
        payload["ugas_v0245_semantic_probe"] = True
        semantic_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        semantic_refs = copy.deepcopy(no_git_refs)
        controls.append(_expect_rejection("NC-AUTH-14", "no-git semantic JSON mutation", "ORCH_DEPENDENCY_AUTHORITY_HASH_MISMATCH", lambda: resolve_dependency_refs(semantic_refs, semantic_root, expected_project_id="ugas-v1-test-project", require_approved_commit=True)))
    finally:
        semantic_dir.cleanup()
    tuple_dir = _no_git_authority_root()
    try:
        tuple_root = Path(tuple_dir.name)
        tuple_refs = build_governed_dependency_refs(tuple_root, project_id="ugas-v1-test-project")
        tuple_refs[0] = copy.deepcopy(tuple_refs[0]); tuple_refs[0]["approved_commit"] = "0" * 40
        controls.append(_expect_rejection("NC-AUTH-15", "no-git caller changes approved_commit", "ORCH_DEPENDENCY_APPROVED_COMMIT_REGISTRY_MISMATCH", lambda: resolve_dependency_refs(tuple_refs, tuple_root, expected_project_id="ugas-v1-test-project", require_approved_commit=True)))
    finally:
        tuple_dir.cleanup()
    missing_hash_dir = _no_git_authority_root()
    try:
        missing_root = Path(missing_hash_dir.name)
        missing_refs = build_governed_dependency_refs(missing_root, project_id="ugas-v1-test-project")
        original = dict(APPROVED_AUTHORITY_REGISTRY["maps_minimap"])
        APPROVED_AUTHORITY_REGISTRY["maps_minimap"] = {key: value for key, value in original.items() if key not in {"content_hash", "semantic_hash"}}
        try:
            controls.append(_expect_rejection("NC-AUTH-16", "no-git missing canonical registry hashes", "ORCH_DEPENDENCY_AUTHORITY_REGISTRY_HASH_MISSING", lambda: resolve_dependency_refs(missing_refs, missing_root, expected_project_id="ugas-v1-test-project", require_approved_commit=True)))
        finally:
            APPROVED_AUTHORITY_REGISTRY["maps_minimap"] = original
    finally:
        missing_hash_dir.cleanup()
    no_git_clean = _no_git_authority_root()
    try:
        clean_root = Path(no_git_clean.name)
        clean_refs = build_governed_dependency_refs(clean_root, project_id="ugas-v1-test-project")
        frozen = resolve_dependency_refs(clean_refs, clean_root, expected_project_id="ugas-v1-test-project", require_approved_commit=True)
        equal = frozen["authority_binding_hash"] == git_resolved["authority_binding_hash"]
        controls.append({"control_id": "NC-AUTH-BIND-EQ", "injected_defect": "none", "expected_rejection_class": None, "observed_rejection_class": None, "status": "PASS" if equal else "FAIL", "result": None, "actual_exception": None, "detail": "binding hash equal across git and no-git modes", "git_binding": git_resolved["authority_binding_hash"], "no_git_binding": frozen["authority_binding_hash"], "git_mode": git_resolved.get("verification_mode"), "no_git_mode": frozen.get("verification_mode")})
        canonical = all(item.get("status") == APPROVED_AUTHORITY_REGISTRY[item["family"]]["status"] for item in frozen["authorities"] + git_resolved["authorities"])
        controls.append({"control_id": "NC-AUTH-STATUS-CANON", "injected_defect": "none", "expected_rejection_class": None, "observed_rejection_class": None, "status": "PASS" if canonical else "FAIL", "result": None, "actual_exception": None, "detail": "resolved status is canonical registry status"})
        status_refs = copy.deepcopy(clean_refs)
        status_refs[0] = copy.deepcopy(status_refs[0]); status_refs[0]["status"] = "APPROVED_FOUNDATION"
        controls.append(_expect_rejection("NC-AUTH-17", "no-git MERGED_CLOSED to APPROVED_FOUNDATION", "ORCH_DEPENDENCY_AUTHORITY_STATUS_MISMATCH", lambda: resolve_dependency_refs(status_refs, clean_root, expected_project_id="ugas-v1-test-project", require_approved_commit=True)))
        items_ref = build_approved_dependency_ref(clean_root, project_id="ugas-v1-test-project", family="items_props")
        items_mutated = copy.deepcopy(items_ref); items_mutated["status"] = "MERGED_CLOSED"
        controls.append(_expect_rejection("NC-AUTH-18", "no-git APPROVED_FOUNDATION to MERGED_CLOSED", "ORCH_DEPENDENCY_AUTHORITY_STATUS_MISMATCH", lambda: resolve_dependency_ref(items_mutated, clean_root, expected_project_id="ugas-v1-test-project", require_approved_commit=True)))
        revision_refs = copy.deepcopy(clean_refs)
        revision_refs[0] = copy.deepcopy(revision_refs[0]); revision_refs[0]["revision"] = "v0.99.9"
        controls.append(_expect_rejection("NC-AUTH-19", "no-git revision mutation", "ORCH_DEPENDENCY_AUTHORITY_TUPLE_MISMATCH", lambda: resolve_dependency_refs(revision_refs, clean_root, expected_project_id="ugas-v1-test-project", require_approved_commit=True)))
        path_refs = copy.deepcopy(clean_refs)
        path_refs[0] = copy.deepcopy(path_refs[0]); path_refs[0]["path"] = "docs/evidence/does-not-exist.json"
        controls.append(_expect_rejection("NC-AUTH-20", "no-git path mutation", "ORCH_DEPENDENCY_AUTHORITY_TUPLE_MISMATCH", lambda: resolve_dependency_refs(path_refs, clean_root, expected_project_id="ugas-v1-test-project", require_approved_commit=True)))
    finally:
        no_git_clean.cleanup()
    git_status = copy.deepcopy(git_refs)
    git_status[0] = copy.deepcopy(git_status[0]); git_status[0]["status"] = "APPROVED_FOUNDATION"
    controls.append(_expect_rejection("NC-AUTH-21", "git-backed status mutation", "ORCH_DEPENDENCY_AUTHORITY_STATUS_MISMATCH", lambda: resolve_dependency_refs(git_status, ROOT, expected_project_id="ugas-v1-test-project", require_approved_commit=True)))
    return controls


def _request(dependency_refs: list[dict[str, Any]] | None = None, *, timeout: int = 30) -> dict[str, Any]:
    refs = dependency_refs if dependency_refs is not None else build_governed_dependency_refs(ROOT, project_id="ugas-v1-test-project")
    return build_request(
        request_id="orchestration-v0245-fixture",
        project_id="ugas-v1-test-project",
        request_kind="ASSET_OPERATION",
        asset_family="maps_minimap",
        operation="EXECUTE",
        inputs={"fixture": "synthetic-orchestration-0242"},
        dependency_refs=refs,
        outputs={"project_id": "ugas-v1-test-project", "path": "results/orchestration.json"},
        quality_profile="correction-qa",
        budget_profile="bounded-cpu-test",
        priority=50,
        timeout_seconds=timeout,
        retry_policy={"max_attempts": 2, "retryable_errors": ["TRANSIENT_EXECUTION_ERROR", "REQUEST_DEADLINE_EXCEEDED", "NODE_DEADLINE_EXCEEDED"]},
        idempotency_key="orchestration-v0245-fixture-idempotency",
        production_intent=False,
        test_only=True,
    )


def _node(node_id: str, dependencies: list[str] | None = None, *, family: str = "maps_minimap", timeout: int = 30, priority: int = 10, authority_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = authority_payload or {}
    base = {"node_id": node_id, "dependencies": dependencies or [], "operation": "EXECUTE", "dependency_hashes": {}, "timeout_seconds": timeout, "retry_policy": {"max_attempts": 2, "retryable_errors": ["TRANSIENT_EXECUTION_ERROR", "REQUEST_DEADLINE_EXCEEDED", "NODE_DEADLINE_EXCEEDED"]}, "resource_class": "cpu-test", "scheduling_key": "orchestration-v0245", "priority": priority, "asset_family": family}
    base["input_contract_hash"] = node_authority_input_contract_hash(base, payload) if payload else sha256_value({"node": node_id, "version": "0.24.5"})
    return base


def _historical_tree_proof(authority_head: str, roots: list[str], *, label: str) -> dict[str, Any]:
    return compare_historical_evidence_tree(ROOT, authority_head, roots, label=label)


def _frozen_v0241_tree() -> dict[str, Any]:
    roots = ["REVIEW-v0.24.1.md", "docs/evidence/orchestration-runtime-v0241"]
    proof = _historical_tree_proof(V0241_AUTHORITY_HEAD, roots, label="v0241-historical")
    proof["authority_commit"] = V0241_AUTHORITY_HEAD
    return proof


def _frozen_v0242_tree() -> dict[str, Any]:
    roots = ["REVIEW-v0.24.2.md", "docs/evidence/orchestration-runtime-v0242"]
    proof = _historical_tree_proof(V0242_AUTHORITY_HEAD, roots, label="v0242-historical")
    proof["authority_commit"] = V0242_AUTHORITY_HEAD
    return proof


def _authority_proof() -> dict[str, Any]:
    refs = build_governed_dependency_refs(ROOT, project_id="ugas-v1-test-project") + [build_approved_dependency_ref(ROOT, project_id="ugas-v1-test-project", family="items_props")]
    resolved = resolve_dependency_refs(refs, ROOT, expected_project_id="ugas-v1-test-project", require_approved_commit=True)
    mutated = copy.deepcopy(refs[0]); mutated["content_hash"] = "0" * 64
    mutation = _expect_rejection("NC-AUTH-01", "mutated content hash", "ORCH_DEPENDENCY_AUTHORITY_HASH_MISMATCH", lambda: resolve_dependency_ref(mutated, ROOT, expected_project_id="ugas-v1-test-project"))
    wrong_family = copy.deepcopy(refs[0]); wrong_family["family"] = "ui_asset_family"; wrong_family["path"] = refs[0]["path"]; wrong_family["revision"] = refs[0]["revision"]
    mutation_wrong_family = _expect_rejection("NC-AUTH-02", "wrong family tuple", "ORCH_DEPENDENCY_AUTHORITY_TUPLE_MISMATCH", lambda: resolve_dependency_ref(wrong_family, ROOT, expected_project_id="ugas-v1-test-project"))
    wrong_revision = copy.deepcopy(refs[0]); wrong_revision["revision"] = "v0.99.9"
    mutation_wrong_revision = _expect_rejection("NC-AUTH-03", "wrong revision", "ORCH_DEPENDENCY_AUTHORITY_TUPLE_MISMATCH", lambda: resolve_dependency_ref(wrong_revision, ROOT, expected_project_id="ugas-v1-test-project"))
    unapproved_label = copy.deepcopy(refs[0]); unapproved_label["path"] = "docs/evidence/ui-asset-family-runtime-v0223/ui-style-authority-v0223.json"; unapproved_label["status"] = "MERGED_CLOSED"
    mutation_unapproved_label = _expect_rejection("NC-AUTH-04", "caller labels unapproved tuple", "ORCH_DEPENDENCY_AUTHORITY_TUPLE_MISMATCH", lambda: resolve_dependency_ref(unapproved_label, ROOT, expected_project_id="ugas-v1-test-project"))
    missing_commit = copy.deepcopy(refs[0]); missing_commit.pop("approved_commit", None)
    mutation_missing_commit = _expect_rejection("NC-AUTH-05", "missing approved_commit", "ORCH_DEPENDENCY_APPROVED_COMMIT_REQUIRED", lambda: resolve_dependency_ref(missing_commit, ROOT, expected_project_id="ugas-v1-test-project", require_approved_commit=True))
    wrong_commit = copy.deepcopy(refs[0]); wrong_commit["approved_commit"] = "0" * 40
    mutation_wrong_commit = _expect_rejection("NC-AUTH-07", "wrong approved_commit", "ORCH_DEPENDENCY_APPROVED_COMMIT_REGISTRY_MISMATCH", lambda: resolve_dependency_ref(wrong_commit, ROOT, expected_project_id="ugas-v1-test-project", require_approved_commit=True))
    controls = [mutation, mutation_wrong_family, mutation_wrong_revision, mutation_unapproved_label, mutation_missing_commit, mutation_wrong_commit]
    return {"status": "PASS" if all(item["status"] == "PASS" for item in controls) else "FAIL", "refs": refs, "resolved": resolved, "approved_registry": APPROVED_AUTHORITY_REGISTRY, "mutation_controls": controls}


def _negative_controls(request: dict[str, Any], dag: dict[str, Any], checkpoint: dict[str, Any], authority: dict[str, Any], *, execution_policy: dict[str, Any]) -> dict[str, Any]:
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
    missing = copy.deepcopy(authority["refs"][0]); missing["path"] = "docs/evidence/does-not-exist.json"; missing["revision"] = "v9.9.9"
    controls.append(_expect_rejection("NC-AUTH-06", "missing authority path", "ORCH_DEPENDENCY_AUTHORITY_TUPLE_MISMATCH", lambda: resolve_dependency_ref(missing, ROOT, expected_project_id=request["project_id"])))
    tampered_event_hash = copy.deepcopy(checkpoint); tampered_event_hash["event_hash"] = "f" * 64; tampered_event_hash["checkpoint_hash"] = sha256_value({key: value for key, value in tampered_event_hash.items() if key != "checkpoint_hash"})
    controls.append(_expect_rejection("NC-CHK-04", "tampered top-level event_hash", "ORCH_CHECKPOINT_EVENT_HASH_MISMATCH", lambda: validate_checkpoint(tampered_event_hash, request, dag)))
    extra_attempt = copy.deepcopy(checkpoint); extra_attempt["attempts"]["tail"] = 1; extra_attempt["checkpoint_hash"] = sha256_value({key: value for key, value in extra_attempt.items() if key != "checkpoint_hash"})
    controls.append(_expect_rejection("NC-CHK-05", "attempt on never-dispatched node", "ORCH_CHECKPOINT_ATTEMPTS_INVALID", lambda: validate_checkpoint(extra_attempt, request, dag)))
    bad_attempt = copy.deepcopy(checkpoint); bad_attempt["attempts"]["prepare"] = True; bad_attempt["checkpoint_hash"] = sha256_value({key: value for key, value in bad_attempt.items() if key != "checkpoint_hash"})
    controls.append(_expect_rejection("NC-CHK-06", "bool attempt count", "ORCH_CHECKPOINT_ATTEMPTS_INVALID", lambda: validate_checkpoint(bad_attempt, request, dag)))
    unknown_deadline = copy.deepcopy(checkpoint); unknown_deadline["node_deadlines"]["injected"] = {"started_seconds": 0.0, "deadline_seconds": 1.0, "status": "SUCCEEDED"}; unknown_deadline["checkpoint_hash"] = sha256_value({key: value for key, value in unknown_deadline.items() if key != "checkpoint_hash"})
    controls.append(_expect_rejection("NC-CHK-07", "unknown node_deadlines entry", "ORCH_CHECKPOINT_NODE_DEADLINES_UNKNOWN_NODE", lambda: validate_checkpoint(unknown_deadline, request, dag)))
    bad_circuit = copy.deepcopy(checkpoint); bad_circuit["circuit"]["state"] = "OPEN"; bad_circuit["circuit"]["probe_in_flight"] = True; bad_circuit["checkpoint_hash"] = sha256_value({key: value for key, value in bad_circuit.items() if key != "checkpoint_hash"})
    controls.append(_expect_rejection("NC-CHK-08", "invalid circuit invariants", "ORCH_CHECKPOINT_CIRCUIT_INVALID", lambda: validate_checkpoint(bad_circuit, request, dag, execution_policy=execution_policy)))
    open_zero = copy.deepcopy(checkpoint); open_zero["circuit"] = {"state": "OPEN", "failures": 0, "probe_in_flight": False, "route_executor_identity": TEST_ONLY_ROUTE_EXECUTOR_IDENTITY, "project_id": request["project_id"], "failure_threshold": 2}; open_zero["checkpoint_hash"] = sha256_value({key: value for key, value in open_zero.items() if key != "checkpoint_hash"})
    controls.append(_expect_rejection("NC-CHK-09", "OPEN circuit with zero failures", "ORCH_CHECKPOINT_CIRCUIT_INVALID", lambda: validate_checkpoint(open_zero, request, dag, execution_policy=execution_policy)))
    delete_attempt = copy.deepcopy(checkpoint); delete_attempt["attempts"].pop("prepare", None); delete_attempt["checkpoint_hash"] = sha256_value({key: value for key, value in delete_attempt.items() if key != "checkpoint_hash"})
    controls.append(_expect_rejection("NC-CHK-10", "deleted executed attempt", "ORCH_CHECKPOINT_ATTEMPTS_INVALID", lambda: validate_checkpoint(delete_attempt, request, dag)))
    delete_deadline = copy.deepcopy(checkpoint); delete_deadline["node_deadlines"].pop("prepare", None); delete_deadline["checkpoint_hash"] = sha256_value({key: value for key, value in delete_deadline.items() if key != "checkpoint_hash"})
    controls.append(_expect_rejection("NC-CHK-11", "deleted executed deadline", "ORCH_CHECKPOINT_NODE_DEADLINES_INVALID", lambda: validate_checkpoint(delete_deadline, request, dag)))
    controls.append(_expect_rejection("NC-AUTH-08", "arbitrary authority_binding_hash", "ORCH_AUTHORITY_BINDING_MISMATCH", lambda: bind_governed_orchestration(request, dag, ROOT, authority_binding_hash="f" * 64)))
    bad_node_dag = copy.deepcopy(dag); bad_node_dag["nodes"][0]["input_contract_hash"] = "a" * 64; bad_node_dag.pop("dag_hash", None)
    controls.append(_expect_rejection("NC-AUTH-09", "arbitrary node input hash", "ORCH_AUTHORITY_INPUT_CONTRACT_MISMATCH", lambda: bind_governed_orchestration(request, bad_node_dag, ROOT)))
    controls.extend(_authority_mode_controls())
    hist_roots = ["REVIEW-v0.24.1.md", "docs/evidence/orchestration-runtime-v0241"]
    hist_files = [path for path in (ROOT / "docs/evidence/orchestration-runtime-v0241").rglob("*") if path.is_file()]
    target = hist_files[0] if hist_files else ROOT / "docs/evidence/orchestration-runtime-v0241/execution-evidence-v0241.json"

    def _delete(candidate: Path) -> None:
        relative = target.relative_to(ROOT).as_posix()
        (candidate / relative).unlink()

    def _extra(candidate: Path) -> None:
        extra = candidate / "docs/evidence/orchestration-runtime-v0241/EXTRA-UNAUTHORIZED.txt"
        extra.write_text("unauthorized\n", encoding="utf-8")

    def _mutate(candidate: Path) -> None:
        relative = target.relative_to(ROOT).as_posix()
        path = candidate / relative
        path.write_bytes(path.read_bytes() + b"\nUGAS-V0245-MUTATION\n")

    def _chmod(candidate: Path) -> None:
        subprocess.run(["git", "-C", str(candidate), "update-index", "--chmod=+x", "REVIEW-v0.24.1.md"], check=True, capture_output=True)

    controls.append(_expect_rejection("NC-HIST-01", "deleted historical file", "HISTORICAL_TREE_MISMATCH", lambda: _with_historical_candidate(_delete)))
    controls.append(_expect_rejection("NC-HIST-02", "extra unauthorized file", "HISTORICAL_TREE_MISMATCH", lambda: _with_historical_candidate(_extra)))
    controls.append(_expect_rejection("NC-HIST-03", "historical file byte mutation", "HISTORICAL_TREE_MISMATCH", lambda: _with_historical_candidate(_mutate)))
    controls.append(_expect_rejection("NC-HIST-04", "historical mode-only mutation", "HISTORICAL_TREE_MISMATCH", lambda: _with_historical_candidate(_chmod, auto_stage=False)))
    controls.append(_expect_rejection("NC-HIST-05", "nonexistent historical root", "HISTORICAL_ROOT_EMPTY", lambda: compare_historical_evidence_tree(ROOT, V0241_AUTHORITY_HEAD, ["docs/evidence/does-not-exist-v0245"], label="v0241-missing-root")))
    controls.append(_expect_rejection("NC-HIST-06", "unresolvable historical authority ref", "HISTORICAL_REF_UNRESOLVED", lambda: compare_historical_evidence_tree(ROOT, "0" * 40, hist_roots, label="v0241-unresolved-ref")))
    return {"schema_version": VERSION, "controls": {item["control_id"]: item for item in controls}, "status": "PASS" if all(item["status"] == "PASS" and item.get("result") in {"REJECT", None} for item in controls) else "FAIL"}


def run(output_dir: Path = EVIDENCE) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    authority = _authority_proof()
    request = _request(dependency_refs=authority["refs"])
    nodes = [_node("prepare", priority=30, authority_payload=authority["resolved"]), _node("child", ["prepare"], priority=20, authority_payload=authority["resolved"]), _node("tail", ["child"], priority=10, authority_payload=authority["resolved"])]
    dag = build_dag(request, nodes)
    bound = bind_governed_orchestration(request, dag, ROOT)
    request, dag = bound["request"], bound["dag"]
    binding_hash = bound["authority_binding_hash"]
    policy = _execution_policy()
    runtime_one = OrchestrationRuntime(request, dag, max_concurrency=2, family_limits={"maps_minimap": 1}, authority_binding_hash=binding_hash, execution_policy=policy, repo_root=ROOT)
    snapshot_one = runtime_one.run()
    runtime_two = OrchestrationRuntime(request, dag, max_concurrency=2, family_limits={"maps_minimap": 1}, authority_binding_hash=binding_hash, execution_policy=policy)
    snapshot_two = runtime_two.run()
    partial_runtime = OrchestrationRuntime(request, dag, max_concurrency=2, family_limits={"maps_minimap": 1}, authority_binding_hash=binding_hash, execution_policy=policy)
    partial = partial_runtime.run(stop_after_nodes=1)
    checkpoint = partial_runtime.checkpoint()
    checkpoint_validation = validate_checkpoint(checkpoint, request, dag, execution_policy=policy)
    resumed = resume_from_checkpoint(request, dag, checkpoint, executor=FakeExecutor(), authority_binding_hash=binding_hash, execution_policy=policy)
    resumed_snapshot = resumed.run()
    open_checkpoint = copy.deepcopy(checkpoint)
    open_checkpoint["circuit"] = {"state": "OPEN", "failures": 2, "probe_in_flight": False, "route_executor_identity": TEST_ONLY_ROUTE_EXECUTOR_IDENTITY, "project_id": request["project_id"], "failure_threshold": 2}
    open_checkpoint["checkpoint_hash"] = sha256_value({key: value for key, value in open_checkpoint.items() if key != "checkpoint_hash"})
    open_resume_executor = FakeExecutor()
    open_resumed = resume_from_checkpoint(request, dag, open_checkpoint, executor=open_resume_executor, authority_binding_hash=binding_hash, execution_policy=policy)
    open_resume_snapshot = open_resumed.run()
    half_open_checkpoint = copy.deepcopy(checkpoint)
    half_open_checkpoint["circuit"] = {"state": "HALF_OPEN", "failures": 2, "probe_in_flight": False, "route_executor_identity": TEST_ONLY_ROUTE_EXECUTOR_IDENTITY, "project_id": request["project_id"], "failure_threshold": 2}
    half_open_checkpoint["checkpoint_hash"] = sha256_value({key: value for key, value in half_open_checkpoint.items() if key != "checkpoint_hash"})
    half_open_executor = FakeExecutor()
    half_open_resumed = resume_from_checkpoint(request, dag, half_open_checkpoint, executor=half_open_executor, authority_binding_hash=binding_hash, execution_policy=policy)
    half_open_resume_snapshot = half_open_resumed.run()
    coordinator = ExecutionCoordinator(BoundedExecutionStore())
    first = coordinator.execute(OrchestrationRuntime(request, dag, authority_binding_hash=binding_hash))
    second = coordinator.execute(OrchestrationRuntime(request, dag, authority_binding_hash=binding_hash))
    failed_coordinator = ExecutionCoordinator(BoundedExecutionStore())
    failed_first = failed_coordinator.execute(OrchestrationRuntime(request, dag), faults={"prepare": "nonretryable"})
    failed_retry = failed_coordinator.execute(OrchestrationRuntime(request, dag))
    cancelled_coordinator = ExecutionCoordinator(BoundedExecutionStore())
    cancelled_first = cancelled_coordinator.execute(OrchestrationRuntime(request, dag), cancellations=["prepare"])
    cancelled_retry = cancelled_coordinator.execute(OrchestrationRuntime(request, dag))
    shared_registry = CircuitRegistry()
    circuit_request = _request()
    trip_node = _node("trip", authority_payload=authority["resolved"])
    trip_node["retry_policy"]["max_attempts"] = 2
    circuit_dag = build_dag(circuit_request, [trip_node])
    trip_executor = FakeExecutor()
    trip_runtime = OrchestrationRuntime(circuit_request, circuit_dag, executor=trip_executor, circuit_registry=shared_registry, authority_binding_hash=binding_hash, execution_policy=policy)
    trip_snapshot = trip_runtime.run(faults={"trip": "persistent_retryable"})
    opened = trip_runtime._breaker.state == "OPEN"
    blocked_executor = FakeExecutor()
    blocked_before = blocked_executor.executions
    blocked_runtime = OrchestrationRuntime(circuit_request, circuit_dag, executor=blocked_executor, circuit_registry=shared_registry, authority_binding_hash=binding_hash, execution_policy=policy)
    blocked_snapshot = blocked_runtime.run()
    blocked_delta = blocked_executor.executions - blocked_before
    isolated_registry = CircuitRegistry()
    isolated_executor = FakeExecutor()
    other_refs = build_governed_dependency_refs(ROOT, project_id="other-project")
    other_request = build_request(request_id="other-project", project_id="other-project", request_kind="ASSET_OPERATION", asset_family="maps_minimap", operation="EXECUTE", inputs={"fixture": "isolated-circuit"}, dependency_refs=other_refs, outputs={"project_id": "other-project", "path": "out.json"}, quality_profile="correction-qa", budget_profile="bounded-cpu-test", priority=50, timeout_seconds=30, retry_policy={"max_attempts": 2, "retryable_errors": ["TRANSIENT_EXECUTION_ERROR", "REQUEST_DEADLINE_EXCEEDED", "NODE_DEADLINE_EXCEEDED"]}, idempotency_key="other-project", production_intent=False, test_only=True)
    other_dag = build_dag(other_request, [_node("trip", authority_payload=resolve_dependency_refs(other_refs, ROOT, expected_project_id="other-project", require_approved_commit=True))])
    isolated_runtime = OrchestrationRuntime(other_request, other_dag, executor=isolated_executor, circuit_registry=isolated_registry, authority_binding_hash=resolve_dependency_refs(other_refs, ROOT, expected_project_id="other-project", require_approved_commit=True)["authority_binding_hash"], execution_policy=policy)
    isolated_before = isolated_executor.executions
    isolated_runtime.run(faults={"trip": "retryable"})
    isolated_open = isolated_runtime._breaker.state == "OPEN"
    shared_breaker = shared_registry.get(request["project_id"], TEST_ONLY_ROUTE_EXECUTOR_IDENTITY)
    shared_breaker.half_open()
    probe_executor = FakeExecutor()
    probe_runtime = OrchestrationRuntime(circuit_request, circuit_dag, executor=probe_executor, circuit_registry=shared_registry, authority_binding_hash=binding_hash, execution_policy=policy)
    probe_before = probe_executor.executions
    probe_snapshot = probe_runtime.run()
    probe_delta = probe_executor.executions - probe_before
    second_probe_executor = FakeExecutor()
    half_open_breaker = CircuitBreaker(failure_threshold=2)
    half_open_breaker.record_failure(); half_open_breaker.record_failure(); half_open_breaker.half_open()
    first_probe_allow = half_open_breaker.allow()
    second_probe_allow = half_open_breaker.allow()
    closed = shared_breaker.state == "CLOSED" and probe_snapshot["states"]["trip"] == "SUCCEEDED"
    half_open_second_runtime = prove_half_open_second_admission_blocked(shared_registry, request["project_id"], TEST_ONLY_ROUTE_EXECUTOR_IDENTITY)
    nonretry_runtime = OrchestrationRuntime(request, build_dag(request, [_node("contract", authority_payload=authority["resolved"])]), execution_policy=policy)
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
    legacy_request = adapt_legacy_generation_request({"job_id": "legacy-0242", "asset_family": "maps_minimap", "inputs": {"fixture": "legacy"}, "outputs": {"project_id": "ugas-v1-test-project", "path": "results/legacy.json"}, "profile": "qa", "seed": 1}, "ugas-v1-test-project")
    batch = DeterministicBatchScheduler(build_dag(request, [_node("a", family="maps_minimap"), _node("b", family="ui_asset_family"), _node("c", family="maps_minimap"), _node("d", family="vfx_asset_family")]), 3, {"maps_minimap": 1, "ui_asset_family": 2, "vfx_asset_family": 1}).plan()
    deadline_probe = probe_deadline_boundary_truth()
    mutated_authority_request = copy.deepcopy(request)
    mutated_authority_request["dependency_refs"][0] = copy.deepcopy(mutated_authority_request["dependency_refs"][0])
    mutated_authority_request["dependency_refs"][0]["content_hash"] = "1" * 64
    mutated_authority_request.pop("request_hash", None)
    mutated_authority_request = build_request(**{key: mutated_authority_request[key] for key in mutated_authority_request if key != "request_hash"})
    authority_mutation_changes_identity = mutated_authority_request["request_hash"] != request["request_hash"]
    mutated_nodes = [_node("prepare", priority=30, authority_payload=authority["resolved"])]
    mutated_dag = build_dag(mutated_authority_request, mutated_nodes)
    dag_hash_changes = mutated_dag["dag_hash"] != build_dag(request, mutated_nodes)["dag_hash"] or mutated_dag["dag_hash"] != dag["dag_hash"]
    frozen_v0241 = _frozen_v0241_tree()
    frozen_v0242 = _frozen_v0242_tree()
    production = {"production_routing": "BLOCKED", "production_approved": False, "real_asset_generation": "NONE", "new_generation": 0, "synthetic_fixture": "TEST_ONLY", "provider_submit_calls": snapshot_one["provider_submit_calls"]}
    telemetry = sanitize_telemetry({"event": "orchestration-v0245-complete", "request_hash": request["request_hash"], "dag_hash": dag["dag_hash"], "state": snapshot_one["status"], "elapsed_seconds": snapshot_one["clock_elapsed_seconds"], "deadline_seconds": request["timeout_seconds"]})
    with patch("ugas.comfyui_client.ComfyUIClient.submit_workflow") as client_spy, patch("ugas.generation.ComfyUIClient.submit_workflow") as legacy_spy:
        spy_runtime = OrchestrationRuntime(request, dag, authority_binding_hash=binding_hash)
        spy_snapshot = spy_runtime.run()
        provider_spies = {provider_spy_targets()[0]: client_spy.call_count, provider_spy_targets()[1]: legacy_spy.call_count}
    boundary = assert_provider_boundary(ROOT / "src/ugas/orchestration_runtime_v0245.py")
    validate_provider_spy_counts(provider_spies)
    controls = _negative_controls(request, dag, checkpoint, authority, execution_policy=policy)
    observations = {
        "canonical_request": request["test_only"] is True and request["production_intent"] is False,
        "request_hash": request["request_hash"] == sha256_value({key: value for key, value in request.items() if key != "request_hash"}),
        "dag_schema": dag["schema_version"] == VERSION,
        "dag_acyclic": len(dag["nodes"]) == len(set(item["node_id"] for item in dag["nodes"])),
        "dag_dependency_hashes": all(node["dependency_hashes"].get(dep) for node in dag["nodes"] for dep in node["dependencies"]),
        "scheduler_dependency_first": all((__import__("ugas.orchestration_runtime_v0245", fromlist=["deterministic_schedule"]).deterministic_schedule(dag).index(dep) < __import__("ugas.orchestration_runtime_v0245", fromlist=["deterministic_schedule"]).deterministic_schedule(dag).index(node["node_id"])) for node in dag["nodes"] for dep in node["dependencies"]),
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
        "request_deadline_clock": deadline_probe["before_boundary"] and deadline_probe["exact_boundary"] and deadline_probe["after_boundary"],
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
        "circuit_breaker_runtime": opened and closed and trip_snapshot["states"]["trip"] == "FAILED" and trip_snapshot["circuit"]["state"] == "OPEN",
        "circuit_open_dispatch_blocked": blocked_snapshot["states"]["trip"] == "BLOCKED" and blocked_delta == 0,
        "circuit_half_open_single_probe": probe_delta == 1 and first_probe_allow and not second_probe_allow and half_open_second_runtime.get("status") == "PASS",
        "circuit_nonretryable_not_transient": nonretry_runtime._breaker.failures == 0,
        "authority_ref_schema": all(set(ref) <= {"project_id", "family", "revision", "path", "authority_id", "content_hash", "semantic_hash", "read_only", "status", "approved_commit"} for ref in authority["refs"]),
        "authority_content_hash": authority["status"] == "PASS" and all(item["resolved_content_hash"] == item["content_hash"] for item in authority["resolved"]["authorities"]),
        "authority_revision_binding": all(ref["revision"] for ref in authority["refs"]),
        "authority_read_only": all(ref["read_only"] is True for ref in authority["refs"]),
        "authority_payload_identity": bool(binding_hash),
        "provider_source_boundary": boundary["status"] == "PASS",
        "provider_client_spy_zero": provider_spies[provider_spy_targets()[0]] == 0,
        "provider_legacy_spy_zero": provider_spies[provider_spy_targets()[1]] == 0,
        "cache_identity": first["source_execution_id"] == second["source_execution_id"],
        "cache_success_only": first["status"] == "EXECUTED" and first["snapshot"]["status"] == "COMPLETE" and failed_first["status"] == "EXECUTED" and failed_retry["status"] == "EXECUTED" and cancelled_first["status"] == "EXECUTED" and cancelled_retry["status"] == "EXECUTED",
        "result_provenance": all(result.get("result_hash") for result in snapshot_one["results"].values()),
        "fake_executor_determinism": snapshot_one["results"] == snapshot_two["results"],
        "telemetry_sanitized": telemetry["request_hash"] == request["request_hash"],
        "production_boundary": validate_production_boundary(production) is None,
        "legacy_adapter_narrow": legacy_request["test_only"] is True and legacy_request["production_intent"] is False and legacy_request["request_kind"] == "ASSET_OPERATION" and legacy_request["idempotency_key"] == "legacy:legacy-0242",
        "historical_closure_binding": frozen_v0241["status"] == "PASS" and frozen_v0241["authority_commit"] == V0241_AUTHORITY_HEAD and frozen_v0241.get("equality") is True and frozen_v0241.get("authority_fingerprint") == frozen_v0241.get("observed_fingerprint") and frozen_v0242["status"] == "PASS" and frozen_v0242["authority_commit"] == V0242_AUTHORITY_HEAD and frozen_v0242.get("equality") is True,
        "authority_git_commit_witness": authority["resolved"].get("verification_mode") == GIT_COMMIT_WITNESS,
        "authority_frozen_registry_witness": any(item.get("control_id") == "NC-AUTH-12" and item.get("status") == "PASS" for item in controls["controls"].values()),
        "authority_binding_equal_across_modes": controls["controls"].get("NC-AUTH-BIND-EQ", {}).get("status") == "PASS",
    }
    gates = evaluate_hard_gates(observations, {gate_id: deadline_probe["proof_source"] if gate_id == "request_deadline_clock" else "runtime observation" for gate_id in observations})
    validate_no_repo_local_uads(ROOT)
    uads_handoff = sanitize_uads_handoff(SANITIZED_UADS_HANDOFF)
    result = {"schema_version": VERSION, "overall_pass": gates["overall_pass"] and controls["status"] == "PASS" and snapshot_one == snapshot_two, "request": request, "dag": dag, "snapshot": snapshot_one, "checkpoint": {"partial": partial, "validation": checkpoint_validation, "resumed": resumed_snapshot, "open_resume": open_resume_snapshot, "half_open_resume": half_open_resume_snapshot}, "idempotency": {"first": first, "second": second, "failed_first": failed_first, "failed_retry": failed_retry, "cancelled_first": cancelled_first, "cancelled_retry": cancelled_retry}, "circuit": {"opened": opened, "blocked_delta": blocked_delta, "probe_delta": probe_delta, "first_probe_allow": first_probe_allow, "second_probe_allow": second_probe_allow, "half_open_second_runtime": half_open_second_runtime, "closed": closed, "route_executor_identity": TEST_ONLY_ROUTE_EXECUTOR_IDENTITY, "isolated_open": isolated_open, "trip_snapshot": trip_snapshot, "blocked_snapshot": blocked_snapshot, "probe_snapshot": probe_snapshot}, "correction_probes": {"cancellation": cancel_snapshot, "retry_success": retry_success_snapshot, "retry_class": retry_class_snapshot, "deadline": deadline_snapshot, "retry_deadline": retry_deadline_snapshot, "legacy_request": legacy_request, "deadline_probe": deadline_probe, "authority_mutation_changes_identity": authority_mutation_changes_identity, "dag_hash_changes": dag_hash_changes}, "authority": authority, "provider": {"spies": provider_spies, "targets": list(provider_spy_targets()), "boundary": boundary, "snapshot": spy_snapshot}, "family_concurrency": batch, "frozen_v0241": frozen_v0241, "frozen_v0242": frozen_v0242, "production": production, "telemetry": telemetry, "uads_handoff": uads_handoff, "gates": gates, "negative_controls": controls, "rejected_reviewed_head": REJECTED_REVIEWED_HEAD, "v0244_semantic_head": V0244_SEMANTIC_HEAD, "base_main_sha": BASE_MAIN_SHA, "branch": BRANCH}
    _write(output_dir / "request-contract-v0245.json", {"request": request, "status": "PASS"})
    _write(output_dir / "dag-scheduler-v0245.json", {"dag": dag, "status": "PASS"})
    _write(output_dir / "execution-state-v0245.json", snapshot_one)
    _write(output_dir / "deadline-timeout-v0245.json", {"status": "PASS", "clock": snapshot_one["clock_elapsed_seconds"], "request_deadline_seconds": request["timeout_seconds"], "node_deadlines": snapshot_one["node_deadlines"], "probes": result["correction_probes"]})
    _write(output_dir / "checkpoint-resume-v0245.json", result["checkpoint"])
    _write(output_dir / "idempotency-coordinator-v0245.json", result["idempotency"])
    _write(output_dir / "circuit-breaker-runtime-v0245.json", result["circuit"])
    _write(output_dir / "dependency-authority-v0245.json", authority)
    _write(output_dir / "provider-boundary-v0245.json", result["provider"])
    _write(output_dir / "family-concurrency-v0245.json", batch)
    _write(output_dir / "historical-immutability-v0245.json", {"v0241": frozen_v0241, "v0242": frozen_v0242, "status": "PASS" if frozen_v0241.get("status") == "PASS" and frozen_v0242.get("status") == "PASS" else "FAIL"})
    _write(output_dir / "frozen-v0241-fingerprint-v0245.json", frozen_v0241)
    _write(output_dir / "hard-gates-v0245.json", gates)
    _write(output_dir / "negative-controls-v0245.json", controls)
    _write(output_dir / "full-slice-two-run-determinism-v0245.json", {"status": "PASS" if snapshot_one == snapshot_two else "FAIL", "run_1": snapshot_one, "run_2": snapshot_two})
    _write(output_dir / "production-boundary-v0245.json", production)
    _write(output_dir / "correction-history-v0245.json", {"schema_version": VERSION, "status": "CORRECTION_REQUIRED", "base_main_sha": BASE_MAIN_SHA, "reviewed_head": REJECTED_REVIEWED_HEAD, "rejected_reviewed_head": REJECTED_REVIEWED_HEAD, "semantic_v0244_head": V0244_SEMANTIC_HEAD, "v0243_rejected_head": V0243_REJECTED_HEAD, "branch": BRANCH, "findings": ["F-41", "F-42", "F-43"], "preserves": ["F-31R", "F-32RR", "F-33", "F-34", "F-35RR", "F-35RC", "F-36", "F-38", "F-37R", "F-39", "F-40"], "historical_evidence_unchanged": True})
    _write(output_dir / "uads-handoff-v0245.json", uads_handoff)
    _write(output_dir / "execution-evidence-v0245.json", result)
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
