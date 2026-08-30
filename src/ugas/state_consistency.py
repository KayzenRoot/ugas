"""Fatal consistency checks for the active UGAS v0.5.5 release state.

Historical v0.5.2, v0.5.3 and v0.5.4 reports remain immutable evidence. This
module keeps the v0.5.4 pose result separate from the v0.5.5 review snapshot
gate; it never grants external approval.
"""

from __future__ import annotations

import re
from typing import Any, Mapping


CURRENT_SCHEMA_VERSION = "0.5.5"
CANONICAL_R4_SHA256 = "7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798"
CANONICAL_R4_REVISION = "revision-3a425d184b1a49be9f6d6c8d52d04b96"
CURRENT_PHASES = {"REVIEW_SNAPSHOT_INTEGRITY"}
CURRENT_GATES = {"REVIEW_SNAPSHOT_INTEGRITY_FIXED"}
POSE_LANE_STATUS = "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED"
PREVIOUS_REPORTED_STATUS = POSE_LANE_STATUS


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
        "canonical_anchor", "allowed_next_actions", "forbidden_actions",
        "generation_provider_change_authorized", "walk_authorized", "pose_lane_status",
        "review_snapshot_status", "state_consistency",
    }
    failures.extend(f"missing:{key}" for key in sorted(required - set(state)))
    if state.get("schema_version") != CURRENT_SCHEMA_VERSION:
        failures.append("state_schema_version_must_be_0.5.5")
    if state.get("version") != CURRENT_SCHEMA_VERSION:
        failures.append("state_version_must_be_0.5.5")
    if state.get("phase") not in CURRENT_PHASES:
        failures.append("state_phase_invalid")
    if state.get("current_gate") not in CURRENT_GATES:
        failures.append("state_current_gate_invalid")
    if state.get("generation_provider_change_authorized") is not False:
        failures.append("generation_provider_change_must_be_false")
    if state.get("walk_authorized") is not False:
        failures.append("walk_must_be_false")
    if state.get("pose_lane_status") != POSE_LANE_STATUS:
        failures.append("pose_lane_status_must_preserve_v0.5.4_decision")
    if state.get("review_snapshot_status") != "REVIEW_ARCHIVE_VERIFIED":
        failures.append("review_snapshot_status_must_be_verified")
    if state.get("stop_reason") is not None:
        failures.append("review_snapshot_fix_must_not_use_pose_stop_reason")

    previous = state.get("previous_release") if isinstance(state.get("previous_release"), Mapping) else {}
    if previous.get("version") != "0.5.4":
        failures.append("previous_release_must_be_0.5.4")
    if previous.get("reported_status") != PREVIOUS_REPORTED_STATUS:
        failures.append("previous_release_pose_status_missing")

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
    if not isinstance(started, bool):
        failures.append("new_generation_started_must_be_boolean")
    elif gate == "REVIEW_SNAPSHOT_INTEGRITY_FIXED" and started is not False:
        failures.append("review_snapshot_fix_must_record_no_new_generation")
    if nested.get("new_generation_jobs") != 0:
        failures.append("review_snapshot_fix_must_record_zero_new_generation_jobs")

    combined = f"{checkpoint_text}\n{review_text}"
    if CURRENT_SCHEMA_VERSION not in combined:
        failures.append("active_documents_must_identify_0.5.5")
    if "REVIEW_SNAPSHOT_INTEGRITY_FIXED" not in combined:
        failures.append("active_documents_must_record_review_snapshot_fix")
    if POSE_LANE_STATUS not in combined:
        failures.append("active_documents_must_preserve_pose_decision")
    if gate and gate not in combined:
        failures.append("active_gate_missing_from_documents")
    if "POSE_QA_LOCAL_USE_LICENSE_RESOLVED" not in combined:
        failures.append("active_documents_must_record_pose_license_resolution")
    if "v054-provider-qualification.json" not in combined:
        failures.append("provider_gap_evidence_missing_from_documents")
    if "A próxima ação autorizada é verificar o RefControl" in combined or re.search(
        r"pr[oó]xima\s+a[cç][aã]o[^\n]{0,100}verificar\s+o?\s*RefControl", combined, re.IGNORECASE
    ):
        failures.append("active_documents_have_stale_refcontrol_pending_action")

    contradictory = re.compile(
        r"(?:WALK(?:/FRONT/8|\s+FRONT\s*[/ ]\s*8|\s+V[23])?[^\n.]{0,80}\b(?:PASSED|PASSOU|PASSARAM|PASSADO|QUALIFIED|QUALIFICADO)|"
        r"(?:DIRECTIONAL\s+ANCHOR|ÂNCORAS?)[^\n.]{0,80}\b(?:PASSED|PASSOU|PASSARAM|PASSADO|QUALIFIED|QUALIFICADO))",
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
    if state.get("stop_reason") is None and "READY_FOR_REVIEW" in combined:
        failures.append("active_documents_cannot_claim_ready_for_review_before_gate")

    return {
        "status": "STATE_CONSISTENCY_PASSED" if not failures else "STATE_CONSISTENCY_FAILED",
        "schema_version": CURRENT_SCHEMA_VERSION,
        "failures": failures,
        "checked": {
            "current_gate": state.get("current_gate"),
            "stop_reason": state.get("stop_reason"),
            "nested_status": nested.get("status"),
            "contradictory_promotion_scan": True,
            "stale_refcontrol_action_scan": True,
            "license_resolution_scan": True,
            "new_generation_started": started,
        },
    }


def assert_state_consistency(state: Mapping[str, Any], checkpoint_text: str, review_text: str) -> dict[str, Any]:
    result = validate_state_consistency(state, checkpoint_text, review_text)
    if result["status"] != "STATE_CONSISTENCY_PASSED":
        raise StateConsistencyError("; ".join(result["failures"]))
    return result
