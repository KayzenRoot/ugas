"""Focused F-26S/F-29/F-30 correction tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from PIL import Image

from ugas.historical_immutability_v0233 import validate_historical_immutability, validate_historical_root
from ugas.vfx_asset_family_runtime_v0233 import (
    VFXAssetFamilyContractError,
    _alpha_bounds,
    _expected_output_hash,
    generate_fixture_pack,
    render_fallback_output,
    select_fallback,
    validate_degraded_determinism,
    validate_degraded_output,
    validate_fallback_result,
)

ROOT = Path(__file__).resolve().parents[1]


class VfxAssetFamilyRuntimeV0233Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="ugas-test-vfx-v0233-")
        self.root = Path(self.tmp.name)
        self.pack = generate_fixture_pack(self.root)
        self.profile = {"profile_id": "constrained-v1", "max_particles_per_instance": 8, "max_layers": 1, "max_spawn_events_per_second": 10, "max_visual_area_ratio": 0.20, "supported_steps": ["REDUCE_PARTICLE_COUNT", "REDUCE_LAYER_COUNT", "REDUCE_SPAWN_RATE", "REDUCE_VISUAL_AREA", "REDUCE_FRAME_COUNT", "REDUCE_OPACITY", "REDUCE_RADIUS", "SKIP_VISUAL"]}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_fallback_validator_replays_exact_order_and_state(self) -> None:
        record = self.pack["records"][2]
        result = select_fallback(record, self.profile)
        validate_fallback_result(record, result, self.profile)
        mutated = deepcopy(result)
        mutated["applied_steps"] = list(reversed(mutated["applied_steps"]))
        with self.assertRaises(VFXAssetFamilyContractError) as context:
            validate_fallback_result(record, mutated, self.profile)
        self.assertEqual(context.exception.rejection_class, "VFX_FALLBACK_ORDER_INVALID")

    def test_validator_rejects_recomputed_hash_for_arbitrary_valid_png(self) -> None:
        record = self.pack["records"][2]
        result = select_fallback(record, self.profile)
        output_root = self.root / "degraded"
        output = render_fallback_output(record, result, self.root, output_root)
        replacement = self.root / "replacement.png"
        Image.new("RGBA", (96, 96), (255, 0, 255, 255)).save(replacement, format="PNG", optimize=False, compress_level=9)
        with Image.open(replacement) as image:
            output["frames"][0].update({"path": "replacement.png", "sha256": __import__("hashlib").sha256(replacement.read_bytes()).hexdigest(), "width": image.width, "height": image.height, "alpha_bounds": _alpha_bounds(image), "alpha_range": list(image.getchannel("A").getextrema())})
        output["output_hash"] = _expected_output_hash(record, output, output["frames"])
        with self.assertRaises(VFXAssetFamilyContractError) as context:
            validate_degraded_output(record, output, self.root, self.root)
        self.assertEqual(context.exception.rejection_class, "VFX_DEGRADED_PIXELS_INVALID")

    def test_terminal_skip_requires_empty_frames_and_record(self) -> None:
        record = self.pack["records"][2]
        result = select_fallback(record, self.profile)
        output = render_fallback_output(record, result, self.root, self.root / "skip", force_skip=True)
        validate_degraded_output(record, output, self.root, self.root / "skip")
        output["frames"] = [deepcopy(self.pack["records"][0]["frames"][0])]
        with self.assertRaises(VFXAssetFamilyContractError) as context:
            validate_degraded_output(record, output, self.root, self.root / "skip")
        self.assertEqual(context.exception.rejection_class, "VFX_FALLBACK_SKIP_RECORD_INVALID")

    def test_independent_second_render_is_persisted_and_validated(self) -> None:
        record = self.pack["records"][2]
        result = select_fallback(record, self.profile)
        first = render_fallback_output(record, result, self.root, self.root / "first")
        repeat = render_fallback_output(record, result, self.root, self.root / "repeat")
        validate_degraded_output(record, first, self.root, self.root / "first")
        validate_degraded_output(record, repeat, self.root, self.root / "repeat")
        validate_degraded_determinism(first, repeat)
        self.assertNotEqual(self.root / "first" / first["frames"][0]["path"], self.root / "repeat" / repeat["frames"][0]["path"])
        repeat["output_hash"] = "0" * 64
        with self.assertRaises(VFXAssetFamilyContractError) as context:
            validate_degraded_determinism(first, repeat)
        self.assertEqual(context.exception.rejection_class, "VFX_DEGRADED_DETERMINISM_MISMATCH")

    def test_git_object_bound_historical_validator_rejects_injected_mutation(self) -> None:
        proof = validate_historical_immutability(ROOT)
        self.assertEqual(proof["status"], "PASS")
        with tempfile.TemporaryDirectory(prefix="ugas-test-history-v0233-") as temp:
            candidate_root = Path(temp) / "docs/evidence/vfx-asset-family-runtime-v0230"
            shutil.copytree(ROOT / "docs/evidence/vfx-asset-family-runtime-v0230", candidate_root)
            target = next(path for path in candidate_root.rglob("*") if path.is_file())
            target.write_bytes(target.read_bytes() + b"\nmutation")
            with self.assertRaises(VFXAssetFamilyContractError) as context:
                validate_historical_root(ROOT, "c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72", "docs/evidence/vfx-asset-family-runtime-v0230", candidate_root)
            self.assertEqual(context.exception.rejection_class, "VFX_HISTORICAL_IMMUTABILITY_REJECTED")


if __name__ == "__main__":
    unittest.main()
