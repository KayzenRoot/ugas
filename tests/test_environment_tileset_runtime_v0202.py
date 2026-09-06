"""Focused executable tests for the v0.20.2 environment QA-integrity correction."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ugas.environment_tileset_runtime_v0202 import (  # noqa: E402
    CARDINAL_ONLY,
    CLASS_TO_LAYER,
    EnvironmentTileResolver,
    EnvironmentTileRegistry,
    EnvironmentTilesetContractError,
    ProductionRoutingPolicy,
    ResolverRequest,
    generate_fixture_pack,
    materialize_tile_variant,
    tile_to_world,
    validate_effective_tile_variant,
    validate_grid_roundtrip,
    validate_resolution_independence,
    validate_tileset_manifest,
    world_to_tile,
)


class EnvironmentTilesetRuntimeV0202Tests(unittest.TestCase):
    def _fixture(self):
        directory = tempfile.TemporaryDirectory()
        root = Path(directory.name)
        manifest = generate_fixture_pack(root)
        self.addCleanup(directory.cleanup)
        return root, manifest

    def test_manifest_has_mask_specific_class_layer_bound_tiles(self):
        root, manifest = self._fixture()
        result = validate_tileset_manifest(root, manifest)
        self.assertEqual("ENVIRONMENT_TILESET_MANIFEST_VALID", result["status"])
        self.assertGreaterEqual(result["autotile_binding_count"], 100)
        self.assertTrue(all(item["target_layer_role"] == CLASS_TO_LAYER[item["target_class_id"]] for family in manifest["terrain_families"] for item in family["autotile_variants"]))

    def test_resolver_exposes_requested_and_resolved_identity(self):
        root, manifest = self._fixture()
        resolver = EnvironmentTileResolver(manifest, root)
        tile = next(item for item in manifest["tiles"] if item["is_base_tile"] and item["class_id"] == "ground_terrain")
        result = resolver.resolve(ResolverRequest(manifest["tileset_id"], "temperate_cardinal", tile["tile_id"], "ground_terrain", "ground_base", CARDINAL_ONLY, {"N": True}))
        self.assertEqual("ground_terrain", result["requested_class_id"])
        self.assertEqual("ground_terrain", result["resolved_class_id"])
        self.assertEqual("ground_base", result["requested_layer"])
        self.assertEqual("ground_base", result["resolved_layer"])
        self.assertEqual(result, resolver.get_cached(result))

    def test_class_and_layer_mismatches_fail_closed(self):
        root, manifest = self._fixture()
        tile = next(item for item in manifest["tiles"] if item["is_base_tile"] and item["class_id"] == "path_road")
        resolver = EnvironmentTileResolver(manifest, root)
        with self.assertRaisesRegex(EnvironmentTilesetContractError, "TILE_CLASS_MISMATCH"):
            resolver.resolve(ResolverRequest(manifest["tileset_id"], "temperate_cardinal", tile["tile_id"], "ground_terrain", "ground_overlay", CARDINAL_ONLY, {"N": True}))
        ground = next(item for item in manifest["tiles"] if item["is_base_tile"] and item["class_id"] == "ground_terrain")
        with self.assertRaisesRegex(EnvironmentTilesetContractError, "TILE_LAYER_MISMATCH"):
            resolver.resolve(ResolverRequest(manifest["tileset_id"], "temperate_cardinal", ground["tile_id"], "ground_terrain", "structure", CARDINAL_ONLY, {"N": True}))

    def test_world_units_are_resolution_independent(self):
        _, manifest = self._fixture()
        metrics = manifest["metrics"]
        self.assertEqual((3.0, 5.0), tile_to_world(3, 5, metrics))
        self.assertEqual((3, 5), world_to_tile(3.0, 5.0, metrics))
        self.assertTrue(validate_grid_roundtrip(metrics, [(0, 0), (2, 3), (-3, 4)]))
        self.assertEqual("WORLD_PIXEL_SCALE_INDEPENDENT", validate_resolution_independence(metrics)["status"])

    def test_effective_variant_is_materialized_and_revalidated(self):
        root, manifest = self._fixture()
        tiles = {item["tile_id"]: item for item in manifest["tiles"]}
        atlases = {item["terrain_family_id"]: item["atlas"] for item in manifest["terrain_families"]}
        variant = manifest["variants"][0]
        effective = materialize_tile_variant(tiles[variant["parent_tile_id"]], variant)
        result = validate_effective_tile_variant(effective, variant, {"root": root, "metrics": manifest["metrics"], "tiles": tiles, "atlases": atlases})
        self.assertEqual("EFFECTIVE_TILE_VARIANT_VALID", result["status"])

    def test_variant_and_cache_cross_identity_fail_closed(self):
        root, manifest = self._fixture()
        resolver = EnvironmentTileResolver(manifest, root)
        tile = next(item for item in manifest["tiles"] if item["is_base_tile"] and item["class_id"] == "ground_terrain")
        result = resolver.resolve(ResolverRequest(manifest["tileset_id"], "temperate_cardinal", tile["tile_id"], "ground_terrain", "ground_base", CARDINAL_ONLY, {"N": True}))
        stale = copy.deepcopy(result)
        stale["requested_class_id"] = "path_road"
        with self.assertRaisesRegex(EnvironmentTilesetContractError, "STALE_CACHE_CROSS_CLASS_LAYER"):
            resolver.get_cached(stale)
        mutation = copy.deepcopy(manifest)
        mutation["variants"][0]["overrides"]["gameplay"] = {"damage": 1}
        with self.assertRaisesRegex(EnvironmentTilesetContractError, "VARIANT_OVERRIDE_FORBIDDEN"):
            validate_tileset_manifest(root, mutation)

    def test_supported_mask_cross_product_is_exact(self):
        root, manifest = self._fixture()
        for family in manifest["terrain_families"]:
            expected = {(class_id, mask) for class_id in manifest["classes"] for mask in family["supported_masks"]}
            observed = {(item["target_class_id"], item["adjacency_mask"]) for item in family["autotile_variants"]}
            self.assertEqual(expected, observed)
        self.assertEqual("ENVIRONMENT_TILESET_MANIFEST_VALID", validate_tileset_manifest(root, manifest)["status"])

    def test_production_registry_blocks_and_requires_semantic_validation(self):
        root, manifest = self._fixture()
        with self.assertRaisesRegex(EnvironmentTilesetContractError, "TEST_FIXTURE_IN_PRODUCTION_REGISTRY"):
            EnvironmentTileRegistry(production=True).register(manifest)
        candidate = copy.deepcopy(manifest)
        candidate.update({"test_only": False, "production_safe": True, "production_approved": True})
        with self.assertRaisesRegex(EnvironmentTilesetContractError, "PRODUCTION_ROUTING_BLOCKED"):
            EnvironmentTileRegistry(production=True).register(candidate)
        candidate["production_routing"] = "ENABLED"
        with self.assertRaisesRegex(EnvironmentTilesetContractError, "MANIFEST_VALIDATION_REQUIRED"):
            EnvironmentTileRegistry(production=True, production_policy=ProductionRoutingPolicy("ENABLED")).register(candidate)

    def test_center_origin_has_distinct_exact_inverse_semantics(self):
        _, manifest = self._fixture()
        top_left = dict(manifest["metrics"])
        center = dict(manifest["metrics"]); center["origin"] = "CENTER"
        self.assertNotEqual(tile_to_world(0, 0, top_left), tile_to_world(0, 0, center))
        for origin in ("TOP_LEFT", "CENTER"):
            for orientation in ("Y_DOWN", "Y_UP"):
                metrics = dict(manifest["metrics"]); metrics.update({"origin": origin, "grid_orientation": orientation})
                self.assertTrue(validate_grid_roundtrip(metrics, [(0, 0), (1, 1), (-2, 3)]))

    def test_variant_identity_fields_are_authoritative(self):
        root, manifest = self._fixture()
        for field, expected in (("content_hash", "VARIANT_CONTENT_HASH_MISMATCH"), ("atlas_revision", "VARIANT_ATLAS_REVISION_MISMATCH")):
            mutation = copy.deepcopy(manifest)
            mutation["variants"][0][field] = "tampered"
            with self.assertRaisesRegex(EnvironmentTilesetContractError, expected):
                validate_tileset_manifest(root, mutation)


if __name__ == "__main__":
    unittest.main()
