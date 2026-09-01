"""Contract and negative-control tests for the reusable v0.9.0 runtime."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))

from ugas.animation import AnimationContractError, compile_spec, load_spec, normalized_timing, package_compiled, qa_compiled
from ugas.animation_profiles import idle_front_v1 as idle
from ugas.animation_profiles import walk_front_v1 as walk
from ugas.schema_validation import SchemaValidationError
from ugas.state_consistency_v081 import validate_state_consistency as validate_state_v081


class AnimationRuntimeV090Tests(unittest.TestCase):
    def setUp(self):
        self.idle_spec_path = ROOT / "profiles/animation/idle-front-v1.json"
        self.walk_spec_path = ROOT / "profiles/animation/walk-front-v1.json"
        self.idle_manifest_path = ROOT / "docs/evidence/animation-runtime-v090/idle-front-v1/compiled-manifest.json"
        self.walk_manifest_path = ROOT / "docs/evidence/animation-runtime-v090/replay/walk-front-v1/compiled-manifest.json"

    def test_schema_rejects_frame_count_and_ambiguous_timing(self):
        spec = json.loads(self.idle_spec_path.read_text(encoding="utf-8"))
        bad_count = copy.deepcopy(spec); bad_count["frame_count"] = 1
        bad_timing = copy.deepcopy(spec); bad_timing["per_frame_duration_ms"] = 125
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            p = Path(directory) / "bad.json"
            p.write_text(json.dumps(bad_count), encoding="utf-8")
            with self.assertRaises((SchemaValidationError, AnimationContractError)): load_spec(p, ROOT)
            p.write_text(json.dumps(bad_timing), encoding="utf-8")
            with self.assertRaises((SchemaValidationError, AnimationContractError)): load_spec(p, ROOT)

    def test_timing_representations_are_exclusive_and_normalized(self):
        fixture = json.loads((ROOT / "tests/fixtures/dummy-two-key-v1.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            p = Path(directory) / "timing.json"
            fps_only = copy.deepcopy(fixture); fps_only.pop("per_frame_duration_ms"); fps_only["fps"] = 8
            p.write_text(json.dumps(fps_only), encoding="utf-8"); loaded = load_spec(p, ROOT); self.assertEqual({"fps": 8.0, "per_frame_duration_ms": 125.0}, normalized_timing(loaded))
            duration_only = copy.deepcopy(fixture); loaded = load_spec(p, ROOT); self.assertEqual({"fps": 8.0, "per_frame_duration_ms": 125.0}, normalized_timing(loaded))
            p.write_text(json.dumps(duration_only), encoding="utf-8"); loaded = load_spec(p, ROOT); self.assertEqual({"fps": 8.0, "per_frame_duration_ms": 125.0}, normalized_timing(loaded))
            for invalid in (dict(fixture, fps=8), {key: value for key, value in fixture.items() if key != "per_frame_duration_ms"}):
                p.write_text(json.dumps(invalid), encoding="utf-8")
                with self.assertRaises((SchemaValidationError, AnimationContractError)): load_spec(p, ROOT)

    def test_generic_dummy_status_is_not_a_package_policy(self):
        fixture = ROOT / "tests/fixtures/dummy-two-key-v1.json"
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "dummy"
            manifest = compile_spec(fixture, output, ROOT)
            qa_path = qa_compiled(manifest, ROOT)
            qa = json.loads(qa_path.read_text(encoding="utf-8")); self.assertEqual("QUALIFIED", qa["decision"]); self.assertEqual("SYNTHETIC_FIXTURE_TECHNICALLY_OK", qa["status"])
            package = json.loads(package_compiled(manifest, ROOT).read_text(encoding="utf-8")); self.assertEqual("QUALIFIED", package["qa_decision"])

    def test_generic_dummy_failed_decision_gate_and_failures_are_fail_closed(self):
        fixture = ROOT / "tests/fixtures/dummy-two-key-v1.json"
        for mutation in ("decision", "hard_gate", "failure"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(dir=ROOT) as directory:
                output = Path(directory) / "dummy"; manifest = compile_spec(fixture, output, ROOT); qa_path = qa_compiled(manifest, ROOT); qa = json.loads(qa_path.read_text(encoding="utf-8"))
                if mutation == "decision": qa["decision"] = "FAILED"
                elif mutation == "hard_gate": qa["hard_gates"]["fixture_integrity"] = False
                else: qa["failures"] = ["synthetic_failure"]
                qa_path.write_text(json.dumps(qa), encoding="utf-8")
                with self.assertRaises(AnimationContractError): package_compiled(manifest, ROOT)
                self.assertFalse((output / "package-manifest.json").exists())

    def test_walk_replay_is_byte_identical(self):
        manifest = json.loads(self.walk_manifest_path.read_text(encoding="utf-8")); qa = json.loads((self.walk_manifest_path.parent / "qa-result.json").read_text(encoding="utf-8"))
        self.assertEqual("CUTOUT_ANIMATION_RUNTIME_V1_WALK_REPLAY_IDENTICAL", qa["status"])
        self.assertEqual([item["rgba_sha256"] for item in manifest["frames"]], [item["rgba_sha256"] for item in qa["frames"]])

    def test_walk_replay_negative_target_mismatch(self):
        spec = load_spec(self.walk_spec_path, ROOT); context = walk.load_context(spec, ROOT); manifest = json.loads(self.walk_manifest_path.read_text(encoding="utf-8")); manifest["frames"][0]["rgba_sha256"] = "0" * 64
        self.assertEqual("ANIMATION_RUNTIME_WALK_REPLAY_GAP", walk.qa(spec, context, manifest, ROOT)["status"])

    def test_idle_deterministic_replay_twice(self):
        manifest = json.loads(self.idle_manifest_path.read_text(encoding="utf-8")); repeat = json.loads((ROOT / "docs/evidence/animation-runtime-v090/repro/idle-front-v1-repeat/compiled-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([(i["rgba_sha256"], i["target_hash"]) for i in manifest["frames"]], [(i["rgba_sha256"], i["target_hash"]) for i in repeat["frames"]])

    def test_negative_foot_three_pixels_fails(self):
        feet = {"feet": {"left": {"sole_error_px": 0, "ground_penetration_px": 0}, "right": {"sole_error_px": 3, "ground_penetration_px": 0}}}
        self.assertFalse(idle.dual_foot_gate(feet))

    def test_dual_foot_drift_negative_controls_and_boundary(self):
        records = []
        for index in range(12):
            records.append({"feet": {"feet": {side: {"projected_ground_y": 100.0, "sole_error_px": 0.0, "ground_penetration_px": 0.0, "ankle_x": 10.0 if side == "left" else 20.0} for side in ("left", "right")}, "hard_gates": {"left": True, "right": True}}})
        self.assertEqual("IDLE_DUAL_FEET_DRIFT_PASSED", idle.dual_foot_drift_qa(records)["status"])
        sole_bad = copy.deepcopy(records); sole_bad[3]["feet"]["feet"]["left"]["projected_ground_y"] += 2.0
        self.assertFalse(idle.dual_foot_drift_qa(sole_bad)["sides"]["left"]["hard_gates"]["frame_to_frame_sole_anchor_drift_le_threshold"])
        ankle_bad = copy.deepcopy(records); ankle_bad[3]["feet"]["feet"]["right"]["ankle_x"] += 3.0
        self.assertFalse(idle.dual_foot_drift_qa(ankle_bad)["sides"]["right"]["hard_gates"]["ankle_horizontal_drift_from_baseline_le_threshold"])
        ankle_boundary = copy.deepcopy(records); ankle_boundary[3]["feet"]["feet"]["right"]["ankle_x"] += 1.5
        self.assertTrue(idle.dual_foot_drift_qa(ankle_boundary)["sides"]["right"]["hard_gates"]["ankle_horizontal_drift_from_baseline_le_threshold"])

    def test_head_and_torso_layer_bbox_negative_controls_are_independent(self):
        from PIL import Image, ImageDraw
        def layer(head_size=4, torso_size=6):
            head = Image.new("RGBA", (16, 16), (0, 0, 0, 0)); ImageDraw.Draw(head).rectangle((0, 0, head_size - 1, head_size - 1), fill=(255, 255, 255, 255))
            torso = Image.new("RGBA", (16, 16), (0, 0, 0, 0)); ImageDraw.Draw(torso).rectangle((0, 0, torso_size - 1, torso_size - 1), fill=(255, 255, 255, 255))
            return idle.layer_bbox_measurement({"head": head, "torso_pelvis": torso})
        good = [layer() for _ in range(12)]
        head_bad = copy.deepcopy(good); head_bad[3] = layer(head_size=8)
        result = idle.layer_bbox_temporal_gate(head_bad); self.assertFalse(result["hard_gates"]["head_bbox_area_cv_le_threshold"]); self.assertTrue(result["hard_gates"]["torso_bbox_area_cv_le_threshold"])
        torso_bad = copy.deepcopy(good); torso_bad[3] = layer(torso_size=12)
        result = idle.layer_bbox_temporal_gate(torso_bad); self.assertFalse(result["hard_gates"]["torso_bbox_area_cv_le_threshold"]); self.assertTrue(result["hard_gates"]["head_bbox_area_cv_le_threshold"])

    def test_negative_frozen_z_order_fails(self):
        good = [{"z_order": list(idle.Z_ORDER)} for _ in range(12)]; good[4]["z_order"] = list(reversed(idle.Z_ORDER))
        self.assertFalse(idle.z_order_gate(good))

    def test_negative_zero_motion_and_overmotion_fail(self):
        spec = load_spec(self.idle_spec_path, ROOT); context = idle.load_context(spec, ROOT); prepared = idle.prepare(spec, context); manifest = json.loads(self.idle_manifest_path.read_text(encoding="utf-8")); outputs = []
        from PIL import Image
        outputs = [Image.open(ROOT / item["path"]).convert("RGBA") for item in manifest["frames"]]
        zero = [copy.deepcopy(prepared["targets"][0]) for _ in range(12)]
        self.assertNotEqual("IDLE_TEMPORAL_LOOP_PASSED", idle.temporal_gate_summary(spec, zero, outputs, [{"z_order": list(idle.Z_ORDER), "feet": {"hard_gates": {"left": True, "right": True}}} for _ in range(12)])["status"])
        over = copy.deepcopy(prepared["targets"]); over[3]["joints"]["pelvis"]["y"] += 100
        self.assertNotEqual("IDLE_TEMPORAL_LOOP_PASSED", idle.temporal_gate_summary(spec, over, outputs, [{"z_order": list(idle.Z_ORDER), "feet": {"hard_gates": {"left": True, "right": True}}} for _ in range(12)])["status"])

    def test_package_absent_on_gate_failure(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            manifest = Path(directory) / "compiled-manifest.json"; manifest.write_text(self.idle_manifest_path.read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaises(AnimationContractError): package_compiled(manifest, ROOT)

    def test_no_ai_generation_in_active_specs(self):
        for path in (self.idle_spec_path, self.walk_spec_path):
            spec = json.loads(path.read_text(encoding="utf-8")); self.assertFalse(spec["provenance"]["sam2_used"] or spec["provenance"]["diffusion_used"]); self.assertEqual(0, spec["provenance"]["comfyui_generation_jobs"])

    def test_review_index_v2_semantics_and_hash(self):
        from scripts.validation.validate_review_index_v090 import validate
        result = validate(ROOT / "docs/evidence/review-index-v0.9.0.json")
        self.assertEqual("REVIEW_INDEX_V2_PASSED", result["status"])
        value = json.loads((ROOT / "docs/evidence/review-index-v0.9.0.json").read_text(encoding="utf-8")); self.assertNotIn("head_commit", value); self.assertTrue(value["publication"]["final_head_must_be_resolved_by_external_reviewer"])

    def test_historical_v081_snapshot_remains_green(self):
        state = json.loads((ROOT / "docs/evidence/current-state-v0.8.1.json").read_text(encoding="utf-8")); result = validate_state_v081(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.8.1.md").read_text(encoding="utf-8")); self.assertEqual("STATE_CONSISTENCY_PASSED", result["status"])
