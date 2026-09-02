"""Fail-closed governance checks for the v0.12.4 recovery slice."""

from __future__ import annotations

from typing import Any, Mapping

CURRENT_VERSION = "0.12.4"
CURRENT_PHASE = "GITHUB_CI_GOVERNANCE_RECOVERY"
READY_GATE = "GITHUB_CI_GOVERNANCE_RECOVERY_READY_FOR_PR"
QUALIFIED_GATE = "GITHUB_CI_GOVERNANCE_RECOVERY_TECHNICALLY_QUALIFIED"
CURRENT_GATE = READY_GATE
NEXT_ACTION = "external_review_github_ci_governance_v0124"
FEATURE_BRANCH = "codex/v0.12.4-github-ci-governance-recovery"
BASELINE_HEAD = "877ede34afadd631764887ad6c5fb941ca4371a8"
INCIDENT_CLASSIFICATION = "GOVERNANCE_ORDER_VIOLATION_AND_FAILED_CHECK_MERGE"


def validate_state_consistency(
    state: Mapping[str, Any], checkpoint_text: str, review_text: str, roadmap_text: str = ""
) -> dict[str, Any]:
    failures: list[str] = []
    required = {
        "schema_version", "version", "phase", "previous_release", "current_gate",
        "allowed_next_actions", "forbidden_actions", "production_approved",
        "production_routing", "external_visual_review", "always_on_dashboard_policy",
        "runtime_mode", "new_generation", "review", "incident", "evidence",
        "state_consistency",
    }
    failures.extend(f"missing:{key}" for key in sorted(required - set(state)))
    if state.get("schema_version") != CURRENT_VERSION or state.get("version") != CURRENT_VERSION:
        failures.append("version_must_be_0.12.4")
    if state.get("phase") != CURRENT_PHASE:
        failures.append("phase_invalid")
    if state.get("current_gate") not in {READY_GATE, QUALIFIED_GATE}:
        failures.append("current_gate_invalid")
    if state.get("production_approved") is not False:
        failures.append("production_approved_must_remain_false")
    if state.get("production_routing") != "BLOCKED":
        failures.append("production_routing_must_remain_blocked")
    if state.get("always_on_dashboard_policy") != "ENABLED":
        failures.append("always_on_dashboard_policy_must_remain_enabled")
    if state.get("runtime_mode") != "DOCKER_ALWAYS_ON_LOCAL":
        failures.append("runtime_mode_invalid")
    if state.get("new_generation") != 0:
        failures.append("new_generation_must_remain_zero")
    if state.get("allowed_next_actions") != [NEXT_ACTION]:
        failures.append("next_action_must_wait_for_external_github_ci_governance_review")

    previous = state.get("previous_release") if isinstance(state.get("previous_release"), Mapping) else {}
    if previous.get("version") != "0.12.3":
        failures.append("previous_release_must_be_0.12.3")
    external = state.get("external_visual_review") if isinstance(state.get("external_visual_review"), Mapping) else {}
    if external.get("attack_front_v2") != "APPROVED_PILOT":
        failures.append("attack_front_v2_pilot_decision_missing")
    if external.get("observability_dashboard") != "APPROVED_PILOT":
        failures.append("dashboard_external_visual_must_be_approved_pilot")

    review = state.get("review") if isinstance(state.get("review"), Mapping) else {}
    if review.get("repository") != "csn1985-ship-it/ugas":
        failures.append("repository_invalid")
    if review.get("baseline_head") != BASELINE_HEAD:
        failures.append("baseline_head_invalid")
    if review.get("feature_branch") != FEATURE_BRANCH:
        failures.append("feature_branch_invalid")
    if review.get("execution_mode") != "GITHUB_PR_FIRST":
        failures.append("execution_mode_invalid")
    if review.get("merge_policy") != "NO_SELF_MERGE_UNTIL_EXPLICIT_SOL_APPROVAL":
        failures.append("merge_policy_invalid")
    if review.get("no_self_merge_until_external_approval") is not True:
        failures.append("no_self_merge_policy_missing")
    if review.get("direct_main_push_forbidden") is not True:
        failures.append("direct_main_push_policy_missing")

    incident = state.get("incident") if isinstance(state.get("incident"), Mapping) else {}
    if incident.get("classification") != INCIDENT_CLASSIFICATION:
        failures.append("incident_classification_invalid")
    if incident.get("pr_number") != 1 or incident.get("review_workflow_conclusion") != "FAILURE":
        failures.append("pr1_incident_binding_invalid")

    nested = state.get("state_consistency") if isinstance(state.get("state_consistency"), Mapping) else {}
    expected_nested = {
        "status": state.get("current_gate"), "version": CURRENT_VERSION, "phase": CURRENT_PHASE,
        "current_gate": state.get("current_gate"), "feature_branch": FEATURE_BRANCH,
        "baseline_head": BASELINE_HEAD, "production_routing": "BLOCKED",
        "production_approved": False, "dashboard_read_only": True, "local_only": True,
        "telemetry_upload": False, "new_generation": 0, "historical_v0123_preserved": True,
        "observability_dashboard_external_visual": "APPROVED_PILOT",
        "attack_front_v2_external_visual": "APPROVED_PILOT",
        "runtime_mode": "DOCKER_ALWAYS_ON_LOCAL", "always_on_dashboard_policy": "ENABLED",
        "allowed_next_actions": [NEXT_ACTION],
    }
    failures.extend(f"state_consistency:{key}" for key, expected in expected_nested.items() if nested.get(key) != expected)

    evidence = state.get("evidence") if isinstance(state.get("evidence"), Mapping) else {}
    for key in ("incident", "dashboard_visual_approval", "workflow_validation", "ruleset_readback", "tests", "validation", "negative_controls"):
        if not evidence.get(key):
            failures.append(f"evidence_missing:{key}")

    active_checkpoint = checkpoint_text.split("## Historical", 1)[0]
    active_roadmap = roadmap_text.split("## Historical", 1)[0] if roadmap_text else ""
    sources = [("checkpoint", active_checkpoint), ("review", review_text)]
    if roadmap_text:
        sources.append(("roadmap", active_roadmap))
    for source_name, source in sources:
        for literal in (
            "0.12.4", CURRENT_PHASE, NEXT_ACTION, "production_routing=BLOCKED",
            "production_approved=false", "DOCKER_ALWAYS_ON_LOCAL", "ALWAYS_ON_DASHBOARD_POLICY",
            "PR #1", "GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED",
            "USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY", "NO_SELF_MERGE_UNTIL_EXTERNAL_APPROVAL=true",
            "RUN_FRONT_V1",
        ):
            if literal.casefold() not in source.casefold():
                failures.append(f"{source_name}_missing:{literal}")
    if "external_review_observability_dashboard_v0121" in active_checkpoint.casefold() or "external_review_observability_dashboard_v0121" in active_roadmap.casefold():
        failures.append("active_navigation_contains_stale_v0121_gate")
    if "gh pr merge" in review_text.casefold() or "auto-merge" in review_text.casefold():
        failures.append("review_documents_must_not_authorize_self_merge")

    return {
        "status": state.get("current_gate") if not failures else "STATE_CONSISTENCY_FAILED",
        "schema_version": CURRENT_VERSION,
        "failures": failures,
        "checked": {
            "version": state.get("version"), "phase": state.get("phase"),
            "current_gate": state.get("current_gate"), "feature_branch": review.get("feature_branch"),
            "baseline_head": review.get("baseline_head"), "next_action": state.get("allowed_next_actions"),
            "production_routing": state.get("production_routing"),
            "production_approved": state.get("production_approved"),
        },
    }
