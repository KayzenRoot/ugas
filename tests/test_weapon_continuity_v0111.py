"""Regression tests for the v0.11.1 attack-front-v2 weapon contract."""

from __future__ import annotations

import copy
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ugas.animation import compile_spec, load_spec
from ugas.animation_profiles import attack_front_v2


class WeaponContinuityV0111Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = load_spec(ROOT / "profiles/animation/attack-front-v2.json", ROOT)
        self.context = attack_front_v2.load_context(self.spec, ROOT)
        self.prepared = attack_front_v2.prepare(self.spec, self.context)
        presentation = self.spec["presentation_transform"]
        self.tips = [attack_front_v2._trajectory_point(target, "weapon_tip", presentation) for target in self.prepared["targets"]]
        self.angles = [attack_front_v2._direction(attack_front_v2._xy(target["joints"]["wrist_right"]), attack_front_v2._xy(target["joints"]["weapon_tip"])) for target in self.prepared["targets"]]
        self.points = {key: [attack_front_v2._trajectory_point(target, joint, presentation) for target in self.prepared["targets"]] for key, joint in {"wrist": "wrist_right", "elbow": "elbow_right", "pelvis": "pelvis", "head_nose": "nose"}.items()}
        self.torso = [attack_front_v2._scalar(sample, "torso_rotation_deg") for sample in self.prepared["samples"]]

    def _result(self, mutate):
        tips, angles, points, torso = copy.deepcopy((self.tips, self.angles, self.points, self.torso))
        mutate(tips, angles, points, torso)
        return attack_front_v2._weapon_continuity_metrics(self.spec, tips, angles, points, torso, require_recovery_metrics=True)

    def test_pre_render_contract_passes_with_measured_margin(self) -> None:
        result = self.prepared["weapon_continuity_pre_render"]
        self.assertEqual("ATTACK_V2_WEAPON_CONTINUITY_QA_PASSED", result["status"])
        self.assertGreaterEqual(result["metrics"]["post_hit_follow_path_px"], 12.0)
        self.assertGreaterEqual(result["metrics"]["follow_ratio"], 0.15)
        self.assertLessEqual(result["metrics"]["follow_ratio"], 0.60)
        self.assertGreaterEqual(result["metrics"]["velocity_retention_ratio"], 0.25)
        self.assertLessEqual(result["metrics"]["velocity_retention_ratio"], 0.85)
        self.assertLessEqual(result["metrics"]["max_abs_weapon_acceleration"], 10.0)
        self.assertEqual([8, 9], result["metrics"]["reversal_transition"])
        self.assertLessEqual(result["metrics"]["V11_vs_V0_sword_angle_delta"], 5.0)
        self.assertLessEqual(result["metrics"]["V11_vs_V0_tip_distance"], 16.0)

    def test_required_negative_controls_are_rejected(self) -> None:
        hit_velocity = abs(self.angles[6] - self.angles[5])
        cases = {
            "zero_follow": lambda tips, angles, points, torso: (tips.__setitem__(7, tips[6]), tips.__setitem__(8, tips[6])),
            "one_px_follow": lambda tips, angles, points, torso: (tips.__setitem__(7, (tips[6][0] + 0.5, tips[6][1])), tips.__setitem__(8, (tips[6][0] + 1.0, tips[6][1]))),
            "ratio_010": lambda tips, angles, points, torso: (tips.__setitem__(7, (tips[6][0] + 5.0, tips[6][1])), tips.__setitem__(8, (tips[6][0] + 10.0, tips[6][1]))),
            "retention_010": lambda tips, angles, points, torso: angles.__setitem__(7, angles[6] + hit_velocity * 0.10),
            "retention_over_090": lambda tips, angles, points, torso: angles.__setitem__(7, angles[6] + hit_velocity * 0.95),
            "acceleration_12": lambda tips, angles, points, torso: (angles.__setitem__(7, angles[6] + (angles[6] - angles[5])), angles.__setitem__(8, angles[7] + (angles[6] - angles[5]) + 12.0)),
            "reversal_early_67": lambda tips, angles, points, torso: angles.__setitem__(7, angles[6] - 1.0),
            "reversal_early_78": lambda tips, angles, points, torso: (angles.__setitem__(7, angles[6] + 4.0), angles.__setitem__(8, angles[6] + 3.0)),
            "reversal_acceleration_over_10": lambda tips, angles, points, torso: (angles.__setitem__(7, angles[6] + 4.0), angles.__setitem__(8, angles[7] + 4.0), angles.__setitem__(9, angles[8] - 15.0)),
            "recovery_angle_20": lambda tips, angles, points, torso: angles.__setitem__(11, angles[0] + 20.0),
            "recovery_tip_40": lambda tips, angles, points, torso: tips.__setitem__(11, (tips[0][0] + 40.0, tips[0][1])),
            "recovery_wrist_elbow_far": lambda tips, angles, points, torso: (points["wrist"].__setitem__(11, (points["wrist"][0][0] + 40.0, points["wrist"][0][1])), points["elbow"].__setitem__(11, (points["elbow"][0][0] + 40.0, points["elbow"][0][1]))),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                self.assertEqual("ATTACK_V2_WEAPON_CONTINUITY_GAP", self._result(mutate)["status"])

    def test_near_ready_fixture_passes_all_recovery_bounds(self) -> None:
        result = attack_front_v2.weapon_continuity_pre_render_qa(self.spec, self.prepared["targets"], self.prepared["samples"])
        self.assertEqual("ATTACK_V2_WEAPON_CONTINUITY_QA_PASSED", result["status"])
        self.assertTrue(all(result["hard_gates"].values()))

    def test_pre_render_failure_creates_no_render_output(self) -> None:
        bad = copy.deepcopy(self.spec)
        for track_id, values in {"sword_rotation_deg": {7: 38.0, 8: 38.0}, "right_forearm_rotation_deg": {7: 25.0, 8: 25.0}, "right_wrist/grip_rotation_deg": {7: 5.0, 8: 5.0}}.items():
            track = next(item for item in bad["motion_tracks"] if item["track_id"] == track_id)
            for keyframe in track["keyframes"]:
                if keyframe["frame"] in values:
                    keyframe["value"] = values[keyframe["frame"]]
        with tempfile.TemporaryDirectory(prefix="ugas-v0111-test-", dir=ROOT / "tmp") as directory:
            temp_root = Path(directory)
            profile = temp_root / "bad.json"
            output = temp_root / "output"
            profile.write_text(__import__("json").dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                compile_spec(profile, output, ROOT)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
