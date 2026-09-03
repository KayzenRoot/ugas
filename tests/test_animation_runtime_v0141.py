from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/validation"))

from ugas.animation import decode_gif_timing, encode_gif, gif_frame_durations_ms, gif_timing_within_tolerance, inspect_gif_loop_extension, load_spec
from run_animation_runtime_v0141 import IMMUTABLE_BASE, REJECTED_REVIEWED_HEAD, _loop_negative_controls, _record_v0140_baseline


class HitFrontV0141Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load_spec(ROOT / "profiles/animation/hit-front-v1.json", ROOT)
        cls.run_spec = load_spec(ROOT / "profiles/animation/run-front-v1.json", ROOT)

    def test_profile_remains_six_frame_non_loop(self) -> None:
        self.assertEqual(self.spec["frame_count"], 6)
        self.assertEqual(self.spec["fps"], 12)
        self.assertFalse(self.spec["loop"])
        self.assertTrue(self.run_spec["loop"])

    def test_encoder_omits_netscape_for_nonloop_and_emits_infinite_for_loop(self) -> None:
        frames = [Image.new("RGB", (8, 8), (index * 30, 8, 16)) for index in range(3)]
        with tempfile.TemporaryDirectory() as directory:
            once = Path(directory) / "once.gif"
            looped = Path(directory) / "loop.gif"
            encode_gif(frames, once, [80, 80, 80], loop=False)
            encode_gif(frames, looped, [80, 80, 80], loop=True)
            once_decoded = decode_gif_timing(once)
            loop_decoded = decode_gif_timing(looped)
            self.assertFalse(once_decoded["loop_extension_present"])
            self.assertIsNone(once_decoded["loop_count"])
            self.assertIsNone(once_decoded["loop"])
            self.assertTrue(loop_decoded["loop_extension_present"])
            self.assertEqual(loop_decoded["loop_count"], 0)
            self.assertNotIn(b"NETSCAPE2.0", once.read_bytes())
            self.assertIn(b"NETSCAPE2.0", looped.read_bytes())

    def test_decoder_does_not_collapse_absence_and_loop_one(self) -> None:
        frames = [Image.new("RGB", (8, 8), (12, index * 20, 9)) for index in range(2)]
        with tempfile.TemporaryDirectory() as directory:
            absent = Path(directory) / "absent.gif"
            explicit = Path(directory) / "loop1.gif"
            encode_gif(frames, absent, [80, 80], loop=False)
            frames[0].save(explicit, format="GIF", save_all=True, append_images=frames[1:], duration=[80, 80], loop=1, disposal=2, optimize=False)
            absent_decoded = decode_gif_timing(absent)
            explicit_decoded = decode_gif_timing(explicit)
            self.assertNotEqual(absent_decoded["loop_extension_present"], explicit_decoded["loop_extension_present"])
            self.assertIsNone(absent_decoded["loop_count"])
            self.assertEqual(explicit_decoded["loop_count"], 1)

    def test_loop_negative_controls_use_real_encoded_gifs(self) -> None:
        result = _loop_negative_controls(self.spec, self.run_spec)
        self.assertEqual(result["status"], "NC_LOOP_01_TO_05_PASSED")
        self.assertEqual(len(result["controls"]), 5)
        for item in result["controls"].values():
            self.assertTrue(item["match"])
            self.assertEqual(64, len(item["gif_sha256"]))

    def test_rejected_v0140_gif_still_has_explicit_loop_one(self) -> None:
        baseline = _record_v0140_baseline()
        self.assertEqual(baseline["rejected_reviewed_head"], REJECTED_REVIEWED_HEAD)
        self.assertTrue(baseline["gif_loop_extension_present"])
        self.assertEqual(baseline["gif_loop_count"], 1)
        self.assertEqual(inspect_gif_loop_extension(ROOT / "docs/evidence/animation-runtime-v0140/hit-front-v1/hit-front-preview-v0140.gif")["loop_count"], 1)

    def test_nonloop_spec_rejects_both_infinite_and_loop_one(self) -> None:
        durations = gif_frame_durations_ms(self.spec)
        decoded_infinite = {"frame_count": 6, "loop_extension_present": True, "loop_count": 0, "loop": 0, "durations_ms": durations, "total_cycle_ms": sum(durations), "effective_fps": 12.0}
        decoded_one = {"frame_count": 6, "loop_extension_present": True, "loop_count": 1, "loop": 1, "durations_ms": durations, "total_cycle_ms": sum(durations), "effective_fps": 12.0}
        decoded_absent = {"frame_count": 6, "loop_extension_present": False, "loop_count": None, "loop": None, "durations_ms": durations, "total_cycle_ms": sum(durations), "effective_fps": 12.0}
        self.assertEqual(gif_timing_within_tolerance(self.spec, decoded_infinite)["status"], "GIF_TIMING_GAP")
        self.assertEqual(gif_timing_within_tolerance(self.spec, decoded_one)["status"], "GIF_TIMING_GAP")
        self.assertEqual(gif_timing_within_tolerance(self.spec, decoded_absent)["status"], "GIF_TIMING_PASSED")

    def test_v0141_contract_keeps_hit_ncs_and_adds_loop_ncs(self) -> None:
        contract = json.loads((ROOT / "docs/evidence/animation-runtime-v0141/hit-front-contract-v0141.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["dependencies"]["implementation_base_commit"], IMMUTABLE_BASE)
        self.assertEqual(len(contract["negative_controls"]), 10)
        self.assertEqual(len(contract["loop_negative_controls"]), 5)
        self.assertTrue(contract["gif_loop_semantics"]["loop_1_is_not_non_loop"])


if __name__ == "__main__":
    unittest.main()
