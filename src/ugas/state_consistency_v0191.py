"""Fail-closed active-state contract for the v0.19.1 correction."""

from __future__ import annotations

from typing import Any, Mapping


CURRENT_VERSION = "0.19.1"
CURRENT_PHASE = "ITEMS_PROPS"
CURRENT_GATE = "ITEMS_PROPS_LINKAGE_REPRESENTATION_STACK_INTEGRITY_TECHNICALLY_QUALIFIED"
NEXT_ACTION = "external_review_items_props_v0191"
BASELINE_HEAD = "52938a04016352d50ad54621a4df981a9c36b058"
FEATURE_BRANCH = "codex/v0.19.0-items-props-runtime-foundation"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str = "", review_text: str = "", roadmap_text: str = "") -> dict[str, Any]:
    failures: list[str] = []
    expected = {
        "schema_version": CURRENT_VERSION,
        "version": CURRENT_VERSION,
        "phase": CURRENT_PHASE,
        "current_gate": CURRENT_GATE,
        "creatures_monsters": "APPROVED_FOUNDATION",
        "items_props_runtime": "TECHNICALLY_QUALIFIED_FOUNDATION",
        "items_props_runtime_external_review": "REQUIRED",
        "real_item_prop_asset_coverage": "NONE",
        "synthetic_item_prop_fixture": "TEST_ONLY",
        "production_routing": "BLOCKED",
        "production_approved": False,
        "new_generation": 0,
        "always_on_dashboard_policy": "ENABLED",
        "runtime_mode": "DOCKER_ALWAYS_ON_LOCAL",
    }
    failures.extend(f"{key}_invalid" for key, value in expected.items() if state.get(key) != value)
    if state.get("allowed_next_actions") != [NEXT_ACTION]:
        failures.append("allowed_next_actions_invalid")
    forbidden = state.get("forbidden_actions", [])
    required_forbidden = {"direct_main_push", "force_push_or_history_rewrite", "enable_production_routing", "new_generation", "environment_tilesets", "maps_minimap_assets", "ui_asset_family", "vfx_asset_family", "items_props_generation"}
    if not isinstance(forbidden, list) or not required_forbidden.issubset(forbidden):
        failures.append("forbidden_boundaries_incomplete")
    previous = _mapping(state.get("previous_release"))
    if previous.get("version") != "0.18.2" or previous.get("merge_commit") != BASELINE_HEAD:
        failures.append("previous_release_must_bind_v0182_merge")
    history = _mapping(state.get("correction_history"))
    v0190 = _mapping(history.get("v0.19.0"))
    if v0190.get("status") != "CORRECTION_REQUIRED" or v0190.get("rejected_reviewed_head") != "44937935e644202836b3e1f081b6a63201b850db":
        failures.append("v0190_rejection_history_invalid")
    external = _mapping(state.get("external_visual_review"))
    if external.get("items_props_runtime") != "REQUIRED" or external.get("creatures_monsters_runtime") != "APPROVED_FOUNDATION":
        failures.append("external_review_boundary_invalid")
    review = _mapping(state.get("review"))
    review_expected = {"repository": "KayzenRoot/ugas", "baseline_head": BASELINE_HEAD, "branch_base_commit": BASELINE_HEAD, "feature_branch": FEATURE_BRANCH, "execution_mode": "GITHUB_PR_FIRST", "merge_policy": "NO_SELF_MERGE_UNTIL_EXTERNAL_REVIEW", "no_self_merge_until_external_approval": True, "pr_state": "OPEN"}
    for key, value in review_expected.items():
        if review.get(key) != value:
            failures.append(f"review:{key}")
    if review.get("pr_number") not in {0, 9} or review.get("real_pr_checks_green") not in {True, False}:
        failures.append("review:pr_binding")
    nested = _mapping(state.get("state_consistency"))
    nested_expected = {"status": CURRENT_GATE, "version": CURRENT_VERSION, "phase": CURRENT_PHASE, "current_gate": CURRENT_GATE, "feature_branch": FEATURE_BRANCH, "branch_base_commit": BASELINE_HEAD, "production_routing": "BLOCKED", "production_approved": False, "new_generation": 0, "allowed_next_actions": [NEXT_ACTION], "next_capability_started": False}
    for key, value in nested_expected.items():
        if nested.get(key) != value:
            failures.append(f"state_consistency:{key}")
    active = "\n".join((checkpoint_text, review_text, roadmap_text))
    for literal in ("0.19.1", "0.19.0", CURRENT_PHASE, CURRENT_GATE, NEXT_ACTION, "creatures_monsters=APPROVED_FOUNDATION", "real_item_prop_asset_coverage=NONE", "synthetic_item_prop_fixture=TEST_ONLY", "production_approved=false", "production_routing=BLOCKED", "new_generation=0", "environment_tilesets", "CORRECTION_REQUIRED"):
        if literal.casefold() not in active.casefold():
            failures.append(f"active_documents_missing:{literal}")
    return {"status": CURRENT_GATE if not failures else "STATE_CONSISTENCY_FAILED", "schema_version": CURRENT_VERSION, "failures": failures, "checked": {"version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "feature_branch": review.get("feature_branch"), "branch_base_commit": review.get("branch_base_commit"), "next_action": state.get("allowed_next_actions"), "production_routing": state.get("production_routing"), "new_generation": state.get("new_generation"), "pr_number": review.get("pr_number"), "pr_state": review.get("pr_state"), "real_pr_checks_green": review.get("real_pr_checks_green")}}


__all__ = ["BASELINE_HEAD", "CURRENT_GATE", "CURRENT_PHASE", "CURRENT_VERSION", "FEATURE_BRANCH", "NEXT_ACTION", "validate_state_consistency"]
