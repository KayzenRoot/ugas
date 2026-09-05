"""Fail-closed active-state checks for the v0.18.0 creature foundation."""

from __future__ import annotations

from typing import Any, Mapping


CURRENT_VERSION = "0.18.0"
CURRENT_PHASE = "CREATURES_MONSTERS"
CURRENT_GATE = "CREATURES_MONSTERS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED"
NEXT_ACTION = "external_review_creatures_monsters_v0180"
BASELINE_HEAD = "39e148bef50c8f04db194048dbe9fbb15d8ff3d4"
FEATURE_BRANCH = "codex/v0.18.0-creatures-monsters-runtime-foundation"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str = "", review_text: str = "", roadmap_text: str = "") -> dict[str, Any]:
    failures: list[str] = []
    expected = {
        "schema_version": CURRENT_VERSION,
        "version": CURRENT_VERSION,
        "phase": CURRENT_PHASE,
        "current_gate": CURRENT_GATE,
        "equipment_outfits": "APPROVED_FOUNDATION",
        "creatures_monsters_runtime": "TECHNICALLY_QUALIFIED_FOUNDATION",
        "real_creature_asset_coverage": "NONE",
        "synthetic_creature_fixture": "TEST_ONLY",
        "production_routing": "BLOCKED",
        "runtime_mode": "DOCKER_ALWAYS_ON_LOCAL",
        "always_on_dashboard_policy": "ENABLED",
    }
    failures.extend(f"{key}_invalid" for key, value in expected.items() if state.get(key) != value)
    if state.get("allowed_next_actions") != [NEXT_ACTION]:
        failures.append("allowed_next_actions_invalid")
    if state.get("production_approved") is not False:
        failures.append("production_must_remain_unapproved")
    if state.get("new_generation") != 0:
        failures.append("new_generation_must_remain_zero")
    forbidden = state.get("forbidden_actions", [])
    required_forbidden = {"direct_main_push", "force_push_or_history_rewrite", "enable_production_routing", "new_generation", "items_props", "environment_tilesets", "ui_asset_family", "vfx_asset_family"}
    if not isinstance(forbidden, list) or not required_forbidden.issubset(forbidden):
        failures.append("forbidden_boundaries_incomplete")
    previous = _mapping(state.get("previous_release"))
    if previous.get("version") != "0.17.1" or previous.get("review") != "REVIEW-v0.17.1.md":
        failures.append("previous_release_must_bind_v0171")
    history = _mapping(state.get("correction_history"))
    if _mapping(history.get("v0.17.0")).get("status") != "CORRECTION_REQUIRED":
        failures.append("v0170_rejection_history_invalid")
    external = _mapping(state.get("external_visual_review"))
    if external.get("equipment_outfits_runtime") != "APPROVED_FOUNDATION" or external.get("creatures_monsters_runtime") != "REQUIRED":
        failures.append("external_review_boundary_invalid")
    review = _mapping(state.get("review"))
    for key, value in {"repository": "KayzenRoot/ugas", "branch_base_commit": BASELINE_HEAD, "feature_branch": FEATURE_BRANCH, "execution_mode": "GITHUB_PR_FIRST", "pr_state": "OPEN", "no_self_merge_until_external_approval": True}.items():
        if review.get(key) != value:
            failures.append(f"review:{key}")
    if not isinstance(review.get("pr_number"), int) or review.get("pr_number") < 0:
        failures.append("review:pr_number")
    if review.get("real_pr_checks_green") not in {True, False}:
        failures.append("review:real_pr_checks_green")
    nested = _mapping(state.get("state_consistency"))
    nested_expected = {"status": CURRENT_GATE, "version": CURRENT_VERSION, "phase": CURRENT_PHASE, "current_gate": CURRENT_GATE, "feature_branch": FEATURE_BRANCH, "branch_base_commit": BASELINE_HEAD, "production_routing": "BLOCKED", "production_approved": False, "new_generation": 0, "allowed_next_actions": [NEXT_ACTION], "next_capability_started": False}
    for key, value in nested_expected.items():
        if nested.get(key) != value:
            failures.append(f"state_consistency:{key}")
    active = "\n".join((checkpoint_text, review_text, roadmap_text))
    for literal in ("0.18.0", CURRENT_PHASE, CURRENT_GATE, NEXT_ACTION, "equipment_outfits=APPROVED_FOUNDATION", "real_creature_asset_coverage=NONE", "synthetic_creature_fixture=TEST_ONLY", "production_approved=false", "production_routing=BLOCKED", "new_generation=0", "items_props"):
        if literal.casefold() not in active.casefold():
            failures.append(f"active_documents_missing:{literal}")
    return {
        "status": CURRENT_GATE if not failures else "STATE_CONSISTENCY_FAILED",
        "schema_version": CURRENT_VERSION,
        "failures": failures,
        "checked": {"version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "feature_branch": review.get("feature_branch"), "branch_base_commit": review.get("branch_base_commit"), "next_action": state.get("allowed_next_actions"), "production_routing": state.get("production_routing"), "new_generation": state.get("new_generation"), "pr_number": review.get("pr_number"), "pr_state": review.get("pr_state"), "real_pr_checks_green": review.get("real_pr_checks_green")},
    }
