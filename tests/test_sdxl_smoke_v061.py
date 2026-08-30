"""Regression coverage for the v0.6.1 SDXL smoke-evidence hard gates."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "validation"))

import run_sdxl_provider_qualification as provider
from ugas.identity_hard_gates import analyze_foreground_components, evaluate_identity_hard_gates
from ugas.sdxl_smoke_evidence import validate_execution_evidence_v061


class _FakeComfy:
    base_url = "http://127.0.0.1:8188"

    def upload_image(self, _path: Path) -> dict[str, str]:
        return {"name": "fixture.png"}

    def node_info(self) -> dict:
        return {}

    def list_models(self, _folder: str) -> list[str]:
        return []


def _rgba_fixture(path: Path, *, second_body: bool = False, sword: bool = False) -> Path:
    image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((28, 12, 58, 106), fill=(30, 80, 150, 255))
    if second_body:
        draw.rectangle((76, 14, 106, 108), fill=(30, 80, 150, 255))
    if sword:
        draw.rectangle((63, 42, 66, 76), fill=(210, 210, 220, 255))
    image.save(path)
    return path


class SdxlSmokeV061Tests(unittest.TestCase):
    def test_identity_hard_gates_are_fail_closed(self):
        descriptor = {
            "identity_descriptor_score": 0.99,
            "threshold": 0.70,
            "weapon_present": True,
            "components": {"head_face": 0.1, "armor_palette_material": 0.1, "black_cloth": 0.1, "body_proportions": 0.1},
            "failure_reasons": [],
        }
        result = evaluate_identity_hard_gates(descriptor, {"multiple_subjects_detected": False, "single_subject_pass": True})
        self.assertFalse(result["identity_pass"])
        self.assertIn("head_face_drift", result["failure_reasons"])
        self.assertIn("armor_palette_drift", result["failure_reasons"])
        self.assertIn("black_cloth_drift", result["failure_reasons"])
        self.assertIn("body_proportion_drift", result["failure_reasons"])

    def test_single_subject_connected_components(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            one = analyze_foreground_components(_rgba_fixture(root / "one.png", sword=True))
            two = analyze_foreground_components(_rgba_fixture(root / "two.png", second_body=True))
            self.assertTrue(one["single_subject_pass"])
            self.assertEqual(1, one["large_foreground_components"])
            self.assertEqual(1, len(one["accessory_or_weapon_components"]))
            self.assertTrue(two["multiple_subjects_detected"])
            self.assertGreaterEqual(two["large_foreground_components"], 2)
            self.assertIn("MULTIPLE_BODY_SUBJECTS", two["classification"])

    def test_historical_smoke_i_fixture_fails_single_subject(self):
        path = ROOT / "docs/evidence/sdxl-qualification/outputs/smoke-i-seed-60701.png"
        self.assertTrue(path.is_file())
        result = analyze_foreground_components(path)
        self.assertTrue(result["multiple_subjects_detected"])
        self.assertGreaterEqual(result["large_foreground_components"], 2)

    def test_execution_validator_requires_all_completed_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_paths = []
            records = []
            for lane in ("P", "I", "PI"):
                raw = root / f"{lane}.png"
                raw.write_bytes(f"{lane}-raw".encode())
                raw_paths.append(raw)
                raw_hash = hashlib.sha256(raw.read_bytes()).hexdigest()
                records.append({"lane": lane, "seed": 61701, "generation": {"completed": True, "prompt_id": provider.PROMPT_ID, "history_key_matches_prompt_id": True, "target_existed_before_submission": False, "fresh_binding": True, "previous_frame_chaining": False, "raw_output_path": raw.name, "raw_output_sha256": raw_hash, "raw_output_hash_matches_comfy": True}})
            evidence = {"schema_version": "0.6.1", "attempted_record_count": 3, "generation_completed_count": 3, "completed_execution_count": 3, "records": records, "all_prompt_ids_present": True, "all_history_bindings_exact": True, "all_raw_outputs_hash_bound": True, "all_targets_fresh": True, "previous_frame_chaining": False, "weights_in_git": False, "custom_node_source_vendored": False}
            self.assertEqual("SDXL_V061_EXECUTION_EVIDENCE_PASSED", validate_execution_evidence_v061(evidence, root)["status"])
            evidence["generation_completed_count"] = 2
            self.assertEqual("SDXL_V061_EXECUTION_EVIDENCE_FAILED", validate_execution_evidence_v061(evidence, root)["status"])

    def test_postprocess_exception_preserves_generation_evidence(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            root = Path(directory)
            permanent = root / "permanent"
            output_root = root / "output"
            job_dir = root / "job"
            job_dir.mkdir()
            raw = job_dir / "P.png"
            Image.new("RGBA", (512, 512), (40, 80, 150, 255)).save(raw)
            raw_hash = hashlib.sha256(raw.read_bytes()).hexdigest()
            execution = {"prompt_id": provider.PROMPT_ID, "history_record_key": provider.PROMPT_ID, "history_key_matches_prompt_id": True, "fresh_binding": True, "target_existed_before_submission": False, "seed_was_used_before": False, "outputs": [{"data_sha256": raw_hash}], "runtime_ms": 1}
            fake_result = {"job": {"execution_evidence": execution}}

            def fake_job(*_args, **kwargs):
                return fake_result, [{"path": str(raw)}]

            def fake_job_dir(*_args, **_kwargs):
                return job_dir

            with patch.object(provider, "PERMANENT_ROOT", permanent), patch.object(provider, "RAW_ROOT", permanent / "raw"), patch.object(provider, "OUTPUT_ROOT", output_root), patch.object(provider, "_unique_job_dir", fake_job_dir), patch.object(provider, "_run_job", fake_job), patch.object(provider, "validate_api_workflow", return_value={"live_valid": True}), patch.object(provider, "_raw_pose_qa", return_value={"absolute_pose_pass": True, "status": "RAW_POSE_PASS"}), patch.object(provider, "background_remove", side_effect=RuntimeError("BiRefNet failure")):
                result = provider._run_one(_FakeComfy(), lane="P", seed=61701, anchor=ROOT / "docs/evidence/reference-edit-selected-transparent.png", guide=ROOT / "docs/evidence/openpose-guide-v3-control-example.png", guide_value={}, guide_points={}, thresholds={"absolute_pose": {}}, stage="test-postprocess-preservation")
            self.assertTrue(result["generation"]["completed"])
            self.assertTrue((permanent / "raw" / "test-postprocess-preservation.png").is_file())
            self.assertEqual(raw_hash, result["generation"]["raw_output_sha256"])
            self.assertEqual("POSTPROCESS_FAILED", result["postprocess"]["status"])
            self.assertIn("BiRefNet failure", result["postprocess"]["error"])

    def test_v061_smoke_scope_and_seed(self):
        self.assertEqual(61701, provider.SMOKE_SEED)
        self.assertEqual((), provider.PAIRED_SEEDS)
        self.assertIsNone(provider.BENCHMARK_SEED)
        self.assertEqual((), provider.CONFIRMATION_SEEDS)
        self.assertEqual(("P", "I", "PI"), tuple(provider.WORKFLOWS))

    def test_v060_history_and_boundaries_preserved(self):
        state = json.loads((ROOT / "docs/evidence/current-state-v0.6.0.json").read_text(encoding="utf-8"))
        self.assertEqual("0.6.0", state["version"])
        self.assertEqual("SDXL_OPENPOSE_CONTROL_GAP", state["current_gate"])
        self.assertEqual("REVIEW_ARCHIVE_VERIFIED", state["previous_review_snapshot_status"])
        self.assertEqual("a0f451a5113cf9becb0847b92884cb10cbdec0ef", json.loads((ROOT / "docs/evidence/custom-node-audit-ipadapter-plus.json").read_text(encoding="utf-8"))["commit"])

    def test_no_weights_or_vendored_source(self):
        tracked = [path.as_posix().casefold() for path in ROOT.rglob("*") if path.is_file()]
        self.assertFalse(any(path.endswith((".safetensors", ".ckpt", ".gguf", ".onnx")) for path in tracked))
        self.assertFalse((ROOT / "providers/custom-nodes/ComfyUI_IPAdapter_plus").exists())


if __name__ == "__main__":
    unittest.main()
