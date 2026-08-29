"""Deterministic v0.4.2 integrity, margin, matte and review-manifest tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))

from ugas.generation import GenerationError, _create_revision
from ugas.image_utils import inspect_png, rgb_preservation, sha256
from ugas.master_assets import candidate_metrics, reference_edit_structural_qa, verify_asset_integrity
from ugas.model_registry import ModelRegistryError, load_model, validate_model_workflow_compatibility
from ugas.review import validate_review_visual_manifest
from ugas.workflow_registry import load_workflow
from ugas.qa import validate_output


def _rgba_subject(path: Path, *, color=(40, 90, 180, 255), alpha: int = 255, left: int = 12, top: int = 8, right: int = 52, bottom: int = 56) -> Path:
    image = Image.new("RGBA", (64, 64), (225, 225, 225, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((left, top, right - 1, bottom - 1), fill=(*color[:3], alpha))
    image.save(path)
    return path


def _write_asset(asset_path: Path, revisions: list[dict], current: dict | None = None, *, requires_transparency: bool = True) -> None:
    value = {
        "schema_version": "0.4.2",
        "asset_id": "asset-integrity-test",
        "requires_transparency": requires_transparency,
        "revisions": revisions,
        "current_revision": current or revisions[-1],
    }
    asset_path.write_text(json.dumps(value, indent=2), encoding="utf-8")


class RevisionStorageTests(unittest.TestCase):
    def test_revision_output_paths_are_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            asset_dir = Path(directory) / "asset"; asset_dir.mkdir(); source = _rgba_subject(asset_dir / "source.png")
            qa = validate_output(source)
            first = _create_revision(asset_dir, "asset-test", 1, source, qa)
            second_source = _rgba_subject(asset_dir / "source-2.png", color=(20, 140, 80, 255))
            second = _create_revision(asset_dir, "asset-test", 2, second_source, validate_output(second_source), derived_from={"revision_id": first["revision_id"], "output_sha256": first["output_sha256"]})
            self.assertNotEqual(first["revision_id"], second["revision_id"])
            self.assertNotEqual(first["output_path"], second["output_path"])
            self.assertTrue(Path(first["output_path"]).is_file()); self.assertTrue(Path(second["metadata_path"]).is_file())

    def test_later_background_removal_does_not_mutate_previous_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            asset_dir = Path(directory) / "asset"; asset_dir.mkdir(); source = _rgba_subject(asset_dir / "source.png")
            first = _create_revision(asset_dir, "asset-test", 1, source, validate_output(source))
            original_bytes = Path(first["output_path"]).read_bytes(); original_hash = first["output_sha256"]
            later = _rgba_subject(asset_dir / "later.png", color=(180, 30, 30, 255))
            _create_revision(asset_dir, "asset-test", 2, later, validate_output(later), derived_from={"revision_id": first["revision_id"], "output_sha256": original_hash})
            self.assertEqual(original_bytes, Path(first["output_path"]).read_bytes()); self.assertEqual(original_hash, sha256(Path(first["output_path"])))

    def test_revision_integrity_detects_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = _rgba_subject(root / "output.png"); revision = {"schema_version": "0.4.2", "revision_id": "r1", "asset_id": "asset-integrity-test", "revision_number": 1, "derived_from": None, "output_path": str(output), "output_sha256": "wrong", "technical_status": "TECHNICAL_VALID", "transparency_status": "not-required", "state": "VISUAL_REVIEW_REQUIRED", "visual_approval": {"status": "pending"}, "production_ready": False}; path = root / "asset.json"; _write_asset(path, [revision], revision, requires_transparency=False); result = verify_asset_integrity(root, str(path)); self.assertEqual("REVISION_INTEGRITY_FAILED", result["status"]); self.assertFalse(result["checks"]["output_hashes_match"])

    def test_revision_integrity_detects_shared_output_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = _rgba_subject(root / "output.png"); digest = sha256(output); base = {"schema_version": "0.4.2", "asset_id": "asset-integrity-test", "revision_number": 1, "derived_from": None, "output_path": str(output), "output_sha256": digest, "technical_status": "TECHNICAL_VALID", "transparency_status": "not-required", "state": "VISUAL_REVIEW_REQUIRED", "visual_approval": {"status": "pending"}, "production_ready": False}; first = {**base, "revision_id": "r1"}; second = {**base, "revision_id": "r2", "revision_number": 2, "derived_from": {"revision_id": "r1", "output_sha256": digest}}; path = root / "asset.json"; _write_asset(path, [first, second], second, requires_transparency=False); result = verify_asset_integrity(root, str(path)); self.assertEqual("REVISION_INTEGRITY_FAILED", result["status"]); self.assertFalse(result["checks"]["unique_output_paths"])


class RevisionQATests(unittest.TestCase):
    def test_reference_qa_rejects_same_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _rgba_subject(Path(directory) / "same.png"); result = reference_edit_structural_qa(path, path, source_revision_id="r2", output_revision_id="r4"); self.assertEqual("REFERENCE_EDIT_QA_FAILED", result["status"]); self.assertFalse(result["checks"]["distinct_paths"])

    def test_safe_margin_is_hard_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "margin.png"; image = Image.new("RGB", (64, 64), (230, 230, 230)); ImageDraw.Draw(image).rectangle((5, 20, 48, 58), fill=(30, 80, 150)); image.save(path); result = candidate_metrics(path, width=64, height=64, margins={"left": 8, "top": 8, "right": 8, "bottom": 8}); self.assertFalse(result["eligible"]); self.assertFalse(result["safe_margin_ok"]); self.assertIn("left", result["safe_margin_violations"]); self.assertIn("safe_margin", result["hard_gate_failures"])

    def test_safe_margin_passes_when_bbox_respects_spec(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "margin.png"; image = Image.new("RGB", (64, 64), (230, 230, 230)); ImageDraw.Draw(image).rectangle((12, 12, 48, 52), fill=(30, 80, 150)); image.save(path); result = candidate_metrics(path, width=64, height=64, margins={"left": 8, "top": 8, "right": 8, "bottom": 8}); self.assertTrue(result["eligible"]); self.assertTrue(result["safe_margin_ok"]); self.assertEqual([], result["safe_margin_violations"])

    def test_rgb_preservation_passes_for_alpha_only_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = _rgba_subject(root / "source.png", color=(40, 90, 180, 255)); result = Image.open(source).copy(); result.putalpha(254); result.save(root / "result.png"); qa = rgb_preservation(source, root / "result.png"); self.assertTrue(qa["passed"]); self.assertEqual(0.0, qa["mae_total"])

    def test_rgb_preservation_fails_for_recolored_foreground(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = _rgba_subject(root / "source.png", color=(40, 90, 180, 255)); result = Image.open(source).copy(); pixels = result.load();
            for y in range(8, 56):
                for x in range(12, 52): pixels[x, y] = (220, 20, 20, 255)
            result.save(root / "result.png"); qa = rgb_preservation(source, root / "result.png"); self.assertFalse(qa["passed"]); self.assertGreater(qa["mae_total"], 2.0)

    def test_near_opaque_metric_treats_alpha_254_as_near_opaque(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _rgba_subject(Path(directory) / "near.png", alpha=254); info = inspect_png(path); self.assertEqual(250, info["near_opaque_threshold"]); self.assertEqual(1.0, info["near_opaque_foreground_fraction"]); self.assertEqual("TECHNICAL_VALID", validate_output(path, requires_transparency=True)["status"])


class RevisionStateTests(unittest.TestCase):
    def _approved_asset(self, root: Path) -> tuple[Path, dict, dict]:
        first_path = _rgba_subject(root / "r1.png", color=(40, 90, 180, 255)); second_path = _rgba_subject(root / "r2.png", color=(20, 140, 80, 255)); first_hash = sha256(first_path); second_hash = sha256(second_path); first = {"schema_version": "0.4.2", "revision_id": "r1", "asset_id": "asset-integrity-test", "revision_number": 1, "derived_from": None, "output_path": str(first_path), "output_sha256": first_hash, "technical_status": "TECHNICAL_VALID", "transparency_status": "TRANSPARENCY_VALID", "state": "VISUALLY_APPROVED", "visual_approval": {"status": "approved", "revision_id": "r1", "output_sha256": first_hash}, "production_ready": True}; second = {"schema_version": "0.4.2", "revision_id": "r2", "asset_id": "asset-integrity-test", "revision_number": 2, "derived_from": {"revision_id": "r1", "output_sha256": first_hash}, "output_path": str(second_path), "output_sha256": second_hash, "technical_status": "TECHNICAL_VALID", "transparency_status": "TRANSPARENCY_VALID", "state": "VISUAL_REVIEW_REQUIRED", "visual_approval": {"status": "pending"}, "production_ready": False}; path = root / "asset.json"; _write_asset(path, [first, second], second); return path, first, second

    def test_visual_approval_invalidated_after_new_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _, second = self._approved_asset(Path(directory)); result = verify_asset_integrity(Path(directory), str(path)); self.assertEqual("REVISION_INTEGRITY_PASSED", result["status"]); self.assertFalse(result["production_ready_recomputed"]); self.assertFalse(second["production_ready"])

    def test_production_ready_requires_integrity_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path, _, second = self._approved_asset(root); second["visual_approval"] = {"status": "approved", "revision_id": "r2", "output_sha256": second["output_sha256"]}; second["production_ready"] = True; _write_asset(path, [json.loads(json.dumps({**second, "revision_number": 1, "revision_id": "r1", "derived_from": None, "output_path": str(root / "r1.png"), "output_sha256": sha256(root / "r1.png"), "visual_approval": {"status": "approved", "revision_id": "r1", "output_sha256": sha256(root / "r1.png")}, "production_ready": True})), second], second); Path(second["output_path"]).write_bytes(b"tampered"); result = verify_asset_integrity(root, str(path)); self.assertEqual("REVISION_INTEGRITY_FAILED", result["status"]); self.assertFalse(result["production_ready_recomputed"])


class ReviewManifestTests(unittest.TestCase):
    def test_review_manifest_rejects_duplicate_logical_visual_role(self):
        names = sorted({"quality-benchmark-contact-sheet.png", "quality-benchmark.json", "master-selected-before-bg.png", "master-selected-transparent.png", "master-selected-checkerboard.png", "reference-edit-before-after.png", "reference-edit-transparent.png", "reference-edit-checkerboard.png", "revision-chain.json", "reference-edit-qa.json", "transparency-qa-master.json", "transparency-qa-reference-edit.json"})
        items = [{"archive_name": name, "source_path": "same.png", "revision_id": "r2", "sha256": "same"} for name in names]; result = validate_review_visual_manifest({"images": items}); self.assertEqual("REVIEW_VISUAL_MANIFEST_FAILED", result["status"]); self.assertTrue(any("source path" in failure for failure in result["failures"]))


class ExistingScopeRegressionTests(unittest.TestCase):
    def test_base_distilled_mismatch_tests_remain_green(self):
        base = load_model(ROOT, "flux2-klein-4b-base-nvfp4"); workflow = load_workflow(ROOT, "flux2-klein-base-4b-quality-text-to-image"); workflow["parameters"]["steps"] = 4; workflow["parameters"]["guidance"] = 1.0
        with self.assertRaises(ModelRegistryError): validate_model_workflow_compatibility(base, workflow)

    def test_sprite_grid_scope_block_remains_green(self):
        with self.assertRaisesRegex(GenerationError, "v0.4.3"): __import__("ugas.generation", fromlist=["sprite_pilot"]).sprite_pilot(ROOT, endpoint="http://127.0.0.1:1", prompt="grid", columns=2, rows=1)


if __name__ == "__main__":
    unittest.main()
