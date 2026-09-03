"""Fail-closed state checks for the v0.14.1 HIT_REACTION_FRONT package-integrity correction."""

from __future__ import annotations

import re
from typing import Any, Mapping

CURRENT_VERSION = "0.14.1"
CURRENT_PHASE = "HIT_REACTION_FRONT"
CURRENT_GATE = "HIT_REACTION_FRONT_PACKAGE_INTEGRITY_TECHNICALLY_QUALIFIED"
NEXT_ACTION = "external_review_hit_reaction_front_v0141"
VISUAL_CONTENT = "APPROVED_PILOT_CONTENT_PENDING_PACKAGE_INTEGRITY_REVIEW"
BASELINE_HEAD = "0beb4c23604f1e45736c3082f99d2e08fa1ac308"
FEATURE_BRANCH = "codex/v0.14.0-hit-reaction-front"
RUN_APPROVED_HEAD = "f3d68faa5524392e66aee2fc2a450b9da8fa734b"
REJECTED_REVIEWED_HEAD = "c059e24a4fa215882fac4b36991f7860f185a920"
BRANCH_BASE = "ebcf0b587628dcd33c316378fb2815f616172ffa"


def validate_state_consistency(
    state: Mapping[str, Any], checkpoint_text: str, review_text: str, roadmap_text: str = ""
) -> dict[str, Any]:
    failures: list[str] = []
    required = {
        "schema_version", "version", "phase", "previous_release", "current_gate",
        "stop_reason", "allowed_next_actions", "forbidden_actions", "production_approved",
        "production_routing", "external_visual_review", "always_on_dashboard_policy",
        "runtime_mode", "new_generation", "review", "incident", "evidence", "state_consistency",
        "hit_reaction_front_visual_content",
    }
    failures.extend(f"missing:{key}" for key in sorted(required - set(state)))
    if state.get("schema_version") != CURRENT_VERSION or state.get("version") != CURRENT_VERSION:
        failures.append("version_must_be_0.14.1")
    if state.get("phase") != CURRENT_PHASE:
        failures.append("phase_must_be_HIT_REACTION_FRONT")
    if state.get("current_gate") != CURRENT_GATE:
        failures.append("current_gate_invalid")
    if state.get("hit_reaction_front_visual_content") != VISUAL_CONTENT:
        failures.append("visual_content_must_remain_approved_pilot_pending_package_review")
    if state.get("production_approved") is not False or state.get("production_routing") != "BLOCKED":
        failures.append("production_must_remain_blocked")
    if state.get("always_on_dashboard_policy") != "ENABLED" or state.get("runtime_mode") != "DOCKER_ALWAYS_ON_LOCAL":
        failures.append("always_on_dashboard_boundary_invalid")
    if state.get("new_generation") != 0:
        failures.append("new_generation_must_remain_zero")
    if state.get("allowed_next_actions") != [NEXT_ACTION]:
        failures.append("next_action_must_be_external_review_hit_reaction_front_v0141")

    previous = state.get("previous_release") if isinstance(state.get("previous_release"), Mapping) else {}
    if previous.get("version") != "0.13.1":
        failures.append("previous_release_must_be_approved_pilot_0.13.1")
    external = state.get("external_visual_review") if isinstance(state.get("external_visual_review"), Mapping) else {}
    if external.get("run_front_v1") != "APPROVED_PILOT":
        failures.append("run_front_external_visual_review_must_remain_approved_pilot")
    if external.get("hit_reaction_front") != "APPROVED_PILOT_CONTENT_PENDING_PACKAGE_INTEGRITY":
        failures.append("hit_reaction_front_must_be_approved_pilot_content_pending_package_integrity")
    if external.get("attack_front_v2") != "APPROVED_PILOT" or external.get("observability_dashboard") != "APPROVED_PILOT":
        failures.append("historical_external_decisions_missing")

    review = state.get("review") if isinstance(state.get("review"), Mapping) else {}
    expected_review = {
        "repository": "csn1985-ship-it/ugas", "baseline_head": BASELINE_HEAD,
        "feature_branch": FEATURE_BRANCH, "execution_mode": "GITHUB_PR_FIRST",
        "merge_policy": "NO_SELF_MERGE_UNTIL_EXTERNAL_VISUAL_APPROVAL",
        "no_self_merge_until_external_approval": True, "direct_main_push_forbidden": True,
    }
    failures.extend(f"review:{key}" for key, expected in expected_review.items() if review.get(key) != expected)
    pr_state = review.get("pr_state")
    if pr_state != "OPEN":
        failures.append("review_pr_state_must_remain_open")
    if review.get("pr_number") != 4:
        failures.append("review_pr_number_must_remain_4")
    if review.get("rejected_reviewed_head") != REJECTED_REVIEWED_HEAD:
        failures.append("rejected_reviewed_head_must_bind_c059e24")
    if review.get("merge_authorization") == "APPROVED_TO_MERGE":
        failures.append("v0141_must_not_claim_merge_authorization")

    nested = state.get("state_consistency") if isinstance(state.get("state_consistency"), Mapping) else {}
    nested_expected = {
        "status": CURRENT_GATE, "version": CURRENT_VERSION, "phase": CURRENT_PHASE,
        "current_gate": CURRENT_GATE, "feature_branch": FEATURE_BRANCH,
        "baseline_head": BASELINE_HEAD, "production_routing": "BLOCKED",
        "production_approved": False, "dashboard_read_only": True, "local_only": True,
        "telemetry_upload": False, "new_generation": 0, "source_only_pixels": True,
        "sam2_runs": 0, "comfyui_generation_jobs": 0, "diffusion_runs": 0,
        "run_front_v1_external_visual": "APPROVED_PILOT",
        "hit_reaction_front_external_visual": "APPROVED_PILOT_CONTENT_PENDING_PACKAGE_INTEGRITY",
        "hit_reaction_front_visual_content": VISUAL_CONTENT,
        "capability_matrix_next_candidate": "HIT_REACTION_FRONT",
        "capability_count": 16, "runtime_mode": "DOCKER_ALWAYS_ON_LOCAL",
        "always_on_dashboard_policy": "ENABLED", "allowed_next_actions": [NEXT_ACTION],
        "next_capability_started": False,
    }
    failures.extend(f"state_consistency:{key}" for key, expected in nested_expected.items() if nested.get(key) != expected)

    evidence = state.get("evidence") if isinstance(state.get("evidence"), Mapping) else {}
    for key in ("historical_v0140_state", "historical_v0131_state", "historical_v0130_state", "capability_matrix", "contract", "execution", "visual_manifest", "negative_controls", "loop_negative_controls", "visual_preservation"):
        if not evidence.get(key):
            failures.append(f"evidence_missing:{key}")

    active_sources = [checkpoint_text.split("## Historical", 1)[0], review_text]
    if roadmap_text:
        active_sources.append(roadmap_text.split("## Historical", 1)[0])
    required_literals = (
        "0.14.1", CURRENT_PHASE, "HIT_REACTION_FRONT", CURRENT_GATE, NEXT_ACTION,
        "APPROVED_PILOT_CONTENT_PENDING_PACKAGE_INTEGRITY_REVIEW",
        "run_front_v1=APPROVED_PILOT",
        "production_approved=false", "production_routing=BLOCKED", "new_generation=0",
        "CAPABILITY_COUNT=16", "GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED",
        "USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY",
        "NO_SELF_MERGE_UNTIL_EXTERNAL_VISUAL_APPROVAL=true",
        "ALWAYS_ON_DASHBOARD_POLICY=ENABLED", "DOCKER_ALWAYS_ON_LOCAL",
        "0.13.1", "0.14.0", RUN_APPROVED_HEAD, REJECTED_REVIEWED_HEAD,
        "Do not merge", "DEATH_ANIMATION_FRONT",
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
            "version": state.get("version"), "phase": state.get("phase"),
            "current_gate": state.get("current_gate"), "feature_branch": review.get("feature_branch"),
            "baseline_head": review.get("baseline_head"), "next_action": state.get("allowed_next_actions"),
            "visual_content": state.get("hit_reaction_front_visual_content"),
            "production_routing": state.get("production_routing"),
            "new_generation": state.get("new_generation"),
        },
    }
