"""Frozen v0.8.1 state validator retained for historical regression checks."""

from __future__ import annotations

import re
from typing import Any, Mapping

CURRENT_SCHEMA_VERSION = "0.8.1"
CANONICAL_R4_SHA256 = "7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798"
CANONICAL_R4_REVISION = "revision-3a425d184b1a49be9f6d6c8d52d04b96"
CURRENT_PHASE = "DETERMINISTIC_FRONT_WALK_8FRAME_PILOT"
CURRENT_GATES = {"CUTOUT_RIG_FRONT_WALK_FRAME_GAP", "CUTOUT_RIG_FRONT_WALK_TEMPORAL_GAP", "CUTOUT_RIG_FRONT_WALK_LOOP_GAP", "CUTOUT_RIG_FRONT_WALK_PACKAGING_GAP", "CUTOUT_RIG_FRONT_WALK_8FRAME_TECHNICALLY_QUALIFIED"}
HISTORICAL_SMOKE_STATUS = "SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS"
HISTORICAL_POSE_STATUS = "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED"
HISTORICAL_REVIEW_STATUS = "REVIEW_ARCHIVE_VERIFIED"


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str, review_text: str) -> dict[str, Any]:
    failures: list[str] = []
    required = {"schema_version", "version", "phase", "previous_release", "current_gate", "stop_reason", "canonical_anchor", "allowed_next_actions", "forbidden_actions", "historical_smoke_status", "generation_provider_change_authorized", "walk_authorized", "production_walk_authorized", "provider_smoke_status", "historical_pose_lane_status", "pose_lane_status", "previous_review_snapshot_status", "state_consistency"}
    failures.extend(f"missing:{key}" for key in sorted(required - set(state)))
    if state.get("schema_version") != CURRENT_SCHEMA_VERSION: failures.append("state_schema_version_must_be_0.8.1")
    if state.get("version") != CURRENT_SCHEMA_VERSION: failures.append("state_version_must_be_0.8.1")
    if state.get("phase") != CURRENT_PHASE: failures.append("state_phase_invalid_for_v081")
    if state.get("current_gate") not in CURRENT_GATES: failures.append("state_current_gate_invalid")
    if state.get("provider_smoke_status") != state.get("current_gate"): failures.append("provider_smoke_status_must_equal_current_gate")
    if state.get("walk_authorized") != "pilot_only": failures.append("walk_must_be_pilot_only")
    if state.get("production_walk_authorized") is not False: failures.append("production_walk_must_be_false")
    if state.get("historical_smoke_status") != HISTORICAL_SMOKE_STATUS: failures.append("historical_smoke_status_must_preserve_v0.6.2")
    if state.get("historical_pose_lane_status") != HISTORICAL_POSE_STATUS: failures.append("historical_pose_lane_status_must_preserve_v0.5.4")
    if state.get("previous_review_snapshot_status") != HISTORICAL_REVIEW_STATUS: failures.append("previous_review_snapshot_status_must_preserve_v0.5.5")
    previous = state.get("previous_release") if isinstance(state.get("previous_release"), Mapping) else {}
    if previous.get("version") != "0.8.0": failures.append("previous_release_must_be_0.8.0")
    if previous.get("review_snapshot_status") != HISTORICAL_REVIEW_STATUS: failures.append("previous_release_review_snapshot_missing")
    if previous.get("pose_lane_status") != "CUTOUT_RIG_FRONT_WALK_8FRAME_TECHNICALLY_QUALIFIED": failures.append("previous_release_pose_status_must_preserve_v080")
    anchor = state.get("canonical_anchor") if isinstance(state.get("canonical_anchor"), Mapping) else {}
    if anchor.get("revision_id") != CANONICAL_R4_REVISION: failures.append("canonical_r4_revision_mismatch")
    if str(anchor.get("sha256", "")).casefold() != CANONICAL_R4_SHA256: failures.append("canonical_r4_sha256_mismatch")
    if state.get("allowed_next_actions") != ["external_review_front_walk_cycle"]: failures.append("allowed_next_actions_must_stop_at_external_review")
    if not isinstance(state.get("forbidden_actions"), list) or not state.get("forbidden_actions"): failures.append("forbidden_actions_required")
    nested = state.get("state_consistency") if isinstance(state.get("state_consistency"), Mapping) else {}
    if nested.get("status") != state.get("current_gate"): failures.append("nested_status_must_equal_current_gate")
    if nested.get("contradictory_walk_or_anchor_promotion") is not False: failures.append("contradictory_walk_or_anchor_promotion_must_be_false")
    if nested.get("new_generation_started") is not False or nested.get("new_generation_jobs") != 0 or nested.get("sam2_runs") != 0 or nested.get("comfyui_generation_jobs") != 0: failures.append("v081_must_record_no_new_generation")
    combined = f"{checkpoint_text}\n{review_text}"
    required_texts = ("0.8.1", CURRENT_PHASE, "0.8.0", "0.7.3", HISTORICAL_SMOKE_STATUS, HISTORICAL_POSE_STATUS, HISTORICAL_REVIEW_STATUS, str(state.get("current_gate")), "external_review_front_walk_cycle", "production_routing=BLOCKED", "sam2_runs=0", "comfyui_generation_jobs=0")
    failures.extend(f"active_documents_missing:{item}" for item in required_texts if item not in combined)
    if "not-claimed" not in combined.casefold() and "não reivindicada" not in combined.casefold(): failures.append("active_documents_must_not_claim_external_approval")
    if re.search(r"verificar\s+o\s+refcontrol", combined, re.IGNORECASE): failures.append("active_documents_have_stale_refcontrol_pending_action")
    return {"status": "STATE_CONSISTENCY_PASSED" if not failures else "STATE_CONSISTENCY_FAILED", "schema_version": CURRENT_SCHEMA_VERSION, "failures": failures, "checked": {"phase": state.get("phase"), "current_gate": state.get("current_gate"), "walk_authorized": state.get("walk_authorized"), "production_walk_authorized": state.get("production_walk_authorized"), "new_generation_started": nested.get("new_generation_started"), "new_generation_jobs": nested.get("new_generation_jobs")}}
