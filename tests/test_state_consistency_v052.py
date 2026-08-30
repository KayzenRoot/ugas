"""Regression tests for the v0.5.2-to-v0.5.3 state correction."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ugas.state_consistency import validate_state_consistency

ROOT = Path(__file__).resolve().parents[1]


class StateConsistencyV052Tests(unittest.TestCase):
    def test_current_state_and_documents_are_consistent(self):
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        checkpoint = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8")
        review = (ROOT / "REVIEW-v0.5.3.md").read_text(encoding="utf-8")
        result = validate_state_consistency(state, checkpoint, review)
        self.assertEqual("STATE_CONSISTENCY_PASSED", result["status"], result)

    def test_contradictory_walk_promotion_fixture_fails(self):
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        checkpoint = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8") + "\nWALK FRONT 8 PASSED."
        review = (ROOT / "REVIEW-v0.5.3.md").read_text(encoding="utf-8")
        result = validate_state_consistency(state, checkpoint, review)
        self.assertEqual("STATE_CONSISTENCY_FAILED", result["status"])
        self.assertIn("active_documents_promote_blocked_walk_or_anchor_result", result["failures"])

    def test_previous_release_flags_are_not_reclassified(self):
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        self.assertEqual("0.5.2", state["previous_release"]["version"])
        self.assertEqual("LOCAL_POSE_CONTROL_PROVIDER_GAP", state["previous_release"]["reported_status"])
        self.assertEqual("POSE_METRIC_GATE_DESIGN_GAP", state["previous_release"]["audit_reclassification"])

    def test_modified_state_fails_canonical_hash(self):
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        state["canonical_anchor"]["sha256"] = "0" * 64
        result = validate_state_consistency(state, "0.5.3 POSE_METRIC_GATE_DESIGN_GAP POSE_QA_MODEL_LICENSE_GAP", "0.5.3 POSE_METRIC_GATE_DESIGN_GAP POSE_QA_MODEL_LICENSE_GAP")
        self.assertEqual("STATE_CONSISTENCY_FAILED", result["status"])
        self.assertIn("canonical_r4_sha256_mismatch", result["failures"])

    def test_nested_status_must_follow_active_stop(self):
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        state["state_consistency"]["status"] = "POSE_METRIC_CALIBRATION_REQUIRED"
        result = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.5.3.md").read_text(encoding="utf-8"))
        self.assertEqual("STATE_CONSISTENCY_FAILED", result["status"])
        self.assertIn("nested_status_must_equal_current_gate_or_stop_reason", result["failures"])

    def test_stale_refcontrol_pending_action_is_fatal(self):
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        checkpoint = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8") + "\nA próxima ação autorizada é verificar o RefControl."
        result = validate_state_consistency(state, checkpoint, (ROOT / "REVIEW-v0.5.3.md").read_text(encoding="utf-8"))
        self.assertEqual("STATE_CONSISTENCY_FAILED", result["status"])
        self.assertIn("active_documents_have_stale_refcontrol_pending_action", result["failures"])


if __name__ == "__main__":
    unittest.main()
