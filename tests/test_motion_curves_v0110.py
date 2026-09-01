"""Unit coverage for the v0.11.0 generic motion-quality layer."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))

from ugas.animation import load_spec, motion_track_fields
from ugas.animation_profiles import attack_front_v2
from ugas.motion_curves import MotionCurveError, motion_tracks_sha256, sample_all_tracks, sample_track, validate_motion_tracks


class MotionCurvesV0110Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = {"frame_count": 6, "motion_tracks": [{"track_id": "scalar", "value_type": "scalar", "interpolation": "linear", "keyframes": [{"frame": 0, "value": 0.0}, {"frame": 5, "value": 10.0}]}, {"track_id": "vector", "value_type": "vec2", "interpolation": "smoothstep", "keyframes": [{"frame": 0, "value": [0.0, 0.0]}, {"frame": 4, "value": [8.0, -4.0]}]}, {"track_id": "hermite", "value_type": "scalar", "interpolation": "cubic_hermite", "keyframes": [{"frame": 0, "value": 0.0}, {"frame": 2, "value": 4.0}, {"frame": 5, "value": 9.0}]}]}

    def test_validates_scalar_vec2_and_all_interpolations(self) -> None:
        for interpolation in ("linear", "smoothstep", "cubic_hermite"):
            value = copy.deepcopy(self.spec["motion_tracks"][0]); value["interpolation"] = interpolation
            normalized = validate_motion_tracks({"frame_count": 6, "motion_tracks": [value]})
            self.assertEqual(interpolation, normalized[0]["interpolation"])
        normalized = validate_motion_tracks(self.spec)
        self.assertEqual(["scalar", "vector", "hermite"], [item["track_id"] for item in normalized])
        self.assertEqual([4.0, -2.0], sample_track(normalized[1], 2.0))

    def test_exact_keyframes_and_linear_interpolation_are_unrounded(self) -> None:
        track = validate_motion_tracks(self.spec)[0]
        self.assertEqual(0.0, sample_track(track, 0.0))
        self.assertEqual(10.0, sample_track(track, 5.0))
        self.assertAlmostEqual(5.0, sample_track(track, 2.5), places=12)

    def test_smoothstep_and_hermite_are_deterministic(self) -> None:
        tracks = validate_motion_tracks(self.spec)
        smooth = sample_track(tracks[1], 1.0)
        self.assertEqual([1.25, -0.625], smooth)
        first = sample_track(tracks[2], 1.25)
        for _ in range(5):
            self.assertEqual(first, sample_track(tracks[2], 1.25))

    def test_sample_all_tracks_preserves_opaque_ids(self) -> None:
        values = sample_all_tracks(self.spec, 2.0)
        self.assertEqual({"scalar", "vector", "hermite"}, set(values))
        self.assertEqual(4.0, values["scalar"])

    def test_duplicate_track_id_is_rejected(self) -> None:
        value = copy.deepcopy(self.spec)
        value["motion_tracks"].append(copy.deepcopy(value["motion_tracks"][0]))
        with self.assertRaises(MotionCurveError):
            validate_motion_tracks(value)

    def test_keyframes_must_be_strictly_ascending(self) -> None:
        value = copy.deepcopy(self.spec)
        value["motion_tracks"][0]["keyframes"] = [{"frame": 2, "value": 2.0}, {"frame": 1, "value": 1.0}]
        with self.assertRaises(MotionCurveError):
            validate_motion_tracks(value)

    def test_keyframes_must_stay_inside_timeline(self) -> None:
        value = copy.deepcopy(self.spec)
        value["motion_tracks"][0]["keyframes"][-1]["frame"] = 6
        with self.assertRaises(MotionCurveError):
            validate_motion_tracks(value)

    def test_nonfinite_and_unknown_policy_are_rejected(self) -> None:
        nonfinite = copy.deepcopy(self.spec)
        nonfinite["motion_tracks"][0]["keyframes"][0]["value"] = float("inf")
        with self.assertRaises(MotionCurveError):
            validate_motion_tracks(nonfinite)
        bad_policy = copy.deepcopy(self.spec)
        bad_policy["motion_tracks"][0]["clamp_policy"] = "extrapolate"
        with self.assertRaises(MotionCurveError):
            validate_motion_tracks(bad_policy)

    def test_out_of_range_sampling_fails_closed_unless_clamped(self) -> None:
        track = validate_motion_tracks(self.spec)[0]
        with self.assertRaises(MotionCurveError):
            sample_track(track, -0.1)
        clamped = {**track, "clamp_policy": "clamp"}
        self.assertEqual(0.0, sample_track(clamped, -0.1))
        self.assertEqual(10.0, sample_track(clamped, 7.0))

    def test_track_hash_changes_when_track_changes(self) -> None:
        changed = copy.deepcopy(self.spec)
        before = motion_tracks_sha256(self.spec)
        changed["motion_tracks"][0]["keyframes"][1]["value"] = 11.0
        self.assertNotEqual(before, motion_tracks_sha256(changed))

    def test_legacy_spec_has_no_optional_motion_fields(self) -> None:
        legacy = load_spec(ROOT / "profiles/animation/attack-front-v1.json", ROOT)
        self.assertEqual({}, motion_track_fields(legacy))

    def test_attack_v2_profile_has_bound_motion_and_body_proxies(self) -> None:
        spec = load_spec(ROOT / "profiles/animation/attack-front-v2.json", ROOT)
        self.assertEqual(11, len(spec["motion_tracks"]))
        self.assertEqual(12, spec["frame_count"])
        context = attack_front_v2.load_context(spec, ROOT)
        prepared = attack_front_v2.prepare(spec, context)
        self.assertEqual(12, len(prepared["targets"]))
        self.assertEqual(12, prepared["series"]["target_hash_count"])
        self.assertTrue(prepared["proxies"]["body_mechanics"]["hard_gates"]["right_shoulder_to_wrist_path_gt_attack_v1"])
        self.assertTrue(all(value is True for value in prepared["temporal_gates"].values()))

    def test_attack_v2_body_mechanics_zero_motion_is_rejected(self) -> None:
        spec = load_spec(ROOT / "profiles/animation/attack-front-v2.json", ROOT)
        context = attack_front_v2.load_context(spec, ROOT)
        prepared = attack_front_v2.prepare(spec, context)
        targets = [copy.deepcopy(prepared["targets"][0]) for _ in prepared["targets"]]
        samples = [{key: [0.0, 0.0] if isinstance(value, list) else 0.0 for key, value in sample.items()} for sample in prepared["samples"]]
        result = attack_front_v2._body_mechanics(spec, targets, samples, context)
        self.assertEqual("ATTACK_V2_BODY_MECHANICS_GAP", result["status"])

    def test_attack_v2_weapon_zero_follow_through_is_rejected(self) -> None:
        spec = load_spec(ROOT / "profiles/animation/attack-front-v2.json", ROOT)
        result = json.loads((ROOT / "docs/evidence/animation-runtime-v0110/attack-front-v2/qa-result.json").read_text(encoding="utf-8"))
        records = copy.deepcopy(result["frames"])
        frozen_tip = list(records[6]["weapon"]["tip_presented"])
        records[7]["weapon"]["tip_presented"] = list(frozen_tip)
        records[8]["weapon"]["tip_presented"] = list(frozen_tip)
        self.assertEqual("ATTACK_V2_WEAPON_ARC_GAP", attack_front_v2._weapon_arc_qa(spec, records)["status"])

    def test_attack_v2_foot_slide_is_rejected(self) -> None:
        spec = load_spec(ROOT / "profiles/animation/attack-front-v2.json", ROOT)
        context = attack_front_v2.load_context(spec, ROOT)
        prepared = attack_front_v2.prepare(spec, context)
        result = json.loads((ROOT / "docs/evidence/animation-runtime-v0110/attack-front-v2/qa-result.json").read_text(encoding="utf-8"))
        records = copy.deepcopy(result["frames"])
        records[1]["feet"]["feet"]["left"]["projected_ground_y"] += 10.0
        self.assertEqual("ATTACK_V2_FOOT_GROUND_GAP", attack_front_v2._foot_ground_qa(records, prepared["targets"], spec)["status"])


if __name__ == "__main__":
    unittest.main()
