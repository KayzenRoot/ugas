"""Regression tests for the v0.8.1 front-walk QA integrity correction."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ugas.cutout_temporal_v081 import (  # noqa: E402
    PHASES,
    build_initial_targets_v081,
    foot_contact_qa_v081,
    loop_qa_v081,
    smooth_walk_targets,
)
from ugas.cutout_rig import canonical_json  # noqa: E402
from ugas.review import validate_review_visual_manifest  # noqa: E402


EVIDENCE = ROOT / "docs" / "evidence"


def read(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


class FrontWalkV081Tests(unittest.TestCase):
    def test_exact_phase_contract_and_same_cycle_boundary(self) -> None:
        self.assertEqual(PHASES, ("F0-contact-left", "F1-down-left", "F2-passing-left", "F3-up-left", "F4-contact-right", "F5-down-right", "F6-passing-right", "F7-up-right"))
        config = read("front-walk-cycle-v1-config-v081.json")
        self.assertEqual(config["cycle"]["frame_count"], 8)
        self.assertEqual(config["cycle"]["direction"], "front")
        self.assertFalse(config["intermediate_generator"]["image_inputs_used_for_smoothing"])
        self.assertFalse(config["presentation_transform"]["frame_specific_transforms"])
        self.assertIn("same-cycle correction only", read("front-walk-provider-qualification-v081.json")["forbidden"])

    def test_config_hash_is_bound_and_correction_is_frozen(self) -> None:
        config = read("front-walk-cycle-v1-config-v081.json")
        config_hash = hashlib.sha256(canonical_json(config).encode("utf-8")).hexdigest()
        targets = read("front-walk-targets-v081.json")
        self.assertEqual(targets["config_sha256"], config_hash)
        self.assertEqual(config["status"], "FROZEN_BEFORE_RENDER")
        self.assertEqual(config["phase_corrections"]["2"]["swing_foot_clearance_bias_px"], 5.0)
        self.assertEqual(config["phase_corrections"]["2"]["support_ground_calibration_offset_px"], 3.0)
        self.assertEqual(config["smoothing"]["relative_bone_ratio_bounds"], {"min": 0.94, "max": 1.04})

    def test_key_bindings_are_exact_and_all_targets_distinct(self) -> None:
        targets = read("front-walk-targets-v081.json")
        self.assertTrue(all(item["canonical_exact"] for item in targets["key_binding"].values()))
        canonical = targets["canonical_targets"]
        self.assertEqual(len(canonical), 8)
        self.assertEqual(len({item["target_joint_sha256"] for item in canonical.values()}), 8)
        self.assertEqual(len({item["presentation_target_joint_sha256"] for item in targets["presentation_targets"].values()}), 8)
        for frame in ("F0-contact-left", "F2-passing-left", "F4-contact-right", "F6-passing-right"):
            self.assertEqual(canonical[frame]["generator"]["kind"], "deterministic_skeleton_only")

    def test_smoothing_is_deterministic_and_image_free(self) -> None:
        config = read("front-walk-cycle-v1-config-v081.json")
        report = read("front-walk-targets-v081.json")
        key_frames = {0: report["canonical_targets"][PHASES[0]], 2: report["canonical_targets"][PHASES[2]], 4: report["canonical_targets"][PHASES[4]], 6: report["canonical_targets"][PHASES[6]]}
        initial_a = build_initial_targets_v081(key_frames, config)
        initial_b = build_initial_targets_v081(key_frames, config)
        smoothed_a, audit_a = smooth_walk_targets(initial_a, config)
        smoothed_b, audit_b = smooth_walk_targets(initial_b, config)
        self.assertEqual(canonical_json(smoothed_a), canonical_json(smoothed_b))
        self.assertEqual(audit_a, audit_b)
        self.assertFalse(audit_a["image_inputs_used"])

    def test_strict_angular_gate_has_no_generic_30_degree_exception(self) -> None:
        temporal = read("front-walk-temporal-qa-v081.json")
        self.assertEqual(temporal["status"], "CUTOUT_RIG_FRONT_WALK_TEMPORAL_PASSED")
        self.assertLessEqual(temporal["max_angular_acceleration_degrees_per_frame2"], 25.0)
        self.assertFalse(temporal["angular_acceleration_fixture_calibration"]["allowed"])
        self.assertTrue(temporal["angular_acceleration_fixture_calibration"]["generic_exception_removed"])

    def test_actual_alpha_metrics_are_not_skeleton_bbox_metrics(self) -> None:
        temporal = read("front-walk-temporal-qa-v081.json")
        self.assertLessEqual(temporal["head_bbox_area_cv"], 0.04)
        self.assertLessEqual(temporal["torso_bbox_area_cv"], 0.04)
        self.assertEqual(len(temporal["head_bbox_areas_actual_alpha"]), 8)
        self.assertEqual(len(temporal["torso_bbox_areas_actual_alpha"]), 8)
        self.assertIn("actual_alpha", temporal.get("head_bbox_measurement_method", "actual_alpha"))

    def test_foot_gate_uses_visible_sole_and_projected_ground(self) -> None:
        report = read("front-walk-foot-contact-qa-v081.json")
        self.assertEqual(report["status"], "CUTOUT_RIG_FRONT_WALK_FOOT_CONTACT_PASSED")
        f2 = next(item for item in report["swing_clearance"] if item["frame"] == 2)
        self.assertGreaterEqual(f2["visible_clearance_px"], 4.0)
        self.assertEqual(f2["ground_penetration_px"], 0.0)
        records = read("front-walk-foot-ground-record-v081.json")
        self.assertIn("support_ground_calibration_offset_px", records["frames"]["F2-passing-left"]["feet"]["right"])

    def test_foot_negative_fixture_rejects_boot_penetration_even_with_high_ankle(self) -> None:
        targets = read("front-walk-targets-v081.json")["canonical_targets"]
        records = read("front-walk-foot-ground-record-v081.json")["frames"]
        bad = copy.deepcopy(records)
        bad["F2-passing-left"]["feet"]["left"]["actual_sole_y"] = 500.0
        bad["F2-passing-left"]["feet"]["left"]["ground_penetration_px"] = 50.0
        bad["F2-passing-left"]["feet"]["left"]["visible_clearance_px"] = -50.0
        result = foot_contact_qa_v081(targets, bad, read("front-walk-cycle-v1-config-v081.json"))
        self.assertNotEqual(result["status"], "CUTOUT_RIG_FRONT_WALK_FOOT_CONTACT_PASSED")
        self.assertFalse(result["hard_gates"]["all_swing_visible_clearance"])

    def test_loop_qa_is_bound_to_frozen_z_order_boundary(self) -> None:
        targets = read("front-walk-targets-v081.json")["canonical_targets"]
        plan = read("front-walk-z-order-v081.json")
        self.assertEqual(loop_qa_v081(targets, plan)["status"], "CUTOUT_RIG_FRONT_WALK_LOOP_PASSED")
        mutated = copy.deepcopy(plan)
        order = mutated["phase_plans"]["F7-up-right"]["z_order"]
        order[0], order[1] = order[1], order[0]
        self.assertNotEqual(loop_qa_v081(targets, mutated)["status"], "CUTOUT_RIG_FRONT_WALK_LOOP_PASSED")

    def test_every_frame_and_all_auxiliary_gates_pass(self) -> None:
        report = read("front-walk-per-frame-qa-v081.json")
        self.assertEqual(report["status"], "CUTOUT_RIG_FRONT_WALK_FRAMES_PASSED")
        self.assertEqual(len(report["frames"]), 8)
        for frame in report["frames"]:
            self.assertEqual(frame["status"], "CUTOUT_RIG_FRONT_WALK_FRAME_PASSED")
            self.assertTrue(all(frame["hard_gates"].values()))
            self.assertNotIn("step_px", frame["root_pelvis"])
            self.assertEqual(frame["hard_gate_proof_sources"]["generated_pixel_fraction"], 0.0)
            self.assertEqual(frame["hard_gate_proof_sources"]["recolor_count"], 0)
        for name in ("front-walk-structural-coverage-v081.json", "front-walk-layer-integrity-v081.json", "front-walk-occlusion-v081.json", "front-walk-retention-v081.json"):
            self.assertTrue(read(name)["status"].endswith("PASSED"))

    def test_package_is_rgba_and_pilot_only(self) -> None:
        image = Image.open(EVIDENCE / "walk-front-v081" / "walk-front-spritesheet-v081.png")
        self.assertEqual((image.mode, image.size), ("RGBA", (2048, 1024)))
        metadata = read("walk-front-v081/walk-front-metadata-v081.json")
        self.assertEqual([item["index"] for item in metadata["frames"]], list(range(8)))
        package = read("walk-front-v081/walk-front-package-manifest-v081.json")
        self.assertEqual(package["registry_state"], "pilot/technical-qualified")
        self.assertFalse(package["production_approved"])
        self.assertEqual(package["production_routing"], "BLOCKED")

    def test_no_generation_and_external_review_boundary(self) -> None:
        execution = read("execution-evidence-v0.8.1.json")
        qualification = read("front-walk-provider-qualification-v081.json")
        self.assertEqual(execution["sam2_runs"], 0)
        self.assertEqual(execution["comfyui_generation_jobs"], 0)
        self.assertEqual(execution["new_generation_jobs"], 0)
        self.assertEqual(qualification["external_visual_review"], "REQUIRED")
        self.assertEqual(qualification["external_approval"], "not-claimed")
        self.assertFalse(qualification["production_walk_authorized"])

    def test_review_visual_manifest_is_complete_and_hash_bound(self) -> None:
        result = validate_review_visual_manifest(read("review-visuals-v0.8.1.json"), ROOT)
        self.assertEqual(result["status"], "REVIEW_VISUAL_MANIFEST_PASSED", result)

    def test_root_motion_is_real_and_bounded(self) -> None:
        motion = read("front-walk-root-motion-v081.json")
        self.assertTrue(all(value <= 8.0 for value in motion["steps_px"]))
        self.assertLessEqual(motion["root_vertical_amplitude_px"], 12.0)


if __name__ == "__main__":
    unittest.main()
