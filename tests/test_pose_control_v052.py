"""v0.5.2 OpenPose and native-order contract tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ugas.constants import UGAS_VERSION
from ugas.openpose_guides import COCO18_JOINTS, OPENPOSE_GUIDE_RENDERER_VERSION, challenge_openpose_guide, render_openpose_guide, validate_openpose_guide
from ugas.pose_control import NATIVE_LANES, _lane_summary
from ugas.refcontrol import inspect_refcontrol_native_loader
from ugas.model_registry import ModelRegistryError, download_exact
from ugas.workflow_registry import bind_workflow, load_workflow

ROOT = Path(__file__).resolve().parents[1]


class PoseControlV052Tests(unittest.TestCase):
    def test_openpose_is_exactly_deterministic_coco18_and_black_control(self):
        guide_a = challenge_openpose_guide()
        guide_b = challenge_openpose_guide()
        self.assertEqual(guide_a, guide_b)
        self.assertEqual(UGAS_VERSION, guide_a["schema_version"])
        self.assertEqual(tuple(guide_a["joints"]), COCO18_JOINTS)
        self.assertEqual(OPENPOSE_GUIDE_RENDERER_VERSION, guide_a["renderer"]["version"])
        self.assertEqual("OPENPOSE_GUIDE_VALID", validate_openpose_guide(guide_a)["status"])
        with tempfile.TemporaryDirectory() as directory:
            first = render_openpose_guide(guide_a, Path(directory) / "one.png")
            second = render_openpose_guide(guide_b, Path(directory) / "two.png")
            self.assertEqual(first["sha256"], second["sha256"])
            with Image.open(Path(directory) / "one.png") as image:
                self.assertEqual((0, 0, 0, 255), image.getpixel((0, 0)))

    def test_unavailable_joints_are_explicit_not_random(self):
        guide = challenge_openpose_guide()
        for name in ("eye_right", "eye_left", "ear_right", "ear_left"):
            self.assertFalse(guide["joints"][name]["visible"])
            self.assertIsNone(guide["joints"][name]["source"])

    def test_b_and_c_have_different_workflow_hash_and_semantic_order(self):
        b = load_workflow(ROOT, NATIVE_LANES["B"]["workflow_id"])
        c = load_workflow(ROOT, NATIVE_LANES["C"]["workflow_id"])
        self.assertNotEqual(b["sha256"], c["sha256"])
        bound_b = bind_workflow(b["api"], prompt="b", seed=1, image_filenames=["identity.png", "pose.png"])
        bound_c = bind_workflow(c["api"], prompt="c", seed=1, image_filenames=["identity.png", "pose.png"])
        self.assertEqual("identity.png", bound_b["6"]["inputs"]["image"])
        self.assertEqual("pose.png", bound_b["8"]["inputs"]["image"])
        self.assertEqual("pose.png", bound_c["6"]["inputs"]["image"])
        self.assertEqual("identity.png", bound_c["8"]["inputs"]["image"])

    def test_native_lane_does_not_qualify_without_gain(self):
        def record(pose: float, seed: int) -> dict:
            return {"lane": "B", "seed": seed, "eligible": True, "fresh_binding": True, "score": {"pose": {"pose_score": pose}, "identity": {"identity_descriptor_score": .9}, "weapon_present": True}}
        summary = _lane_summary([record(.80, 52701), record(.80, 52702), record(.80, 52703)], "B", .70)
        self.assertFalse(summary["qualified"])
        self.assertEqual(.1, summary["pose_gain_over_A"])

    def test_refcontrol_requires_a_native_lora_loader(self):
        class FakeClient:
            def node_info(self):
                return {
                    "LoraLoaderModelOnly": {
                        "python_module": "nodes",
                        "input": {"required": {"model": ["MODEL"], "lora_name": ["STRING"], "strength_model": ["FLOAT"]}},
                        "output": ["MODEL"],
                    }
                }

        result = inspect_refcontrol_native_loader(ROOT, FakeClient())
        self.assertEqual("REFCONTROL_NATIVE_LORA_LOADER_FOUND", result["status"])
        self.assertEqual("LoraLoaderModelOnly", result["selected"]["node"])
        self.assertTrue(result["selected"]["native"])

    def test_refcontrol_download_rejects_hash_mismatch_without_promoting_file(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.bin"
            destination = Path(directory) / "nested" / "download.bin"
            source.write_bytes(b"UGAS test payload")
            with self.assertRaises(ModelRegistryError):
                download_exact(source.as_uri(), destination, "0" * 64)
            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_suffix(destination.suffix + ".part").exists())

    def test_refcontrol_evidence_is_below_fixed_gain_gate(self):
        evidence = json.loads((ROOT / "docs/evidence/refcontrol-pose-qualification.json").read_text(encoding="utf-8"))
        self.assertEqual("LOCAL_POSE_CONTROL_PROVIDER_GAP", evidence["status"])
        self.assertLess(max(item["pose_gain_over_A"] for item in evidence["triage"]), 0.15)


if __name__ == "__main__":
    unittest.main()
