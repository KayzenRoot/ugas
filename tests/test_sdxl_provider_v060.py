"""Regression tests for the v0.6.0 SDXL provider qualification contract."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ugas.workflow_registry import bind_workflow, validate_api_workflow


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


class SdxlProviderV060Tests(unittest.TestCase):
    def test_active_state_preserves_history_and_blocks_walk(self):
        state = load("docs/evidence/current-state-v0.6.1.json")
        self.assertEqual("0.6.1", state["version"])
        self.assertEqual("SDXL_CONTROL_POSE_PROVIDER_SMOKE_CORRECTION", state["phase"])
        self.assertEqual("0.6.0", state["previous_release"]["version"])
        self.assertFalse(state["walk_authorized"])
        self.assertEqual("LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED", state["pose_lane_status"])

    def test_factorial_workflows_are_separate_and_deterministic(self):
        registry = load("providers/workflows/registry.json")
        workflows = {item["id"]: item for item in registry["workflows"]}
        self.assertEqual(
            {"sdxl-openpose-controlnet-p", "sdxl-ipadapter-i", "sdxl-openpose-ipadapter-character"},
            set(workflows) & {"sdxl-openpose-controlnet-p", "sdxl-ipadapter-i", "sdxl-openpose-ipadapter-character"},
        )
        for workflow_id in ("sdxl-openpose-controlnet-p", "sdxl-ipadapter-i", "sdxl-openpose-ipadapter-character"):
            self.assertTrue(workflows[workflow_id]["deterministic_seed"])
            self.assertEqual("0.6.0", workflows[workflow_id]["schema_version"])

    def test_bound_provider_model_keys_are_checked_against_live_inventory(self):
        template = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "__SDXL_CHECKPOINT__"}},
            "2": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "__CONTROLNET__"}},
            "3": {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": "__IPADAPTER__"}},
            "4": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "__CLIP_VISION__"}},
        }
        bound = bind_workflow(
            template,
            prompt="p",
            model_names={
                "__SDXL_CHECKPOINT__": "base.safetensors",
                "__CONTROLNET__": "pose.safetensors",
                "__IPADAPTER__": "ip.safetensors",
                "__CLIP_VISION__": "clip.safetensors",
            },
        )
        valid = validate_api_workflow(bound, model_names={"base.safetensors", "pose.safetensors", "ip.safetensors", "clip.safetensors"})
        self.assertTrue(valid["live_valid"])
        invalid = validate_api_workflow(bound, model_names={"base.safetensors", "pose.safetensors", "clip.safetensors"})
        self.assertEqual(["ip.safetensors"], invalid["missing_models"])

    def test_bound_provider_seed_is_an_integer(self):
        bound = bind_workflow(
            {"1": {"class_type": "KSampler", "inputs": {"seed": "__SEED__"}}},
            prompt="p",
            seed=60701,
        )
        self.assertEqual(60701, bound["1"]["inputs"]["seed"])

    def test_model_contracts_have_content_hashes_and_license_records(self):
        registry = load("providers/models/registry.json")
        models = {item["id"]: item for item in registry["models"]}
        for model_id in ("sdxl-base-1.0", "xinsir-controlnet-openpose-sdxl-1.0", "ipadapter-plus-sdxl-vit-h", "clip-vision-vit-h"):
            model = models[model_id]
            digest = next(iter(model["sha256"].values()))
            self.assertEqual(64, len(digest))
            self.assertTrue(model["license"])
            self.assertTrue(model["exact_files"])
            self.assertTrue(model["qualification_evidence"])

    def test_ipadapter_sdxl_vit_h_uses_openclip_vit_h_encoder_pair(self):
        registry = load("providers/models/registry.json")
        models = {item["id"]: item for item in registry["models"]}
        ipadapter = models["ipadapter-plus-sdxl-vit-h"]
        clip = models["clip-vision-vit-h"]
        self.assertEqual("OpenCLIP-ViT-H-14", clip["artifact_variant"])
        self.assertEqual("models/image_encoder/model.safetensors", clip["source_subpath"])
        self.assertEqual("ip-adapter-plus_sdxl_vit-h.safetensors", clip["paired_with"])
        self.assertEqual("OpenCLIP-ViT-H-14", ipadapter["required_clip_vision_variant"])
        self.assertNotEqual("sdxl_models/image_encoder/model.safetensors", clip["source_subpath"])

    def test_custom_node_pin_is_auditable_and_not_vendored(self):
        audit = load("docs/evidence/custom-node-audit-ipadapter-plus.json")
        self.assertEqual("CUSTOM_NODE_AUDIT_PASSED", audit["audit_status"])
        self.assertEqual("a0f451a5113cf9becb0847b92884cb10cbdec0ef", audit["commit"])
        self.assertEqual("GPL-3.0-only", audit["license"])
        self.assertTrue(audit["install_allowed"])
        self.assertFalse(audit["source_vendored_in_ugas"])

    def test_pose_thresholds_are_reused_without_changes(self):
        thresholds = load("docs/evidence/pose-thresholds-v054.json")
        self.assertTrue(thresholds["thresholds_are_frozen_before_jobs"])
        self.assertEqual(10, thresholds["absolute_pose"]["measurable_body_joints_min"])
        self.assertEqual(0.80, thresholds["absolute_pose"]["pck_at_010_min"])
        self.assertEqual(0.10, thresholds["absolute_pose"]["nme_max"])
        self.assertEqual(18.0, thresholds["absolute_pose"]["limb_angle_mae_max_degrees"])
        self.assertEqual(0.75, thresholds["absolute_pose"]["lower_body_pck_min"])

    def test_weights_and_custom_source_are_not_in_the_repository_tree(self):
        names = [path.as_posix().casefold() for path in ROOT.rglob("*") if path.is_file()]
        self.assertFalse(any(name.endswith(('.safetensors', '.ckpt', '.gguf', '.onnx')) for name in names))
        self.assertFalse((ROOT / "providers/custom-nodes/ComfyUI_IPAdapter_plus").exists())


if __name__ == "__main__":
    unittest.main()
