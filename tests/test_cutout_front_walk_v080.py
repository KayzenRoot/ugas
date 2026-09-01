"""Regression gates for the deterministic v0.8.0 front-walk pilot."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "validation"))

from ugas.cutout_temporal import PHASES, target_digest  # noqa: E402


EVIDENCE = ROOT / "docs" / "evidence"


def read(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


class FrontWalkV080Tests(unittest.TestCase):
    def test_phase_contract_is_exactly_eight_front_frames(self) -> None:
        self.assertEqual(PHASES, ("F0-contact-left", "F1-down-left", "F2-passing-left", "F3-up-left", "F4-contact-right", "F5-down-right", "F6-passing-right", "F7-up-right"))

    def test_config_is_frozen_before_render(self) -> None:
        config = read("front-walk-cycle-v1-config.json")
        self.assertEqual(config["status"], "FROZEN_BEFORE_RENDER")
        self.assertEqual(config["cycle"]["frame_count"], 8)
        self.assertFalse(config["intermediate_generator"]["pixel_interpolation"])

    def test_config_sha_is_bound_to_targets(self) -> None:
        config_hash = hashlib.sha256(json.dumps(read("front-walk-cycle-v1-config.json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(read("front-walk-targets-v080.json")["config_sha256"], config_hash)

    def test_key_pose_hash_binding_is_exact(self) -> None:
        binding = read("front-walk-targets-v080.json")["key_binding"]
        self.assertTrue(all(item["exact"] for item in binding.values()))
        self.assertEqual(binding["F0"]["target_joint_sha256"], "f2f74f19d576d4705f4040b98aaa0ad32c5d001db96d7ace706fcd1a1555e1d8")
        self.assertEqual(binding["F2"]["target_joint_sha256"], "3f1f8e8c17373fd2d10ee7fc7f316708e77bb21814f54b57e1c870f51ba770e6")
        self.assertEqual(binding["F4"]["target_joint_sha256"], "428016ce4d11f56702cb57501dbb400bc9d534c337fe3cf6a5d16bb1d1c53648")
        self.assertEqual(binding["F6"]["target_joint_sha256"], "a1aa58129262cbad344cce22059299cc8754e021b8507700f86eb3fd7e18c2c4")

    def test_all_targets_are_distinct(self) -> None:
        targets = read("front-walk-targets-v080.json")["targets"]
        self.assertEqual(len(targets), 8)
        self.assertEqual(len({target_digest(item) for item in targets.values()}), 8)

    def test_z_order_has_eight_plan_entries_and_hash(self) -> None:
        plan = read("front-walk-z-order-v080.json")
        self.assertEqual(len(plan["phase_plans"]), 8)
        self.assertTrue(plan["render_and_qa_share_plan_hash"])
        self.assertRegex(plan["plan_sha256"], r"^[0-9a-f]{64}$")

    def test_bone_projection_passes(self) -> None:
        self.assertEqual(read("front-walk-bone-projection-v080.json")["status"], "BONE_PROJECTION_PASSED")

    def test_each_frame_passes_all_hard_gates(self) -> None:
        report = read("front-walk-per-frame-qa-v080.json")
        self.assertEqual(report["status"], "CUTOUT_RIG_FRONT_WALK_FRAMES_PASSED")
        self.assertEqual(len(report["frames"]), 8)
        for frame in report["frames"]:
            self.assertEqual(frame["status"], "CUTOUT_RIG_FRONT_WALK_FRAME_PASSED")
            self.assertTrue(all(frame["hard_gates"].values()))

    def test_structural_coverage_passes_every_frame(self) -> None:
        report = read("front-walk-structural-coverage-v080.json")
        self.assertEqual(report["status"], "STRUCTURAL_COVERAGE_PASSED")
        self.assertEqual(len(report["poses"]), 8)

    def test_layer_integrity_passes_every_frame(self) -> None:
        report = read("front-walk-layer-integrity-v080.json")
        self.assertEqual(report["status"], "LAYER_INTEGRITY_PASSED")
        self.assertEqual(len(report["poses"]), 8)

    def test_occlusion_and_retention_pass_every_frame(self) -> None:
        self.assertEqual(read("front-walk-occlusion-v080.json")["status"], "OCCLUSION_QA_PASSED")
        self.assertEqual(read("front-walk-retention-v080.json")["status"], "RETENTION_OCCLUSION_PASSED")

    def test_temporal_qa_passes(self) -> None:
        report = read("front-walk-temporal-qa-v080.json")
        self.assertEqual(report["status"], "CUTOUT_RIG_FRONT_WALK_TEMPORAL_PASSED")
        self.assertTrue(all(report["hard_gates"].values()))

    def test_foot_contact_passes(self) -> None:
        report = read("front-walk-foot-contact-qa-v080.json")
        self.assertEqual(report["status"], "CUTOUT_RIG_FRONT_WALK_FOOT_CONTACT_PASSED")
        self.assertTrue(all(report["hard_gates"].values()))

    def test_half_cycle_passes(self) -> None:
        self.assertEqual(read("front-walk-half-cycle-qa-v080.json")["status"], "CUTOUT_RIG_FRONT_WALK_HALF_CYCLE_PASSED")

    def test_loop_passes(self) -> None:
        report = read("front-walk-loop-qa-v080.json")
        self.assertEqual(report["edge"], "F7->F0")
        self.assertEqual(report["status"], "CUTOUT_RIG_FRONT_WALK_LOOP_PASSED")

    def test_sprite_is_rgba_2048_by_1024(self) -> None:
        image = Image.open(EVIDENCE / "walk-front-v080" / "walk-front-spritesheet-v080.png")
        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.size, (2048, 1024))

    def test_metadata_has_row_major_order_and_hashes(self) -> None:
        metadata = read("walk-front-v080/walk-front-metadata-v080.json")
        self.assertEqual(metadata["status"], "SPRITESHEET_METADATA_PASSED")
        self.assertEqual([item["index"] for item in metadata["frames"]], list(range(8)))
        self.assertEqual([item["phase"] for item in metadata["frames"]], list(PHASES))
        self.assertTrue(all(len(item["rgba_sha256"]) == 64 for item in metadata["frames"]))

    def test_package_is_pilot_only(self) -> None:
        package = read("walk-front-v080/walk-front-package-manifest-v080.json")
        self.assertEqual(package["registry_state"], "pilot/technical-qualified")
        self.assertFalse(package["production_approved"])
        self.assertEqual(package["production_routing"], "BLOCKED")

    def test_no_generation_provider_calls(self) -> None:
        execution = read("execution-evidence-v0.8.0.json")
        qualification = read("front-walk-provider-qualification-v080.json")
        self.assertEqual(execution["sam2_runs"], 0)
        self.assertEqual(execution["comfyui_generation_jobs"], 0)
        self.assertEqual(qualification["new_generation_jobs"], 0)

    def test_all_visual_evidence_sets_have_eight_frames(self) -> None:
        for directory in ("frames", "checkerboard", "target-detected-overlays", "structural-hole-maps"):
            self.assertEqual(len(list((EVIDENCE / "walk-front-v080" / directory).glob("frame-*.png"))), 8)

    def test_historical_v073_snapshot_exists(self) -> None:
        self.assertTrue((EVIDENCE / "current-state-v0.7.3.json").is_file())
        self.assertTrue((ROOT / "schemas" / "current-state-v0.7.3.json").is_file())
        self.assertTrue((ROOT / "providers" / "manifests" / "deterministic-cutout-rig-2d-v0.7.3.json").is_file())


if __name__ == "__main__":
    unittest.main()
