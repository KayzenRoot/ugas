"""Fail-closed active-state validator for UGAS v0.24.0."""

from __future__ import annotations

from typing import Any, Mapping


VERSION = "0.24.0"
BASELINE_MAIN_SHA = "dee98f8cd89ebd83a36ead7a22a184700d6e916f"
CURRENT_PHASE = "ORCHESTRATION_RUNTIME_HARDENING"
CURRENT_GATE = "ORCHESTRATION_RUNTIME_HARDENING_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED"
STOP_REASON = "ORCHESTRATION_RUNTIME_HARDENING_EXTERNAL_REVIEW_REQUIRED"
NEXT_ACTION = "external_review_orchestration_runtime_v0240"
NEXT_CANDIDATE = "V1_FINAL_ACCEPTANCE"
BRANCH = "codex/v0.24.0-orchestration-runtime-hardening-foundation"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _strict_false(value: Any) -> bool:
    return type(value) is bool and value is False


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str, roadmap_text: str, matrix: Mapping[str, Any], binding: Mapping[str, Any] | None = None) -> dict[str, Any]:
    failures: list[str] = []
    expected = {
        "schema_version": VERSION,
        "version": VERSION,
        "phase": CURRENT_PHASE,
        "baseline_main_sha": BASELINE_MAIN_SHA,
        "orchestration_base_main_sha": BASELINE_MAIN_SHA,
        "current_gate": CURRENT_GATE,
        "stop_reason": STOP_REASON,
        "next_candidate": NEXT_CANDIDATE,
        "allowed_next_actions": [NEXT_ACTION],
        "orchestration_runtime": "TECHNICALLY_QUALIFIED_FOUNDATION",
        "orchestration_runtime_external_review": "REQUIRED",
        "orchestration_lifecycle": "ACTIVE_FOUNDATION",
        "production_routing": "BLOCKED",
        "production_approved": False,
        "real_asset_generation": "NONE",
        "new_generation": 0,
        "next_capability_started": False,
    }
    for key, expected_value in expected.items():
        if state.get(key) != expected_value:
            failures.append(f"{key}_invalid")
    if "main_sha" in state:
        failures.append("main_sha_forbidden")
    history = _mapping(state.get("correction_history"))
    vfx = _mapping(history.get("v0.23.4"))
    if vfx.get("status") != "MERGED_CLOSED" or vfx.get("merge_commit") != BASELINE_MAIN_SHA or vfx.get("historical_evidence_unchanged") is not True:
        failures.append("v0234_closure_history_invalid")
    review = _mapping(state.get("review"))
    for key, expected_value in {"repository": "KayzenRoot/ugas", "feature_branch": BRANCH, "base_sha": BASELINE_MAIN_SHA, "external_review_required": True, "do_not_merge": True, "merge_authorization": "NOT_AUTHORIZED_UNTIL_SOL_APPROVAL"}.items():
        if review.get(key) != expected_value:
            failures.append(f"review:{key}")
    if review.get("pr_state") not in {"NOT_CREATED", "OPEN"}:
        failures.append("review:pr_state")
    if review.get("pr_state") == "OPEN" and not isinstance(review.get("pr_number"), int):
        failures.append("review:open_pr_number")
    orchestration = _mapping(matrix.get("capabilities"))
    capabilities = matrix.get("capabilities") if isinstance(matrix.get("capabilities"), list) else []
    by_id = {item.get("id"): item for item in capabilities if isinstance(item, Mapping)}
    if matrix.get("version") != VERSION or matrix.get("next_candidate") != NEXT_CANDIDATE or matrix.get("production_routing") != "BLOCKED" or matrix.get("new_generation") != 0:
        failures.append("matrix:global")
    if by_id.get("vfx_asset_family", {}).get("status") != "APPROVED_FOUNDATION; MERGED_CLOSED":
        failures.append("matrix:vfx_not_closed")
    if by_id.get("orchestration_runtime_hardening", {}).get("status") != "TECHNICALLY_QUALIFIED_FOUNDATION; EXTERNAL REVIEW REQUIRED":
        failures.append("matrix:orchestration_status")
    if state.get("forbidden_actions") and any(item in state["allowed_next_actions"] for item in state["forbidden_actions"]):
        failures.append("allowed_action_forbidden_contradiction")
    binding_value = binding or {}
    if binding_value and (binding_value.get("merge_main_sha") != BASELINE_MAIN_SHA or binding_value.get("evidence_status") != "MERGED_CLOSED"):
        failures.append("v0234_binding_invalid")
    active = "\n".join((checkpoint_text, roadmap_text))
    for literal in (VERSION, CURRENT_GATE, STOP_REASON, NEXT_ACTION, "production_routing=BLOCKED", "new_generation=0", "VFX", "MERGED_CLOSED", "external review"):
        if literal.casefold() not in active.casefold():
            failures.append(f"documents_missing:{literal}")
    return {"status": CURRENT_GATE if not failures else "ORCHESTRATION_STATE_FAILED", "version": VERSION, "failures": failures, "checked": {"baseline_main_sha": state.get("baseline_main_sha"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "allowed_next_actions": state.get("allowed_next_actions"), "production_routing": state.get("production_routing"), "new_generation": state.get("new_generation")}}


__all__ = ["BASELINE_MAIN_SHA", "BRANCH", "CURRENT_GATE", "CURRENT_PHASE", "NEXT_ACTION", "NEXT_CANDIDATE", "STOP_REASON", "VERSION", "validate_state_consistency"]
