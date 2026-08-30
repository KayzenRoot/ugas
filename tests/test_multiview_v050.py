"""Historical v0.5.0 multi-reference, deterministic guide and walk contract tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ugas.identity import ANCHOR_ASSET_ID, ANCHOR_REVISION_ID, ANCHOR_SHA256, validate_identity_manifest
from ugas.image_utils import sha256
from ugas.multiview import normalize_frame
from ugas.pose_guides import WALK_NAMES, ensure_pose_guides, validate_pose_guide, walk_guide
from ugas.review import validate_review_visual_manifest
from ugas.workflow_registry import bind_workflow, load_workflow


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_V050_VERSION = "0.5.0"


class MultiViewV050Tests(unittest.TestCase):
    def test_identity_manifest_binds_exact_r4(self):
        value = json.loads((ROOT / "docs/evidence/identity-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(json.loads((ROOT / "docs/evidence/identity-manifest.json").read_text(encoding="utf-8"))["schema_version"], "0.5.1")
        self.assertEqual(value["asset_id"], ANCHOR_ASSET_ID)
        self.assertEqual(value["canonical_revision"]["revision_id"], ANCHOR_REVISION_ID)
        self.assertEqual(value["canonical_revision"]["sha256"], ANCHOR_SHA256)
        self.assertEqual(validate_identity_manifest(value, ROOT)["status"], "IDENTITY_MANIFEST_VALID")

    def test_pose_guides_are_explicit_and_unique(self):
        result = ensure_pose_guides(ROOT)
        self.assertEqual(result["status"], "POSE_GUIDES_VALID")
        self.assertEqual(len(result["walk_frames"]), 8)
        guides = [json.loads((ROOT / path).read_text(encoding="utf-8")) for path in result["walk_frames"]]
        self.assertEqual([item["frame_name"] for item in guides], list(WALK_NAMES))
        self.assertEqual(len({json.dumps(item["keypoints"], sort_keys=True) for item in guides}), 8)
        self.assertTrue(all(validate_pose_guide(item)["status"] == "POSE_GUIDE_VALID" for item in guides))

    def test_multiref_workflow_has_native_reference_chain(self):
        record = load_workflow(ROOT, "flux2-klein-base-4b-quality-multi-reference-edit")
        refs = [node for node in record["api"].values() if node.get("class_type") == "ReferenceLatent"]
        self.assertEqual(len(refs), 4)
        self.assertEqual(record["parameters"]["reference_order"], ["identity-anchor", "pose-view-guide"])
        bound = bind_workflow(record["api"], prompt="p", seed=1, image_filenames=["identity.png", "guide.png"])
        self.assertEqual(bound["6"]["inputs"]["image"], "identity.png")
        self.assertEqual(bound["8"]["inputs"]["image"], "guide.png")

    def test_multiref_gate_does_not_authorize_walk(self):
        qualification = json.loads((ROOT / "docs/evidence/multiref-qualification.json").read_text(encoding="utf-8"))
        self.assertEqual(qualification["status"], "MULTI_REFERENCE_QUALIFIED")
        self.assertEqual(qualification["conditioning_contract"]["previous_frame_chaining"], False)
        self.assertIn("heuristic_requires_human_visual_review", qualification["comparison"])

    def test_walk_contract_forbids_previous_frame(self):
        qa = json.loads((ROOT / "docs/evidence/walk-front-8-animation-qa.json").read_text(encoding="utf-8"))
        self.assertTrue(qa["temporal"]["no_previous_frame_chaining"])
        self.assertTrue(all(item["selected"]["previous_frame_input"] is None for item in qa["frames"]))

    def test_candidate_and_retry_bounds_are_bounded(self):
        anchors = json.loads((ROOT / "docs/evidence/directional-anchor-set.json").read_text(encoding="utf-8"))
        self.assertEqual(anchors["candidate_count_per_generated_direction"], 2)
        walk = json.loads((ROOT / "docs/evidence/walk-front-8-animation-qa.json").read_text(encoding="utf-8"))
        self.assertTrue(all(len(item["attempts"]) <= 2 for item in walk["frames"]))

    def test_normalization_keeps_pivot_and_no_stretch(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"; destination = Path(directory) / "normalized.png"
            image = Image.new("RGBA", (512, 512), (0, 0, 0, 0)); image.paste((20, 40, 180, 255), (200, 30, 300, 470)); image.save(source)
            result = normalize_frame(source, destination, frame_name="test", guide=walk_guide(0))
            self.assertEqual(result["scale"], 1.0); self.assertEqual(result["ground_baseline"], 478); self.assertEqual(sha256(destination), result["sha256"])

    def test_temporal_contract_requires_eight_unique_frames(self):
        qa = json.loads((ROOT / "docs/evidence/walk-front-8-animation-qa.json").read_text(encoding="utf-8"))
        temporal = qa["temporal"]
        self.assertEqual(temporal["frame_count"], 8); self.assertTrue(temporal["unique_sha256"]); self.assertEqual(temporal["status"], "TEMPORAL_QA_PASSED")

    def test_walk_pack_contract_is_exact(self):
        metadata = json.loads((ROOT / "docs/evidence/walk-front-8.json").read_text(encoding="utf-8"))
        self.assertEqual({metadata[key] for key in ("animation", "view", "frames", "fps", "frame_width", "frame_height")}, {"walk", "front", 8, 512})
        self.assertTrue(metadata["loop"]); self.assertEqual(len(metadata["frame_files"]), 8); self.assertEqual(len(metadata["frame_hashes"]), 8)
        self.assertTrue((ROOT / "docs/evidence/walk-front-8-spritesheet.png").is_file()); self.assertTrue((ROOT / "docs/evidence/walk-front-8-preview.gif").is_file())

    def test_v050_visual_manifest_is_hash_bound(self):
        value = json.loads((ROOT / "docs/evidence/review-visuals-v0.5.0.json").read_text(encoding="utf-8"))
        result = validate_review_visual_manifest(value, ROOT)
        self.assertEqual(result["status"], "REVIEW_VISUAL_MANIFEST_PASSED")
        self.assertEqual(result["required_count"], 12)


if __name__ == "__main__":
    unittest.main()
