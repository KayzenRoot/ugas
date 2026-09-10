"""Fail-closed active-state validator for UGAS orchestration v0.24.3."""

from __future__ import annotations

from typing import Any, Mapping

VERSION = "0.24.3"
BASELINE_MAIN_SHA = "dee98f8cd89ebd83a36ead7a22a184700d6e916f"
REJECTED_REVIEWED_HEAD = "cd3345db7c0e587915e56eb9314879c4a9cf98a3"
V0241_REJECTED_HEAD = "ed9fa927fd50193130b3e085ef077dea267f2790"
BRANCH = "codex/v0.24.0-orchestration-runtime-hardening-foundation"
CURRENT_PHASE = "ORCHESTRATION_RUNTIME_HARDENING"
CURRENT_GATE = "ORCHESTRATION_RUNTIME_HARDENING_F32RR_F35RR_F35RC_F37_CORRECTION_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED"
STOP_REASON = "ORCHESTRATION_RUNTIME_HARDENING_F32RR_F35RR_F35RC_F37_EXTERNAL_REVIEW_REQUIRED"
NEXT_ACTION = "external_review_orchestration_runtime_v0243"
NEXT_CANDIDATE = "V1_FINAL_ACCEPTANCE"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str, roadmap_text: str, matrix: Mapping[str, Any], binding: Mapping[str, Any] | None = None, evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
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
    v0240 = _mapping(history.get("v0.24.0"))
    if v0240.get("status") != "CORRECTION_REQUIRED" or v0240.get("rejected_reviewed_head") != "36064a215bf3e7bff06ac22e750a242c6556f83e" or v0240.get("historical_evidence_unchanged") is not True:
        failures.append("v0240_correction_history_invalid")
    v0241 = _mapping(history.get("v0.24.1"))
    if v0241.get("status") != "CORRECTION_REQUIRED" or v0241.get("rejected_reviewed_head") != V0241_REJECTED_HEAD or v0241.get("historical_evidence_unchanged") is not True:
        failures.append("v0241_correction_history_invalid")
    v0242 = _mapping(history.get("v0.24.2"))
    if v0242.get("status") != "CORRECTION_REQUIRED" or v0242.get("rejected_reviewed_head") != REJECTED_REVIEWED_HEAD or v0242.get("historical_evidence_unchanged") is not True:
        failures.append("v0242_correction_history_invalid")
    review = _mapping(state.get("review"))
    for key, expected_value in {"repository": "KayzenRoot/ugas", "feature_branch": BRANCH, "base_sha": BASELINE_MAIN_SHA, "external_review_required": True, "do_not_merge": True, "merge_authorization": "NOT_AUTHORIZED_UNTIL_SOL_APPROVAL", "pr_number": 15}.items():
        if review.get(key) != expected_value:
            failures.append(f"review:{key}")
    if review.get("pr_state") != "OPEN":
        failures.append("review:pr_state")
    if review.get("head_sha_source") != "GitHub LIVE exact-head metadata":
        failures.append("review:head_sha_source")
    capabilities = matrix.get("capabilities") if isinstance(matrix.get("capabilities"), list) else []
    by_id = {item.get("id"): item for item in capabilities if isinstance(item, Mapping)}
    if matrix.get("version") != VERSION or matrix.get("next_candidate") != NEXT_CANDIDATE or matrix.get("production_routing") != "BLOCKED" or matrix.get("new_generation") != 0:
        failures.append("matrix:global")
    if by_id.get("orchestration_runtime_hardening", {}).get("status") != "TECHNICALLY_QUALIFIED_FOUNDATION; EXTERNAL REVIEW REQUIRED":
        failures.append("matrix:orchestration_status")
    if by_id.get("vfx_asset_family", {}).get("status") != "APPROVED_FOUNDATION; MERGED_CLOSED":
        failures.append("matrix:vfx_not_closed")
    allowed = state.get("allowed_next_actions", [])
    forbidden = state.get("forbidden_actions", [])
    if any(action in forbidden for action in allowed):
        failures.append("allowed_action_forbidden_contradiction")
    if "start_ui_asset_family_v0220" in allowed or "start_v1_final_acceptance" in allowed:
        failures.append("unsafe_next_action")
    binding_value = binding or {}
    if binding_value:
        if binding_value.get("base_main_sha") != BASELINE_MAIN_SHA or binding_value.get("reviewed_head") != REJECTED_REVIEWED_HEAD or binding_value.get("status") != "CORRECTION_REQUIRED":
            failures.append("v0242_binding_invalid")
    evidence_value = evidence or {}
    if evidence_value and evidence_value.get("orchestration_root") != "docs/evidence/orchestration-runtime-v0243/":
        failures.append("evidence_root_invalid")
    active = "\n".join((checkpoint_text, roadmap_text))
    for literal in (VERSION, CURRENT_GATE, STOP_REASON, NEXT_ACTION, "baseline_main_sha", "production_routing=BLOCKED", "new_generation=0", "F-32RR", "F-35RR", "F-35RC", "F-37", "F-34S", "F-31R", "F-33", "F-36", "external review"):
        if literal.casefold() not in active.casefold():
            failures.append(f"documents_missing:{literal}")
    return {"status": CURRENT_GATE if not failures else "ORCHESTRATION_STATE_FAILED", "version": VERSION, "failures": failures, "checked": {"baseline_main_sha": state.get("baseline_main_sha"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "allowed_next_actions": state.get("allowed_next_actions"), "production_routing": state.get("production_routing"), "new_generation": state.get("new_generation"), "rejected_reviewed_head": REJECTED_REVIEWED_HEAD}}


__all__ = ["BASELINE_MAIN_SHA", "BRANCH", "CURRENT_GATE", "CURRENT_PHASE", "NEXT_ACTION", "NEXT_CANDIDATE", "REJECTED_REVIEWED_HEAD", "STOP_REASON", "V0241_REJECTED_HEAD", "VERSION", "validate_state_consistency"]
