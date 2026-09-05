"""Fail-closed active-state checks for the v0.17.0 equipment slice."""

from __future__ import annotations

from typing import Any, Mapping


CURRENT_VERSION = "0.17.0"
CURRENT_PHASE = "EQUIPMENT_OUTFITS"
CURRENT_GATE = "EQUIPMENT_OUTFITS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED"
NEXT_ACTION = "external_review_equipment_outfits_v0170"
BASELINE_HEAD = "a8d2897211c4b72c2cd2fe7a7f5729c7009d8566"
FEATURE_BRANCH = "codex/v0.17.0-equipment-outfits-runtime-foundation"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str = "", review_text: str = "", roadmap_text: str = "") -> dict[str, Any]:
    failures: list[str] = []
    expected_scalars = {
        "schema_version": CURRENT_VERSION,
        "version": CURRENT_VERSION,
        "phase": CURRENT_PHASE,
        "current_gate": CURRENT_GATE,
        "multi_direction_animation_runtime": "APPROVED_FOUNDATION",
        "real_directional_character_asset_coverage": "SOUTH_ONLY",
        "real_equipment_asset_coverage": "NONE_OR_EXPLICITLY_APPROVED_ONLY",
        "synthetic_equipment_fixture": "TEST_ONLY",
        "production_routing": "BLOCKED",
        "runtime_mode": "DOCKER_ALWAYS_ON_LOCAL",
        "always_on_dashboard_policy": "ENABLED",
    }
    failures.extend(f"{key}_invalid" for key, value in expected_scalars.items() if state.get(key) != value)
    if state.get("allowed_next_actions") != [NEXT_ACTION]:
        failures.append("allowed_next_actions_invalid")
    if state.get("production_approved") is not False:
        failures.append("production_must_remain_unapproved")
    if state.get("new_generation") != 0:
        failures.append("new_generation_must_remain_zero")
    forbidden = state.get("forbidden_actions", [])
    if not isinstance(forbidden, list) or not {"direct_main_push", "enable_production_routing", "new_generation", "creatures_monsters"}.issubset(forbidden):
        failures.append("forbidden_boundaries_incomplete")
    previous = _mapping(state.get("previous_release"))
    if previous.get("version") != "0.16.2" or previous.get("review") != "REVIEW-v0.16.2.md":
        failures.append("previous_release_must_bind_v0162")
    external = _mapping(state.get("external_visual_review"))
    if external.get("multi_direction_animation_runtime") != "APPROVED_FOUNDATION" or external.get("equipment_outfits_runtime") != "REQUIRED":
        failures.append("external_review_boundary_invalid")
    review = _mapping(state.get("review"))
    for key, expected in {"repository": "KayzenRoot/ugas", "branch_base_commit": BASELINE_HEAD, "feature_branch": FEATURE_BRANCH, "no_self_merge_until_external_approval": True}.items():
        if review.get(key) != expected:
            failures.append(f"review:{key}")
    if review.get("pr_state") not in {"NOT_CREATED", "OPEN"}:
        failures.append("review:pr_state")
    if not isinstance(review.get("pr_number"), int) or review["pr_number"] < 0:
        failures.append("review:pr_number")
    if review.get("real_pr_checks_green") not in {True, False}:
        failures.append("review:real_pr_checks_green")
    nested = _mapping(state.get("state_consistency"))
    for key, expected in {"status": CURRENT_GATE, "version": CURRENT_VERSION, "phase": CURRENT_PHASE, "current_gate": CURRENT_GATE, "feature_branch": FEATURE_BRANCH, "branch_base_commit": BASELINE_HEAD, "production_routing": "BLOCKED", "production_approved": False, "new_generation": 0, "allowed_next_actions": [NEXT_ACTION], "next_capability_started": False}.items():
        if nested.get(key) != expected:
            failures.append(f"state_consistency:{key}")
    active = "\n".join((checkpoint_text, review_text, roadmap_text))
    for literal in ("0.17.0", CURRENT_PHASE, CURRENT_GATE, NEXT_ACTION, "multi_direction_animation_runtime=APPROVED_FOUNDATION", "real_equipment_asset_coverage=NONE_OR_EXPLICITLY_APPROVED_ONLY", "synthetic_equipment_fixture=TEST_ONLY", "production_approved=false", "production_routing=BLOCKED", "new_generation=0", "EQUIPMENT_OUTFITS"):
        if literal.casefold() not in active.casefold():
            failures.append(f"active_documents_missing:{literal}")
    return {"status": CURRENT_GATE if not failures else "STATE_CONSISTENCY_FAILED", "schema_version": CURRENT_VERSION, "failures": failures, "checked": {"version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "feature_branch": review.get("feature_branch"), "branch_base_commit": review.get("branch_base_commit"), "next_action": state.get("allowed_next_actions"), "production_routing": state.get("production_routing"), "new_generation": state.get("new_generation"), "pr_number": review.get("pr_number"), "pr_state": review.get("pr_state"), "real_pr_checks_green": review.get("real_pr_checks_green")}}
