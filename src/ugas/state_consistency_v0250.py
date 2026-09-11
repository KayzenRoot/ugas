"""Fail-closed active-state validator for the UGAS V1 final acceptance (v0.25.0)."""

from __future__ import annotations

from typing import Any, Mapping

VERSION = "0.25.0"
PHASE = "V1_FINAL_ACCEPTANCE"
BASELINE_MAIN_SHA = "6c6d53dab5a95226bf9578a6099d755d51327d8e"
BRANCH = "codex/v1-final-acceptance"
PR_TITLE = "UGAS V1 Final Acceptance"
PREVIOUS_RELEASE_VERSION = "0.24.7"
CURRENT_GATE = "V1_TECHNICAL_BASELINE_EXTERNALLY_APPROVED_PENDING_GOVERNED_MERGE"
STOP_REASON = "V1_TECHNICAL_BASELINE_EXTERNALLY_APPROVED_AWAITING_GOVERNED_MERGE"
ACCEPTANCE_VERDICT = "V1_ACCEPTANCE_CANDIDATE"
NEXT_ACTION = "external_review_v1_final_acceptance_pr"
NEXT_CANDIDATE = "V1_FINAL_ACCEPTANCE"
MERGE_AUTHORIZATION = "GOVERNED_MERGE_ONLY_AFTER_EXACT_HEAD_BOOKKEEPING_REVIEW"
ORCHESTRATION_SEMANTIC_HEAD = "6b1af57ec5f488d71bafafa17a892467adf1d1c1"
ORCHESTRATION_BOOKKEEPING_HEAD = "984a517d823aa426778c3bf2469eed72457eb028"
ORCHESTRATION_MERGE_MAIN_SHA = BASELINE_MAIN_SHA
POST_MERGE_CI_RUN = 34523428088
POST_MERGE_UNIT_JOB = 103026362729
POST_MERGE_DOCKER_JOB = 103026362968
CLOSURE_COMMENT_ID = 5625161567
ORCHESTRATION_LIFECYCLE = "MERGED_CLOSED"
OBSERVABILITY_STATUS = "APPROVED_PILOT"
OBSERVABILITY_ROW_STATUS = "APPROVED_PILOT; EXTERNAL_VISUAL_APPROVAL_BOUND"
OBSERVABILITY_APPROVAL_RECORD = "docs/evidence/github-governance-v0124/dashboard-external-visual-approval.json"
OBSERVABILITY_APPROVAL_ARTIFACT_ID = "9867524286"
OBSERVABILITY_APPROVAL_ARTIFACT_DIGEST = "sha256:6ffe21738ed7960aabb5cd874cc44c4030a3b5fee0463f58c004805637a4d6d2"
OBSERVABILITY_APPROVED_HEAD = "2f8d04f03a6f4de0ead7683899f945cd60d5000f"
EVIDENCE_ROOT = "docs/evidence/v1-final-acceptance/"
FINAL_ACCEPTANCE_SUMMARY = "docs/evidence/v1-final-acceptance/final-acceptance-summary.json"
CAPABILITY_COUNT = 16
REQUIRED_CONTEXTS = ("UGAS CI / unit-and-validation", "UGAS CI / docker-smoke", "UGAS Review / evidence")
APPROVED_SEMANTIC_HEAD = "66db255fdb2483da4bae08e418c904f24d215ebb"
APPROVAL_RECORD = "docs/evidence/v1-final-acceptance/sol-external-approval-v0251.json"
APPROVAL_REVIEW_ID_NUMERIC = 5177113418
POST_BOOKKEEPING_REPROOF_REQUIRED = True


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str, roadmap_text: str, matrix: Mapping[str, Any], audit: Mapping[str, Any] | None = None) -> dict[str, Any]:
    failures: list[str] = []
    expected = {
        "schema_version": VERSION,
        "version": VERSION,
        "phase": PHASE,
        "baseline_main_sha": BASELINE_MAIN_SHA,
        "current_gate": CURRENT_GATE,
        "stop_reason": STOP_REASON,
        "acceptance_verdict": ACCEPTANCE_VERDICT,
        "next_candidate": NEXT_CANDIDATE,
        "allowed_next_actions": [NEXT_ACTION],
        "orchestration_runtime": "APPROVED_FOUNDATION",
        "orchestration_lifecycle": ORCHESTRATION_LIFECYCLE,
        "production_routing": "BLOCKED",
        "production_approved": False,
        "real_asset_generation": "NONE",
        "new_generation": 0,
        "provider_submit_calls": 0,
        "next_capability_started": False,
        "production_readiness_workstream": "NOT_STARTED_REQUIRED_SEPARATELY",
    }
    for key, expected_value in expected.items():
        if state.get(key) != expected_value:
            failures.append(f"{key}_invalid")
    if "main_sha" in state:
        failures.append("main_sha_forbidden")
    closure = _mapping(state.get("orchestration_closure"))
    for key, expected_value in {
        "semantic_head": ORCHESTRATION_SEMANTIC_HEAD,
        "bookkeeping_head": ORCHESTRATION_BOOKKEEPING_HEAD,
        "merge_main_sha": ORCHESTRATION_MERGE_MAIN_SHA,
        "post_merge_ci_run": POST_MERGE_CI_RUN,
        "unit_job": POST_MERGE_UNIT_JOB,
        "docker_job": POST_MERGE_DOCKER_JOB,
        "closure_comment_id": CLOSURE_COMMENT_ID,
        "tracked_state_binding": "PASS",
    }.items():
        if closure.get(key) != expected_value:
            failures.append(f"orchestration_closure:{key}")
    previous_release = _mapping(state.get("previous_release"))
    if previous_release.get("version") != PREVIOUS_RELEASE_VERSION or previous_release.get("status") != ORCHESTRATION_LIFECYCLE or previous_release.get("merge_commit") != ORCHESTRATION_MERGE_MAIN_SHA:
        failures.append("previous_release_invalid")
    history = _mapping(state.get("correction_history"))
    previous = _mapping(history.get(f"v{PREVIOUS_RELEASE_VERSION}"))
    if previous.get("status") != ORCHESTRATION_LIFECYCLE or previous.get("semantic_head") != ORCHESTRATION_SEMANTIC_HEAD or previous.get("bookkeeping_head") != ORCHESTRATION_BOOKKEEPING_HEAD or previous.get("merge_commit") != ORCHESTRATION_MERGE_MAIN_SHA or previous.get("post_merge_ci_run") != POST_MERGE_CI_RUN or previous.get("unit_job") != POST_MERGE_UNIT_JOB or previous.get("docker_job") != POST_MERGE_DOCKER_JOB or previous.get("closure_comment_id") != CLOSURE_COMMENT_ID or previous.get("historical_evidence_unchanged") is not True:
        failures.append(f"correction_history:{PREVIOUS_RELEASE_VERSION}_closure_invalid")
    if _mapping(history.get("v0.24.6")).get("status") != "CORRECTION_REQUIRED" or _mapping(history.get("v0.24.6")).get("historical_evidence_unchanged") is not True:
        failures.append("correction_history:v0246_missing")
    if _mapping(history.get("v0.23.4")).get("status") != "MERGED_CLOSED" or _mapping(history.get("v0.23.4")).get("merge_commit") != "dee98f8cd89ebd83a36ead7a22a184700d6e916f":
        failures.append("correction_history:v0234_missing")
    observability = _mapping(state.get("observability"))
    for key, expected_value in {
        "status": OBSERVABILITY_STATUS,
        "external_visual_review": "PASS",
        "approval_record": OBSERVABILITY_APPROVAL_RECORD,
        "approval_artifact_id": OBSERVABILITY_APPROVAL_ARTIFACT_ID,
        "approval_artifact_digest": OBSERVABILITY_APPROVAL_ARTIFACT_DIGEST,
        "approved_reviewed_head": OBSERVABILITY_APPROVED_HEAD,
        "visuals_bound": 2,
        "self_approval": False,
        "historical_sources_rewritten": False,
        "production_approved": False,
    }.items():
        if observability.get(key) != expected_value:
            failures.append(f"observability:{key}")
    review = _mapping(state.get("review"))
    for key, expected_value in {"repository": "KayzenRoot/ugas", "base_sha": BASELINE_MAIN_SHA, "feature_branch": BRANCH, "pr_title": PR_TITLE, "pr_state": "OPEN", "head_sha_source": "GitHub LIVE exact-head metadata", "pr_number_source": "GitHub LIVE PR metadata", "external_review_required": True, "merge_authorization": MERGE_AUTHORIZATION, "do_not_merge": True, "approved_semantic_head": APPROVED_SEMANTIC_HEAD, "approval_record": APPROVAL_RECORD, "approval_review_id_numeric": APPROVAL_REVIEW_ID_NUMERIC, "post_bookkeeping_reproof_required": POST_BOOKKEEPING_REPROOF_REQUIRED}.items():
        if review.get(key) != expected_value:
            failures.append(f"review:{key}")
    pr_number = review.get("pr_number")
    if type(pr_number) is not int or pr_number < 0:
        failures.append("review:pr_number")
    if set(REQUIRED_CONTEXTS) - set(review.get("required_contexts", [])):
        failures.append("review:required_contexts")
    acceptance = _mapping(state.get("v1_final_acceptance"))
    if acceptance.get("evidence_root") != EVIDENCE_ROOT or acceptance.get("capability_count") != CAPABILITY_COUNT or acceptance.get("capabilities_audited") != CAPABILITY_COUNT or acceptance.get("observability_visual_review") != "PASS" or acceptance.get("production_scope") != "EXCLUDED":
        failures.append("v1_final_acceptance:binding_invalid")
    capabilities = matrix.get("capabilities") if isinstance(matrix.get("capabilities"), list) else []
    by_id = {item.get("id"): item for item in capabilities if isinstance(item, Mapping)}
    if len(capabilities) != CAPABILITY_COUNT:
        failures.append("matrix:capability_count_invalid")
    if matrix.get("version") != VERSION or matrix.get("next_candidate") != NEXT_CANDIDATE or matrix.get("production_routing") != "BLOCKED" or matrix.get("new_generation") != 0:
        failures.append("matrix:global")
    if by_id.get("orchestration_runtime_hardening", {}).get("status") != "APPROVED_FOUNDATION; MERGED_CLOSED":
        failures.append("matrix:orchestration_not_merged_closed")
    if by_id.get("vfx_asset_family", {}).get("status") != "APPROVED_FOUNDATION; MERGED_CLOSED" or by_id.get("ui_asset_family", {}).get("status") != "APPROVED_FOUNDATION; MERGED_CLOSED":
        failures.append("matrix:closed_family_regressed")
    observability_row = str(by_id.get("local_always_on_observability", {}).get("status", ""))
    if observability_row != OBSERVABILITY_ROW_STATUS:
        failures.append("matrix:observability_status_invalid")
    if "pending" in observability_row.casefold() or "required" in observability_row.casefold():
        failures.append("matrix:observability_pending_claim_retained")
    allowed = state.get("allowed_next_actions", [])
    forbidden = state.get("forbidden_actions", [])
    if any(action in forbidden for action in allowed):
        failures.append("allowed_action_forbidden_contradiction")
    for action in ("start_production_readiness", "enable_production_routing", "real_asset_generation", "merge_v1_final_acceptance_pr", "self_merge_v1_final_acceptance_pr", "start_ugas_v2"):
        if action not in forbidden:
            failures.append(f"forbidden_action_missing:{action}")
    if any(action in allowed for action in ("start_production_readiness", "enable_production_routing", "merge_v1_final_acceptance_pr", "self_merge_v1_final_acceptance_pr")):
        failures.append("unsafe_next_action")
    evidence_value = _mapping(state.get("evidence"))
    if evidence_value.get("root") != EVIDENCE_ROOT or evidence_value.get("final_acceptance_summary") != FINAL_ACCEPTANCE_SUMMARY:
        failures.append("evidence_root_invalid")
    if audit is not None:
        audit_value = _mapping(audit)
        if audit_value.get("capability_count") != CAPABILITY_COUNT or audit_value.get("production_routing") != "BLOCKED" or audit_value.get("new_generation") != 0 or audit_value.get("status") != "PASS":
            failures.append("capability_audit_invalid")
        if _mapping(audit_value.get("observability")).get("visual_review_status") != "PASS":
            failures.append("capability_audit:observability_gate_invalid")
    documents = "\n".join((checkpoint_text, roadmap_text))
    for literal in (VERSION, PHASE, CURRENT_GATE, STOP_REASON, NEXT_ACTION, ORCHESTRATION_LIFECYCLE, str(CLOSURE_COMMENT_ID), str(POST_MERGE_CI_RUN), ORCHESTRATION_SEMANTIC_HEAD, "production_routing=BLOCKED", "new_generation=0", "production_approved=false", "external review"):
        if literal.casefold() not in documents.casefold():
            failures.append(f"documents_missing:{literal}")
    return {"status": CURRENT_GATE if not failures else "V1_FINAL_ACCEPTANCE_STATE_FAILED", "version": VERSION, "failures": failures, "checked": {"baseline_main_sha": state.get("baseline_main_sha"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "allowed_next_actions": state.get("allowed_next_actions"), "production_routing": state.get("production_routing"), "new_generation": state.get("new_generation"), "orchestration_lifecycle": state.get("orchestration_lifecycle"), "closure_comment_id": closure.get("closure_comment_id"), "capability_count": len(capabilities)}}


__all__ = ["ACCEPTANCE_VERDICT", "APPROVAL_RECORD", "APPROVAL_REVIEW_ID_NUMERIC", "APPROVED_SEMANTIC_HEAD", "BASELINE_MAIN_SHA", "BRANCH", "CAPABILITY_COUNT", "CLOSURE_COMMENT_ID", "CURRENT_GATE", "EVIDENCE_ROOT", "FINAL_ACCEPTANCE_SUMMARY", "MERGE_AUTHORIZATION", "NEXT_ACTION", "NEXT_CANDIDATE", "OBSERVABILITY_APPROVAL_ARTIFACT_DIGEST", "OBSERVABILITY_APPROVAL_ARTIFACT_ID", "OBSERVABILITY_APPROVAL_RECORD", "OBSERVABILITY_APPROVED_HEAD", "OBSERVABILITY_ROW_STATUS", "OBSERVABILITY_STATUS", "ORCHESTRATION_BOOKKEEPING_HEAD", "ORCHESTRATION_LIFECYCLE", "ORCHESTRATION_MERGE_MAIN_SHA", "ORCHESTRATION_SEMANTIC_HEAD", "PHASE", "POST_BOOKKEEPING_REPROOF_REQUIRED", "POST_MERGE_CI_RUN", "POST_MERGE_DOCKER_JOB", "POST_MERGE_UNIT_JOB", "PREVIOUS_RELEASE_VERSION", "PR_TITLE", "REQUIRED_CONTEXTS", "STOP_REASON", "VERSION", "validate_state_consistency"]
