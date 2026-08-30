"""Fatal consistency checks for the active UGAS release state.

Historical review files are evidence of what happened in an earlier slice.  The
active checkpoint and review must describe the same current gate and must never
promote a result that the current-state record marks as blocked.
"""

from __future__ import annotations

import re
from typing import Any, Mapping


CURRENT_SCHEMA_VERSION = "0.5.2"
CANONICAL_R4_SHA256 = "7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798"
CANONICAL_R4_REVISION = "revision-3a425d184b1a49be9f6d6c8d52d04b96"
CURRENT_PHASE = "POSE_CONTROL_ESCALATION"
GAP_STATUS = "MULTI_REFERENCE_POSE_CONTROL_GAP"


class StateConsistencyError(ValueError):
    """Raised when a release state is contradictory or incomplete."""


def validate_state_consistency(
    state: Mapping[str, Any],
    checkpoint_text: str,
    review_text: str,
) -> dict[str, Any]:
    failures: list[str] = []
    required = {
        "schema_version", "version", "phase", "previous_release", "current_gate",
        "stop_reason", "canonical_anchor", "allowed_next_actions", "forbidden_actions",
    }
    failures.extend(f"missing:{key}" for key in sorted(required - set(state)))
    if state.get("schema_version") != CURRENT_SCHEMA_VERSION:
        failures.append("state_schema_version_must_be_0.5.2")
    if state.get("version") != CURRENT_SCHEMA_VERSION:
        failures.append("state_version_must_be_0.5.2")
    if state.get("phase") != CURRENT_PHASE:
        failures.append("state_phase_invalid")

    previous = state.get("previous_release") if isinstance(state.get("previous_release"), Mapping) else {}
    if previous.get("version") != "0.5.1":
        failures.append("previous_release_must_be_0.5.1")
    if previous.get("status") != GAP_STATUS:
        failures.append("previous_release_gap_status_missing")
    if previous.get("anchors_passed") is not False:
        failures.append("previous_release_anchors_must_be_false")
    if previous.get("walk_passed") is not False:
        failures.append("previous_release_walk_must_be_false")

    anchor = state.get("canonical_anchor") if isinstance(state.get("canonical_anchor"), Mapping) else {}
    if anchor.get("revision_id") != CANONICAL_R4_REVISION:
        failures.append("canonical_r4_revision_mismatch")
    if str(anchor.get("sha256", "")).casefold() != CANONICAL_R4_SHA256.casefold():
        failures.append("canonical_r4_sha256_mismatch")

    if not isinstance(state.get("allowed_next_actions"), list) or not state.get("allowed_next_actions"):
        failures.append("allowed_next_actions_required")
    if not isinstance(state.get("forbidden_actions"), list) or not state.get("forbidden_actions"):
        failures.append("forbidden_actions_required")

    combined = f"{checkpoint_text}\n{review_text}"
    if CURRENT_SCHEMA_VERSION not in combined:
        failures.append("active_documents_must_identify_0.5.2")
    if GAP_STATUS not in combined:
        failures.append("active_documents_must_record_v0.5.1_gap")
    gate = str(state.get("current_gate", ""))
    if gate and gate not in combined:
        failures.append("active_gate_missing_from_documents")
    contradictory = re.compile(
        r"(?:WALK(?:/FRONT/8|\s+FRONT\s*[/ ]\s*8|\s+V[23])?[^\n.]{0,80}\b(?:PASSED|PASSOU|PASSARAM|PASSADO|QUALIFIED|QUALIFICADO)|"
        r"(?:DIRECTIONAL\s+ANCHOR|ÂNCORAS?)[^\n.]{0,80}\b(?:PASSED|PASSOU|PASSARAM|PASSADO|QUALIFIED|QUALIFICADO))",
        re.IGNORECASE,
    )
    positive_lines = []
    for line in combined.splitlines():
        match = contradictory.search(line)
        prefix = line[:match.start()].casefold() if match else ""
        if match and "não" not in prefix and "nao" not in prefix:
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
            "previous_release_status": previous.get("status"),
            "contradictory_promotion_scan": True,
        },
    }


def assert_state_consistency(state: Mapping[str, Any], checkpoint_text: str, review_text: str) -> dict[str, Any]:
    result = validate_state_consistency(state, checkpoint_text, review_text)
    if result["status"] != "STATE_CONSISTENCY_PASSED":
        raise StateConsistencyError("; ".join(result["failures"]))
    return result
