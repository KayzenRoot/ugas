"""Fail-closed active-state checks for the v0.16.0 direction-runtime foundation."""

from __future__ import annotations

import re
from typing import Any, Mapping

CURRENT_VERSION = "0.16.0"
CURRENT_PHASE = "MULTI_DIRECTION_ANIMATION_RUNTIME"
CURRENT_GATE = "MULTI_DIRECTION_ANIMATION_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED"
NEXT_ACTION = "external_review_multi_direction_runtime_v0160"
BASELINE_HEAD = "514a17818469b567966293db808cafbf708f8311"
FEATURE_BRANCH = "codex/v0.16.0-multi-direction-runtime-foundation"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str, review_text: str, roadmap_text: str = "") -> dict[str, Any]:
    failures: list[str] = []
    if state.get("schema_version") != CURRENT_VERSION or state.get("version") != CURRENT_VERSION:
        failures.append("version_must_be_0.16.0")
    if state.get("phase") != CURRENT_PHASE:
        failures.append("phase_must_be_MULTI_DIRECTION_ANIMATION_RUNTIME")
    if state.get("current_gate") != CURRENT_GATE:
        failures.append("current_gate_invalid")
    if state.get("allowed_next_actions") != [NEXT_ACTION]:
        failures.append("next_action_must_be_external_review_multi_direction_runtime_v0160")
    if state.get("production_approved") is not False or state.get("production_routing") != "BLOCKED":
        failures.append("production_must_remain_blocked")
    if state.get("new_generation") != 0:
        failures.append("new_generation_must_remain_zero")
    if state.get("death_animation_front_visual_content") != "APPROVED_PILOT":
        failures.append("death_visual_must_remain_approved_pilot")
    if state.get("multi_direction_animation_runtime") != "TECHNICALLY_QUALIFIED_FOUNDATION":
        failures.append("direction_runtime_must_be_foundation_only")
    if state.get("real_directional_character_asset_coverage") != "SOUTH_ONLY":
        failures.append("real_directional_coverage_must_remain_south_only")

    previous = _mapping(state.get("previous_release"))
    if previous.get("version") != "0.15.1" or previous.get("review") != "REVIEW-v0.15.1.md" or previous.get("evidence") != "docs/evidence/current-state-v0.15.1.json":
        failures.append("previous_release_must_bind_approved_v0151")
    external = _mapping(state.get("external_visual_review"))
    if external.get("death_animation_front") != "APPROVED_PILOT" or external.get("multi_direction_animation_runtime") != "REQUIRED":
        failures.append("external_review_boundary_invalid")

    review = _mapping(state.get("review"))
    expected = {"repository": "KayzenRoot/ugas", "branch_base_commit": BASELINE_HEAD, "feature_branch": FEATURE_BRANCH, "pr_number": 0, "pr_state": "NOT_CREATED", "real_pr_checks_green": False, "no_self_merge_until_external_approval": True}
    failures.extend(f"review:{key}" for key, value in expected.items() if review.get(key) != value)
    if review.get("merge_authorization") is not None:
        failures.append("direction_pr_must_not_claim_merge_authorization")
    if review.get("approved_head_sha") != "f89184cd2dd317cbba584ddcf6115301d90666ab":
        failures.append("previous_approved_head_binding_invalid")

    nested = _mapping(state.get("state_consistency"))
    nested_expected = {"status": CURRENT_GATE, "version": CURRENT_VERSION, "phase": CURRENT_PHASE, "current_gate": CURRENT_GATE, "branch_base_commit": BASELINE_HEAD, "production_routing": "BLOCKED", "production_approved": False, "new_generation": 0, "multi_direction_animation_runtime": "TECHNICALLY_QUALIFIED_FOUNDATION", "real_directional_character_asset_coverage": "SOUTH_ONLY", "allowed_next_actions": [NEXT_ACTION], "next_capability_started": False, "v0151_merge_commit": BASELINE_HEAD}
    failures.extend(f"state_consistency:{key}" for key, value in nested_expected.items() if nested.get(key) != value)

    evidence = _mapping(state.get("evidence"))
    required_evidence = ("v0151_merge_commit", "direction_contract", "direction_coverage", "direction_validation", "direction_negative_controls", "direction_fixture_manifest")
    failures.extend(f"evidence_missing:{key}" for key in required_evidence if not evidence.get(key))
    active = "\n".join((checkpoint_text.split("## Historical", 1)[0], review_text, roadmap_text.split("## Historical", 1)[0] if roadmap_text else ""))
    required_literals = ("0.16.0", CURRENT_PHASE, CURRENT_GATE, NEXT_ACTION, "multi_direction_animation_runtime=TECHNICALLY_QUALIFIED_FOUNDATION", "real_directional_character_asset_coverage=SOUTH_ONLY", "production_approved=false", "production_routing=BLOCKED", "new_generation=0", "514a17818469b567966293db808cafbf708f8311", "Merge v0.16.0 PR only after external review", "south", "south_east", "north_west", "SOUTH_ONLY", "TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE")
    for literal in required_literals:
        if literal.casefold() not in active.casefold():
            failures.append(f"active_documents_missing:{literal}")
    if re.search(r"production[^\n.]{0,100}\b(?:enabled|active|unblocked|promoted)", active, re.IGNORECASE):
        failures.append("active_documents_promote_production")
    return {"status": CURRENT_GATE if not failures else "STATE_CONSISTENCY_FAILED", "schema_version": CURRENT_VERSION, "failures": failures, "checked": {"version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "feature_branch": review.get("feature_branch"), "branch_base_commit": review.get("branch_base_commit"), "next_action": state.get("allowed_next_actions"), "direction_runtime": state.get("multi_direction_animation_runtime"), "real_directional_coverage": state.get("real_directional_character_asset_coverage"), "production_routing": state.get("production_routing"), "new_generation": state.get("new_generation"), "pr_state": review.get("pr_state")}}
