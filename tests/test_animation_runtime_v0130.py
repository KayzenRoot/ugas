from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ugas.animation import load_spec
from ugas.animation_profiles import run_front_v1


class RunFrontV0130Tests(unittest.TestCase):
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
        self.assertEqual(self.spec["provenance"]["comfyui_generation_jobs"], 0)

    def test_phase_and_tracks_are_complete(self) -> None:
        self.assertEqual(self.prepared["phases"], list(run_front_v1.PHASES))
        self.assertEqual(len(self.prepared["tracks"]), 12)
        self.assertEqual(len({item["target_joint_sha256"] for item in self.prepared["targets"]}), 8)
        self.assertEqual(self.prepared["track_hash"], run_front_v1.motion_tracks_sha256(self.spec))

    def test_repeated_prepare_is_deterministic(self) -> None:
        repeated = run_front_v1.prepare(self.spec, self.context)
        self.assertEqual(
            [item["target_joint_sha256"] for item in self.prepared["targets"]],
            [item["target_joint_sha256"] for item in repeated["targets"]],
        )
        self.assertEqual(self.prepared["track_hash"], repeated["track_hash"])

    def test_duplicate_leg_phase_rejects_cadence_gate(self) -> None:
        fixture = copy.deepcopy(self.prepared)
        fixture["samples"][6]["right_stride_x"] = fixture["samples"][4]["right_stride_x"]
        base = run_front_v1._base_target(self.context)
        fixture["targets"] = [
            run_front_v1._target_for_frame(self.context, index, fixture["samples"][index], base)
            for index in range(self.spec["frame_count"])
        ]
        records = [{"feet": {"status": "RUN_FOOT_GROUND_QA_PASSED"}} for _ in fixture["targets"]]
        outputs = [Image.new("RGBA", (512, 512), (0, 0, 0, 0)) for _ in fixture["targets"]]
        result = run_front_v1._temporal_qa(self.spec, self.context, fixture, records, outputs)
        self.assertFalse(result["hard_gates"]["cadence_phase_alternates"])

    def test_inverted_arm_fixture_rejects_opposition_gate(self) -> None:
        fixture = copy.deepcopy(self.prepared)
        for sample in fixture["samples"]:
            sample["right_arm_swing_deg"] = sample["left_arm_swing_deg"]
        base = run_front_v1._base_target(self.context)
        fixture["targets"] = [
            run_front_v1._target_for_frame(self.context, index, fixture["samples"][index], base)
            for index in range(self.spec["frame_count"])
        ]
        records = [{"feet": {"status": "RUN_FOOT_GROUND_QA_PASSED"}} for _ in fixture["targets"]]
        outputs = [Image.new("RGBA", (512, 512), (0, 0, 0, 0)) for _ in fixture["targets"]]
        result = run_front_v1._temporal_qa(self.spec, self.context, fixture, records, outputs)
        self.assertFalse(result["hard_gates"]["arm_leg_opposition"])

    def test_contract_binds_matrix_and_review_boundary(self) -> None:
        contract = json.loads((ROOT / "docs/evidence/animation-runtime-v0130/run-front-contract-v0130.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["dependencies"]["matrix_next_candidate"], "RUN_FRONT_V1")
        self.assertEqual(contract["dependencies"]["matrix_capability_count"], 16)
        self.assertEqual(contract["review_policy"]["external_visual"], "REQUIRED")
        self.assertEqual(contract["review_policy"]["production_routing"], "BLOCKED")
        self.assertEqual(len(contract["negative_controls"]), 8)


if __name__ == "__main__":
    unittest.main()
