"""Historical preservation checks for the rejected v0.11.1 slice."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class HistoricalV0111Tests(unittest.TestCase):
    def test_rejected_review_and_execution_evidence_remain_immutable(self) -> None:
        self.assertTrue((ROOT / "REVIEW-v0.11.1.md").is_file())
        self.assertTrue((ROOT / "docs/evidence/animation-runtime-v0111/execution-evidence-v0.11.1.json").is_file())
        value = json.loads((ROOT / "docs/evidence/animation-runtime-v0111/historical-replay-v0111.json").read_text(encoding="utf-8"))
        self.assertEqual("HISTORICAL_REPLAY_V0111_PASSED", value["status"])

    def test_active_profile_does_not_enable_rejected_numeric_lane(self) -> None:
        profile = json.loads((ROOT / "profiles/animation/attack-front-v2.json").read_text(encoding="utf-8"))
        self.assertNotIn("weapon_continuity", profile["qa_profile"]["feature_flags"])
        self.assertNotIn("weapon_continuity", profile["qa_profile"]["thresholds"])


if __name__ == "__main__":
    unittest.main()
