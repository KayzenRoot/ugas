"""Contract tests for the v0.6.2 model-card calibration slice."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ugas.openpose_guides import render_openpose_guide_at_resolution, validate_openpose_guide
from ugas.sdxl_openpose_calibration import (
    CALIBRATION_MATRIX,
    CONFIRMATION_SEEDS,
    MODEL_CARD_CONFIGURATION,
    SEED,
    derive_p_workflow,
    is_oom_error,
    qualification_status,
    validate_calibration_matrix,
)


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


class SdxlOpenPoseCalibrationV062Tests(unittest.TestCase):
    def test_exact_matrix_and_model_card_operating_point(self):
        self.assertEqual([], validate_calibration_matrix())
        self.assertEqual(["P0", "P1", "P2"], [item["id"] for item in CALIBRATION_MATRIX])
        self.assertEqual(1.0, MODEL_CARD_CONFIGURATION["controlnet_conditioning_scale"])
        self.assertEqual(30, MODEL_CARD_CONFIGURATION["num_inference_steps"])
        self.assertEqual("EulerAncestralDiscreteScheduler", MODEL_CARD_CONFIGURATION["scheduler"])

    def test_matrix_rejects_parameter_drift(self):
        changed = [dict(item) for item in CALIBRATION_MATRIX]
        changed[1]["steps"] = 20
        self.assertIn("matrix_config_invalid:P1", validate_calibration_matrix(changed))

    def test_p_workflow_is_p_only_and_preserves_topology(self):
        template = load("providers/workflows/sdxl-openpose-controlnet-p.api.json")
        config = CALIBRATION_MATRIX[1]
        workflow, meta = derive_p_workflow(
            template,
            config,
            prompt="prompt",
            negative_prompt="negative",
            seed=SEED,
            guide_filename="guide.png",
            model_names={
                "__SDXL_CHECKPOINT__": "sd_xl_base_1.0.safetensors",
                "__CONTROLNET__": "xinsir-controlnet-openpose-sdxl-1.0.safetensors",
            },
            available_models={"sd_xl_base_1.0.safetensors", "xinsir-controlnet-openpose-sdxl-1.0.safetensors"},
        )
        self.assertEqual(10, len(workflow))
        self.assertTrue(meta["graph"]["p_only"])
        self.assertEqual([], meta["graph"]["ipadapter_nodes"])
        sampler = next(node for node in workflow.values() if node.get("class_type") == "KSampler")
        control = next(node for node in workflow.values() if node.get("class_type") == "ControlNetApplyAdvanced")
        self.assertEqual(30, sampler["inputs"]["steps"])
        self.assertEqual("euler_ancestral", sampler["inputs"]["sampler_name"])
        self.assertEqual("normal", sampler["inputs"]["scheduler"])
        self.assertEqual(1.0, control["inputs"]["strength"])

    def test_guide_is_rendered_directly_at_each_bucket(self):
        guide = load("pose-guides/openpose-v3/challenges/multiref-strong-left-arm-up.json")
        self.assertEqual("OPENPOSE_GUIDE_VALID", validate_openpose_guide(guide)["status"])
        with tempfile.TemporaryDirectory() as directory:
            for size in (512, 768, 1024):
                result = render_openpose_guide_at_resolution(guide, Path(directory) / f"guide-{size}.png", width=size, height=size)
                self.assertEqual([size, size], [result["render_parameters"]["width"], result["render_parameters"]["height"]])
                self.assertFalse(result["render_parameters"]["raster_upscale"])
                self.assertTrue(result["render_parameters"]["derived_from_json"])
                self.assertEqual(32, len(bytes.fromhex(result["sha256"])))

    def test_scheduler_translation_is_explicit(self):
        self.assertEqual("EulerAncestralDiscreteScheduler", MODEL_CARD_CONFIGURATION["scheduler"])
        self.assertEqual("euler_ancestral", CALIBRATION_MATRIX[1]["sampler_name"])
        self.assertEqual("normal", CALIBRATION_MATRIX[1]["scheduler"])

    def test_seed_and_confirmation_contract(self):
        self.assertEqual(62701, SEED)
        self.assertEqual((62711, 62712, 62713), CONFIRMATION_SEEDS)

    def test_confirmation_is_conditional_and_qualification_is_fail_closed(self):
        self.assertEqual("SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS", qualification_status(selected_id=None, confirmation_pass=False, p2_hardware_gap=False))
        self.assertEqual("SDXL_OPENPOSE_P_LANE_QUALIFIED_768", qualification_status(selected_id="P1", confirmation_pass=True, p2_hardware_gap=True))
        self.assertEqual("SDXL_OPENPOSE_P_LANE_QUALIFIED", qualification_status(selected_id="P2", confirmation_pass=True, p2_hardware_gap=False))

    def test_oom_detection_is_explicit_for_retry_policy(self):
        self.assertTrue(is_oom_error("CUDA out of memory while allocating VRAM"))
        self.assertTrue(is_oom_error(MemoryError("allocator exhausted")))
        self.assertFalse(is_oom_error("workflow validation failed"))

    def test_active_state_keeps_non_p_lanes_blocked(self):
        state = load("docs/evidence/current-state.json")
        self.assertEqual("0.6.2", state["version"])
        self.assertEqual("SDXL_OPENPOSE_MODEL_CARD_CALIBRATION", state["phase"])
        self.assertFalse(state["walk_authorized"])
        self.assertFalse(state["generation_provider_change_authorized"])
        self.assertEqual("SDXL_OPENPOSE_CONTROL_GAP", state["historical_smoke_status"])


if __name__ == "__main__":
    unittest.main()
