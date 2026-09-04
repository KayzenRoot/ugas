from __future__ import annotations

import json
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ugas.animation import decode_gif_timing, load_spec
from ugas.animation_profiles.common import target_digest


class DeathAnimationFrontV0151Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load_spec(ROOT / "profiles/animation/death-front-v151.json", ROOT)
        cls.context = __import__(
            "ugas.animation_profiles.death_front_v151",
            fromlist=["load_context"],
        ).load_context(cls.spec, ROOT)
        cls.prepared = __import__(
            "ugas.animation_profiles.death_front_v151",
            fromlist=["prepare"],
        ).prepare(cls.spec, cls.context)

    def test_profile_is_eight_frame_front_non_loop(self) -> None:
        self.assertEqual(self.spec["frame_count"], 8)
        self.assertEqual(self.spec["fps"], 12)
        self.assertFalse(self.spec["loop"])
        self.assertEqual(self.spec["direction"], "front")
        self.assertEqual(len(self.spec["motion_tracks"]), 12)

    def test_death_targets_are_distinct_and_key_pose_bound(self) -> None:
        hashes = [target_digest(target) for target in self.prepared["targets"]]
        self.assertEqual(len(set(hashes)), 8)
        for binding in self.spec["key_pose_bindings"]:
            frame = int(binding["frame"])
            self.assertEqual(binding["target_hash"], hashes[frame])

    def test_source_only_provenance_and_runtime_boundary(self) -> None:
        provenance = self.spec["provenance"]
        self.assertTrue(provenance["source_only_pixels"])
        self.assertFalse(provenance["sam2_used"])
        self.assertEqual(provenance["comfyui_generation_jobs"], 0)
        self.assertFalse(provenance["diffusion_used"])
        self.assertEqual(self.spec["runtime_adapter"], "ugas.animation_profiles.death_front_v151")

    def test_qualified_evidence_and_all_death_controls_pass(self) -> None:
        qa = json.loads(
            (ROOT / "docs/evidence/animation-runtime-v0151/death-front-v1/qa-result.json").read_text(
                encoding="utf-8"
            )
        )
        controls = json.loads(
            (ROOT / "docs/evidence/animation-runtime-v0151/death-front-gate-negative-controls-v0151.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(qa["decision"], "QUALIFIED")
        self.assertEqual(qa["failures"], [])
        self.assertTrue(all(qa["hard_gates"].values()))
        self.assertEqual(controls["status"], "NC_01_TO_NC_16_PASSED")
        self.assertEqual(len(controls["controls"]), 16)
        self.assertTrue(all(item["status"] == "REJECTED" for item in controls["controls"].values()))
        ground_contact = controls["ground_contact_controls"]
        self.assertEqual(ground_contact["status"], "NC_GC_01_TO_NC_GC_06_PASSED")
        self.assertEqual(len(ground_contact["controls"]), 6)
        self.assertTrue(all(item["status"] == "REJECTED" for item in ground_contact["controls"].values()))

    def test_measured_body_contact_and_terminal_support_state(self) -> None:
        contact = json.loads(
            (ROOT / "docs/evidence/animation-runtime-v0151/death-front-body-ground-contact-qa-v0151.json").read_text(
                encoding="utf-8"
            )
        )
        support = json.loads(
            (ROOT / "docs/evidence/animation-runtime-v0151/death-front-support-state-qa-v0151.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(contact["transition"]["measured_first_body_contact_frame"], 4)
        self.assertEqual(contact["transition"]["measured_body_contact_frames"], [4, 5, 6, 7])
        self.assertEqual(support["states"][6]["foot_support"], {"left": "lifted", "right": "lifted"})
        self.assertTrue(support["state_transition_valid"])

    def test_ground_reference_terminal_and_provenance_records(self) -> None:
        root = ROOT / "docs/evidence/animation-runtime-v0151"
        ground = json.loads((root / "death-front-ground-reference-v0151.json").read_text(encoding="utf-8"))
        terminal = json.loads((root / "death-front-terminal-support-qa-v0151.json").read_text(encoding="utf-8"))
        separation = json.loads((root / "death-front-death-vs-hit-qa-v0151.json").read_text(encoding="utf-8"))
        provenance = json.loads((root / "v0141-provenance-sha256-correction-v0151.json").read_text(encoding="utf-8"))
        rejection = json.loads((root / "v0150-rejection-record-v0151.json").read_text(encoding="utf-8"))
        self.assertEqual(ground["status"], "GLOBAL_GROUND_REFERENCE_VALID")
        self.assertFalse(ground["reference"]["recomputed_per_frame"])
        self.assertEqual(terminal["status"], "DEATH_TERMINAL_SUPPORT_QA_PASSED")
        self.assertEqual(separation["status"], "DEATH_VS_HIT_SEMANTIC_SEPARATION_PASSED")
        self.assertEqual(provenance["status"], "V0141_PROVENANCE_SHA256_CORRECTION_RECORDED")
        self.assertEqual(provenance["byte_authority"]["raw_git_blob_sha256"], "a648710b66fb21c92ba1030b4f86793719792475c0ecd14a7a48aebc951606bb")
        self.assertTrue(provenance["byte_authority"]["raw_git_blob_matches_independent_reviewer"])
        self.assertEqual(rejection["external_visual"], "FAILED")
        self.assertEqual(rejection["technical_semantic_qa"], "REJECTED_BY_EXTERNAL_REVIEW")

    def test_true_two_run_determinism_and_nc16_mutation_detection(self) -> None:
        determinism = json.loads(
            (ROOT / "docs/evidence/animation-runtime-v0151/death-front-determinism-v0151.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(determinism["status"], "DEATH_DETERMINISM_TRUE_TWO_RUN_PASSED")
        self.assertTrue(determinism["comparison"]["all_fields_match"])
        self.assertTrue(determinism["nc_16_mutation_detected"])

    def test_non_loop_gif_has_no_repeat_extension(self) -> None:
        gif = ROOT / "docs/evidence/animation-runtime-v0151/death-front-v1/death-front-preview-v0151.gif"
        decoded = decode_gif_timing(gif)
        self.assertEqual(decoded["frame_count"], 8)
        self.assertFalse(decoded["loop_extension_present"])
        self.assertIsNone(decoded["loop_count"])
        self.assertNotIn(b"NETSCAPE2.0", gif.read_bytes())

    def test_hit_and_run_regressions_remain_green(self) -> None:
        hit = json.loads(
            (ROOT / "docs/evidence/animation-runtime-v0151/hit-front-nonloop-regression-v0151.json").read_text(
                encoding="utf-8"
            )
        )
        run = json.loads(
            (ROOT / "docs/evidence/animation-runtime-v0151/run-front-loop-regression-v0151.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(hit["status"], "HIT_NONLOOP_REGRESSION_PASSED")
        self.assertEqual(run["status"], "RUN_FRONT_LOOP_REGRESSION_PASSED")

    def test_frozen_v0141_evidence_matches_approved_head(self) -> None:
        live = (ROOT / "docs/evidence/animation-runtime-v0141/state-consistency-v0141.json").read_bytes()
        normalized = live.replace(b"\r\n", b"\n")
        blob = hashlib.sha1(  # noqa: S324  (Git object identity uses SHA-1)
            f"blob {len(normalized)}\0".encode() + normalized
        ).hexdigest()
        self.assertEqual(blob, "9bbc85bd5ca839b4a0fd71b45a279e852a275fc5")

    def test_capability_matrix_keeps_death_unapproved(self) -> None:
        matrix = json.loads((ROOT / "docs/evidence/animation-runtime-v0150/capability-matrix-validation-v0150.json").read_text(encoding="utf-8"))
        state = json.loads((ROOT / "docs/evidence/current-state-v0.15.0.json").read_text(encoding="utf-8"))
        self.assertEqual(matrix["next_candidate"], "DEATH_ANIMATION_FRONT")
        self.assertIn("TECHNICALLY_QUALIFIED", state["current_gate"])
        self.assertNotEqual(state["death_animation_front_visual_content"], "APPROVED_PILOT")


if __name__ == "__main__":
    unittest.main()
