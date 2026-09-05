"""Fail-closed active-state checks for the v0.16.2 cache/state correction."""

from __future__ import annotations

import re
from typing import Any, Mapping


CURRENT_VERSION = "0.16.2"
CURRENT_PHASE = "MULTI_DIRECTION_ANIMATION_RUNTIME"
CURRENT_GATE = "MULTI_DIRECTION_ANIMATION_RUNTIME_CACHE_AND_STATE_INTEGRITY_TECHNICALLY_QUALIFIED"
NEXT_ACTION = "governed_merge_pr_6"
BASELINE_HEAD = "514a17818469b567966293db808cafbf708f8311"
FEATURE_BRANCH = "codex/v0.16.0-multi-direction-runtime-foundation"
PR_NUMBER = 6
PR_STATE = "OPEN"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str, review_text: str, roadmap_text: str = "") -> dict[str, Any]:
    failures: list[str] = []
    if state.get("schema_version") != CURRENT_VERSION or state.get("version") != CURRENT_VERSION:
        failures.append("version_must_be_0.16.2")
    if state.get("phase") != CURRENT_PHASE:
        failures.append("phase_must_be_MULTI_DIRECTION_ANIMATION_RUNTIME")
    if state.get("current_gate") != CURRENT_GATE:
        failures.append("current_gate_invalid")
    if state.get("allowed_next_actions") != [NEXT_ACTION]:
        failures.append("next_action_must_be_governed_merge_pr_6")
    if state.get("production_approved") is not False or state.get("production_routing") != "BLOCKED":
        failures.append("production_must_remain_blocked")
    if state.get("new_generation") != 0:
        failures.append("new_generation_must_remain_zero")
    if state.get("death_animation_front_visual_content") != "APPROVED_PILOT":
        failures.append("death_visual_must_remain_approved_pilot")
    if state.get("multi_direction_animation_runtime") != "APPROVED_FOUNDATION":
        failures.append("direction_runtime_must_be_approved_foundation")
    if state.get("real_directional_character_asset_coverage") != "SOUTH_ONLY":
        failures.append("real_directional_coverage_must_remain_south_only")

    previous = _mapping(state.get("previous_release"))
    if previous.get("version") != "0.15.1" or previous.get("review") != "REVIEW-v0.15.1.md" or previous.get("evidence") != "docs/evidence/animation-runtime-v0151/execution-evidence-v0.15.1.json":
        failures.append("previous_release_must_bind_approved_v0151")
    correction = _mapping(state.get("correction_history"))
    expected_corrections = {
        "v0.16.0": ("CORRECTION_REQUIRED", "7d1e999e91ee8817c6754b363a5c19f1ba6f2e7d"),
        "v0.16.1": ("CORRECTION_REQUIRED", "2513d9f6f8a55345e74d9c0afb5dab22f9d84705"),
    }
    for version, (status, head) in expected_corrections.items():
        record = _mapping(correction.get(version))
        if record.get("status") != status or record.get("rejected_reviewed_head") != head:
            failures.append(f"{version}_correction_history_invalid")
    if correction.get("v0.16.0", {}).get("record") != "docs/evidence/multi-direction-runtime-v0160/v0160-correction-record-v0161.json":
        failures.append("v0160_history_record_invalid")
    if correction.get("v0.16.1", {}).get("record") != "docs/evidence/multi-direction-runtime-v0162/v0161-rejection-correction-record-v0162.json":
        failures.append("v0161_history_record_invalid")

    external = _mapping(state.get("external_visual_review"))
    if external.get("death_animation_front") != "APPROVED_PILOT" or external.get("multi_direction_animation_runtime") != "REQUIRED":
        failures.append("external_review_boundary_invalid")

    review = _mapping(state.get("review"))
    expected = {
        "repository": "KayzenRoot/ugas",
        "branch_base_commit": BASELINE_HEAD,
        "feature_branch": FEATURE_BRANCH,
        "pr_number": PR_NUMBER,
        "pr_state": PR_STATE,
        "no_self_merge_until_external_approval": True,
    }
    failures.extend(f"review:{key}" for key, value in expected.items() if review.get(key) != value)
    if review.get("merge_authorization") != "APPROVED_TO_MERGE":
        failures.append("direction_pr_must_bind_external_merge_authorization")
    if review.get("rejected_reviewed_head") != "2513d9f6f8a55345e74d9c0afb5dab22f9d84705":
        failures.append("rejected_v0161_head_binding_invalid")
    if review.get("approved_head_sha") != "f89184cd2dd317cbba584ddcf6115301d90666ab":
        failures.append("previous_approved_head_binding_invalid")
    if review.get("real_pr_checks_green") is not True:
        failures.append("exact_v0162_pr_checks_must_be_green_after_reproof")

    nested = _mapping(state.get("state_consistency"))
    nested_expected = {
        "status": CURRENT_GATE,
        "version": CURRENT_VERSION,
        "phase": CURRENT_PHASE,
        "current_gate": CURRENT_GATE,
        "feature_branch": FEATURE_BRANCH,
        "branch_base_commit": BASELINE_HEAD,
        "production_routing": "BLOCKED",
        "production_approved": False,
        "new_generation": 0,
        "multi_direction_animation_runtime": "APPROVED_FOUNDATION",
        "real_directional_character_asset_coverage": "SOUTH_ONLY",
        "allowed_next_actions": [NEXT_ACTION],
        "next_capability_started": False,
        "v0151_merge_commit": BASELINE_HEAD,
        "pr_number": PR_NUMBER,
        "pr_state": PR_STATE,
        "real_pr_checks_green": True,
    }
    failures.extend(f"state_consistency:{key}" for key, value in nested_expected.items() if nested.get(key) != value)

    evidence = _mapping(state.get("evidence"))
    required_evidence = (
        "v0160_correction_record",
        "v0161_rejection_correction_record",
        "direction_contract",
        "direction_coverage",
        "direction_validation",
        "direction_negative_controls",
        "cache_unresolved_class_qa",
        "cache_order_negative_controls",
        "test_only_cache_mode_qa",
        "state_consistency",
        "v0162_external_approval",
    )
    failures.extend(f"evidence_missing:{key}" for key in required_evidence if not evidence.get(key))

    active = "\n".join((checkpoint_text.split("## Historical", 1)[0], review_text, roadmap_text.split("## Historical", 1)[0] if roadmap_text else ""))
    required_literals = (
        "0.16.2",
        "0.16.1",
        "0.16.0",
        CURRENT_PHASE,
        CURRENT_GATE,
        NEXT_ACTION,
        "multi_direction_animation_runtime=APPROVED_FOUNDATION",
        "real_directional_character_asset_coverage=SOUTH_ONLY",
        "production_approved=false",
        "production_routing=BLOCKED",
        "new_generation=0",
        BASELINE_HEAD,
        "PR #6",
        "pr_number=6",
        "pr_state=OPEN",
        "real_pr_checks_green=true",
        FEATURE_BRANCH,
        "CORRECTION_REQUIRED",
        "Merge after recorded external approval and exact post-bookkeeping reproof",
        "CACHE-NC-01",
        "CACHE-NC-05",
        "previous_release=0.15.1",
        "south",
        "south_east",
        "north_west",
        "SOUTH_ONLY",
        "TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE",
    )
    for literal in required_literals:
        if literal.casefold() not in active.casefold():
            failures.append(f"active_documents_missing:{literal}")
    if re.search(r"production[^\n.]{0,100}\b(?:enabled|active|unblocked|promoted)", active, re.IGNORECASE):
        failures.append("active_documents_promote_production")

    return {
        "status": CURRENT_GATE if not failures else "STATE_CONSISTENCY_FAILED",
        "schema_version": CURRENT_VERSION,
        "failures": failures,
        "checked": {
            "version": state.get("version"),
            "phase": state.get("phase"),
            "current_gate": state.get("current_gate"),
            "feature_branch": review.get("feature_branch"),
            "branch_base_commit": review.get("branch_base_commit"),
            "next_action": state.get("allowed_next_actions"),
            "direction_runtime": state.get("multi_direction_animation_runtime"),
            "real_directional_coverage": state.get("real_directional_character_asset_coverage"),
            "production_routing": state.get("production_routing"),
            "new_generation": state.get("new_generation"),
            "pr_number": review.get("pr_number"),
            "pr_state": review.get("pr_state"),
            "real_pr_checks_green": review.get("real_pr_checks_green"),
        },
    }
