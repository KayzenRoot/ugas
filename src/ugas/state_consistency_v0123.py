"""Fail-closed active governance checks for v0.12.3."""

from __future__ import annotations

from typing import Any, Mapping

CURRENT_VERSION = "0.12.3"
CURRENT_PHASE = "GITHUB_NATIVE_REVIEW_INFRASTRUCTURE"
CURRENT_GATE = "GITHUB_NATIVE_REVIEW_READY_TECHNICALLY_QUALIFIED"
NEXT_ACTION = "external_review_github_native_v0123_and_dashboard_v0122"
FEATURE_BRANCH = "codex/v0.12.3-github-native-review"
BASELINE_HEAD = "6b956b9299f3a2f75280f17706c38c59e3714034"


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str, review_text: str, roadmap_text: str = "") -> dict[str, Any]:
    failures: list[str] = []
    required = {"schema_version", "version", "phase", "previous_release", "current_gate", "allowed_next_actions", "forbidden_actions", "production_approved", "production_routing", "external_visual_review", "always_on_dashboard_policy", "runtime_mode", "new_generation", "review", "evidence", "state_consistency"}
    failures.extend(f"missing:{key}" for key in sorted(required - set(state)))
    if state.get("schema_version") != CURRENT_VERSION or state.get("version") != CURRENT_VERSION: failures.append("version_must_be_0.12.3")
    if state.get("phase") != CURRENT_PHASE: failures.append("phase_invalid")
    if state.get("current_gate") != CURRENT_GATE: failures.append("current_gate_invalid")
    if state.get("production_approved") is not False: failures.append("production_approved_must_remain_false")
    if state.get("production_routing") != "BLOCKED": failures.append("production_routing_must_remain_blocked")
    if state.get("always_on_dashboard_policy") != "ENABLED": failures.append("always_on_dashboard_policy_must_remain_enabled")
    if state.get("runtime_mode") != "DOCKER_ALWAYS_ON_LOCAL": failures.append("runtime_mode_invalid")
    if state.get("new_generation") != 0: failures.append("new_generation_must_remain_zero")
    if state.get("allowed_next_actions") != [NEXT_ACTION]: failures.append("next_action_must_wait_for_external_github_review")
    previous = state.get("previous_release") if isinstance(state.get("previous_release"), Mapping) else {}
    if previous.get("version") != "0.12.2": failures.append("previous_release_must_be_0.12.2")
    external = state.get("external_visual_review") if isinstance(state.get("external_visual_review"), Mapping) else {}
    if external.get("attack_front_v2") != "APPROVED_PILOT": failures.append("attack_front_v2_pilot_decision_missing")
    if external.get("observability_dashboard") != "REQUIRED": failures.append("dashboard_external_review_must_be_required")
    review = state.get("review") if isinstance(state.get("review"), Mapping) else {}
    if review.get("repository") != "csn1985-ship-it/ugas": failures.append("repository_invalid")
    if review.get("baseline_head") != BASELINE_HEAD: failures.append("baseline_head_invalid")
    if review.get("feature_branch") != FEATURE_BRANCH: failures.append("feature_branch_invalid")
    nested = state.get("state_consistency") if isinstance(state.get("state_consistency"), Mapping) else {}
    checks = {"status": CURRENT_GATE, "version": CURRENT_VERSION, "phase": CURRENT_PHASE, "current_gate": CURRENT_GATE, "feature_branch": FEATURE_BRANCH, "baseline_head": BASELINE_HEAD, "production_routing": "BLOCKED", "production_approved": False, "dashboard_read_only": True, "local_only": True, "telemetry_upload": False, "new_generation": 0, "historical_v0122_preserved": True, "historical_v0121_preserved": True, "attack_front_v2_external_visual": "APPROVED_PILOT", "observability_dashboard_external_visual": "REQUIRED", "runtime_mode": "DOCKER_ALWAYS_ON_LOCAL", "always_on_dashboard_policy": "ENABLED", "allowed_next_actions": [NEXT_ACTION]}
    failures.extend(f"state_consistency:{key}" for key, expected in checks.items() if nested.get(key) != expected)
    evidence = state.get("evidence") if isinstance(state.get("evidence"), Mapping) else {}
    failures.extend(f"evidence_missing:{key}" for key in ("github_preflight", "review_manifest", "visual_manifest", "autostart", "governance_consistency", "v1_capability_matrix", "tests", "validation") if not evidence.get(key))
    active_checkpoint = checkpoint_text.split("## Historical", 1)[0]
    active_roadmap = roadmap_text.split("## Historical v0.12.2", 1)[0] if roadmap_text else ""
    sources = [("checkpoint", active_checkpoint), ("review", review_text)]
    if roadmap_text:
        sources.append(("roadmap", active_roadmap))
    for source_name, source in sources:
        for literal in ("0.12.3", CURRENT_PHASE, CURRENT_GATE, NEXT_ACTION, "production_routing=BLOCKED", "production_approved=false", "DOCKER_ALWAYS_ON_LOCAL", "ALWAYS_ON_DASHBOARD_POLICY", "RUN_FRONT_V1"):
            if literal.casefold() not in source.casefold(): failures.append(f"{source_name}_missing:{literal}")
    if "external_review_observability_dashboard_v0121" in active_checkpoint.casefold() or "external_review_observability_dashboard_v0121" in active_roadmap.casefold(): failures.append("active_navigation_contains_stale_v0121_gate")
    return {"status": CURRENT_GATE if not failures else "STATE_CONSISTENCY_FAILED", "schema_version": CURRENT_VERSION, "failures": failures, "checked": {"version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "feature_branch": review.get("feature_branch"), "baseline_head": review.get("baseline_head"), "next_action": state.get("allowed_next_actions"), "production_routing": state.get("production_routing"), "production_approved": state.get("production_approved"), "runtime_mode": state.get("runtime_mode"), "always_on_dashboard_policy": state.get("always_on_dashboard_policy")}}
