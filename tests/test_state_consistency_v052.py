"""Regression tests for historical-state separation under the v0.5.5 gate."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ugas.state_consistency_v080 import validate_state_consistency

ROOT = Path(__file__).resolve().parents[1]


class StateConsistencyV052Tests(unittest.TestCase):
    def test_current_state_and_documents_are_consistent(self):
        state = json.loads((ROOT / "docs/evidence/current-state-v0.8.0.json").read_text(encoding="utf-8"))
        checkpoint = (ROOT / "REVIEW-v0.8.0.md").read_text(encoding="utf-8") + "\nwalk_authorized=pilot_only"
        review = (ROOT / "REVIEW-v0.8.0.md").read_text(encoding="utf-8")
        result = validate_state_consistency(state, checkpoint, review)
        self.assertEqual("STATE_CONSISTENCY_PASSED", result["status"], result)

    def test_contradictory_walk_promotion_fixture_fails(self):
        state = json.loads((ROOT / "docs/evidence/current-state-v0.8.0.json").read_text(encoding="utf-8"))
        checkpoint = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8") + "\nWALK FRONT 8 PASSED."
        review = (ROOT / "REVIEW-v0.8.0.md").read_text(encoding="utf-8")
        result = validate_state_consistency(state, checkpoint, review)
        self.assertEqual("STATE_CONSISTENCY_FAILED", result["status"])
        self.assertIn("active_documents_promote_blocked_walk_or_anchor_result", result["failures"])

    def test_previous_release_flags_are_not_reclassified(self):
        state = json.loads((ROOT / "docs/evidence/current-state-v0.7.0.json").read_text(encoding="utf-8"))
        self.assertEqual("0.6.2", state["previous_release"]["version"])
        self.assertEqual("SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS", state["historical_smoke_status"])
        self.assertEqual("LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED", state["previous_release"]["pose_lane_status"])

    def test_modified_state_fails_canonical_hash(self):
        state = json.loads((ROOT / "docs/evidence/current-state-v0.8.0.json").read_text(encoding="utf-8"))
        state["canonical_anchor"]["sha256"] = "0" * 64
        result = validate_state_consistency(state, "0.7.0 DETERMINISTIC_CUTOUT_RIG_POSE_PROVIDER CUTOUT_RIG_VISUAL_OR_ESTIMATOR_GAP SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED REVIEW_ARCHIVE_VERIFIED provider_smoke_status sdxl-openpose-p-qualification.json review-visuals-v0.6.1.json", "0.7.0 DETERMINISTIC_CUTOUT_RIG_POSE_PROVIDER CUTOUT_RIG_VISUAL_OR_ESTIMATOR_GAP SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED REVIEW_ARCHIVE_VERIFIED provider_smoke_status sdxl-openpose-p-qualification.json review-visuals-v0.6.1.json")
        self.assertEqual("STATE_CONSISTENCY_FAILED", result["status"])
        self.assertIn("canonical_r4_sha256_mismatch", result["failures"])

    def test_nested_status_must_follow_active_stop(self):
        state = json.loads((ROOT / "docs/evidence/current-state-v0.8.0.json").read_text(encoding="utf-8"))
        state["state_consistency"]["status"] = "POSE_METRIC_CALIBRATION_REQUIRED"
        result = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.8.0.md").read_text(encoding="utf-8"))
        self.assertEqual("STATE_CONSISTENCY_FAILED", result["status"])
        self.assertIn("nested_status_must_equal_current_gate_or_stop_reason", result["failures"])

    def test_stale_refcontrol_pending_action_is_fatal(self):
        state = json.loads((ROOT / "docs/evidence/current-state-v0.8.0.json").read_text(encoding="utf-8"))
        checkpoint = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8") + "\nA próxima ação autorizada é verificar o RefControl."
        result = validate_state_consistency(state, checkpoint, (ROOT / "REVIEW-v0.8.0.md").read_text(encoding="utf-8"))
        self.assertEqual("STATE_CONSISTENCY_FAILED", result["status"])
        self.assertIn("active_documents_have_stale_refcontrol_pending_action", result["failures"])


if __name__ == "__main__":
    unittest.main()
