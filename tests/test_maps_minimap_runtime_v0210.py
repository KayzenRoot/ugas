"""Focused contract tests for the v0.21.0 maps/minimap foundation."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

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
    map_cache_key,
    map_manifest_hash,
    map_to_minimap,
    minimap_cell_geometry,
    minimap_cache_key,
    minimap_to_map,
    render_minimap_base,
    validate_chunk_partition,
    validate_historical_authority,
    validate_map_document,
    validate_raster_cell_geometry,
    validate_visibility,
)
from scripts.validation.run_maps_minimap_runtime_v0210 import (
    APPROVED_MERGE_COMMIT,
    ENVIRONMENT_MANIFEST,
    ITEM_PROP_MANIFEST,
    make_map,
    load_json,
    _gate,
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

    def test_center_y_up_projection_inverse_roundtrip(self) -> None:
        beta = make_map("unit-map-beta", "unit-r1", 7, 4, 3, 2, load_json(ENVIRONMENT_MANIFEST), self.env_authority, self.prop_authority, coordinate_origin="CENTER", grid_orientation="Y_UP")
        for point in ({"x": 0.5, "y": 0.5}, {"x": 6.5, "y": 3.5}):
            projected = map_to_minimap(point, beta)
            recovered = minimap_to_map({"x": projected[0], "y": projected[1]}, beta)
            self.assertAlmostEqual(point["x"], recovered[0], places=9)
            self.assertAlmostEqual(point["y"], recovered[1], places=9)

    def test_top_left_y_down_raster_cell_has_real_2d_geometry(self) -> None:
        geometry = minimap_cell_geometry(self.map, self.map["cells"][0])
        self.assertLess(geometry["projected_corners"][0][1], geometry["projected_corners"][1][1])
        self.assertGreater(geometry["pixel_width"], 0)
        self.assertGreater(geometry["pixel_height"], 0)
        self.assertEqual(validate_raster_cell_geometry(self.map, geometry)["status"], "MINIMAP_RASTER_CELL_GEOMETRY_VALID")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "alpha.png"
            render_minimap_base(self.map, output)
            with Image.open(output) as image:
                self.assertGreater(image.size[0], 0)
                self.assertGreater(image.size[1], 0)

    def test_center_y_up_raster_cell_normalizes_reversed_vertical_bounds(self) -> None:
        beta = make_map("unit-map-beta", "unit-r1", 7, 4, 3, 2, load_json(ENVIRONMENT_MANIFEST), self.env_authority, self.prop_authority, coordinate_origin="CENTER", grid_orientation="Y_UP")
        geometry = minimap_cell_geometry(beta, beta["cells"][0])
        self.assertGreater(geometry["projected_corners"][0][1], geometry["projected_corners"][1][1])
        self.assertLess(geometry["y_min"], geometry["y_max"])
        self.assertGreater(geometry["pixel_width"] * geometry["pixel_height"], 0)
        self.assertEqual(validate_raster_cell_geometry(beta, geometry)["status"], "MINIMAP_RASTER_CELL_GEOMETRY_VALID")
        collapsed = deepcopy(geometry)
        collapsed["y_min"] = collapsed["y_max"]
        collapsed["pixel_height"] = 1
        collapsed["pixel_rect"][3] = collapsed["pixel_rect"][1]
        with self.assertRaisesRegex(MapsMinimapContractError, "MINIMAP_RASTER_CELL_GEOMETRY_INVALID"):
            validate_raster_cell_geometry(beta, collapsed)
        with tempfile.TemporaryDirectory() as directory:
            render_minimap_base(beta, Path(directory) / "beta.png")

    def test_gate_accepts_only_exact_true_bool(self) -> None:
        observations = (True, False, None, 0, 1, [], ["x"], "", "x", {}, {"x": 1})
        for observed in observations:
            gates: dict[str, dict[str, object]] = {}
            _gate(gates, "probe", lambda observed=observed: observed, "strict bool probe")
            expected_pass = type(observed) is bool and observed is True
            self.assertEqual(gates["probe"]["status"], "PASS" if expected_pass else "FAIL")
            self.assertEqual(gates["probe"]["observed"], observed)
            self.assertEqual(gates["probe"]["observed_type"], type(observed).__name__)

    @staticmethod
    def _git_blob_sha(value: bytes) -> str:
        header = f"blob {len(value)}\0".encode("ascii")
        return hashlib.sha1(header + value).hexdigest()

    def test_historical_validator_is_raw_byte_and_blob_exact(self) -> None:
        authority = b"approved\nline\n"
        authority_blob = self._git_blob_sha(authority)
        result = validate_historical_authority(
            authority,
            authority,
            authority_ref="main:historical.json",
            authority_blob=authority_blob,
            candidate_blob=authority_blob,
            authority_commit_sha="main-commit",
            candidate_commit_sha="head-commit",
        )
        self.assertTrue(result["byte_identical"])
        self.assertEqual(result["authority_blob_sha"], authority_blob)
        self.assertEqual(result["candidate_blob_sha"], authority_blob)
        self.assertEqual(result["candidate_sha256"], hashlib.sha256(authority).hexdigest())

        line_ending_mutation = authority.replace(b"\n", b"\r\n")
        with self.assertRaisesRegex(MapsMinimapContractError, "HISTORICAL_EVIDENCE_MUTATION_REJECTED"):
            validate_historical_authority(
                line_ending_mutation,
                authority,
                authority_ref="main:historical.json",
                authority_blob=authority_blob,
                candidate_blob=self._git_blob_sha(line_ending_mutation),
                authority_commit_sha="main-commit",
                candidate_commit_sha="head-commit",
                candidate_sha256=hashlib.sha256(line_ending_mutation).hexdigest(),
            )

        with self.assertRaisesRegex(MapsMinimapContractError, "HISTORICAL_EVIDENCE_MUTATION_REJECTED"):
            validate_historical_authority(
                authority,
                authority,
                authority_ref="main:historical.json",
                authority_blob=authority_blob,
                candidate_blob="different-blob",
                authority_commit_sha="main-commit",
                candidate_commit_sha="head-commit",
            )

    def test_projection_rejects_broken_origin_semantics(self) -> None:
        broken = deepcopy(self.map)
        broken["minimap"]["projection"]["origin"] = "CENTER"
        with self.assertRaisesRegex(MapsMinimapContractError, "MINIMAP_ORIGIN_SEMANTICS_INVALID"):
            map_to_minimap({"x": 0.5, "y": 0.5}, broken)

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

    def test_map_cache_key_changes_for_same_id_revision_changed_content(self) -> None:
        original = map_cache_key(self.map, 0, 0)
        changed = deepcopy(self.map)
        changed["cells"][0]["occupancy"]["occupied"] = not changed["cells"][0]["occupancy"]["occupied"]
        changed["provenance"]["map_hash"] = map_manifest_hash(changed)
        self.assertNotEqual(original, map_cache_key(changed, 0, 0))

    def test_production_snapshot_is_observed_empty(self) -> None:
        registry = MapRegistry(production=True, environment_authority=self.env_authority, items_props_authority=self.prop_authority)
        self.assertEqual(registry.snapshot()["entry_count"], 0)
        self.assertEqual(registry.snapshot()["entries"], [])

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
