"""Unit tests for the v0.11.2 fail-closed QA-integrity contract."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ugas.animation import load_spec
from ugas.animation_profiles import attack_front_v2
from ugas.motion_curves import MotionCurveError, sample_track, validate_motion_tracks


class QAIntegrityV0112Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = load_spec(ROOT / "profiles/animation/attack-front-v2.json", ROOT)
        self.baseline = load_spec(ROOT / "profiles/animation/attack-front-v2-v0.11.0.json", ROOT)
        self.context = attack_front_v2.load_context(self.spec, ROOT)
        self.prepared = attack_front_v2.prepare(self.spec, self.context)

    def test_motion_tracks_and_key_bindings_equal_v0110(self) -> None:
        self.assertEqual(self.baseline["motion_tracks"], self.spec["motion_tracks"])
        self.assertEqual(self.baseline["key_pose_bindings"], self.spec["key_pose_bindings"])

    def test_declared_thresholds_and_relational_weapon_contract_pass(self) -> None:
        thresholds = self.spec["qa_profile"]["thresholds"]
        self.assertEqual({"body_root_path_min_px", "torso_rotation_range_min_deg", "left_wrist_counter_path_min_px", "head_counter_motion_max_deg", "root_horizontal_excursion_min_px", "root_horizontal_excursion_max_px", "root_vertical_excursion_min_px", "root_vertical_excursion_max_px"}, set(attack_front_v2.DECLARED_BODY_THRESHOLDS))
        self.assertNotIn("weapon_continuity", thresholds)
        self.assertEqual("ATTACK_V2_WEAPON_ARC_QA_PASSED", self.prepared["weapon_relational_pre_render"]["status"])
        self.assertTrue(all(self.prepared["weapon_relational_pre_render"]["hard_gates"].values()))

    def test_isolated_body_motion_gates_fail(self) -> None:
        def body(mutate):
            samples = copy.deepcopy(self.prepared["samples"])
            mutate(samples)
            base = attack_front_v2._base_target(self.context)
            targets = [attack_front_v2._target_for_frame(self.context, index, samples[index], base) for index in range(len(samples))]
            return attack_front_v2._body_mechanics(self.spec, targets, samples, self.context)
        root = body(lambda values: [(v.__setitem__("root_shift_x", 0.0), v.__setitem__("root_shift_y", 0.0)) for v in values])
        torso = body(lambda values: [v.__setitem__("torso_rotation_deg", 0.0) for v in values])
        left = body(lambda values: [(v.__setitem__("left_upper_arm_counter_deg", 0.0), v.__setitem__("left_forearm_counter_deg", 0.0)) for v in values])
        self.assertEqual("ATTACK_V2_BODY_MECHANICS_GAP", root["status"])
        self.assertEqual("ATTACK_V2_BODY_MECHANICS_GAP", torso["status"])
        self.assertEqual("ATTACK_V2_BODY_MECHANICS_GAP", left["status"])

    def test_attack_v1_missing_baseline_fails_closed(self) -> None:
        temp_root = ROOT / "tmp"
        temp_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as directory:
            context = dict(self.context)
            context["root"] = Path(directory)
            result = attack_front_v2._body_mechanics(self.spec, self.prepared["targets"], self.prepared["samples"], context)
            self.assertFalse(result["hard_gates"]["right_shoulder_to_wrist_path_gt_attack_v1"])

    def test_weapon_nc07_and_nc08_fail(self) -> None:
        presentation = self.spec["presentation_transform"]
        tips = [attack_front_v2._trajectory_point(target, "weapon_tip", presentation) for target in self.prepared["targets"]]
        angles = [attack_front_v2._direction(attack_front_v2._xy(target["joints"]["wrist_right"]), attack_front_v2._xy(target["joints"]["weapon_tip"])) for target in self.prepared["targets"]]
        bad_accel = copy.deepcopy(angles)
        bad_accel[4], bad_accel[5], bad_accel[6] = bad_accel[3] + 20, bad_accel[3] + 15, bad_accel[3] + 25
        reversal = copy.deepcopy(angles)
        reversal[7] = reversal[6] - 1
        self.assertEqual("ATTACK_V2_WEAPON_ARC_GAP", attack_front_v2._weapon_relational_metrics(self.spec, tips, bad_accel)["status"])
        self.assertEqual("ATTACK_V2_WEAPON_ARC_GAP", attack_front_v2._weapon_relational_metrics(self.spec, tips, reversal)["status"])

    def test_motion_curve_integrity_controls_reject(self) -> None:
        track = {"track_id": "x", "value_type": "scalar", "interpolation": "linear", "keyframes": [{"frame": 0, "value": 0.0}, {"frame": 5, "value": 1.0}]}
        with self.assertRaises(MotionCurveError): validate_motion_tracks({"frame_count": 5, "motion_tracks": [track, copy.deepcopy(track)]})
        with self.assertRaises(MotionCurveError): validate_motion_tracks({"frame_count": 5, "motion_tracks": [{**track, "interpolation": "unknown"}]})
        with self.assertRaises(MotionCurveError): sample_track(track, -1.0)


if __name__ == "__main__":
    unittest.main()
