from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from ugas.direction_runtime import (
    CANONICAL_DIRECTIONS,
    DirectionManifestError,
    DirectionResolver,
    canonicalize_direction,
    direction_contract,
    normalize_direction,
    quantize_vector,
    validate_coverage_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/evidence/multi-direction-runtime-v0160/coverage-manifest-v0160.json"


class DirectionRuntimeV0160Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.resolver = DirectionResolver.from_manifest(MANIFEST)

    def test_schema_has_canonical_eight_and_frozen_convention(self) -> None:
        self.assertEqual(tuple(self.manifest["canonical_directions"]), CANONICAL_DIRECTIONS)
        contract = direction_contract()
        self.assertEqual(contract["coordinate_convention"]["y_positive"], "south")
        self.assertEqual(contract["boundary_policy"], "lower-inclusive-upper-exclusive-after-22.5-degree-clockwise-offset")

    def test_alias_mapping_is_unambiguous(self) -> None:
        self.assertEqual(canonicalize_direction("front"), "south")
        self.assertEqual(canonicalize_direction("front-right"), "south_east")
        self.assertEqual(canonicalize_direction("back"), "north")
        self.assertIsNone(canonicalize_direction("diagonal_unknown"))

    def test_vector_quantization_is_deterministic(self) -> None:
        expected = {(0, 1): "south", (1, 1): "south_east", (1, 0): "east", (1, -1): "north_east", (0, -1): "north", (-1, -1): "north_west", (-1, 0): "west", (-1, 1): "south_west"}
        for vector, direction in expected.items():
            self.assertEqual(quantize_vector(*vector), direction)
            self.assertEqual(quantize_vector(*vector), direction)

    def test_boundary_policy_is_explicit(self) -> None:
        diagonal = math.tan(math.radians(22.5))
        self.assertEqual(quantize_vector(1, diagonal), "south_east")
        self.assertEqual(quantize_vector(1, diagonal - 1e-9), "east")
        self.assertEqual(quantize_vector(1, diagonal + 1e-9), "south_east")
        self.assertEqual(quantize_vector(1, -diagonal), "east")

    def test_zero_vector_never_guesses(self) -> None:
        self.assertIsNone(normalize_direction((0, 0)))
        self.assertEqual(normalize_direction((0, 0), retained_facing="left"), "west")
        unresolved = self.resolver.resolve("death_animation_front", (0, 0))
        self.assertEqual(unresolved.error_code, "DIRECTION_UNRESOLVED")
        self.assertEqual(unresolved.fallback_mode, "UNRESOLVED")

    def test_front_alias_is_backward_compatible_with_south(self) -> None:
        front = self.resolver.resolve("death_animation_front", "front")
        south = self.resolver.resolve("death_animation_front", "south")
        self.assertEqual(front.to_dict(), south.to_dict())
        self.assertEqual(front.resolved_direction, "south")
        self.assertTrue(front.production_safe)

    def test_approved_front_library_is_south_only(self) -> None:
        self.assertEqual(validate_coverage_manifest(MANIFEST, ROOT)["status"], "DIRECTION_COVERAGE_MANIFEST_PASSED")
        self.assertEqual(self.manifest["assets"].__len__(), 6)
        self.assertEqual({item["direction"] for item in self.manifest["assets"]}, {"south"})

    def test_missing_real_direction_fails_closed(self) -> None:
        result = self.resolver.resolve("death_animation_front", "north")
        self.assertEqual(result.error_code, "DIRECTION_ASSET_UNAVAILABLE")
        self.assertEqual(result.fallback_mode, "FAIL_CLOSED")
        self.assertFalse(result.production_safe)

    def test_preview_fallback_is_explicit_and_nonproduction(self) -> None:
        result = self.resolver.resolve("death_animation_front", "north", allow_preview_fallback=True)
        self.assertEqual(result.resolved_direction, "south")
        self.assertEqual(result.fallback_mode, "EXPLICIT_PREVIEW_FALLBACK")
        self.assertFalse(result.production_safe)

    def test_implicit_mirror_is_never_used(self) -> None:
        result = self.resolver.resolve("death_animation_front", "west")
        self.assertEqual(result.fallback_mode, "FAIL_CLOSED")
        self.assertEqual(result.mirror_mode, "NONE")

    def test_mirror_requires_explicit_safe_pair(self) -> None:
        asset = {"capability_id": "fixture", "direction": "east", "variant": "default", "asset_revision_id": "fixture-r1", "asset_id": "fixture-east", "path": "tests/fixtures/east.png", "provenance_hash": "0" * 64, "metadata": {"capability_id": "fixture", "direction": "east", "variant": "default", "asset_revision_id": "fixture-r1"}, "test_only": False, "mirror_safe": True, "mirror_pair": "west"}
        resolver = DirectionResolver([asset], mirror_pairs={"west": "east"})
        denied = resolver.resolve("fixture", "west")
        allowed = resolver.resolve("fixture", "west", allow_mirror=True)
        self.assertEqual(denied.error_code, "DIRECTION_ASSET_UNAVAILABLE")
        self.assertEqual(allowed.mirror_mode, "HORIZONTAL_EXPLICIT")
        self.assertEqual(allowed.fallback_mode, "EXPLICIT_PREVIEW_MIRROR")
        self.assertFalse(allowed.production_safe)

    def test_mirror_unsafe_asymmetry_is_rejected(self) -> None:
        asset = {"capability_id": "fixture", "direction": "east", "variant": "default", "asset_revision_id": "fixture-r1", "asset_id": "fixture-east", "path": "tests/fixtures/east.png", "provenance_hash": "0" * 64, "metadata": {"capability_id": "fixture", "direction": "east", "variant": "default", "asset_revision_id": "fixture-r1"}, "test_only": False, "mirror_safe": False, "mirror_pair": "west"}
        resolver = DirectionResolver([asset], mirror_pairs={"west": "east"})
        result = resolver.resolve("fixture", "west", allow_mirror=True)
        self.assertEqual(result.error_code, "DIRECTION_ASSET_UNAVAILABLE")

    def test_cache_key_contains_capability_direction_variant_and_revision(self) -> None:
        self.resolver.clear_cache()
        south = self.resolver.resolve("death_animation_front", "south", variant="default", asset_revision_id="r4-cutout-rig-v071")
        north = self.resolver.resolve("death_animation_front", "north", variant="default", asset_revision_id="r4-cutout-rig-v071")
        for token in ("death_animation_front", "south", "default", "r4-cutout-rig-v071"):
            self.assertIn(token, south.cache_key)
        self.assertNotEqual(south.cache_key, north.cache_key)
        self.assertEqual(len(self.resolver.cache_keys()), 2)

    def test_metadata_mismatch_is_rejected(self) -> None:
        bad = dict(self.manifest["assets"][0])
        bad["metadata"] = dict(bad["metadata"], direction="north")
        with self.assertRaises(DirectionManifestError):
            DirectionResolver([bad])

    def test_synthetic_fixture_never_enters_production_registry(self) -> None:
        fixture = dict(self.manifest["assets"][0], asset_id="TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE-south", test_only=True)
        with self.assertRaises(DirectionManifestError):
            DirectionResolver([fixture])
        self.assertEqual(DirectionResolver([fixture], production_registry=False).resolve("idle_front", "south").asset_id, fixture["asset_id"])

    def test_review_fixture_pack_has_eight_unique_hash_bound_identities(self) -> None:
        fixture = json.loads((ROOT / "docs/evidence/multi-direction-runtime-v0160/synthetic-fixture-manifest-v0160.json").read_text(encoding="utf-8"))
        self.assertEqual(fixture["manifest_type"], "TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE")
        self.assertEqual(fixture["direction_count"], 8)
        self.assertEqual(fixture["unique_identity_count"], 8)
        self.assertEqual(len({item["sha256"] for item in fixture["fixtures"]}), 8)
        self.assertTrue(all((ROOT / item["path"]).is_file() for item in fixture["fixtures"]))

    def test_all_eight_ids_are_addressable_without_claiming_coverage(self) -> None:
        results = {direction: self.resolver.resolve("death_animation_front", direction) for direction in CANONICAL_DIRECTIONS}
        self.assertEqual(results["south"].error_code, None)
        for direction in CANONICAL_DIRECTIONS[1:]:
            self.assertEqual(results[direction].error_code, "DIRECTION_ASSET_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
