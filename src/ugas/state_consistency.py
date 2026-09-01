"""Fatal consistency checks for the active UGAS v0.9.0 runtime slice."""

from __future__ import annotations

import re
from typing import Any, Mapping

CURRENT_SCHEMA_VERSION = "0.9.0"
CANONICAL_R4_SHA256 = "7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798"
CANONICAL_R4_REVISION = "revision-3a425d184b1a49be9f6d6c8d52d04b96"
CURRENT_PHASE = "REUSABLE_DETERMINISTIC_ANIMATION_RUNTIME"
CURRENT_GATE = "CUTOUT_ANIMATION_RUNTIME_V1_IDLE_FRONT_TECHNICALLY_QUALIFIED"
CURRENT_GATES = {"ANIMATION_RUNTIME_WALK_REPLAY_GAP", "ANIMATION_RUNTIME_IDLE_FRONT_GAP", CURRENT_GATE}


class StateConsistencyError(ValueError):
    pass


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str, review_text: str) -> dict[str, Any]:
    failures: list[str] = []
    required = {"schema_version", "version", "phase", "previous_release", "current_gate", "stop_reason", "canonical_anchor", "allowed_next_actions", "forbidden_actions", "historical_smoke_status", "generation_provider_change_authorized", "walk_authorized", "production_walk_authorized", "provider_smoke_status", "historical_pose_lane_status", "pose_lane_status", "previous_review_snapshot_status", "state_consistency"}
    failures.extend(f"missing:{key}" for key in sorted(required - set(state)))
    if state.get("schema_version") != CURRENT_SCHEMA_VERSION: failures.append("state_schema_version_must_be_0.9.0")
    if state.get("version") != CURRENT_SCHEMA_VERSION: failures.append("state_version_must_be_0.9.0")
    if state.get("phase") != CURRENT_PHASE: failures.append("state_phase_invalid_for_v090")
    if state.get("current_gate") not in CURRENT_GATES: failures.append("state_current_gate_invalid")
    if state.get("provider_smoke_status") != state.get("current_gate"): failures.append("provider_smoke_status_must_equal_current_gate")
    if state.get("walk_authorized") != "pilot_only": failures.append("walk_must_remain_pilot_only")
    if state.get("production_walk_authorized") is not False: failures.append("production_animation_must_be_false")
    anchor = state.get("canonical_anchor") if isinstance(state.get("canonical_anchor"), Mapping) else {}
    if anchor.get("revision_id") != CANONICAL_R4_REVISION: failures.append("canonical_r4_revision_mismatch")
    if str(anchor.get("sha256", "")).casefold() != CANONICAL_R4_SHA256: failures.append("canonical_r4_sha256_mismatch")
    previous = state.get("previous_release") if isinstance(state.get("previous_release"), Mapping) else {}
    if previous.get("version") != "0.8.1": failures.append("previous_release_must_be_0.8.1")
    if state.get("allowed_next_actions") != ["external_review_idle_front"]: failures.append("allowed_next_actions_must_stop_at_idle_external_review")
    if not isinstance(state.get("forbidden_actions"), list) or not state.get("forbidden_actions"): failures.append("forbidden_actions_required")
    nested = state.get("state_consistency") if isinstance(state.get("state_consistency"), Mapping) else {}
    if nested.get("status") != state.get("current_gate"): failures.append("nested_status_must_equal_current_gate")
    if nested.get("contradictory_promotion") is not False: failures.append("contradictory_promotion_must_be_false")
    if nested.get("new_generation_started") is not False or nested.get("new_generation_jobs") != 0 or nested.get("sam2_runs") != 0 or nested.get("comfyui_generation_jobs") != 0: failures.append("v090_must_record_no_new_generation")
    if nested.get("walk_front_v081_external_visual") != "APPROVED_PILOT": failures.append("walk_external_decision_missing")
    if nested.get("idle_front_v1_external_visual") != "REQUIRED": failures.append("idle_external_review_must_be_required")
    if nested.get("production_routing") != "BLOCKED": failures.append("production_routing_must_be_blocked")
    combined = f"{checkpoint_text}\n{review_text}"
    required_texts = ("0.9.0", CURRENT_PHASE, "0.8.1", "0.7.3", "SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS", "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED", "REVIEW_ARCHIVE_VERIFIED", CURRENT_GATE, "FRONT_WALK_V081_PILOT_VISUAL_APPROVED", "external_review_idle_front", "production_routing=BLOCKED", "sam2_runs=0", "comfyui_generation_jobs=0", "not-claimed")
    failures.extend(f"active_documents_missing:{item}" for item in required_texts if item not in combined)
    if re.search(r"production[^\n.]{0,100}\b(?:enabled|active|unblocked|promoted)", combined, re.IGNORECASE): failures.append("active_documents_promote_production")
    if re.search(r"(?:run|start)[^\n.]{0,80}\b(?:attack|hit|death|other direction)", combined, re.IGNORECASE): failures.append("active_documents_expand_animation_scope")
    return {"status": CURRENT_GATE if not failures else "STATE_CONSISTENCY_FAILED", "schema_version": CURRENT_SCHEMA_VERSION, "failures": failures, "checked": {"phase": state.get("phase"), "current_gate": state.get("current_gate"), "walk_front_v081_external_visual": nested.get("walk_front_v081_external_visual"), "idle_front_v1_external_visual": nested.get("idle_front_v1_external_visual"), "production_routing": nested.get("production_routing"), "new_generation_started": nested.get("new_generation_started"), "new_generation_jobs": nested.get("new_generation_jobs")}}


def assert_state_consistency(state: Mapping[str, Any], checkpoint_text: str, review_text: str) -> dict[str, Any]:
    result = validate_state_consistency(state, checkpoint_text, review_text)
    if result["status"] != CURRENT_GATE:
        raise StateConsistencyError("; ".join(result["failures"]))
    return result
