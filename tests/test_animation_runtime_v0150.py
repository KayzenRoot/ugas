from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ugas.animation import decode_gif_timing, load_spec
from ugas.animation_profiles.common import target_digest


class DeathAnimationFrontV0150Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load_spec(ROOT / "profiles/animation/death-front-v1.json", ROOT)
        cls.context = __import__(
            "ugas.animation_profiles.death_front_v1",
            fromlist=["load_context"],
        ).load_context(cls.spec, ROOT)
        cls.prepared = __import__(
            "ugas.animation_profiles.death_front_v1",
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
        self.assertEqual(self.spec["runtime_adapter"], "ugas.animation_profiles.death_front_v1")

    def test_qualified_evidence_and_all_death_controls_pass(self) -> None:
        qa = json.loads(
            (ROOT / "docs/evidence/animation-runtime-v0150/death-front-v1/qa-result.json").read_text(
                encoding="utf-8"
            )
        )
        controls = json.loads(
            (ROOT / "docs/evidence/animation-runtime-v0150/death-front-gate-negative-controls-v0150.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(qa["decision"], "QUALIFIED")
        self.assertEqual(qa["failures"], [])
        self.assertTrue(all(qa["hard_gates"].values()))
        self.assertEqual(controls["status"], "NC_01_TO_NC_13_PASSED")
        self.assertEqual(len(controls["controls"]), 14)
        self.assertTrue(all(item["status"] == "REJECTED" for item in controls["controls"].values()))

    def test_non_loop_gif_has_no_repeat_extension(self) -> None:
        gif = ROOT / "docs/evidence/animation-runtime-v0150/death-front-v1/death-front-preview-v0150.gif"
        decoded = decode_gif_timing(gif)
        self.assertEqual(decoded["frame_count"], 8)
        self.assertFalse(decoded["loop_extension_present"])
        self.assertIsNone(decoded["loop_count"])
        self.assertNotIn(b"NETSCAPE2.0", gif.read_bytes())

    def test_hit_and_run_regressions_remain_green(self) -> None:
        hit = json.loads(
            (ROOT / "docs/evidence/animation-runtime-v0150/hit-front-nonloop-regression-v0150.json").read_text(
                encoding="utf-8"
            )
        )
        run = json.loads(
            (ROOT / "docs/evidence/animation-runtime-v0150/run-front-loop-regression-v0150.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(hit["status"], "HIT_NONLOOP_REGRESSION_PASSED")
        self.assertEqual(run["status"], "RUN_FRONT_LOOP_REGRESSION_PASSED")

    def test_frozen_v0141_evidence_matches_approved_head(self) -> None:
        approved = subprocess.check_output(
            [
                "git",
                "show",
                "a3e37865f260c5a6cd56743e1d4b9131fcb12cda:docs/evidence/animation-runtime-v0141/state-consistency-v0141.json",
            ],
            cwd=ROOT,
        )
        live = (ROOT / "docs/evidence/animation-runtime-v0141/state-consistency-v0141.json").read_bytes()
        self.assertEqual(live.replace(b"\r\n", b"\n"), approved)

    def test_capability_matrix_keeps_death_unapproved(self) -> None:
        matrix = json.loads((ROOT / "docs/ugas-v1-capability-matrix.json").read_text(encoding="utf-8"))
        death = next(item for item in matrix["capabilities"] if item["id"] == "death_animation_front")
        self.assertEqual(matrix["next_candidate"], "DEATH_ANIMATION_FRONT")
        self.assertIn("TECHNICALLY_QUALIFIED", death["status"])
        self.assertNotEqual(death["status"], "APPROVED_PILOT")


if __name__ == "__main__":
    unittest.main()
