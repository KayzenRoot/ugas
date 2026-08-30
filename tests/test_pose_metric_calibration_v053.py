"""v0.5.3 detected-joint metric, calibration, and fail-closed regressions."""

from __future__ import annotations

import unittest

from ugas.pose_metric_calibration import (
    TARGET_POSE,
    detected_joint_pose_metrics,
    identity_only_silhouette_is_not_pose_pass,
    map_mediapipe_landmarks,
    normalized_headroom_gain,
    provider_gap_emission_authorized,
    synthetic_fixtures,
    validate_causal_gate_configuration,
)


class PoseMetricCalibrationV053Tests(unittest.TestCase):
    def test_impossible_additive_gate_is_rejected_exactly(self):
        result = validate_causal_gate_configuration(0.894403, 0.15)
        self.assertEqual("INVALID_CAUSAL_GATE_CONFIGURATION", result["status"])
        self.assertEqual(1.044403, result["required_score"])

    def test_headroom_gain_uses_remaining_metric_headroom(self):
        result = normalized_headroom_gain(0.894403, 0.992258)
        self.assertAlmostEqual(0.926684, result, places=6)

    def test_synthetic_target_and_negative_controls(self):
        fixtures = synthetic_fixtures()
        target = detected_joint_pose_metrics(TARGET_POSE, fixtures["TARGET"]["points"], target_orientation="left_profile", detected_orientation="left_profile")
        self.assertGreaterEqual(target["pose_score"], 0.90)
        for name, fixture in fixtures.items():
            if fixture["kind"] == "negative":
                result = detected_joint_pose_metrics(TARGET_POSE, fixture["points"], target_orientation="left_profile", detected_orientation=fixture["orientation"])
                self.assertLessEqual(result["pose_score"], target["pose_score"] - 0.20, name)
        self.assertFalse(detected_joint_pose_metrics(TARGET_POSE, fixtures["MIRRORED_WRONG_SIDE"]["points"], target_orientation="left_profile", detected_orientation="right_profile")["qualifies"])

    def test_sword_does_not_change_primary_joint_score(self):
        fixtures = synthetic_fixtures()
        clean = detected_joint_pose_metrics(TARGET_POSE, fixtures["TARGET"]["points"], target_orientation="left_profile", detected_orientation="left_profile")
        sword = detected_joint_pose_metrics(TARGET_POSE, fixtures["TARGET_PLUS_LONG_VERTICAL_SWORD"]["points"], target_orientation="left_profile", detected_orientation="left_profile")
        self.assertLessEqual(abs(clean["pose_score"] - sword["pose_score"]), 0.05)

    def test_limb_ablation_and_low_visibility_are_not_passes(self):
        detected = dict(TARGET_POSE)
        detected.pop("wrist_left")
        result = detected_joint_pose_metrics(TARGET_POSE, detected, target_orientation="left_profile", detected_orientation="left_profile")
        self.assertFalse(result["qualifies"])
        self.assertIn("required_core_joint_missing", result["failure_reasons"])
        low = detected_joint_pose_metrics(TARGET_POSE, TARGET_POSE, target_orientation="left_profile", detected_orientation="left_profile", visibility={"wrist_left": 0.1})
        self.assertEqual("UNMEASURABLE", low["measurement_status"])
        self.assertFalse(low["qualifies"])

    def test_wrong_detected_joints_fail_and_correct_joints_pass(self):
        correct = detected_joint_pose_metrics(TARGET_POSE, TARGET_POSE, target_orientation="left_profile", detected_orientation="left_profile")
        wrong = dict(TARGET_POSE)
        wrong.update({"elbow_left": (400, 400), "wrist_left": (420, 420), "knee_right": (80, 430), "ankle_right": (60, 500)})
        rejected = detected_joint_pose_metrics(TARGET_POSE, wrong, target_orientation="left_profile", detected_orientation="left_profile")
        self.assertTrue(correct["qualifies"])
        self.assertFalse(rejected["qualifies"])
        self.assertIn("nme_above_010", rejected["failure_reasons"])

    def test_mediapipe_mapping_preserves_left_right_and_confidence(self):
        landmarks = [{"x": 0.0, "y": 0.0, "visibility": 0.0} for _ in range(33)]
        landmarks[11] = {"x": 0.2, "y": 0.3, "visibility": 0.9}
        landmarks[12] = {"x": 0.8, "y": 0.3, "visibility": 0.9}
        landmarks[15] = {"x": 0.1, "y": 0.4, "visibility": 0.2}
        mapped = map_mediapipe_landmarks(landmarks)
        self.assertEqual(11, mapped["shoulder_left"]["source_index"])
        self.assertEqual(12, mapped["shoulder_right"]["source_index"])
        self.assertFalse(mapped["wrist_left"]["visible"])

    def test_silhouette_overlap_alone_is_not_pose_acceptance(self):
        self.assertTrue(identity_only_silhouette_is_not_pose_pass(silhouette_overlap=0.99, detected_joint_metrics={"qualifies": False}))

    def test_provider_gap_requires_both_measurement_gates(self):
        self.assertFalse(provider_gap_emission_authorized(calibration_status="METRIC_CALIBRATION_FAILED", estimator_status="POSE_QA_MODEL_LICENSE_GAP"))
        self.assertFalse(provider_gap_emission_authorized(calibration_status="METRIC_CALIBRATION_PASSED", estimator_status="POSE_QA_MODEL_LICENSE_GAP"))
        self.assertTrue(provider_gap_emission_authorized(calibration_status="METRIC_CALIBRATION_PASSED", estimator_status="POSE_QA_ESTIMATOR_QUALIFIED"))


if __name__ == "__main__":
    unittest.main()
