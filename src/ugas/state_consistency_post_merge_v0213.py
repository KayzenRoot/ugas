"""Fail-closed post-merge governance state for UGAS v0.21.3."""

from __future__ import annotations

from typing import Any, Mapping


CURRENT_VERSION = "0.21.3"
CURRENT_PHASE = "MAPS_MINIMAP"
CURRENT_GATE = "MAPS_MINIMAP_APPROVED_FOUNDATION_MERGED"
STOP_REASON = "MAPS_MINIMAP_CLOSED_UI_NEXT"
NEXT_ACTION = "start_ui_asset_family_v0220"
MAIN_SHA = "0c9b721b43d3cc12605ce009f6e0deb232b00045"
SEMANTIC_APPROVAL_HEAD = "812a2bed1f77df3d630425f23032c22fc72d5961"
FINAL_BOOKKEEPING_HEAD = "1ba088b40583a0ac6f287cbcc8ed8511031cd7e5"
MERGED_MAIN_SHA = "0c9b721b43d3cc12605ce009f6e0deb232b00045"
PRE_MERGE_APPROVAL_RECORD = "docs/evidence/github-governance-v0220/v0213-external-approval.json"
POST_MERGE_BINDING = "docs/evidence/github-governance-v0220/v0213-post-merge-binding.json"
CLOSURE_BRANCH = "codex/v0.21.3-post-merge-closure-continuity"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def validate_post_merge_state(
    state: Mapping[str, Any],
    binding: Mapping[str, Any],
    checkpoint_text: str = "",
    continuity_text: str = "",
    response_protocol_text: str = "",
) -> dict[str, Any]:
    failures: list[str] = []
    expected = {
        "schema_version": CURRENT_VERSION,
        "version": CURRENT_VERSION,
        "phase": CURRENT_PHASE,
        "current_gate": CURRENT_GATE,
        "stop_reason": STOP_REASON,
        "main_sha": MAIN_SHA,
        "maps_minimap_assets": "APPROVED_FOUNDATION",
        "maps_minimap_runtime_external_review": "APPROVED_FOUNDATION",
        "maps_minimap_lifecycle": "MERGED_CLOSED",
        "production_routing": "BLOCKED",
        "production_approved": False,
        "real_map_asset_coverage": "NONE",
        "real_minimap_asset_coverage": "NONE",
        "synthetic_map_fixture": "TEST_ONLY",
        "new_generation": 0,
        "next_capability_started": False,
    }
    failures.extend(f"{key}_invalid" for key, value in expected.items() if state.get(key) != value)
    if state.get("allowed_next_actions") != [NEXT_ACTION]:
        failures.append("allowed_next_actions_invalid")

    bookkeeping = _mapping(state.get("bookkeeping_approval"))
    expected_bookkeeping = {
        "status": "APPROVED_FOUNDATION",
        "approved_head_sha": SEMANTIC_APPROVAL_HEAD,
        "merged_main_sha": MERGED_MAIN_SHA,
        "approval_record": PRE_MERGE_APPROVAL_RECORD,
        "post_bookkeeping_reproof_required": False,
        "merge_verified_via_protected_path": True,
    }
    failures.extend(f"bookkeeping:{key}" for key, value in expected_bookkeeping.items() if bookkeeping.get(key) != value)

    review = _mapping(state.get("review"))
    expected_review = {
        "repository": "KayzenRoot/ugas",
        "pr_number": 11,
        "pr_state": "MERGED",
        "feature_branch": "codex/v0.21.0-maps-minimap-runtime-foundation",
        "merged_main_sha": MERGED_MAIN_SHA,
        "approval_record": PRE_MERGE_APPROVAL_RECORD,
        "post_bookkeeping_reproof_required": False,
        "do_not_merge": False,
    }
    failures.extend(f"review:{key}" for key, value in expected_review.items() if review.get(key) != value)

    closure = _mapping(state.get("closure_review"))
    expected_closure = {
        "purpose": "GOVERNANCE_ONLY_POST_MERGE_CLOSURE",
        "repository": "KayzenRoot/ugas",
        "base_sha": MERGED_MAIN_SHA,
        "branch": CLOSURE_BRANCH,
        "external_review_required": True,
        "do_not_merge": True,
        "merge_authorization": "NOT_AUTHORIZED_UNTIL_SOL_APPROVAL",
        "binding_record": POST_MERGE_BINDING,
    }
    failures.extend(f"closure_review:{key}" for key, value in expected_closure.items() if closure.get(key) != value)
    if closure.get("pr_state") not in {"NOT_CREATED", "OPEN"}:
        failures.append("closure_review:pr_state")
    if closure.get("pr_state") == "OPEN" and (not isinstance(closure.get("pr_number"), int) or closure["pr_number"] < 1):
        failures.append("closure_review:pr_number")
    if closure.get("pr_state") == "OPEN" and closure.get("head_sha") not in {None, ""}:
        head = str(closure.get("head_sha"))
        if len(head) != 40 or any(char not in "0123456789abcdef" for char in head.casefold()):
            failures.append("closure_review:head_sha")

    expected_binding = {
        "schema_version": "0.22.0",
        "record_type": "post_merge_governance_binding",
        "merged_pr": 11,
        "merged": True,
        "final_bookkeeping_head": FINAL_BOOKKEEPING_HEAD,
        "merge_commit": MERGED_MAIN_SHA,
        "semantic_approval_head": SEMANTIC_APPROVAL_HEAD,
        "pre_merge_approval_record": PRE_MERGE_APPROVAL_RECORD,
        "production_routing": "BLOCKED",
        "production_approved": False,
        "real_map_asset_coverage": "NONE",
        "real_minimap_asset_coverage": "NONE",
        "synthetic_map_fixture": "TEST_ONLY",
        "new_generation": 0,
        "runtime_semantic_diff_final_head_to_merge": False,
        "closure_branch": CLOSURE_BRANCH,
        "closure_base_sha": MERGED_MAIN_SHA,
    }
    failures.extend(f"binding:{key}" for key, value in expected_binding.items() if binding.get(key) != value)
    closure_binding = _mapping(binding.get("closure_pr"))
    if closure_binding.get("branch") != CLOSURE_BRANCH or closure_binding.get("base_sha") != MERGED_MAIN_SHA:
        failures.append("binding:closure_pr_identity")
    if closure.get("pr_state") == "OPEN" and closure_binding.get("number") != closure.get("pr_number"):
        failures.append("binding:closure_pr_number")

    active = "\n".join((checkpoint_text, continuity_text, response_protocol_text))
    for literal in (
        CURRENT_VERSION,
        CURRENT_GATE,
        STOP_REASON,
        NEXT_ACTION,
        POST_MERGE_BINDING,
        "continue do chat anterior",
        "PROGRESSO E ETA",
        "production_routing=BLOCKED",
        "new_generation=0",
    ):
        if literal.casefold() not in active.casefold():
            failures.append(f"active_documents_missing:{literal}")

    return {
        "status": CURRENT_GATE if not failures else "POST_MERGE_STATE_FAILED",
        "schema_version": CURRENT_VERSION,
        "failures": failures,
        "checked": {
            "version": state.get("version"),
            "phase": state.get("phase"),
            "current_gate": state.get("current_gate"),
            "merged_main_sha": bookkeeping.get("merged_main_sha"),
            "closure_pr_number": closure.get("pr_number"),
            "closure_pr_state": closure.get("pr_state"),
            "allowed_next_actions": state.get("allowed_next_actions"),
            "production_routing": state.get("production_routing"),
            "new_generation": state.get("new_generation"),
        },
    }


REQUIRED_PROGRESS_FIELDS = (
    "capability_current",
    "ugas_v1_overall",
    "completed_capabilities",
    "remaining_gates",
    "estimated_cycles",
    "eta_optimistic",
    "eta_realistic",
    "eta_conservative",
    "confidence",
    "critical_path",
    "status_delta",
)


def validate_progress_response(response: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a machine-readable response snapshot against live state anchors."""

    failures = [f"missing:{key}" for key in REQUIRED_PROGRESS_FIELDS if key not in response]
    if response.get("source_main_sha") != state.get("main_sha"):
        failures.append("source_main_sha_mismatch")
    if response.get("source_current_gate") != state.get("current_gate"):
        failures.append("source_current_gate_mismatch")
    if response.get("source_mode") != "LIVE_REPOSITORY_AND_GITHUB":
        failures.append("source_mode_must_be_live")
    return {"status": "PROGRESS_RESPONSE_PASSED" if not failures else "PROGRESS_RESPONSE_FAILED", "failures": failures}


__all__ = [
    "CLOSURE_BRANCH",
    "CURRENT_GATE",
    "CURRENT_PHASE",
    "CURRENT_VERSION",
    "FINAL_BOOKKEEPING_HEAD",
    "MERGED_MAIN_SHA",
    "MAIN_SHA",
    "NEXT_ACTION",
    "POST_MERGE_BINDING",
    "PRE_MERGE_APPROVAL_RECORD",
    "SEMANTIC_APPROVAL_HEAD",
    "STOP_REASON",
    "validate_post_merge_state",
    "validate_progress_response",
]
