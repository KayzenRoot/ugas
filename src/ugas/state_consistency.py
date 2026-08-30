"""Fatal consistency checks for the active UGAS v0.7.0 cutout-rig provider.

The v0.6.2 calibration result, earlier pose decision and review-snapshot
result are immutable historical inputs. This validator permits only the
deterministic R4 cutout-rig slice; it never grants external approval or
animation authorization.
"""

from __future__ import annotations

import re
from typing import Any, Mapping


CURRENT_SCHEMA_VERSION = "0.7.0"
CANONICAL_R4_SHA256 = "7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798"
CANONICAL_R4_REVISION = "revision-3a425d184b1a49be9f6d6c8d52d04b96"
CURRENT_PHASE = "DETERMINISTIC_CUTOUT_RIG_POSE_PROVIDER"
CURRENT_GATES = {
    "CUTOUT_RIG_SAM2_QUALIFICATION_REQUIRED",
    "SAM2_RUNTIME_GAP",
    "CUTOUT_RIG_SEGMENTATION_RUNTIME_GAP",
    "CUTOUT_RIG_SOURCE_SKELETON_GAP",
    "CUTOUT_RIG_SEGMENTATION_GAP",
    "CUTOUT_RIG_RECONSTRUCTION_GAP",
    "CUTOUT_RIG_RENDERER_GAP",
    "CUTOUT_RIG_SEAM_GAP",
    "CUTOUT_RIG_VISUAL_OR_ESTIMATOR_GAP",
    "CUTOUT_RIG_POSE_PROVIDER_QUALIFIED",
}
HISTORICAL_SMOKE_STATUS = "SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS"
POSE_LANE_STATUS = "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED"
HISTORICAL_REVIEW_STATUS = "REVIEW_ARCHIVE_VERIFIED"


class StateConsistencyError(ValueError):
    """Raised when a release state is contradictory or incomplete."""


def _expected_nested_status(state: Mapping[str, Any]) -> str | None:
    stop_reason = state.get("stop_reason")
    if stop_reason is not None:
        return str(stop_reason)
    gate = state.get("current_gate")
    return str(gate) if gate else None


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str, review_text: str) -> dict[str, Any]:
    failures: list[str] = []
    required = {
        "schema_version", "version", "phase", "previous_release", "current_gate", "stop_reason",
        "canonical_anchor", "allowed_next_actions", "forbidden_actions", "historical_smoke_status",
        "generation_provider_change_authorized", "walk_authorized", "provider_smoke_status",
        "historical_pose_lane_status", "pose_lane_status",
        "previous_review_snapshot_status", "state_consistency",
    }
    failures.extend(f"missing:{key}" for key in sorted(required - set(state)))
    if state.get("schema_version") != CURRENT_SCHEMA_VERSION:
        failures.append("state_schema_version_must_be_0.7.0")
    if state.get("version") != CURRENT_SCHEMA_VERSION:
        failures.append("state_version_must_be_0.7.0")
    if state.get("phase") != CURRENT_PHASE:
        failures.append("state_phase_invalid_for_v070")
    if state.get("current_gate") not in CURRENT_GATES:
        failures.append("state_current_gate_invalid")
    if state.get("provider_smoke_status") != state.get("current_gate"):
        failures.append("provider_smoke_status_must_equal_current_gate")
    if state.get("walk_authorized") is not False:
        failures.append("walk_must_be_false")
    if state.get("historical_pose_lane_status") != POSE_LANE_STATUS:
        failures.append("historical_pose_lane_status_must_preserve_v0.5.4_decision")
    if state.get("previous_review_snapshot_status") != HISTORICAL_REVIEW_STATUS:
        failures.append("previous_review_snapshot_status_must_preserve_v0.5.5")

    previous = state.get("previous_release") if isinstance(state.get("previous_release"), Mapping) else {}
    if state.get("historical_smoke_status") != HISTORICAL_SMOKE_STATUS:
        failures.append("historical_smoke_status_must_preserve_v0.6.2")
    if previous.get("version") != "0.6.2":
        failures.append("previous_release_must_be_0.6.2")
    if previous.get("historical_smoke_status") != HISTORICAL_SMOKE_STATUS:
        failures.append("previous_release_historical_smoke_status_missing")
    if previous.get("review_snapshot_status") != HISTORICAL_REVIEW_STATUS:
        failures.append("previous_release_review_snapshot_missing")
    if previous.get("pose_lane_status") != POSE_LANE_STATUS:
        failures.append("previous_release_pose_status_missing")
    if state.get("pose_lane_status") not in CURRENT_GATES:
        failures.append("pose_lane_status_must_identify_current_cutout_rig_gate")

    anchor = state.get("canonical_anchor") if isinstance(state.get("canonical_anchor"), Mapping) else {}
    if anchor.get("revision_id") != CANONICAL_R4_REVISION:
        failures.append("canonical_r4_revision_mismatch")
    if str(anchor.get("sha256", "")).casefold() != CANONICAL_R4_SHA256.casefold():
        failures.append("canonical_r4_sha256_mismatch")

    if not isinstance(state.get("allowed_next_actions"), list) or not state.get("allowed_next_actions"):
        failures.append("allowed_next_actions_required")
    if not isinstance(state.get("forbidden_actions"), list) or not state.get("forbidden_actions"):
        failures.append("forbidden_actions_required")

    gate = str(state.get("current_gate", ""))
    nested = state.get("state_consistency") if isinstance(state.get("state_consistency"), Mapping) else {}
    expected_nested = _expected_nested_status(state)
    if nested.get("status") != expected_nested:
        failures.append("nested_status_must_equal_current_gate_or_stop_reason")
    if nested.get("contradictory_walk_or_anchor_promotion") is not False:
        failures.append("nested_promotion_flag_must_be_false")
    started = nested.get("new_generation_started")
    jobs = nested.get("new_generation_jobs")
    if not isinstance(started, bool):
        failures.append("new_generation_started_must_be_boolean")
    if not isinstance(jobs, int) or jobs < 0:
        failures.append("new_generation_jobs_must_be_nonnegative_integer")
    if gate == "CUTOUT_RIG_SAM2_QUALIFICATION_REQUIRED":
        if started is not False or jobs != 0:
            failures.append("audit_gate_must_record_no_generation")
        if state.get("generation_provider_change_authorized") is not False:
            failures.append("audit_gate_provider_change_must_be_false")
    elif state.get("stop_reason") is not None and state.get("generation_provider_change_authorized") is not False:
        failures.append("stopped_state_provider_change_must_be_false")

    combined = f"{checkpoint_text}\n{review_text}"
    for required_text, failure in (
        (CURRENT_SCHEMA_VERSION, "active_documents_must_identify_0.7.0"),
        (CURRENT_PHASE, "active_documents_must_identify_cutout_rig_provider"),
        ("0.6.2", "active_documents_must_preserve_v0.6.2_history"),
        (HISTORICAL_SMOKE_STATUS, "active_documents_must_preserve_v0.6.2_smoke_status"),
        ("0.6.1", "active_documents_must_preserve_v0.6.1_history"),
        (POSE_LANE_STATUS, "active_documents_must_preserve_pose_decision"),
        (HISTORICAL_REVIEW_STATUS, "active_documents_must_preserve_review_snapshot"),
        (gate, "active_gate_missing_from_documents"),
    ):
        if required_text not in combined:
            failures.append(failure)
    combined_lower = combined.casefold()
    if "walk_authorized=false" not in combined_lower and "walk permanece não autorizado" not in combined_lower:
        failures.append("active_documents_must_keep_walk_blocked")
    if "sdxl-openpose-p-qualification.json" not in combined:
        failures.append("historical_v062_evidence_missing_from_documents")
    if "review-visuals-v0.6.1.json" not in combined:
        failures.append("historical_v061_review_manifest_missing_from_documents")
    if "provider_smoke_status" not in combined:
        failures.append("active_documents_must_distinguish_provider_smoke_status")
    if re.search(r"verificar\s+o\s+RefControl", combined, re.IGNORECASE):
        failures.append("active_documents_have_stale_refcontrol_pending_action")

    contradictory = re.compile(
        r"(?:WALK(?:/FRONT/8|\s+FRONT\s*[/ ]\s*8|\s+V[23])?[^\n.]{0,100}\b(?:PASSED|PASSOU|PASSARAM|PASSADO|QUALIFIED|QUALIFICADO)|"
        r"(?:DIRECTIONAL\s+ANCHOR|ÂNCORAS?)[^\n.]{0,100}\b(?:PASSED|PASSOU|PASSARAM|PASSADO|QUALIFIED|QUALIFICADO))",
        re.IGNORECASE,
    )
    positive_lines = []
    for line in combined.splitlines():
        match = contradictory.search(line)
        prefix = line[:match.start()].casefold() if match else ""
        if match and "não" not in prefix and "nao" not in prefix and "não foram" not in prefix:
            positive_lines.append(line)
    if positive_lines:
        failures.append("active_documents_promote_blocked_walk_or_anchor_result")

    return {
        "status": "STATE_CONSISTENCY_PASSED" if not failures else "STATE_CONSISTENCY_FAILED",
        "schema_version": CURRENT_SCHEMA_VERSION,
        "failures": failures,
        "checked": {
            "phase": state.get("phase"),
            "current_gate": state.get("current_gate"),
            "stop_reason": state.get("stop_reason"),
            "historical_pose_status": state.get("pose_lane_status"),
            "historical_review_status": state.get("previous_review_snapshot_status"),
            "contradictory_walk_or_anchor_scan": True,
            "new_generation_started": started,
            "new_generation_jobs": jobs,
        },
    }


def assert_state_consistency(state: Mapping[str, Any], checkpoint_text: str, review_text: str) -> dict[str, Any]:
    result = validate_state_consistency(state, checkpoint_text, review_text)
    if result["status"] != "STATE_CONSISTENCY_PASSED":
        raise StateConsistencyError("; ".join(result["failures"]))
    return result
