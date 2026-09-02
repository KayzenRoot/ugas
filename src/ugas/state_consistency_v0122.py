"""Fail-closed governance checks for the v0.12.2 always-on observer."""

from __future__ import annotations

import re
from typing import Any, Mapping

CURRENT_VERSION = "0.12.2"
CURRENT_PHASE = "LOCAL_REALTIME_OBSERVABILITY"
CURRENT_GATE = "LOCAL_ALWAYS_ON_OBSERVABILITY_DASHBOARD_TECHNICALLY_QUALIFIED"
NEXT_ACTION = "external_review_observability_dashboard_v0122"


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str, review_text: str) -> dict[str, Any]:
    failures: list[str] = []
    required = {"schema_version", "version", "phase", "previous_release", "current_gate", "allowed_next_actions", "forbidden_actions", "production_approved", "production_routing", "external_visual_review", "state_consistency", "evidence"}
    failures.extend(f"missing:{key}" for key in sorted(required - set(state)))
    if state.get("schema_version") != CURRENT_VERSION or state.get("version") != CURRENT_VERSION: failures.append("version_must_be_0.12.2")
    if state.get("phase") != CURRENT_PHASE: failures.append("phase_invalid")
    if state.get("current_gate") != CURRENT_GATE: failures.append("current_gate_invalid")
    if state.get("production_approved") is not False: failures.append("production_approved_must_remain_false")
    if state.get("production_routing") != "BLOCKED": failures.append("production_routing_must_remain_blocked")
    if state.get("allowed_next_actions") != [NEXT_ACTION]: failures.append("next_action_must_wait_for_external_dashboard_review_v0122")
    previous = state.get("previous_release") if isinstance(state.get("previous_release"), Mapping) else {}
    if previous.get("version") != "0.12.1": failures.append("previous_release_must_be_0.12.1")
    external = state.get("external_visual_review") if isinstance(state.get("external_visual_review"), Mapping) else {}
    if external.get("attack_front_v2") != "APPROVED_PILOT": failures.append("attack_front_v2_pilot_decision_missing")
    if external.get("observability_dashboard") != "REQUIRED": failures.append("dashboard_external_review_must_be_required")
    nested = state.get("state_consistency") if isinstance(state.get("state_consistency"), Mapping) else {}
    checks = {"status": CURRENT_GATE, "production_routing": "BLOCKED", "production_approved": False, "dashboard_read_only": True, "local_only": True, "telemetry_upload": False, "new_generation": 0, "historical_v0120_preserved": True, "historical_v0121_preserved": True, "runtime_mode": "DOCKER_ALWAYS_ON_LOCAL", "always_on_dashboard_policy": "ENABLED"}
    failures.extend(f"state_consistency:{key}" for key, expected in checks.items() if nested.get(key) != expected)
    evidence = state.get("evidence") if isinstance(state.get("evidence"), Mapping) else {}
    failures.extend(f"evidence_missing:{key}" for key in ("external_review", "review_index", "startup", "state_consistency") if not evidence.get(key))
    combined = f"{checkpoint_text}\n{review_text}"
    for literal in ("0.12.2", "0.12.1", "0.12.0", "0.11.2", "APPROVED_PILOT", "production_routing=BLOCKED", "production_approved=false", "local-only", "read-only", "DOCKER_ALWAYS_ON_LOCAL", "ALWAYS_ON_DASHBOARD_POLICY", NEXT_ACTION):
        if literal.casefold() not in combined.casefold(): failures.append(f"documents_missing:{literal}")
    if re.search(r"production[^\n.]{0,120}\b(?:enabled|active|unblocked|promoted|approved)\b", combined, re.IGNORECASE): failures.append("documents_promote_production")
    return {"status": CURRENT_GATE if not failures else "STATE_CONSISTENCY_FAILED", "schema_version": CURRENT_VERSION, "failures": failures, "checked": {"version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "attack_front_v2": external.get("attack_front_v2"), "dashboard_review": external.get("observability_dashboard"), "production_routing": state.get("production_routing"), "production_approved": state.get("production_approved"), "runtime_mode": nested.get("runtime_mode"), "always_on_dashboard_policy": nested.get("always_on_dashboard_policy")}}
