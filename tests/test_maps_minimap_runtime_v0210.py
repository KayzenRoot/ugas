"""Focused contract tests for the v0.21.0 maps/minimap foundation."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from ugas.maps_minimap_runtime_v0210 import (
    MapsMinimapContractError,
    MapMinimapCache,
    MapRegistry,
    build_chunk_index,
    build_environment_authority,
    build_items_props_authority,
    cell_to_chunk,
    chunk_to_cell,
    compare_generated_outputs,
    map_manifest_hash,
    map_to_minimap,
    minimap_cache_key,
    minimap_to_map,
    validate_chunk_partition,
    validate_map_document,
    validate_visibility,
)
from scripts.validation.run_maps_minimap_runtime_v0210 import (
    APPROVED_MERGE_COMMIT,
    ENVIRONMENT_MANIFEST,
    ITEM_PROP_MANIFEST,
    make_map,
    load_json,
)


class MapsMinimapRuntimeV0210Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        env = load_json(ENVIRONMENT_MANIFEST)
        props = load_json(ITEM_PROP_MANIFEST)
        cls.env_authority = build_environment_authority(env, approved_merge_commit=APPROVED_MERGE_COMMIT, source_path="fixture.json")
        cls.prop_authority = build_items_props_authority(props, source_path="props.json")
        cls.map = make_map("unit-map-alpha", "unit-r1", 6, 5, 3, 2, env, cls.env_authority, cls.prop_authority)

    def test_valid_map_binds_both_authorities(self) -> None:
        result = validate_map_document(self.map, self.env_authority, self.prop_authority)
        self.assertEqual(result["status"], "MAP_DOCUMENT_VALID")

    def test_map_hash_changes_when_semantic_cell_changes(self) -> None:
        changed = deepcopy(self.map)
        changed["cells"][0]["occupancy"]["occupied"] = not changed["cells"][0]["occupancy"]["occupied"]
        self.assertNotEqual(map_manifest_hash(self.map), map_manifest_hash(changed))

    def test_chunk_partition_is_exact_and_round_trips(self) -> None:
        chunks = build_chunk_index(self.map)
        self.assertEqual(validate_chunk_partition(self.map, chunks)["status"], "CHUNK_PARTITION_VALID")
        for x in range(self.map["width_tiles"]):
            for y in range(self.map["height_tiles"]):
                cx, cy, lx, ly = cell_to_chunk(x, y, self.map["chunk_width_tiles"], self.map["chunk_height_tiles"])
                self.assertEqual(chunk_to_cell(cx, cy, lx, ly, self.map["chunk_width_tiles"], self.map["chunk_height_tiles"]), (x, y))

    def test_chunk_coverage_mutation_rejects(self) -> None:
        chunks = build_chunk_index(self.map)
        chunks[0]["cells"].pop()
        with self.assertRaisesRegex(MapsMinimapContractError, "CHUNK_PARTITION_COVERAGE_INVALID"):
            validate_chunk_partition(self.map, chunks)

    def test_projection_inverse_roundtrip(self) -> None:
        for point in ({"x": 0.5, "y": 0.5}, {"x": 5.5, "y": 4.5}):
            projected = map_to_minimap(point, self.map)
            recovered = minimap_to_map({"x": projected[0], "y": projected[1]}, self.map)
            self.assertAlmostEqual(point["x"], recovered[0], places=9)
            self.assertAlmostEqual(point["y"], recovered[1], places=9)

    def test_projection_rejects_outside_minimap(self) -> None:
        with self.assertRaisesRegex(MapsMinimapContractError, "MINIMAP_POINT_OUT_OF_BOUNDS"):
            minimap_to_map({"x": -1, "y": 0}, self.map)

    def test_visibility_masks_have_map_dimensions(self) -> None:
        validate_visibility(self.map)
        broken = deepcopy(self.map)
        broken["visibility"]["masks"]["VISIBLE"].pop()
        with self.assertRaisesRegex(MapsMinimapContractError, "VISIBILITY_MASK_DIMENSIONS_INVALID"):
            validate_visibility(broken)

    def test_stale_cache_isolated_by_map_identity(self) -> None:
        cache = MapMinimapCache()
        cache.put_map_chunk(self.map, 0, 0)
        other = deepcopy(self.map)
        other["map_id"] = "unit-map-beta"
        other["provenance"]["map_hash"] = map_manifest_hash(other)
        with self.assertRaisesRegex(MapsMinimapContractError, "STALE_MAP_MINIMAP_CACHE_CONTEXT"):
            cache.resolve_map_chunk(other, 0, 0)

    def test_cache_key_contains_projection_and_map_identity(self) -> None:
        key = minimap_cache_key(self.map)
        self.assertEqual(len(key), 64)
        changed = deepcopy(self.map)
        changed["minimap"]["projection"]["renderer_revision"] = "different"
        self.assertNotEqual(key, minimap_cache_key(changed))

    def test_production_registry_rejects_test_fixture(self) -> None:
        registry = MapRegistry(production=True, environment_authority=self.env_authority, items_props_authority=self.prop_authority)
        with self.assertRaisesRegex(MapsMinimapContractError, "TEST_FIXTURE_IN_PRODUCTION_REGISTRY"):
            registry.register(self.map)

    def test_production_routing_enabled_rejects(self) -> None:
        registry = MapRegistry(production=False, production_routing="ENABLED", environment_authority=self.env_authority, items_props_authority=self.prop_authority)
        with self.assertRaisesRegex(MapsMinimapContractError, "PRODUCTION_ROUTING_ENABLED"):
            registry.register(self.map)

    def test_direct_asset_path_rejects(self) -> None:
        broken = deepcopy(self.map)
        broken["cells"][0]["layers"]["ground"]["asset_path"] = "tiles.png"
        with self.assertRaisesRegex(MapsMinimapContractError, "DIRECT_ENVIRONMENT_ASSET_PATH_IN_MAP"):
            validate_map_document(broken, self.env_authority, self.prop_authority)

    def test_marker_identity_rejects_duplicate(self) -> None:
        broken = deepcopy(self.map)
        broken["markers"].append(deepcopy(broken["markers"][0]))
        with self.assertRaisesRegex(MapsMinimapContractError, "DUPLICATE_MARKER_ID"):
            validate_map_document(broken, self.env_authority, self.prop_authority)

    def test_deterministic_outputs_compare_and_detect_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = Path(first_dir); second = Path(second_dir)
            for path in (first / "nested", second / "nested"):
                path.mkdir(parents=True)
            (first / "nested" / "output.bin").write_bytes(b"same")
            (second / "nested" / "output.bin").write_bytes(b"same")
            self.assertTrue(compare_generated_outputs(first, second)["equal"])
            (second / "nested" / "output.bin").write_bytes(b"changed")
            with self.assertRaisesRegex(MapsMinimapContractError, "NONDETERMINISTIC_SECOND_MAP_MINIMAP_OUTPUT"):
                compare_generated_outputs(first, second)


if __name__ == "__main__":
    unittest.main()
