"""Fail-closed governance checks for the v0.12.0 observability increment."""

from __future__ import annotations

import re
from typing import Any, Mapping

CURRENT_VERSION = "0.12.0"
CURRENT_PHASE = "LOCAL_REALTIME_OBSERVABILITY"
CURRENT_GATE = "LOCAL_REALTIME_OBSERVABILITY_DASHBOARD_MVP_TECHNICALLY_QUALIFIED"


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str, review_text: str) -> dict[str, Any]:
    failures: list[str] = []
    required = {"schema_version", "version", "phase", "previous_release", "current_gate", "allowed_next_actions", "production_approved", "production_routing", "external_visual_review", "state_consistency", "evidence"}
    failures.extend(f"missing:{key}" for key in sorted(required - set(state)))
    if state.get("schema_version") != CURRENT_VERSION or state.get("version") != CURRENT_VERSION: failures.append("version_must_be_0.12.0")
    if state.get("phase") != CURRENT_PHASE: failures.append("phase_invalid")
    if state.get("current_gate") != CURRENT_GATE: failures.append("current_gate_invalid")
    if state.get("production_approved") is not False: failures.append("production_approved_must_remain_false")
    if state.get("production_routing") != "BLOCKED": failures.append("production_routing_must_remain_blocked")
    if state.get("allowed_next_actions") != ["external_review_observability_dashboard_v0120"]: failures.append("next_action_must_wait_for_external_dashboard_review")
    previous = state.get("previous_release") if isinstance(state.get("previous_release"), Mapping) else {}
    if previous.get("version") != "0.11.2": failures.append("previous_release_must_be_0.11.2")
    external = state.get("external_visual_review") if isinstance(state.get("external_visual_review"), Mapping) else {}
    if external.get("attack_front_v2") != "APPROVED_PILOT": failures.append("attack_front_v2_pilot_decision_missing")
    if external.get("observability_dashboard") != "REQUIRED": failures.append("dashboard_external_review_must_be_required")
    nested = state.get("state_consistency") if isinstance(state.get("state_consistency"), Mapping) else {}
    checks = {"status": CURRENT_GATE, "production_routing": "BLOCKED", "production_approved": False, "dashboard_read_only": True, "local_only": True, "telemetry_upload": False, "new_generation": 0, "historical_v0112_preserved": True}
    failures.extend(f"state_consistency:{key}" for key, expected in checks.items() if nested.get(key) != expected)
    evidence = state.get("evidence") if isinstance(state.get("evidence"), Mapping) else {}
    failures.extend(f"evidence_missing:{key}" for key in ("external_review", "review_index", "startup", "state_consistency") if not evidence.get(key))
    combined = f"{checkpoint_text}\n{review_text}"
    for literal in ("0.12.0", "0.11.2", "APPROVED_PILOT", "production_routing=BLOCKED", "production_approved=false", "local-only", "read-only", "external_review_observability_dashboard_v0120"):
        if literal.casefold() not in combined.casefold(): failures.append(f"documents_missing:{literal}")
    if re.search(r"production[^\n.]{0,120}\b(?:enabled|active|unblocked|promoted|approved)\b", combined, re.IGNORECASE): failures.append("documents_promote_production")
    return {"status": CURRENT_GATE if not failures else "STATE_CONSISTENCY_FAILED", "schema_version": CURRENT_VERSION, "failures": failures, "checked": {"version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "attack_front_v2": external.get("attack_front_v2"), "dashboard_review": external.get("observability_dashboard"), "production_routing": state.get("production_routing"), "production_approved": state.get("production_approved")}}
