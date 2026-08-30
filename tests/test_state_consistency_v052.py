"""v0.5.2 state and escalation guard tests."""

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
        review = (ROOT / "REVIEW-v0.5.2.md").read_text(encoding="utf-8")
        result = validate_state_consistency(state, checkpoint, review)
        self.assertEqual("STATE_CONSISTENCY_PASSED", result["status"], result)

    def test_contradictory_walk_promotion_fixture_fails(self):
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        checkpoint = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8") + "\nWALK FRONT 8 PASSED."
        review = (ROOT / "REVIEW-v0.5.2.md").read_text(encoding="utf-8")
        result = validate_state_consistency(state, checkpoint, review)
        self.assertEqual("STATE_CONSISTENCY_FAILED", result["status"])
        self.assertIn("active_documents_promote_blocked_walk_or_anchor_result", result["failures"])

    def test_previous_release_flags_are_not_reclassified(self):
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        self.assertFalse(state["previous_release"]["anchors_passed"])
        self.assertFalse(state["previous_release"]["walk_passed"])
        self.assertEqual("MULTI_REFERENCE_POSE_CONTROL_GAP", state["previous_release"]["status"])

    def test_modified_state_fails_canonical_hash(self):
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        state["canonical_anchor"]["sha256"] = "0" * 64
        result = validate_state_consistency(state, "0.5.2 MULTI_REFERENCE_POSE_CONTROL_GAP NATIVE_REFERENCE_ORDER_BENCHMARK", "0.5.2 MULTI_REFERENCE_POSE_CONTROL_GAP")
        self.assertEqual("STATE_CONSISTENCY_FAILED", result["status"])
        self.assertIn("canonical_r4_sha256_mismatch", result["failures"])


if __name__ == "__main__":
    unittest.main()
