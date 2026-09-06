"""Focused executable tests for the v0.20.0 environment foundation."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ugas.environment_tileset_runtime_v0200 import (  # noqa: E402
    CARDINAL_ONLY,
    EIGHT_NEIGHBOR,
    EnvironmentTileRegistry,
    EnvironmentTileResolver,
    EnvironmentTilesetContractError,
    ResolverRequest,
    compare_generated_outputs,
    compare_seam_bytes,
    decode_adjacency_mask,
    encode_adjacency_mask,
    generate_fixture_pack,
    tile_to_world,
    validate_grid_roundtrip,
    validate_tileset_manifest,
    world_to_tile,
)


class EnvironmentTilesetRuntimeTests(unittest.TestCase):
    def test_fixed_mask_order_and_policy(self):
        mask = encode_adjacency_mask({"N": True, "E": True, "S": False, "W": True}, CARDINAL_ONLY)
        self.assertEqual(1 | 4 | 64, mask)
        self.assertEqual(mask, encode_adjacency_mask(decode_adjacency_mask(mask, CARDINAL_ONLY), CARDINAL_ONLY))
        with self.assertRaisesRegex(EnvironmentTilesetContractError, "DIAGONAL_NOT_ALLOWED"):
            encode_adjacency_mask({"NE": True}, CARDINAL_ONLY)
        self.assertEqual(255, encode_adjacency_mask({name: True for name in ("N", "NE", "E", "SE", "S", "SW", "W", "NW")}, EIGHT_NEIGHBOR))

    def test_metric_conversion_is_deterministic_and_round_trips(self):
        metrics = {"tile_width": 16, "tile_height": 16, "atlas_width": 96, "atlas_height": 16, "origin": "TOP_LEFT", "grid_orientation": "Y_DOWN"}
        self.assertEqual((32.0, 48.0), tile_to_world(2, 3, metrics))
        self.assertEqual((2, 3), world_to_tile(32.0, 48.0, metrics))
        self.assertTrue(validate_grid_roundtrip(metrics, [(0, 0), (2, 3), (-3, 4)]))

    def test_fixture_manifest_binds_standalone_and_atlas_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = generate_fixture_pack(root)
            result = validate_tileset_manifest(root, manifest)
            self.assertEqual("ENVIRONMENT_TILESET_MANIFEST_VALID", result["status"])
            self.assertEqual(12, result["tile_count"])

    def test_resolver_returns_complete_identity_and_rejects_unsupported_transition(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); manifest = generate_fixture_pack(root)
            resolver = EnvironmentTileResolver(manifest, root)
            request = ResolverRequest(manifest["tileset_id"], "temperate_cardinal", manifest["tiles"][0]["tile_id"], "ground_base", CARDINAL_ONLY, {"N": True})
            result = resolver.resolve(request)
            for key in ("tileset_id", "tileset_revision", "terrain_family_id", "variant_id", "variant_revision", "layer", "adjacency_policy", "adjacency_mask", "tile_id", "atlas_revision", "content_hash", "cache_key"):
                self.assertTrue(result[key])
            self.assertEqual(result, resolver.get_cached(result))
            unsupported = ResolverRequest(manifest["tileset_id"], "temperate_cardinal", manifest["tiles"][0]["tile_id"], "ground_base", CARDINAL_ONLY, {"N": True, "E": True, "S": True, "W": True})
            with self.assertRaisesRegex(EnvironmentTilesetContractError, "UNSUPPORTED_TRANSITION"):
                resolver.resolve(unsupported)

    def test_one_pixel_seam_mutation_is_rejected_from_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); manifest = generate_fixture_pack(root)
            left = root / manifest["tiles"][0]["binding"]["artifact_path"]
            right = root / manifest["tiles"][1]["binding"]["artifact_path"]
            changed = root / "changed.png"
            with Image.open(left) as image:
                image = image.convert("RGBA"); pixel = image.getpixel((image.width - 1, image.height - 1)); image.putpixel((image.width - 1, image.height - 1), ((pixel[0] + 1) % 256, pixel[1], pixel[2], pixel[3])); image.save(changed, format="PNG", optimize=False, compress_level=9)
            with self.assertRaisesRegex(EnvironmentTilesetContractError, "SEAM_INCOMPATIBLE"):
                compare_seam_bytes(changed, right)

    def test_variant_provenance_and_production_boundary_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); manifest = generate_fixture_pack(root)
            mutated = copy.deepcopy(manifest); mutated["variants"][0]["overrides"]["damage"] = 1
            with self.assertRaisesRegex(EnvironmentTilesetContractError, "VARIANT_OVERRIDE_FORBIDDEN"):
                validate_tileset_manifest(root, mutated)
            registry = EnvironmentTileRegistry(production=True)
            with self.assertRaisesRegex(EnvironmentTilesetContractError, "TEST_FIXTURE_IN_PRODUCTION_REGISTRY"):
                registry.register(manifest)
            self.assertEqual({"entries": 0}, registry.cache_stats())

    def test_two_fixture_outputs_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as first_directory, tempfile.TemporaryDirectory() as second_directory:
            first = Path(first_directory); second = Path(second_directory)
            generate_fixture_pack(first); generate_fixture_pack(second)
            result = compare_generated_outputs(first, second)
            self.assertTrue(result["equal"])
            self.assertEqual([], result["differences"])


if __name__ == "__main__":
    unittest.main()
