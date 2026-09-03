from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/validation"))

from ugas.animation import gif_timing_within_tolerance, load_spec
from ugas.animation_profiles import run_front_v1
from run_animation_runtime_v0131 import IMMUTABLE_BASE, _approved_assets_untouched


class RunFrontV0131Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load_spec(ROOT / "profiles/animation/run-front-v1.json", ROOT)
        cls.context = run_front_v1.load_context(cls.spec, ROOT)
        cls.prepared = run_front_v1.prepare(cls.spec, cls.context)

    def test_profile_is_eight_frame_source_only_loop(self) -> None:
        self.assertEqual(self.spec["frame_count"], 8)
        self.assertEqual(self.spec["fps"], 12)
        self.assertTrue(self.spec["loop"])
        self.assertEqual(self.spec["direction"], "front")
        self.assertTrue(self.spec["provenance"]["source_only_pixels"])
        self.assertEqual(self.spec["adapter_parameters"]["flight_frames"], [3, 7])

    def test_flight_frames_have_no_support_side(self) -> None:
        self.assertIsNone(run_front_v1.SUPPORT_SIDE[3])
        self.assertIsNone(run_front_v1.SUPPORT_SIDE[7])
        self.assertEqual(run_front_v1.SUPPORT_SIDE[0], "left")
        self.assertEqual(run_front_v1.SUPPORT_SIDE[4], "right")

    def test_injected_flight_support_is_rejected(self) -> None:
        fake = [
            {"frame": 3, "support_side": "right", "ground_reference_y": 462.0, "feet": {"left": {"role": "flight", "visible_clearance_px": 12.0, "ground_penetration_px": 0.0}, "right": {"role": "planted", "visible_clearance_px": 0.0, "ground_penetration_px": 0.0}}},
            {"frame": 7, "support_side": None, "ground_reference_y": 462.0, "feet": {"left": {"role": "flight", "visible_clearance_px": 12.0, "ground_penetration_px": 0.0}, "right": {"role": "flight", "visible_clearance_px": 12.0, "ground_penetration_px": 0.0}}},
        ]
        result = run_front_v1._flight_semantic_qa(self.spec, fake)
        self.assertEqual(result["status"], "RUN_FLIGHT_SEMANTIC_GAP")
        self.assertFalse(result["hard_gates"]["flight_no_support_role"])

    def test_gif_timing_tolerance_rejects_out_of_range_encode(self) -> None:
        decoded = {"frame_count": 8, "loop": 0, "durations_ms": [200] * 8, "total_cycle_ms": 1600, "effective_fps": 5.0}
        result = gif_timing_within_tolerance(self.spec, decoded)
        self.assertEqual(result["status"], "GIF_TIMING_GAP")

    def test_invalid_immutable_baseline_fails_closed(self) -> None:
        result = _approved_assets_untouched("0" * 40)
        self.assertEqual(result["status"], "APPROVED_ASSET_BASELINE_UNAVAILABLE")

    def test_protected_assets_match_immutable_base(self) -> None:
        result = _approved_assets_untouched(IMMUTABLE_BASE)
        self.assertEqual(result["status"], "APPROVED_ASSETS_UNTOUCHED")
        self.assertFalse(result["head_fallback_used"])

    def test_contract_binds_v0131_review_boundary(self) -> None:
        contract = json.loads((ROOT / "docs/evidence/animation-runtime-v0131/run-front-contract-v0131.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["dependencies"]["implementation_base_commit"], IMMUTABLE_BASE)
        self.assertEqual(contract["review_policy"]["external_visual"], "REQUIRED")
        self.assertEqual(len(contract["negative_controls"]), 12)

    def test_contact_windows_do_not_span_flight(self) -> None:
        for first, second, _side in run_front_v1.CONTACT_WINDOWS:
            self.assertNotIn(3, (first, second))
            self.assertNotIn(7, (first, second))

    def test_repeated_prepare_is_deterministic(self) -> None:
        repeated = run_front_v1.prepare(self.spec, self.context)
        self.assertEqual(
            [item["target_joint_sha256"] for item in self.prepared["targets"]],
            [item["target_joint_sha256"] for item in repeated["targets"]],
        )


if __name__ == "__main__":
    unittest.main()
