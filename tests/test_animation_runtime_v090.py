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

from ugas.animation import AnimationContractError, compile_spec, load_spec, package_compiled
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
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            p = Path(directory) / "bad.json"
            p.write_text(json.dumps(bad_count), encoding="utf-8")
            with self.assertRaises((SchemaValidationError, AnimationContractError)): load_spec(p, ROOT)
            p.write_text(json.dumps(bad_timing), encoding="utf-8")
            with self.assertRaises(AnimationContractError): load_spec(p, ROOT)

    def test_generic_core_has_no_profile_specific_universal_dependency(self):
        source = (ROOT / "src/ugas/animation.py").read_text(encoding="utf-8").casefold()
        self.assertNotIn("walk", source); self.assertNotIn("front", source); self.assertNotIn("f0", source)
        self.assertNotIn("frame_count = 8", source)

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
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
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
