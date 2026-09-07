"""Fail-closed active-state contract for the v0.22.1 UI correction."""

from __future__ import annotations

from typing import Any, Mapping


CURRENT_VERSION = "0.22.1"
CURRENT_PHASE = "UI_ASSET_FAMILY"
CURRENT_GATE = "UI_ASSET_FAMILY_SEMANTIC_INTEGRITY_TECHNICALLY_QUALIFIED"
BASELINE_MAIN_SHA = "1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3"
FEATURE_BRANCH = "codex/v0.22.0-ui-asset-family-runtime-foundation"
NEXT_ACTION = "external_review_ui_asset_family_v0221"
NEXT_CANDIDATE = "UI_ASSET_FAMILY"
CLOSURE_BINDING = "docs/evidence/github-governance-v0221/v0213-closure-completion-binding-v2.json"
REQUIRED_CONTEXTS = ("UGAS CI / unit-and-validation", "UGAS CI / docker-smoke", "UGAS Review / evidence")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(char in "0123456789abcdef" for char in value.casefold())


def validate_state_consistency(state: Mapping[str, Any], binding: Mapping[str, Any] | None = None, checkpoint_text: str = "", review_text: str = "", roadmap_text: str = "") -> dict[str, Any]:
    failures: list[str] = []
    expected = {"schema_version": CURRENT_VERSION, "version": CURRENT_VERSION, "phase": CURRENT_PHASE, "current_gate": CURRENT_GATE, "next_candidate": NEXT_CANDIDATE, "ui_asset_family": "TECHNICALLY_QUALIFIED_FOUNDATION", "ui_asset_family_external_review": "REQUIRED", "maps_minimap_assets": "APPROVED_FOUNDATION", "maps_minimap_lifecycle": "MERGED_CLOSED", "maps_minimap_runtime_external_review": "APPROVED_FOUNDATION", "real_ui_asset_coverage": "NONE", "synthetic_ui_fixture": "TEST_ONLY", "production_routing": "BLOCKED", "new_generation": 0, "next_capability_started": False}
    failures.extend(f"{key}_invalid" for key, value in expected.items() if state.get(key) != value)
    if "main_sha" in state: failures.append("main_sha_forbidden")
    if state.get("baseline_main_sha") != BASELINE_MAIN_SHA or state.get("ui_base_main_sha") != BASELINE_MAIN_SHA: failures.append("baseline_main_sha_invalid")
    if state.get("allowed_next_actions") != [NEXT_ACTION]: failures.append("allowed_next_actions_invalid")
    forbidden = state.get("forbidden_actions")
    if not isinstance(forbidden, list) or not {"ui_asset_family", "vfx_asset_family", "orchestration_runtime_hardening", "enable_production_routing", "new_generation"}.issubset(forbidden): failures.append("forbidden_boundaries_incomplete")
    gate = _mapping(state.get("ui_start_gate"))
    if gate.get("status") != "BLOCKED" or gate.get("activation_action") != "start_ui_asset_family_v0222" or gate.get("condition") != "GITHUB_LIVE_PR_13_EXTERNAL_APPROVAL_AND_MERGED" or gate.get("authority") != "GITHUB_LIVE": failures.append("ui_start_gate_invalid")
    review = _mapping(state.get("review")); expected_review = {"repository": "KayzenRoot/ugas", "baseline_head": BASELINE_MAIN_SHA, "branch_base_commit": BASELINE_MAIN_SHA, "feature_branch": FEATURE_BRANCH, "execution_mode": "GITHUB_PR_FIRST", "external_review_required": True, "merge_authorization": "NOT_AUTHORIZED_UNTIL_SOL_APPROVAL", "do_not_merge": True}
    failures.extend(f"review:{key}" for key, value in expected_review.items() if review.get(key) != value)
    if review.get("pr_state") != "OPEN" or review.get("pr_number") != 13: failures.append("review:live_pr_binding")
    if review.get("head_sha") not in {None, ""} and not _is_sha(review.get("head_sha")): failures.append("review:head_sha")
    history = _mapping(state.get("correction_history")); h220 = _mapping(history.get("v0.22.0"))
    if h220.get("status") != "CORRECTION_REQUIRED" or h220.get("rejected_reviewed_head") != "0fad4721c0bfd52822cb3f1e952f306b5c50a151" or h220.get("historical_evidence_unchanged") is not True: failures.append("v0220_history_invalid")
    if binding is not None:
        if binding.get("closure_branch_base_sha") != "0c9b721b43d3cc12605ce009f6e0deb232b00045" or binding.get("closure_merge_commit_sha") != BASELINE_MAIN_SHA or binding.get("historical_roots_immutable") is not True: failures.append("closure_binding_v2_invalid")
        ci = _mapping(binding.get("post_merge_main_ci")); contexts = ci.get("contexts", []); names = [item.get("name") for item in contexts if isinstance(item, Mapping)]
        if tuple(names) != ("UGAS CI / unit-and-validation", "UGAS CI / docker-smoke") or tuple(ci.get("supported_contexts", [])) != tuple(names) or "UGAS Review / evidence" in names: failures.append("closure_binding_main_ci_invalid")
    active = "\n".join((checkpoint_text, review_text, roadmap_text))
    for literal in (CURRENT_VERSION, CURRENT_PHASE, CURRENT_GATE, NEXT_ACTION, "baseline_main_sha", "GITHUB LIVE", "production_routing=BLOCKED", "new_generation=0", "maps_minimap_lifecycle=MERGED_CLOSED"):
        if literal.casefold() not in active.casefold(): failures.append(f"active_documents_missing:{literal}")
    return {"status": CURRENT_GATE if not failures else "UI_STATE_CONSISTENCY_FAILED", "schema_version": CURRENT_VERSION, "failures": failures, "checked": {"version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "baseline_main_sha": state.get("baseline_main_sha"), "allowed_next_actions": state.get("allowed_next_actions"), "pr_state": review.get("pr_state"), "production_routing": state.get("production_routing")}}


def resolve_next_actions(state: Mapping[str, Any], live_closure: Mapping[str, Any] | None) -> dict[str, Any]:
    """Resolve activation from GitHub LIVE without mutating tracked state."""
    if state.get("allowed_next_actions") != [NEXT_ACTION]: return {"status": "UI_STATE_CONSISTENCY_FAILED", "allowed_next_actions": [NEXT_ACTION], "failures": ["tracked_action_invalid"]}
    live = _mapping(live_closure); activated = live.get("pr_number") == 13 and live.get("source_mode") == "GITHUB_LIVE" and live.get("merged") is True and live.get("external_approval") is True
    return {"status": "UI_ASSET_FAMILY_UNBLOCKED" if activated else "UI_ASSET_FAMILY_EXTERNAL_REVIEW_REQUIRED", "allowed_next_actions": ["start_ui_asset_family_v0222"] if activated else [NEXT_ACTION], "failures": [] if activated else ["live_closure_condition_unresolved"]}


__all__ = ["BASELINE_MAIN_SHA", "CLOSURE_BINDING", "CURRENT_GATE", "CURRENT_PHASE", "CURRENT_VERSION", "FEATURE_BRANCH", "NEXT_ACTION", "NEXT_CANDIDATE", "REQUIRED_CONTEXTS", "resolve_next_actions", "validate_state_consistency"]
