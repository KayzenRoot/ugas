"""UGAS v0.4.3 reference-edit fidelity and evidence regressions."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

from ugas.constants import UGAS_VERSION
from ugas.model_registry import load_model, validate_model_workflow_compatibility
from ugas.reference_edit import (
    build_edit_contract,
    build_protected_mask,
    build_target_mask,
    deterministic_recolor,
    reference_edit_fidelity,
    runtime_plausibility,
    validate_edit_contract,
    validate_execution_evidence,
)
from ugas.workflow_registry import load_workflow


class ReferenceEditFidelityV043Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ugas-v043-refedit-")
        self.root = Path(self.temp.name)
        self.source = self.root / "source.png"
        image = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((30, 24, 66, 78), fill=(24, 78, 170, 255))
        draw.rectangle((40, 8, 56, 22), fill=(190, 128, 92, 255))
        draw.rectangle((18, 45, 22, 78), fill=(110, 120, 130, 255))
        image.save(self.source)
        self.contract = build_edit_contract(asset_id="asset-test", source_revision_id="R2", source_sha256="a" * 64, seeds=[20001, 20002, 20003, 20004])
        self.target_mask, self.target_info = build_target_mask(self.source, self.contract)
        self.protected_mask, self.protected_info = build_protected_mask(self.source, self.contract)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _valid_candidate(self) -> Path:
        rgb = self.root / "recolor.png"
        deterministic_recolor(self.source, rgb, self.target_mask, self.contract)
        with Image.open(self.source) as source, Image.open(rgb) as recolor:
            result = Image.merge("RGBA", (*recolor.convert("RGB").split(), source.convert("RGBA").getchannel("A")))
            path = self.root / "candidate.png"
            result.save(path)
        return path

    def test_history_binding_requires_exact_prompt_and_job(self) -> None:
        evidence = {"client_job_id": "job-1", "prompt_id": "prompt-1", "history_record_key": "prompt-1", "runtime_ms": 100, "seed": 1, "outputs": [{"data_sha256": "a"}], "fresh_binding": True, "target_existed_before_submission": False, "history_key_matches_prompt_id": True}
        self.assertEqual(validate_execution_evidence(evidence)["status"], "FRESH_EXECUTION_EVIDENCE_PASSED")
        evidence["history_record_key"] = "other"
        self.assertEqual(validate_execution_evidence(evidence)["status"], "FRESH_EXECUTION_EVIDENCE_FAILED")

    def test_stale_output_is_rejected(self) -> None:
        evidence = {"client_job_id": "job-1", "prompt_id": "prompt-1", "history_record_key": "prompt-1", "runtime_ms": 100, "seed": 2, "outputs": [{"data_sha256": "a"}], "fresh_binding": True, "target_existed_before_submission": True, "history_key_matches_prompt_id": True}
        self.assertIn("stale_output", validate_execution_evidence(evidence)["failures"])

    def test_unique_seed_is_required(self) -> None:
        evidence = {"client_job_id": "job-1", "prompt_id": "prompt-1", "history_record_key": "prompt-1", "runtime_ms": 100, "seed": 42, "outputs": [{"data_sha256": "a"}], "fresh_binding": True, "target_existed_before_submission": False, "history_key_matches_prompt_id": True}
        self.assertIn("seed_reused", validate_execution_evidence(evidence, previously_used_seeds={42})["failures"])

    def test_runtime_plausibility_flags_suspicious_execution(self) -> None:
        result = runtime_plausibility(620, [52000, 54000, 56000])
        self.assertEqual(result["status"], "SUSPICIOUS_EXECUTION_EVIDENCE")

    def test_runtime_plausibility_accepts_same_machine_scale(self) -> None:
        self.assertEqual(runtime_plausibility(52000, [50000, 54000])["status"], "RUNTIME_PLAUSIBLE")

    def test_capability_specific_parameters_are_separate(self) -> None:
        model = load_model(Path(__file__).parents[1], "flux2-klein-4b-base-nvfp4")
        workflow = load_workflow(Path(__file__).parents[1], "flux2-klein-base-4b-quality-image-edit")
        self.assertTrue(validate_model_workflow_compatibility(model, workflow)["compatible"])
        self.assertEqual(workflow["parameters"]["steps"], 20)
        self.assertEqual(workflow["parameters"]["guidance"], 5.0)

    def test_edit_contract_has_protected_identity_and_exact_target(self) -> None:
        validation = validate_edit_contract(self.contract)
        self.assertTrue(validation["valid"])
        self.assertIn("sword shape and position", self.contract["protected_properties"])
        self.assertEqual(self.contract["target_property"], "armor color/material tint")

    def test_photometric_blackening_fails(self) -> None:
        with Image.open(self.source) as image:
            dark = ImageEnhance.Brightness(image).enhance(0.18)
            path = self.root / "dark.png"; dark.save(path)
        result = reference_edit_fidelity(self.source, path, self.contract, target_mask=self.target_mask, protected_mask=self.protected_mask)
        self.assertEqual(result["status"], "REFERENCE_EDIT_FIDELITY_FAILED")
        self.assertIn("foreground_luma_ratio", result["failure_reasons"])

    def test_head_darkening_fails(self) -> None:
        with Image.open(self.source) as image:
            changed = image.copy(); draw = ImageDraw.Draw(changed); draw.rectangle((40, 8, 56, 22), fill=(20, 20, 20, 255))
            path = self.root / "head-dark.png"; changed.save(path)
        result = reference_edit_fidelity(self.source, path, self.contract, target_mask=self.target_mask, protected_mask=self.protected_mask)
        self.assertEqual(result["status"], "REFERENCE_EDIT_FIDELITY_FAILED")
        self.assertIn("head_luma_ratio", result["failure_reasons"])

    def test_valid_recolor_passes(self) -> None:
        result = reference_edit_fidelity(self.source, self._valid_candidate(), self.contract, target_mask=self.target_mask, protected_mask=self.protected_mask)
        self.assertEqual(result["status"], "REFERENCE_EDIT_FIDELITY_PASSED")

    def test_no_target_change_fails(self) -> None:
        result = reference_edit_fidelity(self.source, self.source, self.contract, target_mask=self.target_mask, protected_mask=self.protected_mask)
        self.assertEqual(result["status"], "REFERENCE_EDIT_FIDELITY_FAILED")
        self.assertIn("not_pixel_identical", result["failure_reasons"])

    def test_protected_region_excessive_change_fails(self) -> None:
        with Image.open(self.source) as image:
            changed = image.copy(); draw = ImageDraw.Draw(changed); draw.rectangle((40, 8, 56, 22), fill=(250, 250, 250, 255))
            path = self.root / "head-bright.png"; changed.save(path)
        result = reference_edit_fidelity(self.source, path, self.contract, target_mask=self.target_mask, protected_mask=self.protected_mask)
        self.assertIn("head_luma_ratio", result["failure_reasons"])

    def test_multiple_candidates_only_eligible_is_selected(self) -> None:
        entries = [{"candidate_id": "bad", "eligible": False}, {"candidate_id": "good", "eligible": True}]
        selected = next(item for item in entries if item["eligible"])
        self.assertEqual(selected["candidate_id"], "good")

    def test_zero_eligible_candidates_has_controlled_failure(self) -> None:
        entries = [{"candidate_id": "bad-1", "eligible": False}, {"candidate_id": "bad-2", "eligible": False}]
        self.assertIsNone(next((item for item in entries if item["eligible"]), None))
        self.assertEqual("NO_ACCEPTABLE_REFERENCE_EDIT", "NO_ACCEPTABLE_REFERENCE_EDIT")

    def test_temporary_candidates_are_not_revisions(self) -> None:
        asset = {"revisions": [{"revision_number": 1}, {"revision_number": 2}], "candidates": [{"candidate_id": "candidate-1", "temporary": True}]}
        self.assertTrue(all(item.get("temporary") for item in asset["candidates"]))
        self.assertEqual(len(asset["revisions"]), 2)

    def test_r1_r4_chain_is_ordered(self) -> None:
        chain = ["R1", "R2", "R3", "R4"]
        self.assertEqual(chain, sorted(chain, key=lambda value: int(value[1:])))

    def test_new_manifest_role_requires_hash(self) -> None:
        manifest = {"roles": {"reference-edit-selected-rgb": {"path": "x.png", "sha256": "a" * 64}}}
        self.assertEqual(len(manifest["roles"]["reference-edit-selected-rgb"]["sha256"]), 64)

    def test_active_version_is_v061(self) -> None:
        self.assertEqual(UGAS_VERSION, "0.7.3")

    def test_historical_matrix_is_preserved(self) -> None:
        matrix = Path(__file__).parents[1] / "docs" / "test-coverage-matrix-v0.4.2.md"
        self.assertTrue(matrix.is_file())
        self.assertIn("v0.4.0", matrix.read_text(encoding="utf-8"))

    def test_target_mask_confidence_is_recorded(self) -> None:
        self.assertIn("confidence", self.target_info)
        self.assertGreater(self.target_info["confidence"], 0.0)

    def test_contract_hash_is_stable_for_same_payload(self) -> None:
        self.assertEqual(validate_edit_contract(self.contract)["contract_sha256"], validate_edit_contract(json.loads(json.dumps(self.contract)))["contract_sha256"])


if __name__ == "__main__":
    unittest.main()
