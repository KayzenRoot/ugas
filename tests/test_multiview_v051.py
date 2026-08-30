"""v0.5.1 corrective tests for reproducibility, pose, identity and temporal QA."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw

from ugas import multiview
from ugas.multiview import _identity_descriptor, _pose_metrics, _select_best_candidate, _temporal_qa, generate_walk_pilot
from ugas.pose_guides import CHALLENGE_NAME, WALK_NAMES, ensure_pose_guides, guide_hash, walk_guide


ROOT = Path(__file__).resolve().parents[1]


def _image(path: Path, *, color: tuple[int, int, int, int] = (42, 86, 140, 255), x: int = 180, y: int = 60, width: int = 150, height: int = 400) -> Path:
    image = Image.new("RGBA", (512, 512), (0, 0, 0, 0)); ImageDraw.Draw(image).rectangle((x, y, x + width, y + height), fill=color); image.save(path, format="PNG", optimize=False); return path


class MultiViewV051Tests(unittest.TestCase):
    def test_pose_metric_uses_keypoints_segments_and_silhouette(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _image(Path(directory) / "wrong.png", x=20, y=20, width=170, height=450)
            metrics = _pose_metrics(path, multiview.challenge_guide())
            self.assertIn("guide_keypoint_hit_rate", metrics)
            self.assertIn("guide_segment_coverage", metrics)
            self.assertIn("guide_silhouette_distance", metrics)
            self.assertNotEqual(metrics["pose_score"], metrics["bbox_aspect_ratio_diagnostic"])

    def test_bbox_ratio_alone_cannot_qualify(self):
        guide = multiview.challenge_guide()
        with tempfile.TemporaryDirectory() as directory:
            path = _image(Path(directory) / "ratio.png", x=330, y=28, width=110, height=430)
            metrics = _pose_metrics(path, guide)
            self.assertLess(metrics["pose_score"], 0.70)

    def test_candidate_selection_uses_quality_before_seed(self):
        def candidate(seed: int, pose: float, identity: float) -> dict:
            return {"seed": seed, "eligible": True, "score": {"pose_pass": True, "identity_pass": True, "pose": {"pose_score": pose}, "identity": {"identity_descriptor_score": identity, "candidate_descriptor": {"body_proportions": {"bbox_height": 0.8}}}, "technical": {"safe_margin_ok": True}}}
        chosen = _select_best_candidate([candidate(1, .74, .95), candidate(2, .88, .80)])
        self.assertEqual(chosen["seed"], 2)

    def test_identity_descriptor_rejects_face_armor_weapon_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            anchor = _image(Path(directory) / "anchor.png", color=(42, 86, 140, 255), x=150, y=50, width=190, height=420)
            drift = _image(Path(directory) / "drift.png", color=(210, 30, 30, 255), x=80, y=12, width=300, height=470)
            result = _identity_descriptor(drift, anchor)
            self.assertFalse(result["weapon_present"])
            self.assertLess(result["identity_descriptor_score"], 0.65)
            self.assertTrue(result["failure_reasons"])

    def test_temporal_qa_rejects_nearly_static_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            frames = [_image(Path(directory) / f"frame-{index}.png", x=180 + index, y=60, width=150, height=400) for index in range(8)]
            scores = [{"pose": {"pose_score": .8, "lower_body_guide_coverage": .5}, "identity": {"identity_descriptor_score": .9}, "weapon_present": True} for _ in frames]
            result = _temporal_qa(frames, [walk_guide(index) for index in range(8)], scores)
            self.assertEqual(result["status"], "WALK_TEMPORAL_QA_FAILED")
            self.assertFalse(result["gates"]["lower_body_motion"])

    def test_temporal_qa_rejects_last_first_outlier(self):
        with tempfile.TemporaryDirectory() as directory:
            frames = [_image(Path(directory) / f"frame-{index}.png", x=170 + index * 3, y=60, width=150, height=400) for index in range(7)]
            frames.append(_image(Path(directory) / "frame-7.png", x=20, y=15, width=400, height=490))
            scores = [{"pose": {"pose_score": .8, "lower_body_guide_coverage": .2 + index * .1}, "identity": {"identity_descriptor_score": .9}, "weapon_present": True} for index in range(8)]
            result = _temporal_qa(frames, [walk_guide(index) for index in range(8)], scores)
            self.assertEqual(result["status"], "WALK_TEMPORAL_QA_FAILED")
            self.assertFalse(result["gates"]["loop_closure"])

    def test_half_cycle_mirror_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            frames = []
            for index in range(8):
                frames.append(_image(Path(directory) / f"frame-{index}.png", x=140 + (index % 4) * 8 if index < 4 else 512 - (140 + (index % 4) * 8) - 150, y=60, width=150, height=400))
            scores = [{"pose": {"pose_score": .8, "lower_body_guide_coverage": .2 + index * .1}, "identity": {"identity_descriptor_score": .9}, "weapon_present": True} for index in range(8)]
            result = _temporal_qa(frames, [walk_guide(index) for index in range(8)], scores)
            self.assertEqual(len(result["half_cycle_mirror"]), 4)
            self.assertIn("silhouette_iou_after_mirror", result["half_cycle_mirror"][0])

    def test_pose_guide_v2_is_filled_control_and_separate_review_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); ensure_pose_guides(root); challenge = json.loads((root / "pose-guides" / "challenges" / f"{CHALLENGE_NAME}.json").read_text(encoding="utf-8")); control = multiview.render_pose_guide(challenge, root / "control.png"); review = multiview.render_pose_guide(challenge, root / "review.png", review=True)
            self.assertEqual(control["renderer_version"], "2.0.0")
            self.assertNotEqual(control["sha256"], review["sha256"])
            with Image.open(root / "control.png") as image: self.assertEqual(image.getpixel((0, 0))[:3], (238, 239, 242))

    def test_normalization_uniformly_scales_tall_candidate_without_stretching(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "tall.png"; destination = Path(directory) / "normalized.png"
            _image(source, x=156, y=10, width=169, height=485)
            result = multiview.normalize_frame(source, destination, frame_name="tall", guide=multiview.challenge_guide())
            self.assertLess(result["scale"], 1.0)
            self.assertEqual(result["normalization_status"], "SCALED_UNIFORM_AND_TRANSLATED")
            self.assertGreaterEqual(result["alpha_bbox_scaled"][1] + result["translation"]["y"], 8)
            self.assertLessEqual(result["alpha_bbox_scaled"][3] + result["translation"]["y"], 504)

    def test_generate_walk_pilot_calls_real_reference_path_for_each_frame_in_fake_runtime(self):
        class FakeClient:
            def __init__(self, endpoint: str, timeout: float = 40.0): self.base_url = endpoint; self.counter = 0; self.submissions = []; self.payloads = {}
            def node_info(self, node_class=None):
                classes = ["UNETLoader", "CLIPLoader", "VAELoader", "CLIPTextEncode", "LoadImage", "VAEEncode", "ReferenceLatent", "GetImageSize", "EmptyFlux2LatentImage", "RandomNoise", "KSamplerSelect", "Flux2Scheduler", "CFGGuider", "SamplerCustomAdvanced", "VAEDecode", "SaveImage"]
                return {name: {} for name in classes}
            def upload_image(self, path): self.counter += 1; return {"name": f"fake-upload-{self.counter}.png"}
            def submit_workflow(self, workflow, client_id=None): self.counter += 1; prompt_id = f"fake-prompt-{self.counter}"; self.submissions.append(prompt_id); image = Image.new("RGBA", (512, 512), (0, 0, 0, 0)); ImageDraw.Draw(image).rectangle((150 + (self.counter % 8), 48, 360, 478), fill=(42, 86, 140, 255)); from io import BytesIO; stream = BytesIO(); image.save(stream, format="PNG"); self.payloads[prompt_id] = stream.getvalue(); return {"prompt_id": prompt_id}
            def poll_history(self, prompt_id, on_poll=None):
                if on_poll: on_poll(prompt_id)
                return {"_ugas_prompt_id": prompt_id, "status": {"status_str": "success", "completed": True}, "outputs": {"16": {"images": [{"filename": "fake.png", "subfolder": "", "type": "output"}]}}}
            def fetch_history_outputs(self, history):
                prompt_id = history["_ugas_prompt_id"]; return [{"node_id": "16", "filename": "fake.png", "subfolder": "", "type": "output", "data": self.payloads[prompt_id]}]
            def health(self): return {"system": {"comfyui_version": "0.34.0"}}
            def safe_health(self): return {"status": "healthy", "value": self.health()}
            def features(self): return {}
            def list_model_types(self): return []
            def list_models(self, folder): return []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "docs/evidence").mkdir(parents=True); (root / "providers/models").mkdir(parents=True); (root / "providers/workflows").mkdir(parents=True)
            shutil.copy2(ROOT / "docs/evidence/reference-edit-selected-transparent.png", root / "docs/evidence/reference-edit-selected-transparent.png"); shutil.copy2(ROOT / "providers/models/registry.json", root / "providers/models/registry.json"); shutil.copy2(ROOT / "providers/workflows/registry.json", root / "providers/workflows/registry.json")
            for path in (ROOT / "providers/workflows").glob("*.api.json"): shutil.copy2(path, root / "providers/workflows" / path.name)
            ensure_pose_guides(root); (root / "docs/evidence/multiref-v2-qualification.json").write_text(json.dumps({"status": "MULTI_REFERENCE_QUALIFIED"}), encoding="utf-8"); (root / "docs/evidence/directional-anchor-set-v2.json").write_text(json.dumps({"status": "DIRECTIONAL_ANCHORS_VISUAL_REVIEW_REQUIRED"}), encoding="utf-8")
            fake_score = {"technical": {"eligible": True, "safe_margin_ok": True}, "pose": {"pose_score": .8, "lower_body_guide_coverage": .4}, "identity": {"identity_descriptor_score": .9, "candidate_descriptor": {"body_proportions": {"bbox_height": .8}}}, "pose_pass": True, "identity_pass": True, "weapon_present": True, "eligible": True, "rejection_reasons": []}
            fake_normalization = {"alpha_bbox_before": [150, 48, 360, 478], "source_pivot": {"x": 255, "y": 478}, "translation": {"x": 1, "y": 0}, "delta_applied": {"x": 1, "y": 0}, "scale": 1.0, "pivot_policy": "centerline x 256, ground baseline y 478", "ground_baseline": 478, "normalization_status": "TRANSLATED_NO_STRETCH", "qa": {"eligible": True}, "transparency": {"execution_evidence": {}}}
            with mock.patch.object(multiview, "ComfyUIClient", FakeClient), mock.patch.object(multiview, "_transparent_candidate", side_effect=lambda repo, client, generated, root, label, guide: (generated, fake_normalization)), mock.patch.object(multiview, "_score_output", return_value=fake_score), mock.patch.object(multiview, "_temporal_qa", return_value={"status": "TEMPORAL_QA_PASSED"}), mock.patch.object(multiview, "_runtime_doctor", return_value={"status": "READY"}), mock.patch.object(multiview, "_append_execution", return_value={}):
                result = generate_walk_pilot(root, endpoint="http://fake", seed_base=9000)
            self.assertEqual(result["status"], "WALK_VISUAL_REVIEW_REQUIRED")
            self.assertEqual(len(result["qa"]["frames"]), 8)
            self.assertTrue(all(item["selected"]["previous_frame_input"] is None for item in result["qa"]["frames"]))


if __name__ == "__main__":
    unittest.main()
