"""v0.4.2 contract, gate, immutable revision and provenance tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))

from ugas.constants import UGAS_VERSION
from ugas.generation import GenerationError, sprite_pilot
from ugas.image_utils import inspect_png
from ugas.master_assets import (
    MasterAssetError,
    approve_visual,
    candidate_metrics,
    compile_generation_prompt,
    compile_reference_edit_instruction,
    reference_edit_structural_qa,
)
from ugas.model_registry import ModelRegistryError, load_model, validate_model_workflow_compatibility
from ugas.qa import validate_output
from ugas.workflow_registry import load_workflow


class ContractTests(unittest.TestCase):
    def test_version_and_lane_metadata(self):
        self.assertEqual("0.19.0", UGAS_VERSION)
        models = json.loads((ROOT / "providers/models/registry.json").read_text(encoding="utf-8"))["models"]
        lanes = {item["variant"]: item for item in models if item["family"] == "flux2-klein-4b"}
        self.assertEqual((4, 1.0), (lanes["distilled"]["recommended_steps"], lanes["distilled"]["recommended_guidance"]))
        self.assertEqual((50, 4.0), (lanes["base"]["recommended_steps"], lanes["base"]["recommended_guidance"]))

    def test_workflows_match_their_lane(self):
        for workflow_id in ("flux2-klein-4b-distilled-text-to-image", "flux2-klein-base-4b-quality-text-to-image", "flux2-klein-4b-distilled-image-edit", "flux2-klein-base-4b-quality-image-edit"):
            workflow = load_workflow(ROOT, workflow_id)
            model = load_model(ROOT, workflow["required_models"][0])
            self.assertTrue(validate_model_workflow_compatibility(model, workflow)["compatible"])

    def test_distilled_has_fast_semantics(self):
        model = load_model(ROOT, "flux2-klein-4b-distilled-nvfp4")
        self.assertTrue(model["guidance_distilled"] and model["step_distilled"])
        self.assertEqual("fast", model["quality_tier"])

    def test_base_has_quality_semantics(self):
        model = load_model(ROOT, "flux2-klein-4b-base-nvfp4")
        self.assertFalse(model["guidance_distilled"] or model["step_distilled"])
        self.assertEqual("quality", model["quality_tier"])

    def test_base_with_distilled_parameters_is_rejected(self):
        model = load_model(ROOT, "flux2-klein-4b-base-nvfp4")
        workflow = load_workflow(ROOT, "flux2-klein-base-4b-quality-text-to-image")
        workflow["parameters"]["steps"] = 4
        workflow["parameters"]["guidance"] = 1.0
        with self.assertRaisesRegex(ModelRegistryError, "incompatible"):
            validate_model_workflow_compatibility(model, workflow)

    def test_generation_prompt_contains_visual_language_not_machine_spec(self):
        spec = {"positive_prompt": "stylized fantasy human warrior with blue steel armor", "visual_style": "clear readable cohesive", "orientation": "front-facing three-quarter"}
        prompt = compile_generation_prompt(spec)
        self.assertIn("entire body visible from head to feet", prompt)
        self.assertIn("weapon held beside the body", prompt)
        self.assertNotIn("canvas:", prompt)
        self.assertNotIn("occupancy target", prompt)
        self.assertNotIn("game profile:", prompt)

    def test_reference_instruction_is_separate_and_hashable(self):
        instruction = compile_reference_edit_instruction("change dark steel armor to blue steel")
        self.assertIn("same character identity", instruction)
        self.assertIn("exact pose", instruction)
        self.assertIn("Do not redesign", instruction)


class GateTests(unittest.TestCase):
    def _rgb_subject(self, directory: Path, *, touching_edge: bool = False) -> Path:
        image = Image.new("RGB", (64, 64), (230, 230, 230))
        start = 0 if touching_edge else 12
        for y in range(start, 52):
            for x in range(start, 48):
                image.putpixel((x, y), (35, 80, 150))
        path = directory / ("edge.png" if touching_edge else "good.png")
        image.save(path)
        return path

    def test_edge_clipping_is_hard_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            metrics = candidate_metrics(self._rgb_subject(Path(directory), touching_edge=True), width=64, height=64)
            self.assertFalse(metrics["eligible"])
            self.assertIn("edge_clipping", metrics["hard_gate_failures"])

    def test_duplicate_is_hard_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            metrics = candidate_metrics(self._rgb_subject(Path(directory)), width=64, height=64, duplicate=True)
            self.assertFalse(metrics["eligible"])
            self.assertIn("not_duplicate", metrics["hard_gate_failures"])

    def test_out_of_range_occupancy_is_hard_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tiny.png"; image = Image.new("RGB", (64, 64), (230, 230, 230)); image.putpixel((32, 32), (0, 0, 0)); image.save(path)
            metrics = candidate_metrics(path, width=64, height=64)
            self.assertFalse(metrics["eligible"]); self.assertIn("occupancy", metrics["hard_gate_failures"])

    def test_no_candidate_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "blank.png"
            Image.new("RGB", (64, 64), (230, 230, 230)).save(path)
            metrics = candidate_metrics(path, width=64, height=64)
            self.assertFalse(metrics["eligible"])
            self.assertIn("edge_clipping", metrics["hard_gate_failures"])

    def test_alpha_stats_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rgba.png"
            image = Image.new("RGBA", (32, 32), (10, 20, 30, 0))
            for y in range(8, 24):
                for x in range(8, 24): image.putpixel((x, y), (10, 20, 30, 255))
            image.putpixel((16, 16), (10, 20, 30, 100)); image.save(path)
            info = inspect_png(path)
            self.assertGreater(info["alpha_zero_fraction"], 0)
            self.assertGreater(info["alpha_opaque_fraction"], 0)
            self.assertGreater(info["alpha_partial_fraction"], 0)
            self.assertIsNotNone(info["alpha_bbox"])
            self.assertFalse(info["border_contact"])
            self.assertEqual("TECHNICAL_VALID", validate_output(path, requires_transparency=True)["status"])

    def test_checkerboard_and_structural_qa(self):
        from ugas.master_assets import checkerboard_preview
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "source.png"; output = root / "output.png"; checker = root / "checker.png"
            image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            for y in range(10, 54):
                for x in range(18, 46): image.putpixel((x, y), (20, 80, 150, 255))
            image.save(source); changed = image.copy(); changed.putpixel((30, 30), (240, 40, 40, 255)); changed.save(output)
            checkerboard_preview(source, checker)
            result = reference_edit_structural_qa(source, output)
            self.assertTrue(checker.is_file()); self.assertEqual("REFERENCE_EDIT_QA_PASSED", result["status"]); self.assertFalse(result["metrics"]["pixel_identical"])

    def test_structural_qa_rejects_pixel_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "same.png"; image = Image.new("RGBA", (32, 32), (0, 0, 0, 0)); image.putpixel((16, 16), (1, 2, 3, 255)); image.save(path)
            result = reference_edit_structural_qa(path, path)
            self.assertEqual("REFERENCE_EDIT_QA_FAILED", result["status"]); self.assertFalse(result["checks"]["not_pixel_identical"])

    def test_approval_is_invalidated_by_a_new_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); asset_dir = root / "tmp" / "asset-test"; asset_dir.mkdir(parents=True); first = asset_dir / "first.png"; second = asset_dir / "second.png"
            Image.new("RGBA", (32, 32), (0, 0, 0, 0)).save(first); Image.new("RGBA", (32, 32), (0, 0, 0, 0)).save(second)
            base = {"schema_version": "0.4.1", "asset_id": "asset-test", "requires_transparency": True, "revisions": []}; rev1 = {"revision_id": "r1", "output_path": str(first), "output_sha256": inspect_png(first)["sha256"], "technical_status": "TECHNICAL_VALID", "transparency_status": "TRANSPARENCY_VALID", "state": "VISUALLY_APPROVED", "visual_approval": {"status": "approved", "revision_id": "r1", "output_sha256": inspect_png(first)["sha256"]}, "production_ready": True}; rev2 = {**rev1, "revision_id": "r2", "output_path": str(second), "output_sha256": inspect_png(second)["sha256"], "visual_approval": {"status": "pending"}, "state": "VISUAL_REVIEW_REQUIRED", "production_ready": False}; base["revisions"] = [rev1, rev2]; base["current_revision"] = rev2; path = asset_dir / "asset.json"; path.write_text(json.dumps(base), encoding="utf-8")
            self.assertFalse(__import__("ugas.master_assets", fromlist=["asset_status"]).asset_status(root, str(path))["production_ready"])

    def test_visual_approval_requires_transparency_and_current_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); asset_dir = root / "tmp" / "asset-test"; asset_dir.mkdir(parents=True); output = asset_dir / "master.png"
            image = Image.new("RGBA", (32, 32), (0, 0, 0, 0)); image.putpixel((16, 16), (255, 0, 0, 255)); image.save(output)
            revision = {"schema_version": "0.4.1", "revision_id": "revision-1", "asset_id": "asset-test", "revision_number": 1, "derived_from": None, "output_path": str(output), "output_sha256": inspect_png(output)["sha256"], "technical_status": "TECHNICAL_VALID", "transparency_status": "TRANSPARENCY_VALID", "state": "VISUAL_REVIEW_REQUIRED", "visual_approval": {"status": "pending"}, "production_ready": False}
            asset = {"schema_version": "0.4.1", "asset_id": "asset-test", "requires_transparency": True, "current_revision": revision, "revisions": [revision]}; asset_path = asset_dir / "asset.json"; asset_path.write_text(json.dumps(asset), encoding="utf-8")
            result = approve_visual(root, str(asset_path))
            self.assertTrue(result["production_ready"])
            asset["current_revision"]["output_sha256"] = "tampered"; asset_path.write_text(json.dumps(asset), encoding="utf-8")
            self.assertFalse(__import__("ugas.master_assets", fromlist=["asset_status"]).asset_status(root, str(asset_path))["production_ready"])

    def test_sprite_grid_stays_out_of_scope(self):
        with self.assertRaisesRegex(GenerationError, "v0.4.3"):
            sprite_pilot(ROOT, endpoint="http://127.0.0.1:1", prompt="grid", columns=2, rows=1)


if __name__ == "__main__":
    unittest.main()
