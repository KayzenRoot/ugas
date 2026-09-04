"""Fail-closed active-state checks for the v0.15.1 death-animation pilot."""

from __future__ import annotations

import re
from typing import Any, Mapping

CURRENT_VERSION = "0.15.1"
CURRENT_PHASE = "DEATH_ANIMATION_FRONT"
CURRENT_GATE = "DEATH_ANIMATION_FRONT_GROUND_CONTACT_AND_VISUAL_INTEGRITY_TECHNICALLY_QUALIFIED"
NEXT_ACTION = "governed_merge_pr_5"
BASELINE_HEAD = "0beb4c23604f1e45736c3082f99d2e08fa1ac308"
BRANCH_BASE = "98ebd95564216fbbee222aab630b73b5ff6f298d"
FEATURE_BRANCH = "codex/v0.15.0-death-animation-front"
RUN_APPROVED_HEAD = "f3d68faa5524392e66aee2fc2a450b9da8fa734b"
HIT_APPROVED_HEAD = "a3e37865f260c5a6cd56743e1d4b9131fcb12cda"
PR4_MERGE_COMMIT = "98ebd95564216fbbee222aab630b73b5ff6f298d"
FROZEN_V0141_BLOB = "9bbc85bd5ca839b4a0fd71b45a279e852a275fc5"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def validate_state_consistency(
    state: Mapping[str, Any],
    checkpoint_text: str,
    review_text: str,
    roadmap_text: str = "",
) -> dict[str, Any]:
    """Validate the active v0.15.1 state and its forward-only governance."""
    failures: list[str] = []
    required = {
        "schema_version",
        "version",
        "phase",
        "previous_release",
        "current_gate",
        "stop_reason",
        "allowed_next_actions",
        "forbidden_actions",
        "production_approved",
        "production_routing",
        "external_visual_review",
        "always_on_dashboard_policy",
        "runtime_mode",
        "new_generation",
        "review",
        "incident",
        "evidence",
        "state_consistency",
        "hit_reaction_front_visual_content",
        "death_animation_front_visual_content",
    }
    failures.extend(f"missing:{key}" for key in sorted(required - set(state)))

    if state.get("schema_version") != CURRENT_VERSION or state.get("version") != CURRENT_VERSION:
        failures.append("version_must_be_0.15.1")
    if state.get("phase") != CURRENT_PHASE:
        failures.append("phase_must_be_DEATH_ANIMATION_FRONT")
    if state.get("current_gate") != CURRENT_GATE:
        failures.append("current_gate_invalid")
    if state.get("hit_reaction_front_visual_content") != "APPROVED_PILOT":
        failures.append("hit_visual_content_must_remain_approved_pilot")
    if state.get("death_animation_front_visual_content") != "APPROVED_PILOT":
        failures.append("death_visual_content_must_be_approved_pilot")
    if state.get("production_approved") is not False or state.get("production_routing") != "BLOCKED":
        failures.append("production_must_remain_blocked")
    if state.get("always_on_dashboard_policy") != "ENABLED" or state.get("runtime_mode") != "DOCKER_ALWAYS_ON_LOCAL":
        failures.append("always_on_dashboard_boundary_invalid")
    if state.get("new_generation") != 0:
        failures.append("new_generation_must_remain_zero")
    if state.get("allowed_next_actions") != [NEXT_ACTION]:
        failures.append("next_action_must_be_external_visual_review_death_animation_front")

    previous = _mapping(state.get("previous_release"))
    if previous.get("version") != "0.14.1":
        failures.append("previous_release_must_be_0.14.1")

    external = _mapping(state.get("external_visual_review"))
    for key in ("attack_front_v2", "observability_dashboard", "run_front_v1", "hit_reaction_front"):
        if external.get(key) != "APPROVED_PILOT":
            failures.append(f"external_review:{key}_must_be_approved_pilot")
    if external.get("death_animation_front") != "APPROVED_PILOT":
        failures.append("external_review:death_animation_front_must_be_approved_pilot")

    review = _mapping(state.get("review"))
    expected_review = {
        "repository": "KayzenRoot/ugas",
        "baseline_head": BASELINE_HEAD,
        "branch_base_commit": BRANCH_BASE,
        "feature_branch": FEATURE_BRANCH,
        "execution_mode": "GITHUB_PR_FIRST",
        "merge_policy": "PROTECTED_GOVERNED_MERGE_AFTER_EXTERNAL_VISUAL_APPROVAL",
        "no_self_merge_until_external_approval": False,
        "direct_main_push_forbidden": True,
        "pr4_number": 4,
        "pr4_state": "MERGED",
        "pr4_merge_commit": PR4_MERGE_COMMIT,
        "pr4_merged_head": "761ed5296e05571fdfbed1da04cfb7815049fa87",
        "pr4_technical_approved_head": HIT_APPROVED_HEAD,
    }
    failures.extend(f"review:{key}" for key, expected in expected_review.items() if review.get(key) != expected)
    new_pr_state = review.get("pr_state")
    new_pr_number = review.get("pr_number")
    if new_pr_state not in {"NOT_CREATED", "OPEN"}:
        failures.append("new_pr_state_must_be_not_created_or_open")
    if new_pr_state == "NOT_CREATED" and (new_pr_number != 0 or review.get("real_pr_checks_green") is not False):
        failures.append("not_created_new_pr_must_have_zero_and_false_checks")
    if new_pr_state == "OPEN" and (not isinstance(new_pr_number, int) or new_pr_number <= 0):
        failures.append("open_new_pr_requires_positive_number")
    if new_pr_state == "OPEN" and new_pr_number != 5:
        failures.append("death_v0151_must_continue_pr5")
    if not isinstance(review.get("real_pr_checks_green"), bool):
        failures.append("real_pr_checks_green_must_be_boolean")
    if review.get("rejected_reviewed_head") != "c573ab020106ee89a36e1edb9bfae8b526d5057e":
        failures.append("rejected_reviewed_head_must_bind_v0150_head")
    if review.get("merge_authorization") != "APPROVED_TO_MERGE":
        failures.append("death_pr_merge_authorization_must_be_approved_to_merge")
    if review.get("pr4_state") == "MERGED" and review.get("pr4_merge_commit") == PR4_MERGE_COMMIT and review.get("pr_number") == 4:
        failures.append("new_pr_fields_must_not_reuse_pr4_identity")

    nested = _mapping(state.get("state_consistency"))
    nested_expected = {
        "status": CURRENT_GATE,
        "version": CURRENT_VERSION,
        "phase": CURRENT_PHASE,
        "current_gate": CURRENT_GATE,
        "feature_branch": FEATURE_BRANCH,
        "baseline_head": BASELINE_HEAD,
        "branch_base_commit": BRANCH_BASE,
        "production_routing": "BLOCKED",
        "production_approved": False,
        "dashboard_read_only": True,
        "local_only": True,
        "telemetry_upload": False,
        "new_generation": 0,
        "source_only_pixels": True,
        "sam2_runs": 0,
        "comfyui_generation_jobs": 0,
        "diffusion_runs": 0,
        "run_front_v1_external_visual": "APPROVED_PILOT",
        "hit_reaction_front_external_visual": "APPROVED_PILOT",
        "death_animation_front_external_visual": "APPROVED_PILOT",
        "capability_matrix_next_candidate": "DEATH_ANIMATION_FRONT",
        "capability_count": 16,
        "runtime_mode": "DOCKER_ALWAYS_ON_LOCAL",
        "always_on_dashboard_policy": "ENABLED",
        "allowed_next_actions": [NEXT_ACTION],
        "next_capability_started": False,
        "v0141_frozen_evidence": "RESTORED_AND_VERIFIED",
        "v0150_rejected_reviewed_head": "c573ab020106ee89a36e1edb9bfae8b526d5057e",
    }
    failures.extend(f"state_consistency:{key}" for key, expected in nested_expected.items() if nested.get(key) != expected)

    evidence = _mapping(state.get("evidence"))
    required_evidence = (
        "historical_v0140_state",
        "historical_v0131_state",
        "historical_v0130_state",
        "historical_v0124_state",
        "capability_matrix",
        "contract",
        "execution",
        "visual_manifest",
        "negative_controls",
        "loop_negative_controls",
        "external_approval",
        "provenance",
        "integrity_repair",
        "frozen_v0141_state_consistency",
    )
    failures.extend(f"evidence_missing:{key}" for key in required_evidence if not evidence.get(key))

    active_sources = [checkpoint_text.split("## Historical", 1)[0], review_text]
    if roadmap_text:
        active_sources.append(roadmap_text.split("## Historical", 1)[0])
    required_literals = (
        "0.15.1",
        CURRENT_PHASE,
        CURRENT_GATE,
        NEXT_ACTION,
        "DEATH_ANIMATION_FRONT",
        "hit_reaction_front=APPROVED_PILOT",
        "run_front_v1=APPROVED_PILOT",
        "death_animation_front=APPROVED_PILOT",
        "production_approved=false",
        "production_routing=BLOCKED",
        "new_generation=0",
        "CAPABILITY_COUNT=16",
        "GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED",
        "USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY",
        "GITHUB_REVIEW_MODE=PR_FIRST",
        "ALWAYS_ON_DASHBOARD_POLICY=ENABLED",
        "DOCKER_ALWAYS_ON_LOCAL",
        "PR #4",
        "MERGED",
        PR4_MERGE_COMMIT,
        HIT_APPROVED_HEAD,
        RUN_APPROVED_HEAD,
        "v0141_frozen_evidence=RESTORED_AND_VERIFIED",
        "KayzenRoot/ugas",
        "c573ab020106ee89a36e1edb9bfae8b526d5057e",
        "v0.15.0",
        "Merge PR #5 through the protected GitHub path",
        "Do not start MULTI_DIRECTION_ANIMATION_RUNTIME",
    )
    combined = "\n".join(active_sources)
    for literal in required_literals:
        if literal.casefold() not in combined.casefold():
            failures.append(f"active_documents_missing:{literal}")
    for source in active_sources:
        if re.search(r"production[^\n.]{0,100}\b(?:enabled|active|unblocked|promoted)", source, re.IGNORECASE):
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
            "death_visual": state.get("death_animation_front_visual_content"),
            "production_routing": state.get("production_routing"),
            "new_generation": state.get("new_generation"),
            "pr4_state": review.get("pr4_state"),
            "new_pr_state": review.get("pr_state"),
            "frozen_v0141_blob": FROZEN_V0141_BLOB,
        },
    }
