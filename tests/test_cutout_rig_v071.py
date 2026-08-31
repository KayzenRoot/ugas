"""Regression tests for the v0.7.1 fidelity and false-green corrections."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from PIL import Image

from ugas.cutout_rig import (
    PART_NAMES,
    SCHEMA_VERSION,
    component_gate,
    compose_rig,
    image_metrics,
    map_guide_sides,
    seam_metrics,
    source_skeleton,
    transform_metric_gates,
    transform_parameters,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence"


def _target() -> dict:
    source = {
        "nose": {"x": 0.50, "y": 0.15},
        "shoulder_left": {"x": 0.60, "y": 0.30}, "shoulder_right": {"x": 0.40, "y": 0.30},
        "elbow_left": {"x": 0.68, "y": 0.45}, "elbow_right": {"x": 0.32, "y": 0.45},
        "wrist_left": {"x": 0.72, "y": 0.60}, "wrist_right": {"x": 0.28, "y": 0.60},
        "hip_left": {"x": 0.56, "y": 0.58}, "hip_right": {"x": 0.44, "y": 0.58},
        "knee_left": {"x": 0.60, "y": 0.78}, "knee_right": {"x": 0.40, "y": 0.78},
        "ankle_left": {"x": 0.62, "y": 0.95}, "ankle_right": {"x": 0.38, "y": 0.95},
    }
    skeleton = source_skeleton(source, 64, 64)
    return {"joints": {name: {"x": value["x"], "y": value["y"]} for name, value in skeleton["joints"].items()}, "neck": {"x": 32, "y": 13}, "weapon_tip": {"x": 18, "y": 60}}


class CutoutRigV071Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target_evidence = json.loads((EVIDENCE / "r4-cutout-target-adapter-v071.json").read_text(encoding="utf-8"))
        cls.refined = json.loads((EVIDENCE / "r4-cutout-refined-masks-v071-manifest.json").read_text(encoding="utf-8"))
        cls.retention = json.loads((EVIDENCE / "cutout-rig-pixel-retention-v071.json").read_text(encoding="utf-8"))

    def test_schema_is_active_v071(self):
        self.assertEqual("0.7.1", SCHEMA_VERSION)

    def test_q1_q2_hips_are_distinct(self):
        for pose in ("q1", "q2"):
            joints = self.target_evidence[pose]["joints"]
            self.assertNotEqual(joints["hip_left"], joints["hip_right"])

    def test_target_hip_width_preserves_source_ratio(self):
        for pose in ("q1", "q2"):
            invariant = self.target_evidence[pose]["hip_invariant"]
            self.assertTrue(0.92 <= invariant["ratio"] <= 1.08)

    def test_asymmetric_fixture_preserves_image_to_anatomical_mapping(self):
        raw = {
            "shoulder_left": {"x": 18, "y": 12}, "shoulder_right": {"x": 46, "y": 13},
            "elbow_left": {"x": 16, "y": 28}, "elbow_right": {"x": 49, "y": 27},
            "wrist_left": {"x": 13, "y": 44}, "wrist_right": {"x": 52, "y": 42},
            "hip_left": {"x": 11, "y": 20}, "hip_right": {"x": 53, "y": 24},
            "knee_left": {"x": 17, "y": 45}, "knee_right": {"x": 47, "y": 41},
            "ankle_left": {"x": 14, "y": 60}, "ankle_right": {"x": 51, "y": 58},
            "nose": {"x": 32, "y": 5},
        }
        mapped, side_mapping = map_guide_sides(raw)
        self.assertEqual("guide_right", side_mapping["anatomical_left"])
        self.assertEqual("guide_left", side_mapping["anatomical_right"])
        self.assertEqual(53.0, mapped["hip_left"]["x"])
        self.assertEqual(11.0, mapped["hip_right"]["x"])

    def test_weapon_uses_wrist_and_protected_corridor(self):
        for pose in ("q1", "q2"):
            weapon = self.target_evidence[pose]["weapon_attachment"]
            self.assertEqual("wrist_right", weapon["anatomical_wrist"])
            self.assertFalse(weapon["tip_crosses_protected_torso"])
            self.assertLessEqual(abs(weapon["selected_swing_degrees"]), 12.0)

    def test_raw_and_refined_masks_have_distinct_hash_bound_paths(self):
        for name in PART_NAMES:
            raw = self.refined["parts"][name]["raw_mask_path"]
            refined = self.refined["parts"][name]["mask_path"]
            self.assertNotEqual(raw, refined)
            self.assertTrue((ROOT / raw).is_file())
            self.assertTrue((ROOT / refined).is_file())

    def test_excessive_component_fixture_fails(self):
        self.assertFalse(component_gate([1000] + [20] * 93, 3)["passed"])
        self.assertFalse(component_gate([1000] + [20] * 105, 2)["passed"])

    def test_refined_component_gate_is_below_torso_and_sword_limits(self):
        gates = self.refined["component_gates"]
        self.assertTrue(gates["passed"])
        self.assertLessEqual(gates["measured"]["torso_pelvis"]["meaningful_component_count"], 3)
        self.assertLessEqual(gates["measured"]["sword"]["meaningful_component_count"], 2)

    def test_full_foreground_ownership_and_unassigned_threshold(self):
        global_stats = self.refined["global"]
        self.assertGreaterEqual(global_stats["semantic_alpha_union_coverage"], 0.995)
        self.assertGreaterEqual(global_stats["strict_alpha_ownership_coverage"], 0.99)
        self.assertLessEqual(global_stats["unassigned_semantic_fraction"], 0.005)

    def test_q0_has_no_source_residual_fallback(self):
        q0 = json.loads((EVIDENCE / "cutout-q0-reconstruction-qa-v071.json").read_text(encoding="utf-8"))
        self.assertFalse(q0["source_residual_fallback_used"])
        self.assertTrue(q0["hard_gates"]["no_source_residual_fallback"])

    def test_incomplete_masks_make_q0_fail(self):
        source = Image.new("RGBA", (32, 32), (20, 40, 60, 255))
        parts = {name: Image.new("RGBA", (32, 32), (0, 0, 0, 0)) for name in PART_NAMES}
        skeleton = source_skeleton({"nose": {"x": 0.5, "y": 0.15}, **{name: {"x": 0.5, "y": 0.5} for name in ("shoulder_left", "shoulder_right", "elbow_left", "elbow_right", "wrist_left", "wrist_right", "hip_left", "hip_right", "knee_left", "knee_right", "ankle_left", "ankle_right")}}, 32, 32)
        skeleton["neck"] = {"x": 16, "y": 7}; skeleton["weapon_tip"] = {"x": 16, "y": 28}
        output, _ = compose_rig(parts, skeleton, _target(), (32, 32))
        self.assertLess(image_metrics(source, output)["alpha_iou"], 0.995)

    def test_no_untransformed_joint_patches(self):
        rig = json.loads((EVIDENCE / "r4-cutout-rig-v071.json").read_text(encoding="utf-8"))
        self.assertEqual(0, rig["renderer"]["joint_patch_copy_count"])
        self.assertEqual(0, rig["renderer"]["untransformed_joint_patch_pixels"])

    def test_internal_forward_transform_metrics_are_present(self):
        qa = json.loads((EVIDENCE / "cutout-rig-internal-qa-v071.json").read_text(encoding="utf-8"))
        for pose in qa["poses"].values():
            self.assertTrue(pose["transforms"])
            self.assertTrue(all("forward_affine_matrix" in item for item in pose["transforms"]))
            self.assertEqual(0, pose["measured"]["joint_pivot_error_px_max"])

    def test_internal_transform_is_sensitive_to_incorrect_matrix(self):
        source = source_skeleton({"nose": {"x": 0.5, "y": 0.15}, **{name: {"x": 0.5, "y": 0.5} for name in ("shoulder_left", "shoulder_right", "elbow_left", "elbow_right", "wrist_left", "wrist_right", "hip_left", "hip_right", "knee_left", "knee_right", "ankle_left", "ankle_right")}}, 100, 100)
        target = _target()
        result = transform_parameters(source, target, "left_upper_arm")
        self.assertTrue(transform_metric_gates(result)["pivot_max"])
        bad = dict(result); bad["forward_pivot_error_px"] = 7.0
        self.assertFalse(transform_metric_gates(bad)["pivot_max"])

    def test_safe_margin_uses_real_bbox_and_rejects_bottom_three(self):
        image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        for x in range(8, 24):
            for y in range(4, 29):
                image.putpixel((x, y), (10, 20, 30, 255))
        result = seam_metrics(image, _target())
        self.assertEqual(3, result["margins_px"]["bottom"])
        self.assertFalse(result["safe_margin"])

    def test_clipping_border_contact_is_measured(self):
        image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        for x in range(0, 20):
            for y in range(4, 28):
                image.putpixel((x, y), (10, 20, 30, 255))
        result = seam_metrics(image, _target())
        self.assertTrue(result["clipping"])
        self.assertFalse(result["hard_gates"]["clipping_false"])

    def test_background_hole_and_overlap_are_computed(self):
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        for x in range(10, 54):
            for y in range(5, 60):
                image.putpixel((x, y), (10, 20, 30, 255))
        image.putpixel((32, 32), (0, 0, 0, 0))
        layer_a = image.copy(); layer_b = image.copy()
        result = seam_metrics(image, _target(), layers=[layer_a, layer_b])
        self.assertIsInstance(result["overlap_pixels"], int)
        self.assertGreater(result["overlap_pixels"], 0)
        self.assertIsInstance(result["background_hole_pixels"], int)

    def test_retention_reports_occlusion_per_part(self):
        q2 = self.retention["poses"]["q2-passing-left"]
        self.assertIn("right_thigh", q2["parts"])
        self.assertIn("occluded_source_fraction", q2["parts"]["right_thigh"])
        self.assertFalse(q2["gates"]["required_limb_min"])

    def test_overlay_has_target_and_detected_metadata(self):
        pose = json.loads((EVIDENCE / "cutout-rig-pose-qa-v071.json").read_text(encoding="utf-8"))
        self.assertEqual(2, len(pose["poses"]))
        self.assertTrue(all(item.get("target") and item.get("media_pipe") for item in pose["poses"]))
        self.assertTrue((EVIDENCE / "cutout-q1-q2-target-detected-overlays-v071.png").is_file())

    def test_zero_comfyui_jobs_and_walk_not_run(self):
        execution = json.loads((EVIDENCE / "execution-evidence-v0.7.1.json").read_text(encoding="utf-8"))
        self.assertEqual(0, execution["comfyui_generation_jobs"])
        self.assertEqual("NOT_RUN", execution["walk"])
        self.assertEqual(0, execution["sam2_calls"]["per_frame_segmentation"])


if __name__ == "__main__":
    unittest.main()
