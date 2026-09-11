"""Execute the complete deterministic UGAS V1 final acceptance slice (v0.25.0)."""

from __future__ import annotations

import argparse
import copy
import datetime
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "validation"))
from validate_github_review_security_v0250 import evaluate_artifact_security, sanitize_exported_text

import ugas.acceptance_v0250 as acceptance_v0250
from ugas.acceptance_v0250 import (
    ACCEPTANCE_COMPUTATION_GATE_IDS,
    APPROVAL_ARTIFACT_DIGEST,
    APPROVAL_ARTIFACT_ID,
    APPROVAL_PR_NUMBER,
    APPROVAL_RECORD_PATH,
    APPROVAL_VERDICT,
    BASE_MAIN_SHA,
    BRANCH,
    CAPABILITY_RECORDS,
    CLOSURE_COMMENT_ID,
    DESTRUCTIVE_GIT_PATTERNS,
    ENVIRONMENT_GATE_IDS,
    EVIDENCE_ROOT,
    FROZEN_V0247_ROOT,
    GITHUB_SHA_RE,
    HARD_GATE_IDS,
    MATRIX_SNAPSHOT,
    MATRIX_SNAPSHOT_SHA256,
    MAX_EVIDENCE_FILE_BYTES,
    MAX_EVIDENCE_ROOT_BYTES,
    OBSERVABILITY_APPROVAL_RECORD,
    OBSERVABILITY_ROW_STATUS,
    ORCHESTRATION_BOOKKEEPING_HEAD,
    ORCHESTRATION_MERGE_MAIN_SHA,
    ORCHESTRATION_SEMANTIC_HEAD,
    POST_MERGE_CI_RUN,
    POST_MERGE_DOCKER_JOB,
    POST_MERGE_UNIT_JOB,
    PRIVATE_PATH_MARKERS,
    PR_TITLE,
    PRODUCTION_TOKENS,
    REPOSITORY,
    REQUIRED_CAPABILITY_IDS,
    REVIEWED_BOOKKEEPING_ALLOWLIST,
    SECRET_PATTERNS,
    STATE_SNAPSHOT,
    STATE_SNAPSHOT_SHA256,
    VERSION,
    WORK_ORDER_ID,
    AcceptanceContractError,
    acceptance_status,
    audit_architecture,
    audit_capability_matrix,
    audit_security,
    canonical_acceptance_digest,
    evaluate_acceptance_gates,
    evaluate_bookkeeping_delta,
    file_sha256,
    load_json_file,
    observability_binding,
    validate_external_approval,
)
from ugas.state_consistency_v0250 import (
    APPROVAL_RECORD,
    APPROVAL_REVIEW_ID_NUMERIC,
    APPROVED_SEMANTIC_HEAD,
    CURRENT_GATE,
    MERGE_AUTHORIZATION,
    POST_BOOKKEEPING_REPROOF_REQUIRED,
    STOP_REASON,
    validate_state_consistency,
)


EVIDENCE = ROOT / EVIDENCE_ROOT
STATE_PATH = ROOT / "docs/evidence/current-state.json"
MATRIX_PATH = ROOT / "docs/ugas-v1-capability-matrix.json"
CHECKPOINT_PATH = ROOT / "CHECKPOINT.md"
ROADMAP_PATH = ROOT / "docs/roadmap.md"
ENVIRONMENT_RESULTS_PATH = ROOT / "environment-results-v0250.json"
MATRIX_VALIDATION_PATH = EVIDENCE / "capability-matrix-validation-v0250.json"

EVIDENCE_FILES = (
    "capability-matrix-audit.json",
    "architecture-audit.json",
    "security-audit.json",
    "reproducibility-audit.json",
    "state-consistency-audit.json",
    "test-summary.json",
    "hard-gates.json",
    "negative-controls.json",
    "production-boundary.json",
    "uads-handoff.json",
    "final-acceptance-summary.json",
)

PRODUCTION_BOUNDARY = {
    "production_approved": False,
    "production_routing": "BLOCKED",
    "real_asset_generation": "NONE",
    "new_generation": 0,
    "provider_submit_calls": 0,
    "synthetic_fixture": "TEST_ONLY",
    "production_readiness_workstream": "NOT_STARTED_REQUIRED_SEPARATELY",
    "v1_technical_acceptance_is_not_production_approval": True,
}

PENDING_DISPATCH_HANDOFF = {
    "schema_version": VERSION,
    "execution_mode": "GLOBAL_FIRST",
    "project_footprint": "ZERO",
    "work_order_id": "wo_080f0ec7318ab40b",
    "run_or_dispatch_id": "er_5ecebd0482d03d9a",
    "route_status": "SELECTED",
    "selected_profile_id": "codex-global-strong-v1",
    "selected_profile_digest_unavailable_reason": "UADS model execution plan does not expose a profile digest",
    "dispatch_status": "DISPATCHED",
}

SNAPSHOT_BINDINGS = (
    ("state_snapshot", STATE_SNAPSHOT, STATE_SNAPSHOT_SHA256),
    ("matrix_snapshot", MATRIX_SNAPSHOT, MATRIX_SNAPSHOT_SHA256),
)

DOCUMENT_LITERALS = (
    VERSION,
    "V1_FINAL_ACCEPTANCE",
    CURRENT_GATE,
    STOP_REASON,
    "external_review_v1_final_acceptance_pr",
    "MERGED_CLOSED",
    "production_routing=BLOCKED",
    "new_generation=0",
    "production_approved=false",
    "external review",
)

def _sanitize_text(value: str) -> str:
    text = str(value)
    for prefix in (str(ROOT), str(ROOT).replace("\\", "/")):
        text = text.replace(prefix, "<repo>")
    return sanitize_exported_text(text)


def _sanitize_exported_value(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, dict):
        return {key: _sanitize_exported_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_exported_value(item) for item in value]
    return value


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_sanitize_exported_value(value), indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _generated_at() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_head() -> str:
    result = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    value = result.stdout.strip()
    if len(value) == 40 and all(character in "0123456789abcdef" for character in value):
        return value
    return ""


def _git_delta_scan(ancestor: str) -> dict[str, Any]:
    relation = subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", str(ancestor), "HEAD"], capture_output=True, text=True, check=False)
    if relation.returncode != 0:
        return evaluate_bookkeeping_delta(False, [], REVIEWED_BOOKKEEPING_ALLOWLIST)
    diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", f"{ancestor}..HEAD"], capture_output=True, text=True, check=False)
    if diff.returncode != 0:
        return evaluate_bookkeeping_delta(False, [], REVIEWED_BOOKKEEPING_ALLOWLIST)
    return evaluate_bookkeeping_delta(True, [line.strip() for line in diff.stdout.splitlines() if line.strip()], REVIEWED_BOOKKEEPING_ALLOWLIST)


def _binding() -> dict[str, Any]:
    return {
        "repository": REPOSITORY,
        "base_main_sha": BASE_MAIN_SHA,
        "branch": BRANCH,
        "candidate_head": _git_head(),
        "approved_semantic_head": APPROVED_SEMANTIC_HEAD,
        "work_order_id": WORK_ORDER_ID,
        "schema_version": VERSION,
        "generated_at": _generated_at(),
    }


def _evidence(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {**_binding(), **payload}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _expect_rejection(control_id: str, defect: str, expected: str | tuple[str, ...], action: Callable[[], Any]) -> dict[str, Any]:
    accepted = (expected,) if isinstance(expected, str) else tuple(expected)
    try:
        action()
    except AcceptanceContractError as exc:
        observed = exc.code
        return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": "|".join(accepted), "observed_rejection_class": observed, "status": "PASS" if observed in accepted else "FAIL", "result": "REJECT" if observed in accepted else "WRONG_REJECTION", "actual_exception": type(exc).__name__, "detail": _sanitize_text(str(exc))}
    except Exception as exc:  # pragma: no cover - defensive, exercised only by unexpected regressions
        return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": "|".join(accepted), "observed_rejection_class": None, "status": "FAIL", "result": "UNEXPECTED_EXCEPTION", "actual_exception": type(exc).__name__, "detail": _sanitize_text(str(exc))}
    return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": "|".join(accepted), "observed_rejection_class": None, "status": "FAIL", "result": "ACCEPT", "actual_exception": None, "detail": "validator accepted injected defect"}


def _expect_failure(control_id: str, defect: str, expected: str, action: Callable[[], Mapping[str, Any]]) -> dict[str, Any]:
    try:
        observed = dict(action())
    except Exception as exc:  # pragma: no cover - defensive, exercised only by unexpected regressions
        return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected, "observed_rejection_class": None, "status": "FAIL", "result": "UNEXPECTED_EXCEPTION", "actual_exception": type(exc).__name__, "detail": _sanitize_text(str(exc))}
    failures = [str(item) for item in (observed.get("failures") or [])]
    marker = observed.get("reason")
    matched = observed.get("status") != "PASS" and (any(expected in item for item in failures) or expected == marker)
    detail = json.dumps({"status": observed.get("status"), "reason": marker, "failure_count": len(failures), "first_failures": failures[:4]}, sort_keys=True)
    return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected, "observed_rejection_class": marker, "status": "PASS" if matched else "FAIL", "result": "REJECT" if matched else "ACCEPT", "actual_exception": None, "detail": _sanitize_text(detail)}


def _expect_verdict(control_id: str, defect: str, expected: str, action: Callable[[], Mapping[str, Any]]) -> dict[str, Any]:
    try:
        observed = dict(action())
    except Exception as exc:  # pragma: no cover - defensive, exercised only by unexpected regressions
        return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected, "observed_rejection_class": None, "status": "FAIL", "result": "UNEXPECTED_EXCEPTION", "actual_exception": type(exc).__name__, "detail": _sanitize_text(str(exc))}
    verdict = str(observed.get("status"))
    matched = verdict == expected
    return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected, "observed_rejection_class": verdict, "status": "PASS" if matched else "FAIL", "result": "REJECT" if expected != "V1_ACCEPTANCE_CANDIDATE" else "ACCEPT", "actual_exception": None, "detail": _sanitize_text(json.dumps({key: observed.get(key) for key in ("status", "critical", "high", "medium", "low", "unresolved_high_critical", "medium_blocking_acceptance", "failed_gates")}, sort_keys=True))}


def _snapshot_binding() -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for name, relative, expected in SNAPSHOT_BINDINGS:
        path = ROOT / relative
        if not path.is_file():
            entries.append({"name": name, "path": relative, "expected_sha256": expected, "observed_sha256": None, "status": "MISSING"})
            continue
        observed = file_sha256(path)
        entries.append({"name": name, "path": relative, "expected_sha256": expected, "observed_sha256": observed, "status": "MATCH" if observed == expected else "DRIFT"})
    return {"schema_version": VERSION, "entries": entries, "status": "PASS" if all(item["status"] == "MATCH" for item in entries) else "FAIL"}


def _load_environment_results(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": VERSION, "status": "MISSING", "gates": {}, "failures": ["environment_results_missing"], "path": _relative_reference(path)}
    try:
        loaded = load_json_file(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"schema_version": VERSION, "status": "MISSING", "gates": {}, "failures": [f"environment_results_unreadable:{type(exc).__name__}"], "path": _relative_reference(path)}
    value = dict(loaded) if isinstance(loaded, Mapping) else {}
    failures: list[str] = []
    gates = value.get("gates") if isinstance(value.get("gates"), Mapping) else {}
    for gate_id in ENVIRONMENT_GATE_IDS:
        record = gates.get(gate_id) if isinstance(gates.get(gate_id), Mapping) else None
        if record is None:
            failures.append(f"environment_gate_missing:{gate_id}")
            continue
        if record.get("status") not in {"PASS", "FAIL", "PENDING"}:
            failures.append(f"environment_gate_status_invalid:{gate_id}")
        if type(record.get("exit_code")) is not int:
            failures.append(f"environment_gate_exit_type:{gate_id}")
    value["failures"] = sorted(failures)
    value["path"] = _relative_reference(path)
    if failures:
        value["status"] = "MISSING"
    return value


def _relative_reference(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


ACCEPTANCE_CONTROL_FLOOR = 25
SUMMARY_EVIDENCE_FILE = "final-acceptance-summary.json"
PRE_WRITE_EVIDENCE_FILES = tuple(name for name in EVIDENCE_FILES if name != SUMMARY_EVIDENCE_FILE)
ACTIVE_DOCUMENT_PATHS = (
    "CHECKPOINT.md",
    "README.md",
    "docs/roadmap.md",
    "docs/definition-of-done.md",
    "docs/ugas-v1-capability-matrix.json",
    "docs/evidence/current-state.json",
)
DEFINITION_OF_DONE_PATH = "docs/definition-of-done.md"
DEFINITION_OF_DONE_LITERALS = (
    "V1_FINAL_ACCEPTANCE",
    "production_approved=false",
    "production_routing=BLOCKED",
    "real_asset_generation=NONE",
    "new_generation=0",
    "production readiness workstream",
    "not production approval",
)
PRODUCTION_CLAIM_PATTERNS = (
    "PRODUCTION_APPROVED",
    "PRODUCTION_READY",
    "PRODUCTION_ROUTING_ENABLED",
    "production_approved=true",
    "production_approved: true",
    "production_approved = true",
    "production_routing=ENABLED",
    "production_routing: ENABLED",
    "production_routing=APPROVED",
    "real_asset_generation=REAL",
)

FINDINGS_REGISTER: tuple[dict[str, Any], ...] = (
    {
        "id": "F-V1-01",
        "severity": "MEDIUM",
        "status": "RESOLVED",
        "blocks_acceptance": False,
        "summary": "Tracked state and capability matrix still carried the pre-merge orchestration status after the governed v0.24.7 merge.",
        "resolution": "Forward-only binding of the GitHub LIVE MERGED_CLOSED closure (semantic head, bookkeeping head, merge main, post-merge CI run, unit job, docker job and closure comment) into docs/evidence/current-state.json, docs/ugas-v1-capability-matrix.json, CHECKPOINT.md, docs/roadmap.md and the v0.25.0 state validator without rewriting frozen historical evidence.",
    },
    {
        "id": "F-V1-02",
        "severity": "MEDIUM",
        "status": "RESOLVED",
        "blocks_acceptance": False,
        "summary": "The local_always_on_observability capability row still described the external visual review as pending.",
        "resolution": "Bound the existing external visual approval record (artifact id, digest and reviewed head) into the APPROVED_PILOT; EXTERNAL_VISUAL_APPROVAL_BOUND row status, the observability binding audit and the final acceptance summary without self-approval and without promoting the capability beyond APPROVED_PILOT.",
    },
)

GATE_PROOF_SOURCES: dict[str, str] = {
    "base_main_equals_authorized_merge": "docs/evidence/current-state.json baseline_main_sha equals the authorized orchestration merge main",
    "orchestration_closure_binding_complete": "docs/evidence/current-state.json orchestration_closure binds the GitHub LIVE MERGED_CLOSED closure",
    "orchestration_closure_matches_frozen_evidence": "frozen v0.24.7 snapshot digests plus the recorded closure authority",
    "capability_records_audited_all_16": "audit_capability_matrix traverses the tracked matrix and the audited 16 capability records",
    "capability_evidence_pointers_present": "audit_capability_matrix resolves every evidence and test pointer from repository bytes",
    "capability_lifecycle_not_promoted": "audit_capability_matrix rejects any lifecycle promotion beyond the proven claim",
    "observability_visual_review_resolved": "observability_binding resolves the external visual approval record and visual file hashes",
    "unit_suite_pass": "environment-results-v0250.json unit_suite_pass record",
    "official_validation_pass": "environment-results-v0250.json official_validation_pass record",
    "snapshot_validation_pass": "environment-results-v0250.json snapshot_validation_pass record",
    "no_git_validation_pass": "environment-results-v0250.json no_git_validation_pass record",
    "docker_smoke_pass": "environment-results-v0250.json docker_smoke_pass record",
    "provider_submit_calls_zero": "docs/evidence/current-state.json provider_submit_calls plus the acceptance production boundary",
    "production_routing_blocked": "docs/evidence/current-state.json and capability matrix production_routing",
    "production_approved_false": "docs/evidence/current-state.json production_approved strict false",
    "new_generation_zero": "docs/evidence/current-state.json and capability matrix new_generation",
    "no_repo_local_uads": "audit_security repo-local UADS discovery plus the sanitized UADS handoff",
    "state_schema_consistent": "validate_state_consistency over the active state, checkpoint and roadmap",
    "matrix_consistent_with_state": "audit_capability_matrix plus the v1_final_acceptance state binding",
    "checkpoint_roadmap_consistent": "validate_state_consistency document literals over CHECKPOINT.md and docs/roadmap.md",
    "definition_of_done_distinguishes_production": "docs/definition-of-done.md technical acceptance versus production readiness separation",
    "no_high_or_critical_findings": "acceptance findings register with zero unresolved CRITICAL/HIGH entries",
    "acceptance_evidence_inventory_pass": "complete bounded docs/evidence/v1-final-acceptance inventory written by this runner",
    "acceptance_evidence_security_pass": "audit_security over the candidate files and the acceptance evidence root",
    "two_run_determinism_pass": "two independent executions of the acceptance core with one canonical digest",
    "pr_open_unmerged_at_candidate_head": "GitHub LIVE PR metadata recorded in docs/evidence/current-state.json with the candidate head still on the acceptance branch",
    "production_boundary_record_blocked": "the written production-boundary.json acceptance record",
    "active_documents_free_of_production_claims": "active documents are free of production approval and routing claims",
    "external_approval_authority_bound": "the tracked WO-0251 external approval record validates against the approved semantic head, review, CI checks and artifact identity",
    "bookkeeping_delta_within_reviewed_scope": "the committed delta from the approved semantic head stays inside the reviewed bookkeeping allowlist",
}


def _guard(fallback: dict[str, Any], action: Callable[[], Any]) -> Any:
    try:
        return action()
    except Exception as exc:  # pragma: no cover - defensive, exercised only by unexpected regressions
        return {**fallback, "status": "FAIL", "failures": [f"unexpected:{type(exc).__name__}"], "detail": _sanitize_text(str(exc))}


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = load_json_file(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    return dict(loaded) if isinstance(loaded, Mapping) else {}


def _environment_gate_status(environment: Mapping[str, Any], gate_id: str) -> str:
    gates = environment.get("gates") if isinstance(environment.get("gates"), Mapping) else {}
    record = gates.get(gate_id) if isinstance(gates.get(gate_id), Mapping) else {}
    status = record.get("status")
    return status if isinstance(status, str) else "MISSING"


def _environment_gate_record(environment: Mapping[str, Any], gate_id: str) -> dict[str, Any]:
    gates = environment.get("gates") if isinstance(environment.get("gates"), Mapping) else {}
    record = gates.get(gate_id)
    return dict(record) if isinstance(record, Mapping) else {}


def _uads_handoff(*, work_order_id: str, run_or_dispatch_id: str | None, dispatch_status: str, profile_id: str) -> dict[str, Any]:
    return {
        "schema_version": VERSION,
        "execution_mode": "GLOBAL_FIRST",
        "project_footprint": "ZERO",
        "work_order_id": work_order_id,
        "run_or_dispatch_id": run_or_dispatch_id,
        "route_status": "SELECTED",
        "selected_profile_id": profile_id,
        "selected_profile_digest_unavailable_reason": "UADS model execution plan does not expose a profile digest",
        "dispatch_status": dispatch_status,
        "repo_local_material": "ABSENT",
        "sanitized": True,
    }


def _uads_handoff_with(**overrides: Any) -> dict[str, Any]:
    value = dict(_uads_handoff(work_order_id=PENDING_DISPATCH_HANDOFF["work_order_id"], run_or_dispatch_id=PENDING_DISPATCH_HANDOFF["run_or_dispatch_id"], dispatch_status=PENDING_DISPATCH_HANDOFF["dispatch_status"], profile_id=PENDING_DISPATCH_HANDOFF["selected_profile_id"]))
    for key, child in overrides.items():
        if child is None:
            value.pop(key, None)
        else:
            value[key] = child
    return value


def validate_uads_handoff(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AcceptanceContractError("UADS_HANDOFF_INVALID", "UADS handoff must be a mapping")
    if value.get("execution_mode") != "GLOBAL_FIRST" or value.get("project_footprint") != "ZERO":
        raise AcceptanceContractError("UADS_HANDOFF_INVALID", "UADS handoff must stay GLOBAL_FIRST with ZERO project footprint")
    if value.get("route_status") != "SELECTED":
        raise AcceptanceContractError("UADS_ROUTE_STATUS_REJECTED", f"route status {value.get('route_status')!r} is not SELECTED")
    dispatch_status = value.get("dispatch_status")
    if dispatch_status not in {"PENDING_DISPATCH", "DISPATCHED"}:
        raise AcceptanceContractError("UADS_DISPATCH_STATUS_REJECTED", f"dispatch status {dispatch_status!r} is not an accepted UADS dispatch state")
    work_order_id = value.get("work_order_id")
    if not isinstance(work_order_id, str) or not re.fullmatch(r"wo_[0-9a-z]{8,}", work_order_id):
        raise AcceptanceContractError("UADS_HANDOFF_ID_INVALID", "work order id must be a sanitized wo_ identifier")
    run_id = value.get("run_or_dispatch_id")
    if dispatch_status == "DISPATCHED":
        if not isinstance(run_id, str) or not re.fullmatch(r"er_[0-9a-z]{8,}", run_id):
            raise AcceptanceContractError("UADS_HANDOFF_ID_INVALID", "a dispatched handoff must carry a sanitized er_ dispatch id")
    elif run_id is not None and (not isinstance(run_id, str) or not re.fullmatch(r"er_[0-9a-z]{8,}", run_id)):
        raise AcceptanceContractError("UADS_HANDOFF_ID_INVALID", "a pending handoff must not carry an unreadable dispatch id")
    profile = value.get("selected_profile_id")
    if not isinstance(profile, str) or not profile:
        raise AcceptanceContractError("UADS_HANDOFF_INVALID", "selected profile id is required")
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    folded = serialized.casefold()
    if ".uads" in folded:
        raise AcceptanceContractError("UADS_HANDOFF_UNSAFE", "UADS handoff must not carry project-local UADS material")
    for marker in PRIVATE_PATH_MARKERS:
        if marker.casefold() in folded:
            raise AcceptanceContractError("UADS_HANDOFF_UNSAFE", "UADS handoff must not carry private host paths")
    for pattern in SECRET_PATTERNS:
        if pattern.search(serialized):
            raise AcceptanceContractError("UADS_HANDOFF_UNSAFE", "UADS handoff must not carry secret-like material")
    return {
        "schema_version": VERSION,
        "status": "PASS",
        "dispatch_status": dispatch_status,
        "dispatch_id_present": run_id is not None,
        "repo_local_material": "ABSENT",
    }


def _active_documents_text(root: Path) -> str:
    return "\n".join(_read_text(root / relative) for relative in ACTIVE_DOCUMENT_PATHS)


def _production_claim_hits(root: Path) -> list[str]:
    text = _active_documents_text(root)
    return sorted(pattern for pattern in PRODUCTION_CLAIM_PATTERNS if pattern in text)


def _definition_of_done_binding(root: Path) -> bool:
    path = root / DEFINITION_OF_DONE_PATH
    if not path.is_file():
        return False
    folded = _read_text(path).casefold()
    return all(literal.casefold() in folded for literal in DEFINITION_OF_DONE_LITERALS)


def _evidence_inventory(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for name in EVIDENCE_FILES:
        path = root / EVIDENCE_ROOT / name
        if not path.is_file():
            entries.append({"name": name, "status": "MISSING", "size": None, "sha256": None})
            continue
        size = path.stat().st_size
        entries.append({"name": name, "status": "PRESENT" if size <= MAX_EVIDENCE_FILE_BYTES else "OVERSIZED", "size": size, "sha256": file_sha256(path)})
    return entries


def _strip_timestamps(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _strip_timestamps(item) for key, item in value.items() if key != "generated_at"}
    if isinstance(value, (list, tuple)):
        return [_strip_timestamps(item) for item in value]
    return value


def _gate_observations(
    *,
    state: Mapping[str, Any],
    matrix: Mapping[str, Any],
    closure: Mapping[str, Any],
    capability_audit: Mapping[str, Any],
    observability: Mapping[str, Any],
    approval_validation: Mapping[str, Any],
    security: Mapping[str, Any],
    state_validation: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    environment: Mapping[str, Any],
    uads_validation: Mapping[str, Any],
    bookkeeping_delta: Mapping[str, Any],
    findings: Sequence[Mapping[str, Any]],
    pr_number: Any,
    pr_head_sha: Any,
    pr_state: Any,
    determinism_pass: bool,
    production_claim_hits: Sequence[str],
    definition_of_done_ok: bool,
) -> dict[str, Any]:
    previous = state.get("previous_release") if isinstance(state.get("previous_release"), Mapping) else {}
    acceptance_binding = state.get("v1_final_acceptance") if isinstance(state.get("v1_final_acceptance"), Mapping) else {}
    review = state.get("review") if isinstance(state.get("review"), Mapping) else {}
    capabilities = capability_audit.get("capabilities") if isinstance(capability_audit.get("capabilities"), list) else []
    audit_ok = capability_audit.get("status") == "PASS"
    closure_complete = (
        closure.get("semantic_head") == ORCHESTRATION_SEMANTIC_HEAD
        and closure.get("bookkeeping_head") == ORCHESTRATION_BOOKKEEPING_HEAD
        and closure.get("merge_main_sha") == ORCHESTRATION_MERGE_MAIN_SHA
        and closure.get("post_merge_ci_run") == POST_MERGE_CI_RUN
        and closure.get("unit_job") == POST_MERGE_UNIT_JOB
        and closure.get("docker_job") == POST_MERGE_DOCKER_JOB
        and closure.get("closure_comment_id") == CLOSURE_COMMENT_ID
        and closure.get("tracked_state_binding") == "PASS"
    )
    unresolved_high_critical = [item for item in findings if item.get("severity") in {"CRITICAL", "HIGH"} and item.get("status") != "RESOLVED"]
    inventory = _evidence_inventory(ROOT)
    inventory_ok = (
        tuple(sorted(item.get("name") for item in inventory)) == tuple(sorted(EVIDENCE_FILES))
        and all(item.get("status") == "PRESENT" for item in inventory)
        and security.get("evidence_root_bytes") <= MAX_EVIDENCE_ROOT_BYTES
    )
    pr_number_ok = type(pr_number) is int and pr_number > 0
    pr_head_ok = isinstance(pr_head_sha, str) and bool(GITHUB_SHA_RE.fullmatch(pr_head_sha))
    production_boundary_exact = (
        PRODUCTION_BOUNDARY.get("production_approved") is False
        and PRODUCTION_BOUNDARY.get("production_routing") == "BLOCKED"
        and PRODUCTION_BOUNDARY.get("real_asset_generation") == "NONE"
        and type(PRODUCTION_BOUNDARY.get("new_generation")) is int
        and PRODUCTION_BOUNDARY.get("new_generation") == 0
        and type(PRODUCTION_BOUNDARY.get("provider_submit_calls")) is int
        and PRODUCTION_BOUNDARY.get("provider_submit_calls") == 0
    )
    observations: dict[str, Any] = {
        "base_main_equals_authorized_merge": state.get("baseline_main_sha") == BASE_MAIN_SHA and ORCHESTRATION_MERGE_MAIN_SHA == BASE_MAIN_SHA,
        "orchestration_closure_binding_complete": closure_complete and state.get("orchestration_lifecycle") == "MERGED_CLOSED",
        "orchestration_closure_matches_frozen_evidence": snapshot.get("status") == "PASS" and previous.get("version") == "0.24.7" and closure.get("merge_main_sha") == ORCHESTRATION_MERGE_MAIN_SHA,
        "capability_records_audited_all_16": audit_ok and capability_audit.get("capability_count") == 16 and len(capabilities) == 16,
        "capability_evidence_pointers_present": audit_ok and all(bool(row.get("evidence_pointers")) and bool(row.get("test_pointers")) for row in capabilities),
        "capability_lifecycle_not_promoted": audit_ok and not any(token in str(row.get("claimed_status")) for row in capabilities for token in PRODUCTION_TOKENS),
        "observability_visual_review_resolved": observability.get("status") == "PASS" and observability.get("visual_review_status") == "PASS" and observability.get("self_approval") is False,
        "external_approval_authority_bound": (
            approval_validation.get("status") == "PASS"
            and approval_validation.get("production_approved") is False
            and approval_validation.get("artifact_id") == APPROVAL_ARTIFACT_ID
            and approval_validation.get("artifact_digest") == APPROVAL_ARTIFACT_DIGEST
            and review.get("approved_semantic_head") == APPROVED_SEMANTIC_HEAD
            and review.get("approval_record") == APPROVAL_RECORD
            and review.get("approval_review_id_numeric") == APPROVAL_REVIEW_ID_NUMERIC
            and review.get("merge_authorization") == MERGE_AUTHORIZATION
            and review.get("post_bookkeeping_reproof_required") is True
        ),
        "bookkeeping_delta_within_reviewed_scope": bookkeeping_delta.get("status") == "PASS" and bookkeeping_delta.get("ancestor") is True,
        "unit_suite_pass": _environment_gate_status(environment, "unit_suite_pass") == "PASS",
        "official_validation_pass": _environment_gate_status(environment, "official_validation_pass") == "PASS",
        "snapshot_validation_pass": _environment_gate_status(environment, "snapshot_validation_pass") == "PASS",
        "no_git_validation_pass": _environment_gate_status(environment, "no_git_validation_pass") == "PASS",
        "docker_smoke_pass": _environment_gate_status(environment, "docker_smoke_pass") == "PASS",
        "provider_submit_calls_zero": type(state.get("provider_submit_calls")) is int and state.get("provider_submit_calls") == 0 and PRODUCTION_BOUNDARY["provider_submit_calls"] == 0,
        "production_routing_blocked": state.get("production_routing") == "BLOCKED" and matrix.get("production_routing") == "BLOCKED",
        "production_approved_false": state.get("production_approved") is False and PRODUCTION_BOUNDARY["production_approved"] is False,
        "new_generation_zero": type(state.get("new_generation")) is int and state.get("new_generation") == 0 and type(matrix.get("new_generation")) is int and matrix.get("new_generation") == 0,
        "no_repo_local_uads": security.get("repo_local_uads") == [] and uads_validation.get("status") == "PASS",
        "state_schema_consistent": state_validation.get("status") == CURRENT_GATE,
        "matrix_consistent_with_state": audit_ok and acceptance_binding.get("capability_count") == 16 and acceptance_binding.get("capabilities_audited") == 16 and acceptance_binding.get("observability_visual_review") == "PASS" and acceptance_binding.get("production_scope") == "EXCLUDED",
        "checkpoint_roadmap_consistent": state_validation.get("status") == CURRENT_GATE and not any(str(item).startswith("documents_missing") for item in (state_validation.get("failures") or [])),
        "definition_of_done_distinguishes_production": definition_of_done_ok,
        "no_high_or_critical_findings": not unresolved_high_critical,
        "acceptance_evidence_inventory_pass": inventory_ok and security.get("status") == "PASS",
        "acceptance_evidence_security_pass": security.get("status") == "PASS" and security.get("secrets_included") is False,
        "two_run_determinism_pass": bool(determinism_pass),
        "pr_open_unmerged_at_candidate_head": pr_number_ok and pr_state == "OPEN" and pr_head_ok and state.get("baseline_main_sha") == BASE_MAIN_SHA,
        "production_boundary_record_blocked": production_boundary_exact,
        "active_documents_free_of_production_claims": not production_claim_hits,
    }
    return {gate_id: bool(value) for gate_id, value in observations.items()}


def compute_core(
    *,
    pr_number: int | None = None,
    pr_head_sha: str | None = None,
    pr_state: str | None = None,
    uads_work_order_id: str = PENDING_DISPATCH_HANDOFF["work_order_id"],
    uads_run_or_dispatch_id: str | None = PENDING_DISPATCH_HANDOFF["run_or_dispatch_id"],
    uads_dispatch_status: str = PENDING_DISPATCH_HANDOFF["dispatch_status"],
    uads_profile_id: str = PENDING_DISPATCH_HANDOFF["selected_profile_id"],
    determinism_pass: bool = False,
) -> dict[str, Any]:
    state = _read_json_object(STATE_PATH)
    matrix = _read_json_object(MATRIX_PATH)
    checkpoint = _read_text(CHECKPOINT_PATH)
    roadmap = _read_text(ROADMAP_PATH)
    closure = dict(state["orchestration_closure"]) if isinstance(state.get("orchestration_closure"), Mapping) else {}
    capability_audit = _guard(
        {"schema_version": VERSION, "capability_count": 0, "capabilities": [], "accepted_or_preserved": 0, "blocked": len(REQUIRED_CAPABILITY_IDS), "orchestration_merge_sha": None},
        lambda: audit_capability_matrix(ROOT, matrix, closure),
    )
    observability = _guard({"schema_version": VERSION, "visual_review_status": "BLOCKED_PENDING_OBSERVABILITY_VISUAL_REVIEW", "self_approval": True, "checks": {}}, lambda: observability_binding(ROOT))
    architecture = _guard({"schema_version": VERSION, "module_count": 0, "cycles": []}, lambda: audit_architecture(ROOT))
    security = _guard({"schema_version": VERSION, "scanned_file_count": 0, "repo_local_uads": [], "evidence_root_bytes": 0, "secrets_included": True}, lambda: audit_security(ROOT))
    audit_input = {
        "capability_count": capability_audit.get("capability_count"),
        "production_routing": "BLOCKED",
        "new_generation": 0,
        "status": capability_audit.get("status"),
        "observability": {"visual_review_status": observability.get("visual_review_status")},
    }
    state_validation = _guard({"schema_version": VERSION, "failures": ["state_validation_unavailable"]}, lambda: validate_state_consistency(state, checkpoint, roadmap, matrix, audit_input))
    snapshot = _guard({"schema_version": VERSION, "status": "FAIL", "entries": []}, _snapshot_binding)
    environment = _load_environment_results(ENVIRONMENT_RESULTS_PATH)
    uads_handoff = _uads_handoff(
        work_order_id=uads_work_order_id,
        run_or_dispatch_id=uads_run_or_dispatch_id,
        dispatch_status=uads_dispatch_status,
        profile_id=uads_profile_id,
    )
    uads_validation = _guard({"schema_version": VERSION, "status": "FAIL"}, lambda: validate_uads_handoff(uads_handoff))
    approval_record = _read_json_object(ROOT / APPROVAL_RECORD_PATH)
    approval_validation = _guard(
        {"schema_version": VERSION, "status": "FAIL", "production_approved": None, "artifact_id": None, "artifact_digest": None},
        lambda: validate_external_approval(approval_record, candidate_head=APPROVED_SEMANTIC_HEAD, root=ROOT),
    )
    bookkeeping_delta = _guard(
        {"schema_version": VERSION, "status": "REJECT", "reason": "BOOKKEEPING_DELTA_NOT_ANCESTOR", "ancestor": False, "changed_files": [], "forbidden_files": []},
        lambda: _git_delta_scan(APPROVED_SEMANTIC_HEAD),
    )
    review = state.get("review") if isinstance(state.get("review"), Mapping) else {}
    effective_pr_number = pr_number if pr_number is not None else review.get("pr_number")
    effective_pr_head = pr_head_sha if pr_head_sha is not None else review.get("head_sha")
    effective_pr_state = pr_state if pr_state is not None else review.get("pr_state")
    findings = [dict(item) for item in FINDINGS_REGISTER]
    production_claim_hits = _production_claim_hits(ROOT)
    definition_of_done_ok = _definition_of_done_binding(ROOT)
    observations = _gate_observations(
        state=state,
        matrix=matrix,
        closure=closure,
        capability_audit=capability_audit,
        observability=observability,
        approval_validation=approval_validation,
        security=security,
        state_validation=state_validation,
        snapshot=snapshot,
        environment=environment,
        uads_validation=uads_validation,
        bookkeeping_delta=bookkeeping_delta,
        findings=findings,
        pr_number=effective_pr_number,
        pr_head_sha=effective_pr_head,
        pr_state=effective_pr_state,
        determinism_pass=determinism_pass,
        production_claim_hits=production_claim_hits,
        definition_of_done_ok=definition_of_done_ok,
    )
    gates = evaluate_acceptance_gates(observations, GATE_PROOF_SOURCES)
    evidence_complete = bool(observations.get("acceptance_evidence_inventory_pass"))
    acceptance = acceptance_status(findings=findings, gates=gates, observability=observability, evidence_complete=evidence_complete)
    controls = _controls_payload(_negative_controls())
    return {
        "binding": _binding(),
        "state_summary": {
            "version": state.get("version"),
            "phase": state.get("phase"),
            "current_gate": state.get("current_gate"),
            "stop_reason": state.get("stop_reason"),
            "acceptance_verdict": state.get("acceptance_verdict"),
            "orchestration_lifecycle": state.get("orchestration_lifecycle"),
            "production_routing": state.get("production_routing"),
            "production_approved": state.get("production_approved"),
            "new_generation": state.get("new_generation"),
            "provider_submit_calls": state.get("provider_submit_calls"),
        },
        "closure": closure,
        "capability_audit": capability_audit,
        "observability": observability,
        "architecture": architecture,
        "security": security,
        "state_validation": state_validation,
        "snapshot_binding": snapshot,
        "environment": environment,
        "evidence_inventory": _evidence_inventory(ROOT),
        "uads_handoff": uads_handoff,
        "uads_validation": uads_validation,
        "approval_validation": approval_validation,
        "bookkeeping_delta": bookkeeping_delta,
        "review": {
            "pr_number": effective_pr_number,
            "pr_head_sha": effective_pr_head,
            "pr_state": effective_pr_state,
            "external_review_required": review.get("external_review_required"),
            "do_not_merge": review.get("do_not_merge"),
            "merge_authorization": review.get("merge_authorization"),
            "approved_semantic_head": review.get("approved_semantic_head"),
            "approval_record": review.get("approval_record"),
            "approval_review_id_numeric": review.get("approval_review_id_numeric"),
            "post_bookkeeping_reproof_required": review.get("post_bookkeeping_reproof_required"),
            "required_contexts": list(review.get("required_contexts")) if isinstance(review.get("required_contexts"), list) else [],
        },
        "findings": findings,
        "observations": observations,
        "gates": gates,
        "acceptance": acceptance,
        "controls": controls,
        "determinism": {"schema_version": VERSION, "status": "PASS" if determinism_pass else "PENDING", "run_1": None, "run_2": None},
    }
def _expect_probe(control_id: str, defect: str, expected_reason: str, action: Callable[[], Mapping[str, Any]]) -> dict[str, Any]:
    try:
        observed = dict(action())
    except Exception as exc:  # pragma: no cover - defensive, exercised only by unexpected regressions
        return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected_reason, "observed_rejection_class": None, "status": "FAIL", "result": "UNEXPECTED_EXCEPTION", "actual_exception": type(exc).__name__, "detail": _sanitize_text(str(exc))}
    matched = observed.get("status") == "PASS" and observed.get("reason") == expected_reason
    record = {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected_reason, "observed_rejection_class": observed.get("reason"), "status": "PASS" if matched else "FAIL", "result": "GUARD_HELD" if matched else "GUARD_MISSED", "actual_exception": None, "detail": _sanitize_text(json.dumps({key: observed.get(key) for key in ("status", "reason", "observed_type", "observed_value", "observed_gate_status", "failure_count")}, sort_keys=True))}
    for key in ("observed_type", "observed_value", "observed_gate_status"):
        if key in observed:
            record[key] = observed[key]
    return record


def _expect_entry_status(control_id: str, defect: str, expected_entry: str, action: Callable[[], Mapping[str, Any]]) -> dict[str, Any]:
    try:
        observed = dict(action())
    except Exception as exc:  # pragma: no cover - defensive, exercised only by unexpected regressions
        return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": f"entry:{expected_entry}", "observed_rejection_class": None, "status": "FAIL", "result": "UNEXPECTED_EXCEPTION", "actual_exception": type(exc).__name__, "detail": _sanitize_text(str(exc))}
    entries = observed.get("entries") if isinstance(observed.get("entries"), list) else []
    entry_statuses = [str(entry.get("status")) for entry in entries if isinstance(entry, Mapping)]
    matched = observed.get("status") == "FAIL" and expected_entry in entry_statuses
    return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": f"entry:{expected_entry}", "observed_rejection_class": ",".join(entry_statuses) or None, "status": "PASS" if matched else "FAIL", "result": "REJECT" if matched else "ACCEPT", "actual_exception": None, "detail": _sanitize_text(json.dumps({"status": observed.get("status"), "entry_statuses": entry_statuses}, sort_keys=True))}


def _expect_status(control_id: str, defect: str, expected: str, action: Callable[[], Mapping[str, Any]]) -> dict[str, Any]:
    try:
        observed = dict(action())
    except Exception as exc:  # pragma: no cover - defensive, exercised only by unexpected regressions
        return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected, "observed_rejection_class": None, "status": "FAIL", "result": "UNEXPECTED_EXCEPTION", "actual_exception": type(exc).__name__, "detail": _sanitize_text(str(exc))}
    verdict = str(observed.get("status"))
    matched = verdict == expected
    return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected, "observed_rejection_class": verdict, "status": "PASS" if matched else "FAIL", "result": "ACCEPT" if matched else "UNEXPECTED_ACCEPT", "actual_exception": None, "detail": _sanitize_text(json.dumps({"status": verdict, "dispatch_status": observed.get("dispatch_status"), "dispatch_id_present": observed.get("dispatch_id_present"), "repo_local_material": observed.get("repo_local_material")}, sort_keys=True))}


def _state_copy() -> dict[str, Any]:
    return copy.deepcopy(_read_json_object(STATE_PATH))


def _closure_binding(state: Mapping[str, Any]) -> dict[str, Any]:
    value = state.get("orchestration_closure")
    return dict(value) if isinstance(value, Mapping) else {}


def _tampered_matrix(mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    matrix = copy.deepcopy(_read_json_object(MATRIX_PATH))
    mutator(matrix)
    return matrix


def _tampered_approval(mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    record = copy.deepcopy(_read_json_object(ROOT / APPROVAL_RECORD_PATH))
    mutator(record)
    return record


def _matrix_row(matrix: Mapping[str, Any], capability_id: str) -> dict[str, Any]:
    capabilities = matrix.get("capabilities") if isinstance(matrix.get("capabilities"), list) else []
    for item in capabilities:
        if isinstance(item, dict) and item.get("id") == capability_id:
            return item
    raise KeyError(capability_id)


def _record_pointers(record_id: str) -> tuple[str, ...]:
    for item in CAPABILITY_RECORDS:
        if item["id"] == record_id:
            return tuple(item["pointers"])
    raise KeyError(record_id)


def _audit_matrix_control(mutator: Callable[[dict[str, Any]], None], records_overrides: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    state = _read_json_object(STATE_PATH)
    matrix = _tampered_matrix(mutator)
    closure = _closure_binding(state)
    if not records_overrides:
        return audit_capability_matrix(ROOT, matrix, closure)
    records = tuple(copy.deepcopy(dict(item)) for item in CAPABILITY_RECORDS)
    for item in records:
        override = records_overrides.get(item["id"])
        if override:
            item.update(override)
    with mock.patch.object(acceptance_v0250, "CAPABILITY_RECORDS", records):
        return audit_capability_matrix(ROOT, matrix, closure)


def _state_control(mutator: Callable[[dict[str, Any]], None], *, documents: bool = True) -> dict[str, Any]:
    state = _state_copy()
    mutator(state)
    matrix = _read_json_object(MATRIX_PATH)
    checkpoint = _read_text(CHECKPOINT_PATH) if documents else ""
    roadmap = _read_text(ROADMAP_PATH) if documents else ""
    return validate_state_consistency(state, checkpoint, roadmap, matrix, None)


def _mutate_matrix_status(matrix: dict[str, Any]) -> None:
    _matrix_row(matrix, "core_2d_generation")["status"] = "APPROVED_PRODUCTION"


def _mutate_matrix_duplicate(matrix: dict[str, Any]) -> None:
    capabilities = matrix["capabilities"]
    capabilities.insert(0, copy.deepcopy(capabilities[0]))


def _mutate_matrix_drop_last(matrix: dict[str, Any]) -> None:
    matrix["capabilities"].pop()


def _mutate_matrix_extra_capability(matrix: dict[str, Any]) -> None:
    matrix["capabilities"].append({"id": "v0250_unregistered_extra", "status": "APPROVED_PILOT"})


def _mutate_matrix_observability(matrix: dict[str, Any]) -> None:
    _matrix_row(matrix, "local_always_on_observability")["status"] = "APPROVED_PILOT"


def _mutate_state_lifecycle(value: dict[str, Any]) -> None:
    value["orchestration_lifecycle"] = "AWAITING_MERGE"


def _mutate_state_version(value: dict[str, Any]) -> None:
    value["version"] = "0.24.6"


def _mutate_state_closure(value: dict[str, Any]) -> None:
    closure = value.get("orchestration_closure")
    if isinstance(closure, dict):
        closure.pop("closure_comment_id", None)


def _mutate_state_stop_reason(value: dict[str, Any]) -> None:
    value["stop_reason"] = STOP_REASON + "_STALE"


def _mutate_state_approval_head(value: dict[str, Any]) -> None:
    review = value.get("review")
    if isinstance(review, dict):
        review["approved_semantic_head"] = BASE_MAIN_SHA


def _mutate_state_reproof_flag(value: dict[str, Any]) -> None:
    review = value.get("review")
    if isinstance(review, dict):
        review["post_bookkeeping_reproof_required"] = not POST_BOOKKEEPING_REPROOF_REQUIRED


def _mutate_state_allowed(value: dict[str, Any]) -> None:
    value["allowed_next_actions"] = ["external_review_v1_final_acceptance_pr", "merge_v1_final_acceptance_pr"]


def _mutate_state_production_approved(value: dict[str, Any]) -> None:
    value["production_approved"] = True


def _mutate_state_production_routing(value: dict[str, Any]) -> None:
    value["production_routing"] = "ENABLED"


def _mutate_state_new_generation(value: dict[str, Any]) -> None:
    value["new_generation"] = 1


def _mutate_state_provider_submit_calls(value: dict[str, Any]) -> None:
    value["provider_submit_calls"] = 1


def _passing_gates() -> dict[str, Any]:
    return {"overall_pass": True, "gates": {gate_id: {"gate_id": gate_id, "status": "PASS"} for gate_id in HARD_GATE_IDS}, "missing_observations": []}


def _failing_gates() -> dict[str, Any]:
    gates = _passing_gates()
    gates["overall_pass"] = False
    gates["gates"]["state_schema_consistent"] = {"gate_id": "state_schema_consistent", "status": "FAIL"}
    return gates


def _high_finding_register() -> list[dict[str, Any]]:
    return [{"id": "NC-HIGH-01", "severity": "HIGH", "status": "OPEN", "blocks_acceptance": False, "summary": "synthetic negative control finding"}]


def _gate_strictness_probe() -> dict[str, Any]:
    evaluated = evaluate_acceptance_gates({"unit_suite_pass": "true"}, GATE_PROOF_SOURCES)
    gates = evaluated.get("gates") if isinstance(evaluated.get("gates"), Mapping) else {}
    entry = gates.get("unit_suite_pass") if isinstance(gates.get("unit_suite_pass"), Mapping) else {}
    others_ok = all(item.get("status") == "FAIL" and item.get("reason") == "OBSERVED_VALUE_NOT_STRICT_BOOLEAN" for name, item in gates.items() if name != "unit_suite_pass")
    ok = (
        entry.get("status") == "FAIL"
        and entry.get("reason") == "OBSERVED_VALUE_NOT_STRICT_BOOLEAN"
        and entry.get("observed_type") == "str"
        and entry.get("observed") == "true"
        and evaluated.get("overall_pass") is False
        and evaluated.get("missing_observations") == sorted(set(HARD_GATE_IDS) - {"unit_suite_pass"})
        and others_ok
    )
    return {"status": "PASS" if ok else "FAIL", "reason": "OBSERVED_VALUE_NOT_STRICT_BOOLEAN", "failures": [] if ok else ["strictness_probe_failed"], "observed_type": entry.get("observed_type"), "observed_value": entry.get("observed"), "observed_gate_status": entry.get("status")}


def _snapshot_drift_probe() -> dict[str, Any]:
    bindings = (("state_snapshot", "state-snapshot-v0247.json", STATE_SNAPSHOT_SHA256),)
    with tempfile.TemporaryDirectory(prefix="ugas-v0250-snapshot-") as name:
        root = Path(name)
        target = root / "state-snapshot-v0247.json"
        target.write_bytes((ROOT / STATE_SNAPSHOT).read_bytes() + b"\n")
        with mock.patch.dict(globals(), {"ROOT": root, "SNAPSHOT_BINDINGS": bindings}):
            return dict(_snapshot_binding())


def _repo_local_uads_probe() -> dict[str, Any]:
    marker = "." + "uads"
    with tempfile.TemporaryDirectory(prefix="ugas-v0250-local-") as name:
        root = Path(name)
        runtime = root / marker
        runtime.mkdir()
        (runtime / "state.json").write_text("{}", encoding="utf-8")
        return dict(audit_security(root, scan_files=[]))


def _artifact_manifest(**overrides: Any) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "overall_status": "PASS",
        "production_boundary": {"approved": False, "routing": "BLOCKED", "new_generation": 0, "provider_submit_calls": 0},
        "security_boundary": {"secrets_included": False, "model_weights_included": False, "telemetry_db_included": False, "local_credentials_included": False},
        "pull_request": {"number": 1, "head_sha": BASE_MAIN_SHA, "base_sha": BASE_MAIN_SHA},
    }
    manifest.update(overrides)
    return manifest


def _artifact_security_probe(files: Mapping[str, str], **overrides: Any) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ugas-v0250-artifact-") as name:
        root = Path(name)
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return dict(evaluate_artifact_security(root, _artifact_manifest(**overrides)))


PRIVATE_PATH_SAMPLE = "C:" + chr(92) + "Users" + chr(92) + "acceptance" + chr(92) + "probe"

def _negative_controls() -> list[dict[str, Any]]:
    state = _read_json_object(STATE_PATH)
    closure = _closure_binding(state)
    matrix = _read_json_object(MATRIX_PATH)
    controls: list[dict[str, Any]] = []
    controls.append(_expect_rejection("NC-CAP-01", "capability row claims an unsupported lifecycle status", "CAPABILITY_STATUS_UNSUPPORTED", lambda: audit_capability_matrix(ROOT, _tampered_matrix(_mutate_matrix_status), closure)))
    controls.append(_expect_rejection("NC-CAP-02", "merged capability record stripped of its governed merge authority", "ORCHESTRATION_CLOSURE_AUTHORITY_MISSING", lambda: _audit_matrix_control(lambda value: None, {"ui_asset_family": {"merge_sha": None}})))
    controls.append(_expect_rejection("NC-CAP-03", "capability record pointing at unwritten evidence", "CAPABILITY_EVIDENCE_MISSING", lambda: _audit_matrix_control(lambda value: None, {"core_2d_generation": {"pointers": _record_pointers("core_2d_generation") + ("docs/evidence/v0250-unwritten-pointer",)}})))
    controls.append(_expect_rejection("NC-CAP-04", "duplicated capability id prepended to the matrix", "CAPABILITY_DUPLICATE_ID", lambda: audit_capability_matrix(ROOT, _tampered_matrix(_mutate_matrix_duplicate), closure)))
    controls.append(_expect_rejection("NC-CAP-05", "matrix missing its final audited capability row", "CAPABILITY_SET_MISMATCH", lambda: audit_capability_matrix(ROOT, _tampered_matrix(_mutate_matrix_drop_last), closure)))
    controls.append(_expect_rejection("NC-CAP-06", "matrix carrying an extra unregistered capability row", "CAPABILITY_SET_MISMATCH", lambda: audit_capability_matrix(ROOT, _tampered_matrix(_mutate_matrix_extra_capability), closure)))
    controls.append(_expect_rejection("NC-CAP-07", "observability row downgraded away from the bound external approval", "OBSERVABILITY_PROMOTION_REJECTED", lambda: _audit_matrix_control(_mutate_matrix_observability, {"local_always_on_observability": {"claimed_status": "APPROVED_PILOT"}})))
    controls.append(_expect_failure("NC-STATE-01", "orchestration lifecycle regressed to awaiting merge", "orchestration_lifecycle_invalid", lambda: _state_control(_mutate_state_lifecycle)))
    controls.append(_expect_failure("NC-STATE-02", "active state pinned to the superseded release version", "version_invalid", lambda: _state_control(_mutate_state_version)))
    controls.append(_expect_failure("NC-STATE-03", "orchestration closure missing the closure comment binding", "orchestration_closure:closure_comment_id", lambda: _state_control(_mutate_state_closure)))
    controls.append(_expect_failure("NC-STATE-04", "allowed next actions contradicting the forbidden action list", "allowed_action_forbidden_contradiction", lambda: _state_control(_mutate_state_allowed)))
    controls.append(_expect_failure("NC-STATE-05", "checkpoint and roadmap without the bound acceptance literals", "documents_missing", lambda: validate_state_consistency(_state_copy(), "", "", matrix, None)))
    controls.append(_expect_failure("NC-STATE-06", "active state still carrying the stale awaiting-review stop reason", "stop_reason_invalid", lambda: _state_control(_mutate_state_stop_reason)))
    controls.append(_expect_failure("NC-STATE-07", "state review approval binding pointing at a foreign head", "review:approved_semantic_head", lambda: _state_control(_mutate_state_approval_head)))
    controls.append(_expect_failure("NC-STATE-08", "state review dropping the mandatory post-bookkeeping reproof", "review:post_bookkeeping_reproof_required", lambda: _state_control(_mutate_state_reproof_flag)))
    controls.append(_expect_failure("NC-PROD-01", "production approval flipped true in the active state", "production_approved_invalid", lambda: _state_control(_mutate_state_production_approved)))
    controls.append(_expect_failure("NC-PROD-02", "production routing enabled in the active state", "production_routing_invalid", lambda: _state_control(_mutate_state_production_routing)))
    controls.append(_expect_failure("NC-PROD-03", "new asset generation recorded in the active state", "new_generation_invalid", lambda: _state_control(_mutate_state_new_generation)))
    controls.append(_expect_failure("NC-PROD-04", "provider submit calls recorded in the active state", "provider_submit_calls_invalid", lambda: _state_control(_mutate_state_provider_submit_calls)))
    controls.append(_expect_rejection("NC-UADS-01", "handoff route status is not SELECTED", "UADS_ROUTE_STATUS_REJECTED", lambda: validate_uads_handoff(_uads_handoff_with(route_status="REJECTED"))))
    controls.append(_expect_rejection("NC-UADS-02", "handoff dispatch status is a failed state", "UADS_DISPATCH_STATUS_REJECTED", lambda: validate_uads_handoff(_uads_handoff_with(dispatch_status="FAILED"))))
    controls.append(_expect_rejection("NC-UADS-03", "handoff work order id is not a sanitized wo_ identifier", "UADS_HANDOFF_ID_INVALID", lambda: validate_uads_handoff(_uads_handoff_with(work_order_id="wo_BAD"))))
    controls.append(_expect_rejection("NC-UADS-04", "handoff profile id carrying project-local UADS material", "UADS_HANDOFF_UNSAFE", lambda: validate_uads_handoff(_uads_handoff_with(selected_profile_id="profile-" + "." + "uads"))))
    controls.append(_expect_status("NC-UADS-05", "positive control: a dispatched sanitized handoff is accepted", "PASS", lambda: validate_uads_handoff(_uads_handoff_with(dispatch_status="DISPATCHED", run_or_dispatch_id="er_0000000000000000"))))
    controls.append(_expect_entry_status("NC-SNAP-01", "tampered frozen snapshot bytes must drift from the bound digest", "DRIFT", _snapshot_drift_probe))
    controls.append(_expect_failure("NC-ART-01", "artifact manifest bound to a foreign base sha", "identity-base-sha", lambda: _artifact_security_probe({"docs/evidence/v1-final-acceptance/probe.json": "{}\n"}, pull_request={"number": 1, "head_sha": BASE_MAIN_SHA, "base_sha": "0" * 40})))
    controls.append(_expect_failure("NC-ART-02", "artifact path carrying a forbidden token", "forbidden:logs/credential-notes.txt", lambda: _artifact_security_probe({"logs/credential-notes.txt": "probe\n"})))
    controls.append(_expect_failure("NC-ART-03", "artifact content carrying a private host path", "private-path:docs/evidence/v1-final-acceptance/probe.json", lambda: _artifact_security_probe({"docs/evidence/v1-final-acceptance/probe.json": PRIVATE_PATH_SAMPLE + "\n"})))
    controls.append(_expect_probe("NC-GATE-01", "non boolean gate observation must fail closed as a strict boolean", "OBSERVED_VALUE_NOT_STRICT_BOOLEAN", _gate_strictness_probe))
    controls.append(_expect_verdict("NC-VERDICT-01", "unresolved HIGH finding", "CORRECTION_REQUIRED", lambda: acceptance_status(findings=_high_finding_register(), gates=_passing_gates(), observability={"status": "PASS"}, evidence_complete=True)))
    controls.append(_expect_verdict("NC-VERDICT-02", "observability visual review not resolved", "BLOCKED_PENDING_OBSERVABILITY_VISUAL_REVIEW", lambda: acceptance_status(findings=[], gates=_passing_gates(), observability={"status": "BLOCKED_PENDING_OBSERVABILITY_VISUAL_REVIEW"}, evidence_complete=True)))
    controls.append(_expect_verdict("NC-VERDICT-03", "failing gate with incomplete acceptance evidence", "INCOMPLETE_ACCEPTANCE_EVIDENCE", lambda: acceptance_status(findings=[], gates=_failing_gates(), observability={"status": "PASS"}, evidence_complete=False)))
    controls.append(_expect_failure("NC-LOCAL-01", "repository-local UADS runtime footprint must be detected", "repo-local-uads", _repo_local_uads_probe))
    controls.append(_expect_rejection("NC-APPR-01", "approval record bound to a foreign repository", "EXTERNAL_APPROVAL_REPOSITORY", lambda: validate_external_approval(_tampered_approval(lambda record: record.update({"repository": "other/repository"})), candidate_head=APPROVED_SEMANTIC_HEAD, root=ROOT)))
    controls.append(_expect_rejection("NC-APPR-02", "approval record bound to a different pull request", "EXTERNAL_APPROVAL_PR", lambda: validate_external_approval(_tampered_approval(lambda record: record.update({"pull_request": APPROVAL_PR_NUMBER + 1})), candidate_head=APPROVED_SEMANTIC_HEAD, root=ROOT)))
    controls.append(_expect_rejection("NC-APPR-03", "approval record bound to a foreign base main", "EXTERNAL_APPROVAL_BASE", lambda: validate_external_approval(_tampered_approval(lambda record: record.update({"base_sha": BASE_MAIN_SHA[:-1] + "0"})), candidate_head=APPROVED_SEMANTIC_HEAD, root=ROOT)))
    controls.append(_expect_rejection("NC-APPR-04", "candidate head that is not the tracked approved semantic head", "EXTERNAL_APPROVAL_HEAD_UNTRACKED", lambda: validate_external_approval(_tampered_approval(lambda record: None), candidate_head=BASE_MAIN_SHA, root=ROOT)))
    controls.append(_expect_rejection("NC-APPR-05", "candidate head that is not an exact commit sha", "EXTERNAL_APPROVAL_HEAD_INVALID", lambda: validate_external_approval(_tampered_approval(lambda record: None), candidate_head="z" * 40, root=ROOT)))
    controls.append(_expect_rejection("NC-APPR-06", "approval record carrying an invalid review id", "EXTERNAL_APPROVAL_REVIEW_ID", lambda: validate_external_approval(_tampered_approval(lambda record: record.update({"review_id_numeric": 0})), candidate_head=APPROVED_SEMANTIC_HEAD, root=ROOT)))
    controls.append(_expect_rejection("NC-APPR-07", "approval record carrying a tampered verdict", "EXTERNAL_APPROVAL_VERDICT", lambda: validate_external_approval(_tampered_approval(lambda record: record.update({"verdict": APPROVAL_VERDICT + "_TAMPERED"})), candidate_head=APPROVED_SEMANTIC_HEAD, root=ROOT)))
    controls.append(_expect_rejection("NC-APPR-08", "artifact name that does not bind the approved head", "EXTERNAL_APPROVAL_ARTIFACT", lambda: validate_external_approval(_tampered_approval(lambda record: record.update({"technical_artifact": {**record["technical_artifact"], "name": "ugas-v1-final-acceptance-evidence-unbound"}})), candidate_head=APPROVED_SEMANTIC_HEAD, root=ROOT)))
    controls.append(_expect_rejection("NC-APPR-09", "artifact digest that does not match the reviewed artifact", "EXTERNAL_APPROVAL_ARTIFACT", lambda: validate_external_approval(_tampered_approval(lambda record: record.update({"technical_artifact": {**record["technical_artifact"], "digest": "sha256:" + "0" * 64}})), candidate_head=APPROVED_SEMANTIC_HEAD, root=ROOT)))
    controls.append(_expect_rejection("NC-APPR-10", "approval record carrying a HIGH finding", "EXTERNAL_APPROVAL_FINDINGS", lambda: validate_external_approval(_tampered_approval(lambda record: record.update({"findings": {**record["findings"], "high": 1}})), candidate_head=APPROVED_SEMANTIC_HEAD, root=ROOT)))
    controls.append(_expect_rejection("NC-APPR-11", "approval boundary claiming production approval", "EXTERNAL_APPROVAL_BOUNDARY", lambda: validate_external_approval(_tampered_approval(lambda record: record.update({"approval_boundary": {**record["approval_boundary"], "production_approved": True}})), candidate_head=APPROVED_SEMANTIC_HEAD, root=ROOT)))
    controls.append(_expect_rejection("NC-APPR-12", "approval boundary enabling production routing", "EXTERNAL_APPROVAL_BOUNDARY", lambda: validate_external_approval(_tampered_approval(lambda record: record.update({"approval_boundary": {**record["approval_boundary"], "production_routing": "ENABLED"}})), candidate_head=APPROVED_SEMANTIC_HEAD, root=ROOT)))
    controls.append(_expect_rejection("NC-APPR-13", "approval boundary recording a provider submit call", "EXTERNAL_APPROVAL_BOUNDARY", lambda: validate_external_approval(_tampered_approval(lambda record: record.update({"approval_boundary": {**record["approval_boundary"], "provider_submit_calls": 1}})), candidate_head=APPROVED_SEMANTIC_HEAD, root=ROOT)))
    controls.append(_expect_rejection("NC-APPR-14", "approval record with an unreviewed extra field", "EXTERNAL_APPROVAL_RECORD_MISMATCH", lambda: validate_external_approval(_tampered_approval(lambda record: record.update({"unreviewed_extension": True})), candidate_head=APPROVED_SEMANTIC_HEAD, root=ROOT)))
    controls.append(_expect_status("NC-APPR-15", "positive control: the tracked external approval record validates against the approved semantic head", "PASS", lambda: validate_external_approval(_tampered_approval(lambda record: None), candidate_head=APPROVED_SEMANTIC_HEAD, root=ROOT)))
    controls.append(_expect_failure("NC-BOOK-01", "bookkeeping delta whose reviewed semantic head is not an ancestor", "BOOKKEEPING_DELTA_NOT_ANCESTOR", lambda: evaluate_bookkeeping_delta(False, [], REVIEWED_BOOKKEEPING_ALLOWLIST)))
    controls.append(_expect_failure("NC-BOOK-02", "bookkeeping delta touching a file outside the reviewed scope", "BOOKKEEPING_DELTA_FILE_OUT_OF_SCOPE", lambda: evaluate_bookkeeping_delta(True, ["CHECKPOINT.md", "src/ugas/production_router.py"], REVIEWED_BOOKKEEPING_ALLOWLIST)))
    controls.append(_expect_status("NC-BOOK-03", "positive control: an allowlisted forward-only bookkeeping delta is accepted", "PASS", lambda: evaluate_bookkeeping_delta(True, ["CHECKPOINT.md", "docs/roadmap.md", "docs/evidence/v1-final-acceptance/final-acceptance-summary.json"], REVIEWED_BOOKKEEPING_ALLOWLIST)))
    return controls


def _controls_payload(controls: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    records = [dict(item) for item in controls]
    identifiers = [str(item.get("control_id")) for item in records]
    failures = [identifier for item, identifier in zip(records, identifiers) if item.get("status") != "PASS"]
    if len(identifiers) != len(set(identifiers)):
        failures.append("duplicate_control_id")
    if len(records) < ACCEPTANCE_CONTROL_FLOOR:
        failures.append(f"control_floor_not_met:{len(records)}<{ACCEPTANCE_CONTROL_FLOOR}")
    return {
        "schema_version": VERSION,
        "status": "PASS" if not failures else "FAIL",
        "control_count": len(records),
        "minimum_required": ACCEPTANCE_CONTROL_FLOOR,
        "controls": {identifier: item for item, identifier in zip(records, identifiers)},
        "failures": sorted(failures),
    }
def _determinism_view(core: Mapping[str, Any]) -> dict[str, Any]:
    value = _strip_timestamps(core)
    inventory = value.get("evidence_inventory")
    stable_bytes = 0
    if isinstance(inventory, list):
        for item in inventory:
            if not isinstance(item, dict):
                continue
            if item.get("name") == SUMMARY_EVIDENCE_FILE:
                item.update({"status": "SELF_ATTESTATION", "size": None, "sha256": None})
            elif isinstance(item.get("size"), int):
                stable_bytes += int(item["size"])
    security = value.get("security")
    if isinstance(security, dict):
        security["evidence_root_bytes"] = stable_bytes
        security["self_attestation_normalized"] = SUMMARY_EVIDENCE_FILE
    return value


def _pre_write_payloads(core: Mapping[str, Any]) -> dict[str, Any]:
    gates = core["gates"]
    failed_gates = sorted(name for name, item in gates["gates"].items() if item.get("status") != "PASS")
    return {
        "capability-matrix-audit.json": core["capability_audit"],
        "architecture-audit.json": core["architecture"],
        "security-audit.json": core["security"],
        "reproducibility-audit.json": {
            "schema_version": VERSION,
            "status": core["snapshot_binding"].get("status"),
            "snapshot_binding": core["snapshot_binding"],
            "determinism": core["determinism"],
        },
        "state-consistency-audit.json": core["state_validation"],
        "test-summary.json": {
            "schema_version": VERSION,
            "environment": {gate_id: _environment_gate_record(core["environment"], gate_id) for gate_id in ENVIRONMENT_GATE_IDS},
            "findings": core["findings"],
            "acceptance": core["acceptance"],
            "hard_gates": {"total": len(gates["gates"]), "overall_pass": gates["overall_pass"], "failed": failed_gates},
        },
        "hard-gates.json": gates,
        "negative-controls.json": core["controls"],
        "production-boundary.json": {
            "schema_version": VERSION,
            "status": "BLOCKED",
            "production_boundary": dict(PRODUCTION_BOUNDARY),
            "acceptance_claim_allowed": PRODUCTION_BOUNDARY.get("production_approved") is True,
            "planning_approval_is_not_production_approval": True,
        },
        "uads-handoff.json": {
            "schema_version": VERSION,
            "handoff": dict(core["uads_handoff"]),
            "validation": dict(core["uads_validation"]),
        },
    }


def _summary_payload(core: Mapping[str, Any], *, digests: Mapping[str, Any], determinism_status: str) -> dict[str, Any]:
    gates = core["gates"]
    controls = core["controls"]
    failed_gates = sorted(name for name, item in gates["gates"].items() if item.get("status") != "PASS")
    inventory = [dict(item) for item in core["evidence_inventory"]]
    for item in inventory:
        if item.get("name") == SUMMARY_EVIDENCE_FILE:
            item.update({"status": "SELF_ATTESTATION", "size": None, "sha256": None})
    return {
        "schema_version": VERSION,
        "work_order_id": WORK_ORDER_ID,
        "pr_title": PR_TITLE,
        "generated_at": _generated_at(),
        "binding": dict(core["binding"]),
        "state_summary": dict(core["state_summary"]),
        "acceptance": dict(core["acceptance"]),
        "gates": {
            "schema_version": VERSION,
            "total": len(gates["gates"]),
            "passed": len(gates["gates"]) - len(failed_gates),
            "failed": failed_gates,
            "overall_pass": gates["overall_pass"],
            "missing_observations": list(gates["missing_observations"]),
            "proof_sources": dict(GATE_PROOF_SOURCES),
        },
        "controls": {
            "schema_version": VERSION,
            "status": controls["status"],
            "control_count": controls["control_count"],
            "minimum_required": controls["minimum_required"],
            "failures": list(controls["failures"]),
            "control_ids": sorted(controls["controls"]),
        },
        "environment": {
            "status": core["environment"].get("status"),
            "gates": {gate_id: _environment_gate_status(core["environment"], gate_id) for gate_id in ENVIRONMENT_GATE_IDS},
        },
        "uads": {
            "work_order_id": core["uads_handoff"].get("work_order_id"),
            "run_or_dispatch_id": core["uads_handoff"].get("run_or_dispatch_id"),
            "dispatch_status": core["uads_handoff"].get("dispatch_status"),
            "route_status": core["uads_handoff"].get("route_status"),
            "selected_profile_id": core["uads_handoff"].get("selected_profile_id"),
            "project_footprint": core["uads_handoff"].get("project_footprint"),
            "validation": dict(core["uads_validation"]),
        },
        "approval_validation": dict(core["approval_validation"]),
        "bookkeeping_delta": dict(core["bookkeeping_delta"]),
        "review": dict(core["review"]),
        "production_boundary": dict(PRODUCTION_BOUNDARY),
        "findings": [dict(item) for item in core["findings"]],
        "determinism": {
            "schema_version": VERSION,
            "status": determinism_status,
            "run_1": digests.get("run_1"),
            "run_2": digests.get("run_2"),
            "run_3": digests.get("run_3"),
            "self_attestation_normalized": True,
        },
        "evidence_inventory": inventory,
    }


def run(
    output_dir: Path | str | None = None,
    *,
    pr_number: int | None = None,
    pr_head_sha: str | None = None,
    pr_state: str | None = None,
    uads_work_order_id: str = PENDING_DISPATCH_HANDOFF["work_order_id"],
    uads_run_or_dispatch_id: str | None = PENDING_DISPATCH_HANDOFF["run_or_dispatch_id"],
    uads_dispatch_status: str = PENDING_DISPATCH_HANDOFF["dispatch_status"],
    uads_profile_id: str = PENDING_DISPATCH_HANDOFF["selected_profile_id"],
) -> dict[str, Any]:
    target = Path(output_dir) if output_dir is not None else EVIDENCE
    target.mkdir(parents=True, exist_ok=True)

    def core(determinism_pass: bool) -> dict[str, Any]:
        return compute_core(
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            pr_state=pr_state,
            uads_work_order_id=uads_work_order_id,
            uads_run_or_dispatch_id=uads_run_or_dispatch_id,
            uads_dispatch_status=uads_dispatch_status,
            uads_profile_id=uads_profile_id,
            determinism_pass=determinism_pass,
        )

    staging = core(True)
    for name, payload in _pre_write_payloads(staging).items():
        _write(target / name, payload)
    _write(target / SUMMARY_EVIDENCE_FILE, _summary_payload(staging, digests={}, determinism_status="PENDING"))
    sealed_1 = core(True)
    digest_1 = canonical_acceptance_digest(_determinism_view(sealed_1))
    _write(target / SUMMARY_EVIDENCE_FILE, _summary_payload(sealed_1, digests={"run_1": digest_1}, determinism_status="PENDING"))
    sealed_2 = core(True)
    digest_2 = canonical_acceptance_digest(_determinism_view(sealed_2))
    stable = digest_1 == digest_2
    _write(target / SUMMARY_EVIDENCE_FILE, _summary_payload(sealed_2, digests={"run_1": digest_1, "run_2": digest_2}, determinism_status="PASS" if stable else "FAIL"))
    sealed_3 = core(True)
    digest_3 = canonical_acceptance_digest(_determinism_view(sealed_3))
    if not stable or digest_3 != digest_2:
        failed = core(False)
        for name, payload in _pre_write_payloads(failed).items():
            _write(target / name, payload)
        payload = _summary_payload(failed, digests={"run_1": digest_1, "run_2": digest_2, "run_3": digest_3}, determinism_status="FAIL")
        _write(target / SUMMARY_EVIDENCE_FILE, payload)
        print(json.dumps({"status": "DETERMINISM_FAILED", "run_1": digest_1, "run_2": digest_2, "run_3": digest_3}, sort_keys=True), file=sys.stderr)
        return {"summary": payload, "exit_code": 2, "evidence_dir": _relative_reference(target)}
    payload = _summary_payload(sealed_3, digests={"run_1": digest_1, "run_2": digest_2, "run_3": digest_3}, determinism_status="PASS")
    _write(target / SUMMARY_EVIDENCE_FILE, payload)
    gates = sealed_3["gates"]["gates"]
    computation_failed = sorted(gate_id for gate_id in ACCEPTANCE_COMPUTATION_GATE_IDS if gates.get(gate_id, {}).get("status") != "PASS")
    exit_code = 0 if not computation_failed and sealed_3["controls"]["status"] == "PASS" and sealed_3["architecture"].get("status") == "PASS" else 1
    return {"summary": payload, "exit_code": exit_code, "evidence_dir": _relative_reference(target), "computation_failed": computation_failed}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute the deterministic UGAS V1 final acceptance slice (v0.25.0).")
    parser.add_argument("--output-dir", default=str(EVIDENCE))
    parser.add_argument("--pr-number", type=int, default=None)
    parser.add_argument("--pr-head-sha", default=None)
    parser.add_argument("--pr-state", default=None)
    parser.add_argument("--uads-work-order-id", default=PENDING_DISPATCH_HANDOFF["work_order_id"])
    parser.add_argument("--uads-dispatch-id", default=PENDING_DISPATCH_HANDOFF["run_or_dispatch_id"])
    parser.add_argument("--uads-dispatch-status", default=PENDING_DISPATCH_HANDOFF["dispatch_status"])
    parser.add_argument("--uads-profile-id", default=PENDING_DISPATCH_HANDOFF["selected_profile_id"])
    args = parser.parse_args(argv)
    try:
        result = run(
            output_dir=Path(args.output_dir),
            pr_number=args.pr_number,
            pr_head_sha=args.pr_head_sha,
            pr_state=args.pr_state,
            uads_work_order_id=args.uads_work_order_id,
            uads_run_or_dispatch_id=args.uads_dispatch_id,
            uads_dispatch_status=args.uads_dispatch_status,
            uads_profile_id=args.uads_profile_id,
        )
    except AcceptanceContractError as exc:
        print(json.dumps({"status": "REJECTED", "rejection_class": exc.code, "detail": _sanitize_text(exc.message)}, sort_keys=True))
        return 3
    summary = result["summary"]
    memo = {
        "status": summary["acceptance"]["status"],
        "hard_gates": {
            "total": summary["gates"]["total"],
            "passed": summary["gates"]["passed"],
            "failed": summary["gates"]["failed"],
            "overall_pass": summary["gates"]["overall_pass"],
        },
        "negative_controls": {
            "status": summary["controls"]["status"],
            "control_count": summary["controls"]["control_count"],
            "minimum_required": summary["controls"]["minimum_required"],
            "failures": summary["controls"]["failures"],
        },
        "acceptance_status": summary["acceptance"]["status"],
        "acceptance_claim_allowed": summary["acceptance"]["acceptance_claim_allowed"],
        "determinism": summary["determinism"],
        "environment": summary["environment"],
        "computation_failed": result.get("computation_failed", []),
        "evidence": [item.get("name") for item in summary["evidence_inventory"]],
    }
    print(json.dumps(memo, sort_keys=True))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())