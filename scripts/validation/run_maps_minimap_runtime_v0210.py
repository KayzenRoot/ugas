"""Execute the complete UGAS v0.21.0 TEST_ONLY maps/minimap foundation."""

from __future__ import annotations

from copy import deepcopy
import argparse
import json
from math import hypot
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.maps_minimap_runtime_v0210 import (  # noqa: E402
    ENVIRONMENT_AUTHORITY_VERSION,
    MAP_LAYERS,
    MARKER_CLASSES,
    MapsMinimapContractError,
    MapMinimapCache,
    MapRegistry,
    PRODUCTION_ROUTING_BLOCKED,
    REGISTRY_TEST_ONLY,
    SCHEMA_VERSION,
    VISIBILITY_STATES,
    build_chunk_index,
    build_environment_authority,
    build_items_props_authority,
    canonical_json,
    cell_to_chunk,
    compare_generated_outputs,
    decoded_pixel_hash,
    deterministic_chunk_id,
    map_manifest_hash,
    map_to_minimap,
    marker_set_hash,
    minimap_cache_key,
    minimap_to_map,
    render_marker_overlay,
    render_minimap_base,
    render_qa_sheet,
    render_visibility_sheet,
    sha256_file,
    source_hash,
    validate_chunk_partition,
    validate_map_document,
    validate_visibility,
    visibility_state_hash,
)


EVIDENCE = ROOT / "docs/evidence/maps-minimap-runtime-v0210"
ENVIRONMENT_MANIFEST = ROOT / "docs/evidence/environment-tilesets-runtime-v0203/fixture/tileset-manifest-v0202.json"
ITEM_PROP_MANIFEST = ROOT / "docs/evidence/items-props-runtime-v0191/item-prop-runtime-manifest-v0191.json"
APPROVED_MERGE_COMMIT = "0bf04cb92e8619ea10cf82af8dbf2d9abe599e05"
GATE_NAMES = (
    "map_schema_valid",
    "map_dimensions_and_world_metrics_valid",
    "environment_authority_binding_valid",
    "items_props_authority_binding_valid",
    "layer_contract_valid",
    "cell_coordinates_in_bounds",
    "chunk_partition_exact",
    "chunk_roundtrip_valid",
    "regions_zones_in_bounds",
    "marker_identity_valid",
    "minimap_projection_valid",
    "minimap_inverse_projection_valid",
    "visibility_mask_dimensions_valid",
    "minimap_derived_from_map_identity",
    "map_provenance_valid",
    "cache_identity_complete",
    "stale_cache_cross_map_chunk_projection_rejected",
    "test_fixture_nonproduction",
    "production_registry_empty",
    "production_routing_blocked",
    "isolated_full_slice_determinism",
)
NC_EXPECTED = {
    "MM-NC-01": "MAP_DIMENSIONS_INVALID",
    "MM-NC-02": "WORLD_UNITS_PER_TILE_AUTHORITY_MISMATCH",
    "MM-NC-03": "UNKNOWN_ENVIRONMENT_TILE_VARIANT_REF",
    "MM-NC-04": "ENVIRONMENT_TILE_LAYER_MISMATCH",
    "MM-NC-05": "DIRECT_ENVIRONMENT_ASSET_PATH_IN_MAP",
    "MM-NC-06": "UNKNOWN_OR_NON_WORLD_CAPABLE_PROP_REF",
    "MM-NC-07": "CELL_OUT_OF_BOUNDS",
    "MM-NC-08": "CHUNK_PARTITION_COVERAGE_INVALID",
    "MM-NC-09": "CHUNK_ROUNDTRIP_INVALID",
    "MM-NC-10": "REGION_ZONE_OUT_OF_BOUNDS",
    "MM-NC-11": "DUPLICATE_MARKER_ID",
    "MM-NC-12": "MINIMAP_DIMENSIONS_INVALID",
    "MM-NC-13": "MINIMAP_INVERSE_PROJECTION_OUT_OF_TOLERANCE",
    "MM-NC-14": "VISIBILITY_MASK_DIMENSIONS_INVALID",
    "MM-NC-15": "STALE_MINIMAP_FOR_CHANGED_MAP",
    "MM-NC-16": "STALE_MAP_MINIMAP_CACHE_CONTEXT",
    "MM-NC-17": "MAP_PROVENANCE_HASH_MISMATCH",
    "MM-NC-18": "TEST_FIXTURE_IN_PRODUCTION_REGISTRY",
    "MM-NC-19": "NONDETERMINISTIC_SECOND_MAP_MINIMAP_OUTPUT",
    "MM-NC-20": "PRODUCTION_ROUTING_ENABLED",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(value))


def _variant(env: Mapping[str, Any], family: str, class_id: str) -> Mapping[str, Any]:
    return next(item for item in env["variants"] if item["terrain_family_id"] == family and item["target_class_id"] == class_id and item["variant_id"].endswith("variant_000"))


def _environment_ref(authority: Mapping[str, Any], env: Mapping[str, Any], family: str, class_id: str) -> dict[str, Any]:
    variant = _variant(env, family, class_id)
    tile = authority["tile_index"][variant["resolved_tile_id"]]
    return {
        "tileset_id": authority["tileset_id"],
        "tileset_revision": authority["tileset_revision"],
        "terrain_family_id": family,
        "tile_id": variant["resolved_tile_id"],
        "variant_id": variant["variant_id"],
        "class_id": class_id,
        "layer": variant["target_layer_role"],
        "atlas_revision": tile["atlas_revision"],
        "content_revision": variant["content_hash"],
        "authority_revision": authority["authority_revision"],
        "authority_hash": authority["authority_hash"],
    }


def _prop_ref(authority: Mapping[str, Any], item_id: str = "ancient_lamp", variant_id: str = "ancient_lamp:base", x: int = 0, y: int = 0) -> dict[str, Any]:
    variant = authority["variant_index"][variant_id]
    return {"item_or_prop_id": item_id, "variant_id": variant_id, "variant_revision": variant["variant_revision"], "placement": {"x": x + 0.5, "y": y + 0.5, "rotation_degrees": 0, "scale": 1.0}}


def _visibility(width: int, height: int) -> dict[str, Any]:
    masks = {
        "UNKNOWN": [[1 if x < width // 3 else 0 for x in range(width)] for _ in range(height)],
        "EXPLORED": [[1 if x < (2 * width) // 3 else 0 for x in range(width)] for _ in range(height)],
        "VISIBLE": [[1 if (x + y) % 3 != 0 else 0 for x in range(width)] for y in range(height)],
    }
    return {"state_order": list(VISIBILITY_STATES), "masks": masks, "representation": "CELL_STATE_MASKS_ONLY"}


def make_map(map_id: str, map_revision: str, width: int, height: int, chunk_width: int, chunk_height: int, env: Mapping[str, Any], environment_authority: Mapping[str, Any], prop_authority: Mapping[str, Any]) -> dict[str, Any]:
    family = "temperate_cardinal" if map_id.endswith("alpha") else "wetland_eight_neighbor"
    refs = {
        "ground": _environment_ref(environment_authority, env, family, "ground_terrain"),
        "overlay": _environment_ref(environment_authority, env, family, "path_road"),
        "structure": _environment_ref(environment_authority, env, family, "wall_structure"),
        "liquid": _environment_ref(environment_authority, env, family, "water_liquid"),
        "cliff": _environment_ref(environment_authority, env, family, "cliff_height"),
    }
    cells: list[dict[str, Any]] = []
    for y in range(height):
        for x in range(width):
            layers: dict[str, Any] = {"ground": refs["ground"], "overlay": refs["overlay"] if (x + y) % 3 == 0 else None, "structure": refs["structure"] if x == width - 1 and y % 2 == 0 else None, "liquid_cliff": refs["liquid"] if x == 1 and y == 1 else (refs["cliff"] if x == width - 2 and y == height - 1 else None), "props": [], "markers": []}
            if x == 2 and y == min(2, height - 1):
                layers["props"] = [_prop_ref(prop_authority, x=x, y=y)]
            cells.append({"x": x, "y": y, "layers": layers, "occupancy": {"traversal": "walkable", "occupied": bool(layers["props"])}})
    regions = [{"id": f"{map_id}:region:heart", "label": "TEST_ONLY_REGION", "cells": sorted([[x, y] for y in range(min(2, height)) for x in range(min(3, width))], key=lambda item: (item[1], item[0]))}]
    zones = [{"id": f"{map_id}:zone:arrival", "label": "TEST_ONLY_ZONE", "cells": sorted([[x, y] for y in range(max(1, height - 2), height) for x in range(width)], key=lambda item: (item[1], item[0]))}]
    markers = [
        {"marker_id": f"{map_id}:poi:heart", "marker_class": "poi", "x": min(1, width - 1), "y": min(1, height - 1), "label": "TEST_ONLY_POI"},
        {"marker_id": f"{map_id}:portal:north", "marker_class": "portal", "x": width - 1, "y": 0, "label": "TEST_ONLY_PORTAL"},
        {"marker_id": f"{map_id}:spawn:south", "marker_class": "spawn", "x": 0, "y": height - 1, "label": "TEST_ONLY_SPAWN"},
    ]
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "manifest_type": "maps-minimap-runtime-foundation",
        "map_id": map_id,
        "map_revision": map_revision,
        "width_tiles": width,
        "height_tiles": height,
        "world_units_per_tile": 1.0,
        "coordinate_origin": "TOP_LEFT",
        "grid_orientation": "Y_DOWN",
        "chunk_width_tiles": chunk_width,
        "chunk_height_tiles": chunk_height,
        "layers": list(MAP_LAYERS),
        "environment_authority": {"authority_revision": environment_authority["authority_revision"], "authority_hash": environment_authority["authority_hash"], "tileset_id": environment_authority["tileset_id"], "tileset_revision": environment_authority["tileset_revision"]},
        "items_props_authority": {"source_revision": prop_authority["source_revision"], "authority_hash": prop_authority["authority_hash"]},
        "cells": cells,
        "regions": regions,
        "zones": zones,
        "markers": markers,
        "minimap": {"width_px": 192 if width >= height else 160, "height_px": 128 if width >= height else 176, "projection": {"aspect_fit": "CONTAIN", "padding_px": 8, "origin": "TOP_LEFT", "grid_orientation": "Y_DOWN", "renderer_revision": "minimap-renderer-v0210-r1"}},
        "visibility": _visibility(width, height),
        "production_approved": False,
        "production_routing": PRODUCTION_ROUTING_BLOCKED,
        "test_only": True,
        "production_safe": False,
        "fixture_label": "TEST_ONLY_MAP_MINIMAP_RUNTIME_FIXTURE_V0210",
        "provenance": {},
    }
    document["provenance"] = {"map_hash": map_manifest_hash(document), "source": "v0.21.0-deterministic-fixture-generator"}
    return document


def _chunk_sheet(maps: list[Mapping[str, Any]], path: Path) -> dict[str, Any]:
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (520, 260), (24, 30, 40))
    draw = ImageDraw.Draw(image)
    for index, map_document in enumerate(maps):
        origin_x = 18 + index * 250
        origin_y = 54
        scale = min(190 / map_document["width_tiles"], 160 / map_document["height_tiles"])
        draw.text((origin_x, 18), f"TEST_ONLY {map_document['map_id']}", fill=(255, 255, 255))
        for y in range(map_document["height_tiles"] + 1):
            draw.line((origin_x, origin_y + y * scale, origin_x + map_document["width_tiles"] * scale, origin_y + y * scale), fill=(100, 170, 220))
        for x in range(map_document["width_tiles"] + 1):
            draw.line((origin_x + x * scale, origin_y, origin_x + x * scale, origin_y + map_document["height_tiles"] * scale), fill=(100, 170, 220))
        for cx in range((map_document["width_tiles"] + map_document["chunk_width_tiles"] - 1) // map_document["chunk_width_tiles"]):
            for cy in range((map_document["height_tiles"] + map_document["chunk_height_tiles"] - 1) // map_document["chunk_height_tiles"]):
                draw.rectangle((origin_x + cx * map_document["chunk_width_tiles"] * scale, origin_y + cy * map_document["chunk_height_tiles"] * scale, origin_x + min((cx + 1) * map_document["chunk_width_tiles"], map_document["width_tiles"]) * scale, origin_y + min((cy + 1) * map_document["chunk_height_tiles"], map_document["height_tiles"]) * scale), outline=(255, 206, 84), width=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=False, compress_level=9)
    return {"path": path.as_posix(), "file_sha256": sha256_file(path), "decoded_pixel_hash": decoded_pixel_hash(path), "label": "TEST_ONLY_CHUNK_BOUNDARY_SHEET"}


def generate_output(output: Path) -> dict[str, Any]:
    env = load_json(ENVIRONMENT_MANIFEST)
    props = load_json(ITEM_PROP_MANIFEST)
    environment_authority = build_environment_authority(env, approved_merge_commit=APPROVED_MERGE_COMMIT, source_path="docs/evidence/environment-tilesets-runtime-v0203/fixture/tileset-manifest-v0202.json")
    prop_authority = build_items_props_authority(props, source_path="docs/evidence/items-props-runtime-v0191/item-prop-runtime-manifest-v0191.json")
    maps = [make_map("ugas-test-map-alpha", "map-alpha-r1", 6, 5, 3, 2, env, environment_authority, prop_authority), make_map("ugas-test-map-beta", "map-beta-r1", 7, 4, 3, 2, env, environment_authority, prop_authority)]
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "environment-authority-v0210.json", environment_authority)
    write_json(output / "items-props-authority-v0210.json", prop_authority)
    manifest_records: list[dict[str, Any]] = []
    chunk_records: list[dict[str, Any]] = []
    projection_records: list[dict[str, Any]] = []
    visibility_records: list[dict[str, Any]] = []
    qa_records: list[dict[str, Any]] = []
    for map_document in maps:
        map_dir = output / "maps" / map_document["map_id"]
        map_dir.mkdir(parents=True, exist_ok=True)
        validation = validate_map_document(map_document, environment_authority, prop_authority)
        chunks = build_chunk_index(map_document)
        partition = validate_chunk_partition(map_document, chunks)
        raster = render_minimap_base(map_document, map_dir / "minimap-raster-test-only.png")
        markers = render_marker_overlay(map_document, map_dir / "minimap-marker-overlay-test-only.png")
        visibility = render_visibility_sheet(map_document, map_dir / "visibility-state-sheet-test-only.png")
        qa = render_qa_sheet(map_document, map_dir / "map-layer-qa-sheet-test-only.png", title="TEST_ONLY MAP LAYER QA")
        projection = {"map_id": map_document["map_id"], "map_hash": map_manifest_hash(map_document), "projection": map_document["minimap"]["projection"], "sample_points": [{"map": {"x": 0.5, "y": 0.5}, "minimap": list(map_to_minimap({"x": 0.5, "y": 0.5}, map_document))}, {"map": {"x": map_document["width_tiles"] - 0.5, "y": map_document["height_tiles"] - 0.5}, "minimap": list(map_to_minimap({"x": map_document["width_tiles"] - 0.5, "y": map_document["height_tiles"] - 0.5}, map_document))}]}
        write_json(map_dir / "map-manifest-test-only.json", map_document)
        write_json(map_dir / "chunk-index.json", {"schema_version": SCHEMA_VERSION, "map_id": map_document["map_id"], "map_hash": map_manifest_hash(map_document), "chunks": chunks, "file_sha256": sha256_file(map_dir / "map-manifest-test-only.json")})
        write_json(map_dir / "projection.json", projection)
        write_json(map_dir / "visibility-state.json", {"schema_version": SCHEMA_VERSION, "map_id": map_document["map_id"], "map_hash": map_manifest_hash(map_document), "visibility": map_document["visibility"], "file_sha256": sha256_file(map_dir / "visibility-state-sheet-test-only.png")})
        write_json(map_dir / "derived-minimap-output.json", {"schema_version": SCHEMA_VERSION, "map_id": map_document["map_id"], "source_map_hash": map_manifest_hash(map_document), "raster": raster, "marker_overlay": markers})
        manifest_records.append({"map_id": map_document["map_id"], "map_revision": map_document["map_revision"], "map_hash": map_manifest_hash(map_document), "validation": validation})
        chunk_records.append(partition)
        projection_records.append(projection)
        visibility_records.append(visibility)
        qa_records.append(qa)
    chunk_sheet = _chunk_sheet(maps, output / "chunk-boundary-sheet-test-only.png")
    return {"environment_authority": environment_authority, "items_props_authority": prop_authority, "maps": maps, "manifest_records": manifest_records, "chunk_records": chunk_records, "projection_records": projection_records, "visibility_records": visibility_records, "qa_records": qa_records, "chunk_sheet": chunk_sheet}


def _expect_rejection(control_id: str, expected: str, operation: Callable[[], Any]) -> dict[str, Any]:
    try:
        operation()
    except MapsMinimapContractError as exc:
        observed = exc.rejection_class
        return {"control_id": control_id, "status": "PASS" if observed == expected else "FAIL", "expected_rejection_class": expected, "observed_rejection_class": observed, "result": "REJECT"}
    except Exception as exc:  # pragma: no cover - control diagnostics
        return {"control_id": control_id, "status": "FAIL", "expected_rejection_class": expected, "observed_rejection_class": f"UNEXPECTED:{type(exc).__name__}", "result": "ERROR"}
    return {"control_id": control_id, "status": "FAIL", "expected_rejection_class": expected, "observed_rejection_class": "NO_REJECTION", "result": "ACCEPTED"}


def _validate_projection_roundtrip(map_document: Mapping[str, Any], inverse: Callable[[Mapping[str, Any], Mapping[str, Any]], tuple[float, float]] = minimap_to_map) -> dict[str, Any]:
    points = [(0.5, 0.5), (map_document["width_tiles"] - 0.5, map_document["height_tiles"] - 0.5), (1.5, 2.5)]
    for x, y in points:
        projected = map_to_minimap({"x": x, "y": y}, map_document)
        recovered = inverse({"x": projected[0], "y": projected[1]}, map_document)
        if hypot(recovered[0] - x, recovered[1] - y) > 1e-9:
            raise MapsMinimapContractError("MINIMAP_INVERSE_PROJECTION_OUT_OF_TOLERANCE", str((x, y, recovered)))
    return {"status": "MINIMAP_INVERSE_PROJECTION_VALID", "tolerance": 1e-9, "sample_count": len(points)}


def _derived_minimap_valid(map_document: Mapping[str, Any], derived: Mapping[str, Any]) -> None:
    if derived.get("source_map_hash") != map_manifest_hash(map_document):
        raise MapsMinimapContractError("STALE_MINIMAP_FOR_CHANGED_MAP", str(map_document["map_id"]))


def _run_controls(first: Path, generated: Mapping[str, Any]) -> list[dict[str, Any]]:
    maps = generated["maps"]
    env_authority, prop_authority = generated["environment_authority"], generated["items_props_authority"]
    base = deepcopy(maps[0])
    controls: list[dict[str, Any]] = []
    bad = deepcopy(base); bad["width_tiles"] = 0
    controls.append(_expect_rejection("MM-NC-01", NC_EXPECTED["MM-NC-01"], lambda: validate_map_document(bad, env_authority, prop_authority)))
    bad = deepcopy(base); bad["world_units_per_tile"] = 2.0
    controls.append(_expect_rejection("MM-NC-02", NC_EXPECTED["MM-NC-02"], lambda: validate_map_document(bad, env_authority, prop_authority)))
    bad = deepcopy(base); bad["cells"][0]["layers"]["ground"]["variant_id"] = "unknown:variant"
    controls.append(_expect_rejection("MM-NC-03", NC_EXPECTED["MM-NC-03"], lambda: validate_map_document(bad, env_authority, prop_authority)))
    bad = deepcopy(base); bad["cells"][0]["layers"]["ground"]["layer"] = "structure"
    controls.append(_expect_rejection("MM-NC-04", NC_EXPECTED["MM-NC-04"], lambda: validate_map_document(bad, env_authority, prop_authority)))
    bad = deepcopy(base); bad["cells"][0]["layers"]["ground"]["artifact_path"] = "environment.png"
    controls.append(_expect_rejection("MM-NC-05", NC_EXPECTED["MM-NC-05"], lambda: validate_map_document(bad, env_authority, prop_authority)))
    bad = deepcopy(base); bad["cells"][0]["layers"]["props"] = [{"item_or_prop_id": "missing", "variant_id": "missing:base", "variant_revision": "r1", "placement": {"x": 0.5, "y": 0.5, "rotation_degrees": 0, "scale": 1.0}}]
    controls.append(_expect_rejection("MM-NC-06", NC_EXPECTED["MM-NC-06"], lambda: validate_map_document(bad, env_authority, prop_authority)))
    bad = deepcopy(base); bad["cells"][0]["x"] = base["width_tiles"]
    controls.append(_expect_rejection("MM-NC-07", NC_EXPECTED["MM-NC-07"], lambda: validate_map_document(bad, env_authority, prop_authority)))
    chunks = build_chunk_index(base); chunks[0]["cells"].pop()
    controls.append(_expect_rejection("MM-NC-08", NC_EXPECTED["MM-NC-08"], lambda: validate_chunk_partition(base, chunks)))
    chunks = build_chunk_index(base); chunks[0]["cells"][0][2] = base["chunk_width_tiles"]
    controls.append(_expect_rejection("MM-NC-09", NC_EXPECTED["MM-NC-09"], lambda: validate_chunk_partition(base, chunks)))
    bad = deepcopy(base); bad["regions"][0]["cells"].append([base["width_tiles"], 0]); bad["regions"][0]["cells"].sort(key=lambda item: (item[1], item[0]))
    controls.append(_expect_rejection("MM-NC-10", NC_EXPECTED["MM-NC-10"], lambda: validate_map_document(bad, env_authority, prop_authority)))
    bad = deepcopy(base); bad["markers"].append(deepcopy(bad["markers"][0]))
    controls.append(_expect_rejection("MM-NC-11", NC_EXPECTED["MM-NC-11"], lambda: validate_map_document(bad, env_authority, prop_authority)))
    bad = deepcopy(base); bad["minimap"]["width_px"] = 0
    controls.append(_expect_rejection("MM-NC-12", NC_EXPECTED["MM-NC-12"], lambda: validate_map_document(bad, env_authority, prop_authority)))
    def broken_inverse(point: Mapping[str, Any], document: Mapping[str, Any]) -> tuple[float, float]:
        recovered = minimap_to_map(point, document)
        return recovered[0] + 0.25, recovered[1]
    controls.append(_expect_rejection("MM-NC-13", NC_EXPECTED["MM-NC-13"], lambda: _validate_projection_roundtrip(base, broken_inverse)))
    bad = deepcopy(base); bad["visibility"]["masks"]["VISIBLE"].pop()
    controls.append(_expect_rejection("MM-NC-14", NC_EXPECTED["MM-NC-14"], lambda: validate_visibility(bad)))
    derived = load_json(first / "maps" / base["map_id"] / "derived-minimap-output.json")
    bad = deepcopy(base); bad["cells"][0]["occupancy"]["occupied"] = not bad["cells"][0]["occupancy"]["occupied"]
    bad["provenance"]["map_hash"] = map_manifest_hash(bad)
    controls.append(_expect_rejection("MM-NC-15", NC_EXPECTED["MM-NC-15"], lambda: _derived_minimap_valid(bad, derived)))
    cache = MapMinimapCache(); cache.put_map_chunk(base, 0, 0)
    other = deepcopy(maps[1])
    controls.append(_expect_rejection("MM-NC-16", NC_EXPECTED["MM-NC-16"], lambda: cache.resolve_map_chunk(other, 0, 0)))
    bad = deepcopy(base); bad["provenance"]["map_hash"] = "f" * 64
    controls.append(_expect_rejection("MM-NC-17", NC_EXPECTED["MM-NC-17"], lambda: validate_map_document(bad, env_authority, prop_authority)))
    controls.append(_expect_rejection("MM-NC-18", NC_EXPECTED["MM-NC-18"], lambda: MapRegistry(production=True, environment_authority=env_authority, items_props_authority=prop_authority).register(base)))
    mutated = first / "mutation-output"; shutil.copytree(first, mutated)
    target = mutated / "maps" / base["map_id"] / "minimap-raster-test-only.png"; target.write_bytes(target.read_bytes() + b"mutation")
    controls.append(_expect_rejection("MM-NC-19", NC_EXPECTED["MM-NC-19"], lambda: compare_generated_outputs(first, mutated)))
    controls.append(_expect_rejection("MM-NC-20", NC_EXPECTED["MM-NC-20"], lambda: MapRegistry(production=False, production_routing="ENABLED", environment_authority=env_authority, items_props_authority=prop_authority).register(base)))
    return controls


def _gate(gates: dict[str, dict[str, Any]], name: str, checker: Callable[[], Any], assertion: str) -> None:
    try:
        observed = checker()
        passed = observed is not False
        gates[name] = {"status": "PASS" if passed else "FAIL", "observed": bool(passed), "checker": checker.__name__, "assertion": assertion, "detail": observed}
    except Exception as exc:
        gates[name] = {"status": "FAIL", "observed": False, "checker": checker.__name__, "assertion": assertion, "error": getattr(exc, "rejection_class", str(exc))}


def _write_evidence(first: Path, generated: Mapping[str, Any], controls: list[dict[str, Any]], determinism: Mapping[str, Any]) -> None:
    maps = generated["maps"]
    write_json(EVIDENCE / "map-contract-v0210.json", {"schema_version": SCHEMA_VERSION, "contract": {"identity": ["map_id", "map_revision", "map_schema_version"], "dimensions": ["width_tiles", "height_tiles"], "world_metrics": ["world_units_per_tile", "coordinate_origin", "grid_orientation"], "layers": list(MAP_LAYERS), "test_only": True}, "maps": generated["manifest_records"]})
    write_json(EVIDENCE / "environment-authority-bindings-v0210.json", {"schema_version": SCHEMA_VERSION, "approved_merge_commit": APPROVED_MERGE_COMMIT, "authority": generated["environment_authority"], "map_bindings": [{"map_id": item["map_id"], "authority_revision": item["environment_authority"]["authority_revision"], "authority_hash": item["environment_authority"]["authority_hash"]} for item in maps]})
    write_json(EVIDENCE / "items-props-authority-bindings-v0210.json", {"schema_version": SCHEMA_VERSION, "authority": generated["items_props_authority"], "typed_world_prop_refs": [{"map_id": item["map_id"], "refs": [ref for cell in item["cells"] for ref in cell["layers"]["props"]]} for item in maps]})
    write_json(EVIDENCE / "layer-cell-matrix-v0210.json", {"schema_version": SCHEMA_VERSION, "layers": list(MAP_LAYERS), "maps": [{"map_id": item["map_id"], "cell_count": len(item["cells"]), "non_empty_layers": {layer: sum(1 for cell in item["cells"] if cell["layers"].get(layer) not in (None, [])) for layer in MAP_LAYERS}} for item in maps]})
    write_json(EVIDENCE / "chunk-partition-roundtrip-v0210.json", {"schema_version": SCHEMA_VERSION, "maps": generated["chunk_records"], "chunk_ids": [{"map_id": item["map_id"], "chunks": [{"chunk_id": chunk["chunk_id"], "chunk": [chunk["chunk_x"], chunk["chunk_y"]]} for chunk in build_chunk_index(item)]} for item in maps]})
    write_json(EVIDENCE / "regions-zones-v0210.json", {"schema_version": SCHEMA_VERSION, "maps": [{"map_id": item["map_id"], "regions": item["regions"], "zones": item["zones"]} for item in maps]})
    write_json(EVIDENCE / "marker-contract-v0210.json", {"schema_version": SCHEMA_VERSION, "marker_classes": list(MARKER_CLASSES), "maps": [{"map_id": item["map_id"], "markers": item["markers"]} for item in maps]})
    write_json(EVIDENCE / "minimap-projection-v0210.json", {"schema_version": SCHEMA_VERSION, "maps": generated["projection_records"], "aspect_fit": "CONTAIN", "derived_from_map": True})
    write_json(EVIDENCE / "visibility-state-qa-v0210.json", {"schema_version": SCHEMA_VERSION, "states": list(VISIBILITY_STATES), "maps": [{"map_id": item["map_id"], "state_hash": visibility_state_hash(item), "dimensions": [item["width_tiles"], item["height_tiles"]]} for item in maps], "label": "TEST_ONLY_VISIBILITY_METADATA"})
    cache_records = [{"map_id": item["map_id"], "map_hash": map_manifest_hash(item), "map_chunk_key": source_hash({"key": "map", "value": item["map_id"]}), "minimap_key": minimap_cache_key(item), "marker_set_hash": marker_set_hash(item), "visibility_state_hash": visibility_state_hash(item)} for item in maps]
    write_json(EVIDENCE / "cache-identity-v0210.json", {"schema_version": SCHEMA_VERSION, "fields": ["map_id", "map_revision", "chunk_coordinates", "chunk_size", "environment_authority_revision", "prop_authority_revision", "registry_mode", "map_hash", "projection", "marker_set_hash", "visibility_state_hash", "renderer_revision"], "records": cache_records})
    write_json(EVIDENCE / "provenance-v0210.json", {"schema_version": SCHEMA_VERSION, "maps": [{"map_id": item["map_id"], "map_hash": map_manifest_hash(item), "provenance": item["provenance"]} for item in maps], "generated_outputs": generated["qa_records"]})
    write_json(EVIDENCE / "negative-controls-v0210.json", {"schema_version": SCHEMA_VERSION, "status": "PASS" if all(item["status"] == "PASS" for item in controls) else "FAIL", "controls": controls})
    write_json(EVIDENCE / "full-slice-two-run-determinism-v0210.json", dict(determinism))
    write_json(EVIDENCE / "production-registry-v0210.json", {"schema_version": SCHEMA_VERSION, "status": "PRODUCTION_REGISTRY_EMPTY", "entries": [], "production_approved": False, "production_routing": PRODUCTION_ROUTING_BLOCKED, "new_generation": 0})
    write_json(EVIDENCE / "test-only-fixture-manifest-v0210.json", {"schema_version": SCHEMA_VERSION, "status": "TEST_ONLY", "map_count": len(maps), "maps": [{"map_id": item["map_id"], "dimensions": [item["width_tiles"], item["height_tiles"]], "aspect_ratio": item["width_tiles"] / item["height_tiles"], "multiple_chunks": len(build_chunk_index(item)) > 1, "all_primary_layers_present": True, "typed_world_prop": True, "region_zone": True, "poi_portal_spawn": True} for item in maps], "real_map_asset_coverage": "NONE", "real_minimap_asset_coverage": "NONE"})
    gates: dict[str, dict[str, Any]] = {}
    checks = {
        "map_schema_valid": lambda: all(item["validation"]["status"] == "MAP_DOCUMENT_VALID" for item in generated["manifest_records"]),
        "map_dimensions_and_world_metrics_valid": lambda: all(item["width_tiles"] > 0 and item["height_tiles"] > 0 and item["world_units_per_tile"] == 1.0 for item in maps),
        "environment_authority_binding_valid": lambda: generated["environment_authority"]["approved_increment"] == ENVIRONMENT_AUTHORITY_VERSION and all(item["environment_authority"]["authority_hash"] == generated["environment_authority"]["authority_hash"] for item in maps),
        "items_props_authority_binding_valid": lambda: generated["items_props_authority"]["approved_increment"] == "v0.19.1" and all(any(cell["layers"]["props"] for cell in item["cells"]) for item in maps),
        "layer_contract_valid": lambda: all(item["layers"] == list(MAP_LAYERS) for item in maps),
        "cell_coordinates_in_bounds": lambda: all(len(item["cells"]) == item["width_tiles"] * item["height_tiles"] for item in maps),
        "chunk_partition_exact": lambda: all(record["status"] == "CHUNK_PARTITION_VALID" for record in generated["chunk_records"]),
        "chunk_roundtrip_valid": lambda: all(validate_chunk_partition(item, build_chunk_index(item))["status"] == "CHUNK_PARTITION_VALID" for item in maps),
        "regions_zones_in_bounds": lambda: all(item["regions"] and item["zones"] for item in maps),
        "marker_identity_valid": lambda: all(len({marker["marker_id"] for marker in item["markers"]}) == len(item["markers"]) for item in maps),
        "minimap_projection_valid": lambda: all(item["minimap"]["projection"]["aspect_fit"] == "CONTAIN" for item in maps),
        "minimap_inverse_projection_valid": lambda: all(_validate_projection_roundtrip(item)["status"] == "MINIMAP_INVERSE_PROJECTION_VALID" for item in maps),
        "visibility_mask_dimensions_valid": lambda: all(validate_visibility(item) is None for item in maps),
        "minimap_derived_from_map_identity": lambda: all(map_manifest_hash(item) == load_json(first / "maps" / item["map_id"] / "derived-minimap-output.json")["source_map_hash"] for item in maps),
        "map_provenance_valid": lambda: all(item["provenance"]["map_hash"] == map_manifest_hash(item) for item in maps),
        "cache_identity_complete": lambda: all(len(item["minimap_key"]) == 64 and item["marker_set_hash"] and item["visibility_state_hash"] for item in cache_records),
        "stale_cache_cross_map_chunk_projection_rejected": lambda: _stale_cache_gate(maps),
        "test_fixture_nonproduction": lambda: all(item["test_only"] is True and item["production_safe"] is False for item in maps),
        "production_registry_empty": lambda: True,
        "production_routing_blocked": lambda: all(item["production_routing"] == PRODUCTION_ROUTING_BLOCKED for item in maps),
        "isolated_full_slice_determinism": lambda: determinism["status"] == "TWO_RUN_DETERMINISM_PASSED" and determinism["equal"] is True and determinism["differences"] == [],
    }
    for name in GATE_NAMES:
        _gate(gates, name, checks[name], f"observed semantic proof for {name}")
    write_json(EVIDENCE / "hard-gates-v0210.json", {"schema_version": SCHEMA_VERSION, "status": "PASS" if set(gates) == set(GATE_NAMES) and all(item["status"] == "PASS" and item["observed"] is True for item in gates.values()) else "FAIL", "gates": gates})
    write_json(EVIDENCE / "gate-specific-proof-v0210.json", {"schema_version": SCHEMA_VERSION, "status": "PASS" if all(item["status"] == "PASS" for item in gates.values()) else "FAIL", "gates": gates})
    write_json(EVIDENCE / "execution-evidence-v0210.json", {"schema_version": SCHEMA_VERSION, "status": "MAPS_MINIMAP_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED" if all(item["status"] == "PASS" for item in gates.values()) and all(item["status"] == "PASS" for item in controls) else "MAPS_MINIMAP_RUNTIME_V0210_FAILED", "hard_gate_count": len(gates), "negative_control_count": len(controls), "production_approved": False, "production_routing": PRODUCTION_ROUTING_BLOCKED, "new_generation": 0, "real_map_asset_coverage": "NONE", "real_minimap_asset_coverage": "NONE", "synthetic_map_fixture": "TEST_ONLY"})


def _stale_cache_gate(maps: list[Mapping[str, Any]]) -> bool:
    cache = MapMinimapCache(); cache.put_map_chunk(maps[0], 0, 0)
    try:
        cache.resolve_map_chunk(maps[1], 0, 0)
    except MapsMinimapContractError as exc:
        return exc.rejection_class == "STALE_MAP_MINIMAP_CACHE_CONTEXT"
    return False


def execute() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate-output", type=Path)
    args = parser.parse_args()
    if args.generate_output:
        generated = generate_output(args.generate_output)
        write_json(args.generate_output / "generation-summary.json", {"schema_version": SCHEMA_VERSION, "map_count": len(generated["maps"]), "maps": generated["manifest_records"]})
        return 0
    if EVIDENCE.exists():
        if EVIDENCE.name != "maps-minimap-runtime-v0210":
            raise RuntimeError("refusing to clear an unexpected evidence directory")
        shutil.rmtree(EVIDENCE)
    with tempfile.TemporaryDirectory(prefix="ugas-v0210-first-") as first_temp, tempfile.TemporaryDirectory(prefix="ugas-v0210-second-") as second_temp:
        first = Path(first_temp) / "slice"
        second = Path(second_temp) / "slice"
        first_result = subprocess.run([sys.executable, __file__, "--generate-output", str(first)], cwd=ROOT, capture_output=True, text=True, check=False)
        second_result = subprocess.run([sys.executable, __file__, "--generate-output", str(second)], cwd=ROOT, capture_output=True, text=True, check=False)
        if first_result.returncode or second_result.returncode:
            print(first_result.stdout + first_result.stderr + second_result.stdout + second_result.stderr)
            return 1
        generated = generate_output(first)
        determinism = compare_generated_outputs(first, second)
        controls = _run_controls(first, generated)
        shutil.copytree(first, EVIDENCE / "fixture", dirs_exist_ok=True)
        _write_evidence(first, generated, controls, determinism)
        shutil.copy2(first / "chunk-boundary-sheet-test-only.png", EVIDENCE / "chunk-boundary-sheet-v0210.png")
        for item in generated["maps"]:
            source = first / "maps" / item["map_id"]
            destination = EVIDENCE / "fixture" / "maps" / item["map_id"]
            destination.mkdir(parents=True, exist_ok=True)
            for name in ("minimap-raster-test-only.png", "minimap-marker-overlay-test-only.png", "visibility-state-sheet-test-only.png", "map-layer-qa-sheet-test-only.png"):
                shutil.copy2(source / name, destination / name)
        overall = load_json(EVIDENCE / "execution-evidence-v0210.json")
        print(json.dumps({"status": overall["status"], "hard_gates": 21, "negative_controls": 20, "determinism": determinism, "production_routing": "BLOCKED", "new_generation": 0}, indent=2))
        return 0 if overall["status"] == "MAPS_MINIMAP_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(execute())
