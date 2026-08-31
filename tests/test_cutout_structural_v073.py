"""Executable fixtures for the v0.7.3 structural coverage correction."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "validation"))

import run_cutout_rig_v073 as qualifier  # noqa: E402
from ugas.cutout_occlusion import PHASE_PLANS, build_occlusion_plan, phase_plan, render_part_layers_with_plan  # noqa: E402
from ugas.cutout_rig import PART_NAMES, render_part  # noqa: E402
from ugas.cutout_structural import (  # noqa: E402
    ACTIVE_ALPHA_THRESHOLD,
    build_authorized_occlusion_regions,
    build_structural_core,
    calibrate_layer_integrity_fixtures,
    compose_with_structural_core,
    edge_speckle_qa,
    exclude_protected_regions,
    layer_integrity_qa,
    pairwise_overlap_v073,
    source_core_rgba,
    structural_coverage_qa,
)
from ugas.identity import ANCHOR_SHA256  # noqa: E402


def blank(size: tuple[int, int] = (512, 512)) -> Image.Image:
    return Image.new("RGBA", size, (0, 0, 0, 0))


def draw_layer(box: tuple[int, int, int, int], size: tuple[int, int] = (512, 512)) -> Image.Image:
    image = blank(size)
    ImageDraw.Draw(image).rectangle(box, fill=(255, 255, 255, 255))
    return image


def actual_target(phase: str = "K4-passing-right") -> dict:
    return qualifier.read_json(qualifier.V072_QUALIFICATION_PATH)["poses"][phase]["target"]


def realistic_layers(**overrides: tuple[int, int, int, int]) -> dict[str, Image.Image]:
    layers = {name: blank() for name in PART_NAMES}
    for name, box in overrides.items():
        layers[name] = draw_layer(box)
    return layers


class StructuralCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source, cls.parts, cls.masks, cls.skeleton = qualifier.load_inputs()
        cls.core = build_structural_core(cls.source, cls.source.getchannel("A"), cls.masks["torso_pelvis"], cls.masks, cls.skeleton)

    def test_core_is_deterministic(self):
        again = build_structural_core(self.source, self.source.getchannel("A"), self.masks["torso_pelvis"], self.masks, self.skeleton)
        self.assertEqual(self.core["core_mask_sha256"], again["core_mask_sha256"])
        self.assertEqual(self.core["parameter_sha256"], again["parameter_sha256"])

    def test_core_is_source_only_and_excludes_protected_parts(self):
        self.assertTrue(self.core["source_only"])
        self.assertFalse(self.core["manual_click"])
        self.assertFalse(self.core["sam2"])
        self.assertTrue(self.core["derivation_parameters"]["parameters"]["source_only_pixels"])
        for name in ("head", "sword"):
            overlap = self.core["core_mask"].point(lambda value: value)
            self.assertEqual(0, sum(1 for a, b in zip(overlap.getdata(), self.masks[name].getdata()) if a > 0 and b > ACTIVE_ALPHA_THRESHOLD))

    def test_core_has_redundant_owner_provenance(self):
        self.assertTrue(self.core["controlled_redundant_provenance"])
        self.assertGreater(self.core["structural_core_pixels"], 0)
        self.assertGreater(self.core["owner_counts"]["torso_pelvis"], 0)

    def test_protected_region_exclusion_is_zero_for_rendered_poses(self):
        target = actual_target()
        layers, transforms = render_part_layers_with_plan(self.parts, self.skeleton, target, "K4-passing-right", self.source.size)
        torso = next(item for item in transforms if item["part"] == "torso_pelvis")
        core_layer = render_part(source_core_rgba(self.source, self.core["core_mask"]), tuple(torso["source_pivot"]), tuple(torso["target_pivot"]), tuple(torso["source_end"]), tuple(torso["target_end"]), self.source.size)
        core_layer = exclude_protected_regions(core_layer, layers)
        for name in ("head", "sword"):
            self.assertEqual(0, sum(1 for a, b in zip(core_layer.getchannel("A").getdata(), layers[name].getchannel("A").getdata()) if a > 0 and b > ACTIVE_ALPHA_THRESHOLD))

    def test_q0_evidence_remains_green(self):
        q0 = json.loads((ROOT / "docs/evidence/cutout-q0-regression-v073-qa.json").read_text(encoding="utf-8"))
        self.assertEqual("CUTOUT_RIG_RECONSTRUCTION_PASSED", q0["status"])
        self.assertGreaterEqual(q0["alpha_iou"], 0.995)
        self.assertLessEqual(q0["rgb_mae"], 1.5)


class StructuralCoverageFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.size = (100, 100)
        self.target = {"joints": {name: {"x": 50.0, "y": 50.0} for name in ("nose", "neck", "shoulder_left", "shoulder_right", "elbow_left", "elbow_right", "wrist_left", "wrist_right", "hip_left", "hip_right", "knee_left", "knee_right", "ankle_left", "ankle_right", "pelvis", "shoulder_center", "weapon_tip")}}
        mask = Image.new("L", self.size, 0)
        ImageDraw.Draw(mask).rectangle((38, 38, 62, 72), fill=255)
        bridge = Image.new("L", self.size, 0)
        ImageDraw.Draw(bridge).rectangle((40, 48, 60, 60), fill=255)
        identity = {"source_pivot": [50.0, 50.0], "target_pivot": [50.0, 50.0], "source_end": [50.0, 80.0], "target_end": [50.0, 80.0], "uniform_scale": 1.0, "forward_affine_matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]}
        self.core = {"core_mask": mask, "belt_core_mask": bridge, "pelvis_bridge_mask": bridge, "torso_core_mask": mask, "torso_transform": identity}
        self.core_layer = Image.new("RGBA", self.size, (80, 90, 100, 0))
        self.core_layer.putalpha(mask)

    def test_single_antialias_pixel_hole_passes(self):
        output = self.core_layer.copy()
        alpha = output.getchannel("A")
        alpha.putpixel((50, 65), 0)
        output.putalpha(alpha)
        result = structural_coverage_qa(self.core_layer, output, self.target, "K1-contact-left", self.core)
        self.assertEqual("STRUCTURAL_COVERAGE_PASSED", result["status"])
        self.assertEqual(1, result["structural_hole_pixels"])
        self.assertEqual(1, result["largest_structural_hole_component_pixels"])

    def test_deliberate_large_structural_hole_fails(self):
        output = self.core_layer.copy()
        alpha = output.getchannel("A")
        for y in range(48, 62):
            for x in range(44, 57):
                alpha.putpixel((x, y), 0)
        output.putalpha(alpha)
        result = structural_coverage_qa(self.core_layer, output, self.target, "K1-contact-left", self.core)
        self.assertEqual("CUTOUT_RIG_STRUCTURAL_COVERAGE_GAP", result["status"])
        self.assertGreater(result["largest_structural_hole_component_pixels"], 12)

    def test_v072_k4_transparency_fixture_fails_new_coverage_gate(self):
        source, parts, masks, skeleton = qualifier.load_inputs()
        target = actual_target()
        layers, transforms = render_part_layers_with_plan(parts, skeleton, target, "K4-passing-right", source.size)
        torso = next(item for item in transforms if item["part"] == "torso_pelvis")
        core = build_structural_core(source, source.getchannel("A"), masks["torso_pelvis"], masks, skeleton)
        core_for_pose = dict(core, torso_transform=torso)
        core_layer = render_part(source_core_rgba(source, core["core_mask"]), tuple(torso["source_pivot"]), tuple(torso["target_pivot"]), tuple(torso["source_end"]), tuple(torso["target_end"]), source.size)
        old_output = Image.open(ROOT / "docs/evidence/cutout-k4-passing-right-v072.png").convert("RGBA")
        result = structural_coverage_qa(core_layer, old_output, target, "K4-passing-right", core_for_pose)
        self.assertEqual("CUTOUT_RIG_STRUCTURAL_COVERAGE_GAP", result["status"])
        self.assertGreater(result["structural_hole_pixels"], 0)

    def test_active_coverage_evidence_has_zero_holes(self):
        evidence = json.loads((ROOT / "docs/evidence/cutout-structural-coverage-v073.json").read_text(encoding="utf-8"))
        self.assertEqual("STRUCTURAL_COVERAGE_PASSED", evidence["status"])
        for pose in evidence["poses"].values():
            self.assertEqual(0, pose["structural_hole_pixels"])
            self.assertGreaterEqual(pose["belt_core_coverage"], 0.995)
            self.assertGreaterEqual(pose["torso_core_coverage"], 0.995)

    def test_detached_large_component_fails(self):
        image = blank(self.size)
        ImageDraw.Draw(image).rectangle((10, 10, 20, 20), fill=(255, 255, 255, 255))
        ImageDraw.Draw(image).rectangle((70, 70, 80, 80), fill=(255, 255, 255, 255))
        result = edge_speckle_qa(image)
        self.assertEqual("CUTOUT_RIG_STRUCTURAL_COVERAGE_GAP", result["status"])
        self.assertEqual(1, result["meaningful_detached_fragment_count"])


class LayerIntegrityFixtureTests(unittest.TestCase):
    def test_calibration_has_independent_area_and_negative_crop(self):
        result = calibrate_layer_integrity_fixtures()
        self.assertEqual("LAYER_INTEGRITY_CALIBRATION_PASSED", result["status"])
        self.assertTrue(result["hard_gates"]["scaled_passes"])
        self.assertTrue(result["hard_gates"]["deliberate_crop_fails"])

    def test_active_layer_integrity_is_green(self):
        result = json.loads((ROOT / "docs/evidence/cutout-layer-integrity-v073.json").read_text(encoding="utf-8"))
        self.assertEqual("LAYER_INTEGRITY_PASSED", result["status"])
        self.assertTrue(all(part["predicted_outside_canvas_area"] == 0 for pose in result["poses"].values() for part in pose["parts"].values()))


class PairwiseV073FixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_occlusion_plan(ANCHOR_SHA256, "docs/evidence/r4-cutout-rig-v071.json")
        self.target = actual_target()

    def test_adjacent_pair_outside_region_is_unexpected(self):
        layers = realistic_layers(torso_pelvis=(10, 10, 30, 30), left_upper_arm=(10, 10, 30, 30))
        regions = build_authorized_occlusion_regions(self.target, "K1-contact-left", self.plan, (512, 512))
        result = pairwise_overlap_v073(layers, "K1-contact-left", self.target, self.plan, regions)
        pair = next(item for item in result["pairs"] if {item["first"], item["second"]} == {"torso_pelvis", "left_upper_arm"})
        self.assertEqual("UNEXPECTED_OVERLAP", pair["overlap_class"])

    def test_hip_overlap_inside_explicit_region_passes(self):
        hip = self.target["joints"]["hip_left"]
        box = (int(hip["x"] + 16), int(hip["y"] + 16), int(hip["x"] + 22), int(hip["y"] + 22))
        result = pairwise_overlap_v073(realistic_layers(torso_pelvis=box, left_thigh=box), "K1-contact-left", self.target, self.plan, build_authorized_occlusion_regions(self.target, "K1-contact-left", self.plan, (512, 512)))
        pair = next(item for item in result["pairs"] if {item["first"], item["second"]} == {"torso_pelvis", "left_thigh"})
        self.assertIn(pair["overlap_class"], {"JOINT_OVERLAP", "EXPECTED_OCCLUSION"})

    def test_critical_sword_torso_collision_never_authorized(self):
        result = pairwise_overlap_v073(realistic_layers(sword=(10, 10, 30, 30), torso_pelvis=(10, 10, 30, 30)), "K1-contact-left", self.target, self.plan, build_authorized_occlusion_regions(self.target, "K1-contact-left", self.plan, (512, 512)))
        pair = next(item for item in result["pairs"] if {item["first"], item["second"]} == {"sword", "torso_pelvis"})
        self.assertEqual("CRITICAL_COLLISION", pair["overlap_class"])
        self.assertGreater(result["critical_collision_pixels"], 0)

    def test_z_order_mismatch_is_a_gap(self):
        regions = build_authorized_occlusion_regions(self.target, "K1-contact-left", self.plan, (512, 512))
        mutated = copy.deepcopy(self.plan)
        order = mutated["phase_plans"]["K1-contact-left"]["z_order"]
        torso_index, thigh_index = order.index("torso_pelvis"), order.index("left_thigh")
        order[torso_index], order[thigh_index] = order[thigh_index], order[torso_index]
        hip = self.target["joints"]["hip_left"]
        box = (int(hip["x"] + 16), int(hip["y"] + 16), int(hip["x"] + 22), int(hip["y"] + 22))
        result = pairwise_overlap_v073(realistic_layers(torso_pelvis=box, left_thigh=box), "K1-contact-left", self.target, mutated, regions)
        self.assertTrue(result["z_order_mismatches"])
        self.assertEqual("CUTOUT_RIG_OCCLUSION_REGION_GAP", result["status"])

    def test_active_pairwise_evidence_has_no_critical_or_meaningful_forbidden_overlap(self):
        result = json.loads((ROOT / "docs/evidence/cutout-pairwise-overlap-matrix-v073.json").read_text(encoding="utf-8"))
        self.assertEqual("OCCLUSION_QA_PASSED", result["status"])
        for pose in result["poses"].values():
            self.assertEqual(0, pose["critical_collision_pixels"])
            self.assertFalse(pose["forbidden_meaningful_overlap"])


class V073EvidenceBoundaryTests(unittest.TestCase):
    def test_provider_qualification_and_execution_boundary(self):
        qualification = json.loads((ROOT / "docs/evidence/cutout-rig-provider-qualification-v073.json").read_text(encoding="utf-8"))
        execution = json.loads((ROOT / "docs/evidence/execution-evidence-v0.7.3.json").read_text(encoding="utf-8"))
        self.assertEqual("CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED", qualification["status"])
        self.assertFalse(qualification["walk_authorized"])
        self.assertEqual(0, qualification["sam2_runs"])
        self.assertEqual(0, qualification["comfyui_generation_jobs"])
        self.assertEqual("NOT_RUN", execution["walk"])
        self.assertEqual("not-claimed", qualification["external_approval"])

    def test_all_four_key_poses_keep_v072_target_hashes(self):
        qualification = json.loads((ROOT / "docs/evidence/cutout-rig-provider-qualification-v073.json").read_text(encoding="utf-8"))
        self.assertEqual(set(PHASE_PLANS), set(qualification["poses"]))
        self.assertEqual(set(PHASE_PLANS), set(qualification["historical_v072_target_joint_hashes"]))
        self.assertTrue(all(len(value) == 64 for value in qualification["historical_v072_target_joint_hashes"].values()))

    def test_owner_diagnostics_are_empty_after_correction(self):
        result = json.loads((ROOT / "docs/evidence/cutout-structural-hole-owner-diagnostics-v073.json").read_text(encoding="utf-8"))
        self.assertEqual("STRUCTURAL_HOLE_OWNER_DIAGNOSTICS_PASSED", result["status"])
        self.assertTrue(all(not pose["holes"] for pose in result["poses"].values()))

    def test_required_v073_schemas_are_present(self):
        for name in ("cutout-structural-core-v073.json", "cutout-authorized-occlusion-regions-v073.json", "cutout-layer-integrity-v073.json", "cutout-structural-coverage-v073.json", "cutout-structural-hole-owner-diagnostics-v073.json", "cutout-pairwise-overlap-v073.json", "cutout-seam-topology-qa-v073.json", "cutout-retention-occlusion-v073.json", "cutout-rig-provider-qualification-v073.json", "execution-evidence-v073.json"):
            self.assertTrue((ROOT / "schemas" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
