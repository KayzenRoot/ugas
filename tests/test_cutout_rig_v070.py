"""Historical contract tests retained while the active cutout-rig is v0.7.1."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from PIL import Image

from ugas.cli import build_parser
from ugas.cutout_rig import (
    CAPABILITY_ID,
    MAX_MEMBER_SCALE,
    MIN_MEMBER_SCALE,
    PART_NAMES,
    PROVIDER_ID,
    SCHEMA_VERSION,
    build_part_prompts,
    compose_rig,
    image_metrics,
    mask_stats,
    mask_union_stats,
    seam_metrics,
    source_skeleton,
    transform_parameters,
    validate_rig_manifest,
)


ROOT = Path(__file__).resolve().parents[1]


def skeleton_input() -> dict[str, dict[str, float]]:
    return {
        "nose": {"x": 0.50, "y": 0.15, "confidence": 1.0},
        "shoulder_left": {"x": 0.60, "y": 0.30, "confidence": 1.0},
        "shoulder_right": {"x": 0.40, "y": 0.30, "confidence": 1.0},
        "elbow_left": {"x": 0.68, "y": 0.45, "confidence": 1.0},
        "elbow_right": {"x": 0.32, "y": 0.45, "confidence": 1.0},
        "wrist_left": {"x": 0.72, "y": 0.60, "confidence": 1.0},
        "wrist_right": {"x": 0.28, "y": 0.60, "confidence": 1.0},
        "hip_left": {"x": 0.56, "y": 0.58, "confidence": 1.0},
        "hip_right": {"x": 0.44, "y": 0.58, "confidence": 1.0},
        "knee_left": {"x": 0.60, "y": 0.78, "confidence": 1.0},
        "knee_right": {"x": 0.40, "y": 0.78, "confidence": 1.0},
        "ankle_left": {"x": 0.62, "y": 0.95, "confidence": 1.0},
        "ankle_right": {"x": 0.38, "y": 0.95, "confidence": 1.0},
    }


class CutoutRigContractTests(unittest.TestCase):
    def test_constants_bind_provider_contract(self):
        self.assertEqual("0.7.1", SCHEMA_VERSION)
        self.assertEqual("deterministic-cutout-rig-2d", PROVIDER_ID)
        self.assertEqual("pose_character_front_2d", CAPABILITY_ID)

    def test_source_skeleton_requires_all_core_joints_and_nose(self):
        result = source_skeleton(skeleton_input(), 100, 200)
        self.assertEqual("SOURCE_SKELETON_QUALIFIED", result["status"])
        self.assertEqual(12, result["required_count"])
        self.assertTrue(result["enough_joints"])

    def test_source_skeleton_rejects_missing_core_joint(self):
        source = skeleton_input()
        del source["ankle_left"]
        result = source_skeleton(source, 100, 200)
        self.assertEqual("CUTOUT_RIG_SOURCE_SKELETON_GAP", result["status"])
        self.assertFalse(result["enough_joints"])

    def test_source_skeleton_converts_normalized_coordinates(self):
        result = source_skeleton(skeleton_input(), 512, 512)
        self.assertEqual(256.0, result["joints"]["nose"]["x"])
        self.assertEqual(76.8, result["joints"]["nose"]["y"])

    def test_prompt_builder_emits_exact_eleven_parts(self):
        skeleton = source_skeleton(skeleton_input(), 512, 512)
        alpha = Image.new("L", (512, 512), 255)
        prompts = build_part_prompts(skeleton, alpha, (340.0, 120.0))
        self.assertEqual(set(PART_NAMES), set(prompts["parts"]))
        self.assertTrue(all(item["manual_click"] is False for item in prompts["parts"].values()))

    def test_prompt_builder_is_deterministic(self):
        skeleton = source_skeleton(skeleton_input(), 64, 64)
        alpha = Image.new("L", (64, 64), 255)
        first = build_part_prompts(skeleton, alpha, (40.0, 20.0))
        second = build_part_prompts(skeleton, alpha, (40.0, 20.0))
        self.assertEqual(first, second)

    def test_mask_stats_rejects_foreground_outside_source(self):
        alpha = Image.new("L", (16, 16), 0)
        alpha.putpixel((2, 2), 255)
        mask = Image.new("L", (16, 16), 0)
        mask.putpixel((8, 8), 255)
        result = mask_stats(mask, alpha, (0, 0, 16, 16))
        self.assertEqual(0.0, result["foreground_purity"])
        self.assertEqual(1, result["outside_source_alpha_pixels"])

    def test_mask_union_reports_overlap_and_coverage(self):
        alpha = Image.new("L", (8, 8), 255)
        left = Image.new("L", (8, 8), 0); left.putpixel((1, 1), 255)
        right = Image.new("L", (8, 8), 0); right.putpixel((1, 1), 255); right.putpixel((2, 2), 255)
        result = mask_union_stats([left, right], alpha)
        self.assertEqual(2, result["union_foreground_pixels"])
        self.assertEqual(1, result["overlap_pixels"])
        self.assertGreater(result["unresolved_overlap_fraction"], 0.0)

    def test_transform_parameters_uses_uniform_scale(self):
        source = source_skeleton(skeleton_input(), 100, 100)
        target = {"joints": {name: {"x": value["x"] * 2, "y": value["y"] * 2} for name, value in source["joints"].items()}, "weapon_tip": {"x": 90, "y": 20}}
        result = transform_parameters(source, target, "left_upper_arm")
        self.assertAlmostEqual(2.0, result["uniform_scale"], places=5)
        self.assertFalse(result["nonuniform_scale"])
        self.assertFalse(MIN_MEMBER_SCALE <= result["uniform_scale"] <= MAX_MEMBER_SCALE)

    def test_transform_parameters_accepts_bounded_scale(self):
        source = source_skeleton(skeleton_input(), 100, 100)
        target = {"joints": {name: {"x": value["x"] * 1.02, "y": value["y"] * 1.02} for name, value in source["joints"].items()}, "weapon_tip": {"x": 90, "y": 20}}
        result = transform_parameters(source, target, "left_upper_arm")
        self.assertTrue(result["scale_gate"])
        self.assertTrue(MIN_MEMBER_SCALE <= result["uniform_scale"] <= MAX_MEMBER_SCALE)

    def test_q0_does_not_use_source_residual_fallback(self):
        source_image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        for x in range(8, 24):
            for y in range(4, 28):
                source_image.putpixel((x, y), (20, 40, 60, 255))
        source = source_skeleton(skeleton_input(), 32, 32)
        source["weapon_tip"] = {"x": 24, "y": 8}
        source["neck"] = {"x": 16, "y": 7}
        target = {"joints": {name: {"x": value["x"], "y": value["y"]} for name, value in source["joints"].items()}, "neck": {"x": 16, "y": 7}, "weapon_tip": {"x": 24, "y": 8}}
        parts = {name: Image.new("RGBA", (32, 32), (0, 0, 0, 0)) for name in PART_NAMES}
        output, _ = compose_rig(parts, source, target, (32, 32))
        self.assertEqual(0.0, image_metrics(source_image, output)["alpha_iou"])

    def test_compose_rig_returns_all_part_transforms(self):
        source = source_skeleton(skeleton_input(), 100, 100)
        source["weapon_tip"] = {"x": 90, "y": 20}
        source["neck"] = {"x": 50, "y": 25}
        target = {"joints": {name: {"x": value["x"], "y": value["y"]} for name, value in source["joints"].items()}, "neck": {"x": 50, "y": 25}, "weapon_tip": {"x": 90, "y": 20}}
        parts = {name: Image.new("RGBA", (100, 100), (0, 0, 0, 0)) for name in PART_NAMES}
        _, transforms = compose_rig(parts, source, target, (100, 100))
        self.assertEqual(set(PART_NAMES), {item["part"] for item in transforms})

    def test_image_metrics_identity_is_zero_error(self):
        image = Image.new("RGBA", (8, 8), (1, 2, 3, 0))
        image.putpixel((2, 2), (10, 20, 30, 255))
        result = image_metrics(image, image.copy())
        self.assertEqual(1.0, result["alpha_iou"])
        self.assertEqual(0.0, result["rgb_mae"])
        self.assertEqual(0.0, result["bbox_drift_px"])

    def test_seam_metrics_accepts_connected_identity(self):
        image = Image.new("RGBA", (32, 32), (10, 20, 30, 255))
        source = source_skeleton(skeleton_input(), 32, 32)
        target = {"joints": {name: {"x": value["x"], "y": value["y"]} for name, value in source["joints"].items()}, "weapon_tip": {"x": 24, "y": 8}}
        result = seam_metrics(image, target)
        self.assertEqual("CUTOUT_RIG_SEAM_GAP", result["status"])
        self.assertFalse(result["safe_margin"])
        self.assertEqual(0, result["duplicate_body_components"])

    def test_manifest_validator_rejects_wrong_provider(self):
        result = validate_rig_manifest({"schema_version": SCHEMA_VERSION, "provider_id": "wrong", "parts": []})
        self.assertEqual("CUTOUT_RIG_MANIFEST_INVALID", result["status"])
        self.assertIn("provider_id", result["failures"])

    def test_cli_exposes_qualification_command(self):
        args = build_parser().parse_args(["cutout-rig", "qualify-sam2", "--json"])
        self.assertEqual("cutout-rig", args.command)
        self.assertEqual("qualify-sam2", args.cutout_action)

    def test_cli_requires_canonical_asset_for_build(self):
        args = build_parser().parse_args(["cutout-rig", "build", "--asset-id", "asset-x", "--json"])
        self.assertEqual("asset-x", args.asset_id)

    def test_cli_accepts_explicit_pose_list(self):
        args = build_parser().parse_args(["cutout-rig", "pose-pilot", "--poses", "q0,q1,q2", "--json"])
        self.assertEqual("q0,q1,q2", args.poses)

    def test_provider_manifest_is_current_and_deterministic(self):
        provider = json.loads((ROOT / "providers/manifests/deterministic-cutout-rig-2d.json").read_text(encoding="utf-8"))
        self.assertEqual(PROVIDER_ID, provider["id"])
        self.assertEqual("none", provider["generation_model"])
        self.assertEqual(0, provider["runtime_policy"]["comfyui_jobs"])

    def test_current_evidence_keeps_walk_outside_scope(self):
        execution = json.loads((ROOT / "docs/evidence/execution-evidence-v0.7.0.json").read_text(encoding="utf-8"))
        self.assertEqual(0, execution["comfyui_generation_jobs"])
        self.assertEqual("NOT_RUN", execution["walk"])
        self.assertFalse(execution["sam3_used"])

    def test_current_evidence_is_bound_to_r4(self):
        rig = json.loads((ROOT / "docs/evidence/r4-cutout-rig.json").read_text(encoding="utf-8"))
        self.assertEqual("revision-3a425d184b1a49be9f6d6c8d52d04b96", rig["source"]["revision_id"])
        self.assertEqual("7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798", rig["source"]["sha256"])

    def test_historical_state_is_separate(self):
        current = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        historical = json.loads((ROOT / "docs/evidence/current-state-v0.6.2.json").read_text(encoding="utf-8"))
        self.assertEqual("0.7.2", current["version"])
        self.assertEqual("0.6.2", historical["version"])
        self.assertNotEqual(current["current_gate"], historical["current_gate"])


if __name__ == "__main__":
    unittest.main()
