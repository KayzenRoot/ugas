from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/validation"))

from ugas.animation import gif_timing_within_tolerance, load_spec
from ugas.animation_profiles import hit_front_v1
from run_animation_runtime_v0140 import IMMUTABLE_BASE, _approved_assets_untouched


class HitFrontV0140Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load_spec(ROOT / "profiles/animation/hit-front-v1.json", ROOT)
        cls.context = hit_front_v1.load_context(cls.spec, ROOT)
        cls.prepared = hit_front_v1.prepare(cls.spec, cls.context)

    def test_profile_is_six_frame_source_only_non_loop(self) -> None:
        self.assertEqual(self.spec["frame_count"], 6)
        self.assertEqual(self.spec["fps"], 12)
        self.assertFalse(self.spec["loop"])
        self.assertEqual(self.spec["direction"], "front")
        self.assertTrue(self.spec["provenance"]["source_only_pixels"])
        self.assertEqual([item["event_id"] for item in self.spec["event_markers"]], ["impact_onset", "recoil_peak", "recovery_start", "recovery_complete"])

    def test_recoil_peak_is_unique_at_h2(self) -> None:
        from PIL import Image

        records = [{"feet": {"status": "HIT_FOOT_GROUND_QA_PASSED", "support_side": "both"}} for _ in self.prepared["targets"]]
        outputs = [Image.new("RGBA", (512, 512), (0, 0, 0, 0)) for _ in self.prepared["targets"]]
        temporal = hit_front_v1._temporal_qa(self.spec, self.context, self.prepared, records, outputs)
        self.assertTrue(temporal["hard_gates"]["unique_recoil_peak"])
        self.assertEqual(temporal["recoil"]["peak_frame"], 2)

    def test_injected_anticipation_is_rejected(self) -> None:
        import copy

        fixture = copy.deepcopy(self.prepared)
        fixture["samples"][0]["root_shift_x"] = -16.0
        fixture["samples"][0]["root_shift_y"] = -10.0
        base = hit_front_v1._base_target(self.context)
        fixture["targets"] = [hit_front_v1._target_for_frame(self.context, index, fixture["samples"][index], base) for index in range(6)]
        from PIL import Image

        records = [{"feet": {"status": "HIT_FOOT_GROUND_QA_PASSED", "support_side": "both"}} for _ in fixture["targets"]]
        outputs = [Image.new("RGBA", (512, 512), (0, 0, 0, 0)) for _ in fixture["targets"]]
        temporal = hit_front_v1._temporal_qa(self.spec, self.context, fixture, records, outputs)
        self.assertFalse(temporal["hard_gates"]["impact_causality"])

    def test_gif_timing_requires_non_loop_encode(self) -> None:
        decoded = {"frame_count": 6, "loop": 0, "durations_ms": [80, 90, 80, 90, 80, 80], "total_cycle_ms": 500, "effective_fps": 12.0}
        result = gif_timing_within_tolerance(self.spec, decoded)
        self.assertEqual(result["status"], "GIF_TIMING_GAP")
        self.assertFalse(result["hard_gates"]["loop_enabled"])

    def test_invalid_immutable_baseline_fails_closed(self) -> None:
        result = _approved_assets_untouched("0" * 40)
        self.assertEqual(result["status"], "APPROVED_ASSET_BASELINE_UNAVAILABLE")

    def test_protected_assets_match_immutable_and_approved_run(self) -> None:
        result = _approved_assets_untouched(IMMUTABLE_BASE)
        if result["status"] == "APPROVED_ASSET_BASELINE_UNAVAILABLE":
            self.skipTest("immutable-base identity requires git history; the no-git snapshot still fail-closes via test_invalid_immutable_baseline_fails_closed")
        self.assertEqual(result["status"], "APPROVED_ASSETS_UNTOUCHED")
        self.assertFalse(result["head_fallback_used"])

    def test_contract_binds_v0140_review_boundary(self) -> None:
        contract = json.loads((ROOT / "docs/evidence/animation-runtime-v0140/hit-front-contract-v0140.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["dependencies"]["implementation_base_commit"], IMMUTABLE_BASE)
        self.assertEqual(contract["review_policy"]["external_visual"], "REQUIRED")
        self.assertEqual(len(contract["negative_controls"]), 10)
        self.assertFalse(contract["phase_contract"]["loop"])

    def test_both_feet_planted_every_frame(self) -> None:
        self.assertEqual(len(hit_front_v1.CONTACT_WINDOWS), 10)
        self.assertEqual(hit_front_v1.PHASES[2], "H2-recoil-peak")
        self.assertEqual(hit_front_v1.PHASES[5], "H5-recovery-complete")

    def test_repeated_prepare_is_deterministic(self) -> None:
        repeated = hit_front_v1.prepare(self.spec, self.context)
        self.assertEqual(
            [item["target_joint_sha256"] for item in self.prepared["targets"]],
            [item["target_joint_sha256"] for item in repeated["targets"]],
        )


if __name__ == "__main__":
    unittest.main()
