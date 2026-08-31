"""Regression tests for the v0.7.2 occlusion-aware cutout qualification."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ugas.cutout_occlusion import (  # noqa: E402
    PART_NAMES,
    PHASE_PLANS,
    build_occlusion_plan,
    compose_named_layers,
    pairwise_overlap_qa,
    retention_occlusion_qa,
    topological_seam_qa,
)


def target() -> dict:
    names = {"nose", "neck", "shoulder_left", "shoulder_right", "elbow_left", "elbow_right", "wrist_left", "wrist_right", "hip_left", "hip_right", "knee_left", "knee_right", "ankle_left", "ankle_right", "pelvis", "shoulder_center", "weapon_tip"}
    return {"joints": {name: {"x": 5.0, "y": 5.0} for name in names}}


def layer(box: tuple[int, int, int, int] | None = None, size: tuple[int, int] = (20, 20)) -> Image.Image:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    if box is not None:
        draw = ImageDraw.Draw(image); draw.rectangle(box, fill=(255, 255, 255, 255))
    return image


def layers_with(**overrides: tuple[int, int, int, int]) -> dict[str, Image.Image]:
    result = {name: layer() for name in PART_NAMES}
    for name, box in overrides.items(): result[name] = layer(box)
    return result


class CutoutOcclusionPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_occlusion_plan("a" * 64, "docs/evidence/r4-cutout-rig-v071.json")

    def test_plan_is_schema_versioned_and_hash_bound(self):
        self.assertEqual("0.7.2", self.plan["schema_version"])
        self.assertEqual("a" * 64, self.plan["source_sha256"])
        self.assertEqual(64, len(self.plan["plan_sha256"]))
        self.assertTrue(self.plan["render_and_qa_share_plan_hash"])

    def test_topology_has_ten_required_edges(self):
        self.assertEqual(10, len(self.plan["topology_adjacency"]))
        self.assertIn({"parent": "right_forearm_hand", "child": "sword", "joint": "wrist_right", "allowed_overlap_class": "JOINT_OVERLAP"}, self.plan["topology_adjacency"])

    def test_each_phase_has_complete_z_order_and_roles(self):
        self.assertEqual({"K1-contact-left", "K2-passing-left", "K3-contact-right", "K4-passing-right"}, set(PHASE_PLANS))
        for item in PHASE_PLANS.values():
            self.assertEqual(set(PART_NAMES), set(item["z_order"]))
            self.assertTrue(item["front_parts"] and item["back_parts"])

    def test_allowed_joint_overlap_is_not_unexpected(self):
        value = pairwise_overlap_qa(layers_with(head=(4, 4, 6, 6), torso_pelvis=(4, 4, 6, 6)), "K1-contact-left", target(), self.plan)
        record = next(item for item in value["pairs"] if {item["first"], item["second"]} == {"head", "torso_pelvis"})
        self.assertEqual("JOINT_OVERLAP", record["overlap_class"])
        self.assertEqual(0, value["unexpected_overlap_pixels"])

    def test_expected_nonadjacent_occlusion_is_allowed_by_plan(self):
        value = pairwise_overlap_qa(layers_with(head=(4, 4, 6, 6), right_upper_arm=(4, 4, 6, 6)), "K1-contact-left", target(), self.plan)
        record = next(item for item in value["pairs"] if {item["first"], item["second"]} == {"head", "right_upper_arm"})
        self.assertEqual("EXPECTED_OCCLUSION", record["overlap_class"])
        self.assertEqual("OCCLUSION_QA_PASSED", value["status"])

    def test_unexpected_nonadjacent_overlap_is_a_gap(self):
        value = pairwise_overlap_qa(layers_with(head=(4, 4, 8, 8), left_thigh=(4, 4, 8, 8)), "K1-contact-left", target(), self.plan)
        record = next(item for item in value["pairs"] if {item["first"], item["second"]} == {"head", "left_thigh"})
        self.assertEqual("UNEXPECTED_OVERLAP", record["overlap_class"])
        self.assertEqual("CUTOUT_RIG_OCCLUSION_GAP", value["status"])

    def test_sword_torso_overlap_is_critical_collision(self):
        value = pairwise_overlap_qa(layers_with(sword=(4, 4, 8, 8), torso_pelvis=(4, 4, 8, 8)), "K1-contact-left", target(), self.plan)
        record = next(item for item in value["pairs"] if {item["first"], item["second"]} == {"sword", "torso_pelvis"})
        self.assertEqual("CRITICAL_COLLISION", record["overlap_class"])
        self.assertGreater(value["critical_collision_pixels"], 0)

    def test_allowed_sword_trail_thigh_occlusion_is_expected(self):
        value = pairwise_overlap_qa(layers_with(sword=(4, 4, 8, 8), right_thigh=(4, 4, 8, 8)), "K2-passing-left", target(), self.plan)
        record = next(item for item in value["pairs"] if {item["first"], item["second"]} == {"sword", "right_thigh"})
        self.assertEqual("EXPECTED_OCCLUSION", record["overlap_class"])


class TopologicalSeamFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_occlusion_plan("a" * 64, "docs/evidence/r4-cutout-rig-v071.json")

    def test_perfect_joint_overlap_passes(self):
        value = topological_seam_qa(layers_with(**{name: (4, 4, 6, 6) for name in PART_NAMES}), "K1-contact-left", target(), self.plan)
        self.assertEqual("SEAM_TOPOLOGY_PASSED", value["status"])

    def test_one_pixel_aa_seam_passes_with_tolerance(self):
        data = {name: (4, 4, 6, 6) for name in PART_NAMES}
        data["head"] = (2, 4, 4, 6); data["torso_pelvis"] = (5, 4, 7, 6)
        value = topological_seam_qa(layers_with(**data), "K1-contact-left", target(), self.plan)
        edge = next(item for item in value["pairs"] if item["parent"] == "head" and item["child"] == "torso_pelvis")
        self.assertLessEqual(edge["min_alpha_to_alpha_distance_px"], 1.5)
        self.assertEqual("SEAM_TOPOLOGY_PASSED", edge["status"])

    def test_three_pixel_physical_gap_fails(self):
        data = {name: (4, 4, 6, 6) for name in PART_NAMES}
        data["head"] = (1, 4, 3, 6); data["torso_pelvis"] = (7, 4, 9, 6)
        value = topological_seam_qa(layers_with(**data), "K1-contact-left", target(), self.plan)
        edge = next(item for item in value["pairs"] if item["parent"] == "head" and item["child"] == "torso_pelvis")
        self.assertEqual("CUTOUT_RIG_TOPOLOGY_SEAM_GAP", edge["status"])
        self.assertFalse(edge["hard_gates"]["connected_path"])

    def test_disconnected_forearm_fixture_fails(self):
        data = {name: (4, 4, 6, 6) for name in PART_NAMES}
        data["right_forearm_hand"] = (1, 1, 2, 2); data["sword"] = (10, 10, 11, 11)
        value = topological_seam_qa(layers_with(**data), "K1-contact-left", target(), self.plan)
        edge = next(item for item in value["pairs"] if item["parent"] == "right_forearm_hand" and item["child"] == "sword")
        self.assertEqual("CUTOUT_RIG_TOPOLOGY_SEAM_GAP", edge["status"])


class RetentionOcclusionFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_occlusion_plan("a" * 64, "docs/evidence/r4-cutout-rig-v071.json")
        self.phase = "K1-contact-left"
        self.seam = {"status": "SEAM_TOPOLOGY_PASSED"}

    def _run(self, occluder: str, border: bool = False):
        back = (0, 0, 9, 9) if border else (4, 4, 13, 13)
        front = (4, 4, 6, 13) if border else (4, 4, 6, 13)
        layers = {name: layer() for name in PART_NAMES}
        layers["right_thigh"] = layer(back); layers[occluder] = layer(front)
        parts = {name: layer() for name in PART_NAMES}; parts["right_thigh"] = layer(back)
        output = compose_named_layers(layers, self.plan["phase_plans"][self.phase]["z_order"])
        pair = pairwise_overlap_qa(layers, self.phase, target(), self.plan)
        return retention_occlusion_qa(parts, layers, output, self.phase, pair, self.seam, self.plan)["parts"]["right_thigh"]

    def test_back_limb_at_seventy_percent_visible_passes_when_explained(self):
        value = self._run("torso_pelvis")
        self.assertGreaterEqual(value["visible_fraction"], 0.70)
        self.assertGreaterEqual(value["occlusion_explained_fraction"], 0.95)
        self.assertEqual("RETENTION_OCCLUSION_PASSED", value["status"])

    def test_same_loss_unexplained_fails(self):
        value = self._run("head")
        self.assertLess(value["occlusion_explained_fraction"], 0.95)
        self.assertEqual("CUTOUT_RIG_RETENTION_GAP", value["status"])

    def test_clipped_pixels_fail_closed(self):
        value = self._run("torso_pelvis", border=True)
        self.assertGreater(value["clipped_pixels"], 0)
        self.assertEqual("CUTOUT_RIG_RETENTION_GAP", value["status"])


class V072EvidenceTests(unittest.TestCase):
    def load(self, name: str) -> dict:
        return json.loads((ROOT / "docs" / "evidence" / name).read_text(encoding="utf-8"))

    def test_q0_and_four_key_poses_are_green(self):
        q0 = self.load("cutout-q0-regression-v072-qa.json")
        qualification = self.load("cutout-rig-provider-qualification-v072.json")
        self.assertEqual("CUTOUT_RIG_RECONSTRUCTION_PASSED", q0["status"])
        self.assertEqual("CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED", qualification["status"])
        self.assertEqual({"K1-contact-left", "K2-passing-left", "K3-contact-right", "K4-passing-right"}, set(qualification["poses"]))

    def test_all_four_poses_have_target_detected_media_pipe_evidence(self):
        poses = self.load("cutout-rig-provider-qualification-v072.json")["poses"]
        for record in poses.values():
            self.assertTrue(record["target"])
            self.assertIsNotNone(record["media_pipe"])
            self.assertTrue(record["metrics"]["qualifies"])

    def test_execution_boundary_is_zero_and_not_run(self):
        value = self.load("execution-evidence-v0.7.2.json")
        self.assertEqual(0, value["sam2_runs"])
        self.assertEqual(0, value["comfyui_generation_jobs"])
        self.assertEqual("NOT_RUN", value["walk"])
        self.assertEqual("not-claimed", value["external_approval"])

    def test_gait_and_half_cycle_are_passed(self):
        self.assertEqual("GAIT_CALIBRATION_PASSED", self.load("cutout-front-walk-gait-v2.json")["calibration_status"])
        self.assertEqual("HALF_CYCLE_STRUCTURE_PASSED", self.load("cutout-half-cycle-structure-v072.json")["status"])

    def test_historical_v071_state_snapshot_is_preserved(self):
        value = self.load("current-state-v0.7.1.json")
        self.assertEqual("0.7.1", value["version"])
        self.assertEqual("CUTOUT_RIG_SEAM_GAP", value["current_gate"])

    def test_visual_manifest_has_all_v072_roles(self):
        value = self.load("review-visuals-v0.7.2.json")
        self.assertEqual("0.7.2", value["schema_version"])
        self.assertEqual(20, len(value["required_current_visuals"]))
        self.assertEqual(20, len(value["images"]))


if __name__ == "__main__":
    unittest.main()
