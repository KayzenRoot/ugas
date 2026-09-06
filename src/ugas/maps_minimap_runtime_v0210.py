"""Fail-closed TEST_ONLY maps and minimap runtime foundation for UGAS v0.21.0.

The module deliberately owns semantic map identities and derived minimap outputs,
not production world content. Environment pixels remain owned by the approved
v0.20.3 authority and item/prop pixels remain owned by v0.19.1.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from math import floor, isfinite
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from PIL import Image, ImageDraw


SCHEMA_VERSION = "0.21.1"
ENVIRONMENT_AUTHORITY_VERSION = "v0.20.3"
ITEM_PROP_AUTHORITY_VERSION = "v0.19.1"
REGISTRY_TEST_ONLY = "TEST_ONLY"
REGISTRY_PRODUCTION = "PRODUCTION"
PRODUCTION_ROUTING_BLOCKED = "BLOCKED"
PRODUCTION_ROUTING_ENABLED = "ENABLED"
MAP_LAYERS = ("ground", "overlay", "structure", "liquid_cliff", "props", "markers")
ENVIRONMENT_LAYER_TO_CLASSES = {
    "ground": {"ground_terrain"},
    "overlay": {"path_road", "vegetation_overlay"},
    "structure": {"wall_structure"},
    "liquid_cliff": {"water_liquid", "cliff_height"},
}
MAP_LAYER_TO_ENVIRONMENT_ROLES = {
    "ground": {"ground_base"},
    "overlay": {"ground_overlay", "vegetation_overlay"},
    "structure": {"structure"},
    "liquid_cliff": {"liquid", "cliff"},
}
MARKER_CLASSES = ("poi", "portal", "spawn")
VISIBILITY_STATES = ("UNKNOWN", "EXPLORED", "VISIBLE")
SEMANTIC_COLORS = {
    "ground_terrain": (76, 136, 76, 255),
    "path_road": (174, 142, 84, 255),
    "wall_structure": (98, 98, 108, 255),
    "water_liquid": (55, 116, 184, 255),
    "cliff_height": (128, 102, 70, 255),
    "vegetation_overlay": (44, 112, 58, 255),
    "empty": (30, 38, 48, 255),
}
MARKER_COLORS = {"poi": (255, 220, 64, 255), "portal": (205, 112, 255, 255), "spawn": (255, 112, 112, 255)}


class MapsMinimapContractError(ValueError):
    """Stable semantic rejection class used by map and minimap controls."""

    def __init__(self, rejection_class: str, detail: str):
        self.rejection_class = rejection_class
        self.error_code = rejection_class
        self.detail = detail
        super().__init__(f"{rejection_class}: {detail}")


def _require(condition: bool, rejection_class: str, detail: str) -> None:
    if not condition:
        raise MapsMinimapContractError(rejection_class, detail)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def decoded_pixel_hash(path: Path) -> str:
    try:
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            return sha256_bytes(f"{rgba.width}x{rgba.height}:RGBA:".encode("ascii") + rgba.tobytes())
    except Exception as exc:  # pragma: no cover - Pillow supplies the cause
        raise MapsMinimapContractError("MINIMAP_RASTER_DECODE_FAILED", str(path)) from exc


def _without(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    return {item: deepcopy(data) for item, data in value.items() if item != key}


def map_manifest_hash(map_document: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(_without(map_document, "provenance")))


def source_hash(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def _positive_int(value: Any, rejection_class: str, detail: str) -> None:
    _require(isinstance(value, int) and not isinstance(value, bool) and value > 0, rejection_class, detail)


def _nonnegative_int(value: Any, rejection_class: str, detail: str) -> None:
    _require(isinstance(value, int) and not isinstance(value, bool) and value >= 0, rejection_class, detail)


def _cell_tuple(value: Any, rejection_class: str = "CELL_COORDINATE_INVALID") -> tuple[int, int]:
    _require(isinstance(value, (list, tuple)) and len(value) == 2, rejection_class, str(value))
    _nonnegative_int(value[0], rejection_class, str(value))
    _nonnegative_int(value[1], rejection_class, str(value))
    return int(value[0]), int(value[1])


def cell_to_chunk(x: int, y: int, chunk_width: int, chunk_height: int) -> tuple[int, int, int, int]:
    _positive_int(chunk_width, "CHUNK_DIMENSIONS_INVALID", str(chunk_width))
    _positive_int(chunk_height, "CHUNK_DIMENSIONS_INVALID", str(chunk_height))
    _nonnegative_int(x, "CELL_COORDINATE_INVALID", str(x))
    _nonnegative_int(y, "CELL_COORDINATE_INVALID", str(y))
    chunk_x, local_x = divmod(x, chunk_width)
    chunk_y, local_y = divmod(y, chunk_height)
    return chunk_x, chunk_y, local_x, local_y


def chunk_to_cell(chunk_x: int, chunk_y: int, local_x: int, local_y: int, chunk_width: int, chunk_height: int) -> tuple[int, int]:
    for value in (chunk_x, chunk_y, local_x, local_y):
        _nonnegative_int(value, "CHUNK_COORDINATE_INVALID", str(value))
    _positive_int(chunk_width, "CHUNK_DIMENSIONS_INVALID", str(chunk_width))
    _positive_int(chunk_height, "CHUNK_DIMENSIONS_INVALID", str(chunk_height))
    _require(local_x < chunk_width and local_y < chunk_height, "CHUNK_LOCAL_CELL_OUT_OF_BOUNDS", str((local_x, local_y)))
    return chunk_x * chunk_width + local_x, chunk_y * chunk_height + local_y


def deterministic_chunk_id(map_id: str, map_revision: str, chunk_x: int, chunk_y: int) -> str:
    _require(isinstance(map_id, str) and isinstance(map_revision, str) and map_id and map_revision, "MAP_IDENTITY_INVALID", "chunk identity requires map identity")
    _nonnegative_int(chunk_x, "CHUNK_COORDINATE_INVALID", str(chunk_x))
    _nonnegative_int(chunk_y, "CHUNK_COORDINATE_INVALID", str(chunk_y))
    return f"{map_id}@{map_revision}/chunk/{chunk_x},{chunk_y}"


def _authority_record_hash(manifest: Mapping[str, Any]) -> str:
    return source_hash(manifest)


def build_environment_authority(
    manifest: Mapping[str, Any],
    *,
    approved_merge_commit: str,
    source_path: str,
    registry_mode: str = REGISTRY_TEST_ONLY,
) -> dict[str, Any]:
    """Build a read-only identity index; no environment manifest is mutated."""

    _require(registry_mode == REGISTRY_TEST_ONLY, "ENVIRONMENT_AUTHORITY_MODE_INVALID", registry_mode)
    _require(manifest.get("schema_version") == "0.20.2", "ENVIRONMENT_AUTHORITY_SCHEMA_INVALID", str(manifest.get("schema_version")))
    _require(manifest.get("test_only") is True and manifest.get("production_routing") == PRODUCTION_ROUTING_BLOCKED, "ENVIRONMENT_AUTHORITY_NOT_TEST_ONLY", str(manifest.get("tileset_id")))
    entries: dict[str, Any] = {}
    variants: dict[str, Any] = {}
    for tile in manifest.get("tiles", []):
        if not isinstance(tile, Mapping):
            continue
        entries[str(tile.get("tile_id"))] = {
            "tile_id": tile.get("tile_id"),
            "terrain_family_id": tile.get("terrain_family_id"),
            "class_id": tile.get("class_id"),
            "layer": tile.get("primary_layer"),
            "atlas_revision": tile.get("binding", {}).get("atlas_revision"),
            "content_revision": tile.get("binding", {}).get("decoded_pixel_hash"),
        }
    for variant in manifest.get("variants", []):
        if not isinstance(variant, Mapping):
            continue
        variants[str(variant.get("variant_id"))] = {
            "variant_id": variant.get("variant_id"),
            "terrain_family_id": variant.get("terrain_family_id"),
            "tile_id": variant.get("resolved_tile_id"),
            "class_id": variant.get("target_class_id"),
            "layer": variant.get("target_layer_role"),
            "atlas_revision": variant.get("atlas_revision"),
            "content_revision": variant.get("content_hash"),
            "variant_revision": variant.get("variant_revision"),
        }
    authority_hash = _authority_record_hash({"manifest": manifest, "merge_commit": approved_merge_commit, "source_path": source_path})
    return {
        "schema_version": SCHEMA_VERSION,
        "authority_type": "APPROVED_ENVIRONMENT_TILESET_AUTHORITY",
        "approved_increment": ENVIRONMENT_AUTHORITY_VERSION,
        "approved_merge_commit": approved_merge_commit,
        "source_path": source_path,
        "registry_mode": registry_mode,
        "tileset_id": manifest.get("tileset_id"),
        "tileset_revision": manifest.get("tileset_revision"),
        "authority_revision": f"{ENVIRONMENT_AUTHORITY_VERSION}:{manifest.get('tileset_revision')}",
        "authority_hash": authority_hash,
        "world_metrics": deepcopy(manifest.get("metrics", {})),
        "tile_index": entries,
        "variant_index": variants,
        "read_only": True,
    }


def build_items_props_authority(
    manifest: Mapping[str, Any],
    *,
    source_path: str,
    source_revision: str = ITEM_PROP_AUTHORITY_VERSION,
    registry_mode: str = REGISTRY_TEST_ONLY,
) -> dict[str, Any]:
    _require(registry_mode == REGISTRY_TEST_ONLY, "ITEM_PROP_AUTHORITY_MODE_INVALID", registry_mode)
    _require(manifest.get("schema_version") == "0.19.1", "ITEM_PROP_AUTHORITY_SCHEMA_INVALID", str(manifest.get("schema_version")))
    index: dict[str, dict[str, Any]] = {}
    variants: dict[str, dict[str, Any]] = {}
    for item in manifest.get("items", []):
        if not isinstance(item, Mapping):
            continue
        profile = item.get("representation_profile", {})
        world = profile.get("world_sprite_prop", {}) if isinstance(profile, Mapping) else {}
        index[str(item.get("item_or_prop_id"))] = {
            "item_or_prop_id": item.get("item_or_prop_id"),
            "class_id": item.get("class_id"),
            "world_capable": world.get("availability") == "REQUIRED",
            "test_only": item.get("test_only"),
            "production_safe": item.get("production_safe"),
        }
    for variant in manifest.get("variants", []):
        if isinstance(variant, Mapping):
            variants[str(variant.get("variant_id"))] = {
                "variant_id": variant.get("variant_id"),
                "item_or_prop_id": variant.get("item_or_prop_id"),
                "variant_revision": variant.get("variant_revision"),
            }
    authority_hash = source_hash({"manifest": manifest, "source_revision": source_revision, "source_path": source_path})
    return {
        "schema_version": SCHEMA_VERSION,
        "authority_type": "APPROVED_ITEMS_PROPS_AUTHORITY",
        "approved_increment": source_revision,
        "source_path": source_path,
        "source_revision": source_revision,
        "authority_hash": authority_hash,
        "registry_mode": registry_mode,
        "item_index": index,
        "variant_index": variants,
        "read_only": True,
    }


def _validate_environment_ref(ref: Mapping[str, Any], authority: Mapping[str, Any], expected_layer: str) -> None:
    _require(isinstance(ref, Mapping), "ENVIRONMENT_TILE_REF_INVALID", str(ref))
    required = ("tileset_id", "tileset_revision", "terrain_family_id", "tile_id", "variant_id", "class_id", "layer", "atlas_revision", "content_revision", "authority_revision", "authority_hash")
    _require(all(key in ref for key in required), "ENVIRONMENT_TILE_REF_INVALID", str(ref))
    _require("artifact_path" not in ref and "asset_path" not in ref and "png_path" not in ref, "DIRECT_ENVIRONMENT_ASSET_PATH_IN_MAP", str(ref))
    _require(ref.get("tileset_id") == authority.get("tileset_id") and ref.get("tileset_revision") == authority.get("tileset_revision"), "UNKNOWN_ENVIRONMENT_TILESET_REF", str(ref))
    _require(ref.get("authority_revision") == authority.get("authority_revision") and ref.get("authority_hash") == authority.get("authority_hash"), "STALE_ENVIRONMENT_AUTHORITY_REF", str(ref))
    variant = authority.get("variant_index", {}).get(ref.get("variant_id"))
    tile = authority.get("tile_index", {}).get(ref.get("tile_id"))
    _require(isinstance(variant, Mapping) and isinstance(tile, Mapping), "UNKNOWN_ENVIRONMENT_TILE_VARIANT_REF", str(ref))
    _require(ref.get("terrain_family_id") == variant.get("terrain_family_id") == tile.get("terrain_family_id"), "ENVIRONMENT_TERRAIN_FAMILY_MISMATCH", str(ref))
    _require(ref.get("tile_id") == variant.get("tile_id"), "ENVIRONMENT_VARIANT_TILE_MISMATCH", str(ref))
    _require(ref.get("class_id") == variant.get("class_id") == tile.get("class_id"), "ENVIRONMENT_TILE_CLASS_MISMATCH", str(ref))
    _require(ref.get("layer") == variant.get("layer") == tile.get("layer"), "ENVIRONMENT_TILE_LAYER_MISMATCH", str(ref))
    _require(ref.get("layer") in MAP_LAYER_TO_ENVIRONMENT_ROLES.get(expected_layer, set()), "ENVIRONMENT_TILE_LAYER_MISMATCH", str(ref))
    _require(ref.get("atlas_revision") == variant.get("atlas_revision") == tile.get("atlas_revision"), "ENVIRONMENT_ATLAS_REVISION_MISMATCH", str(ref))
    _require(ref.get("content_revision") == variant.get("content_revision"), "ENVIRONMENT_CONTENT_REVISION_MISMATCH", str(ref))


def _validate_prop_ref(
    ref: Mapping[str, Any],
    authority: Mapping[str, Any],
    *,
    map_document: Mapping[str, Any],
    owner_cell: tuple[int, int],
) -> None:
    _require(isinstance(ref, Mapping), "ITEM_PROP_REF_INVALID", str(ref))
    for key in ("item_or_prop_id", "variant_id", "variant_revision", "placement"):
        _require(key in ref, "ITEM_PROP_REF_INVALID", str(ref))
    _require(not any(key in ref for key in ("asset_path", "artifact_path", "content_hash", "file_sha256", "representation_hash")), "ITEM_PROP_ASSET_AUTHORITY_COPIED", str(ref))
    item = authority.get("item_index", {}).get(ref.get("item_or_prop_id"))
    variant = authority.get("variant_index", {}).get(ref.get("variant_id"))
    _require(isinstance(item, Mapping) and isinstance(variant, Mapping) and variant.get("item_or_prop_id") == ref.get("item_or_prop_id"), "UNKNOWN_OR_NON_WORLD_CAPABLE_PROP_REF", str(ref))
    _require(item.get("world_capable") is True, "UNKNOWN_OR_NON_WORLD_CAPABLE_PROP_REF", str(ref))
    _require(ref.get("variant_revision") == variant.get("variant_revision"), "ITEM_PROP_VARIANT_REVISION_MISMATCH", str(ref))
    placement = ref.get("placement")
    _require(isinstance(placement, Mapping), "ITEM_PROP_PLACEMENT_INVALID", str(ref))
    _require(isinstance(placement.get("x"), (int, float)) and isinstance(placement.get("y"), (int, float)), "ITEM_PROP_PLACEMENT_INVALID", str(ref))
    _require(isinstance(placement.get("rotation_degrees"), (int, float)) and isinstance(placement.get("scale"), (int, float)) and placement.get("scale") > 0, "ITEM_PROP_PLACEMENT_INVALID", str(ref))
    _require(isfinite(float(placement["x"])) and isfinite(float(placement["y"])), "ITEM_PROP_PLACEMENT_INVALID", str(ref))
    _coordinate_transform(map_document)
    placement_x, placement_y = float(placement["x"]), float(placement["y"])
    width, height = map_document["width_tiles"], map_document["height_tiles"]
    _require(0.0 <= placement_x < width and 0.0 <= placement_y < height, "ITEM_PROP_PLACEMENT_OUT_OF_BOUNDS", str(ref))
    containing_cell = (floor(placement_x), floor(placement_y))
    _require(containing_cell == owner_cell, "ITEM_PROP_PLACEMENT_WRONG_OWNING_CELL", str(ref))


def _validate_bounds(x: int, y: int, width: int, height: int, rejection_class: str) -> None:
    _require(0 <= x < width and 0 <= y < height, rejection_class, str((x, y)))


def validate_regions_zones(map_document: Mapping[str, Any]) -> None:
    width, height = map_document["width_tiles"], map_document["height_tiles"]
    for collection_name in ("regions", "zones"):
        seen: set[str] = set()
        for record in map_document.get(collection_name, []):
            _require(isinstance(record, Mapping) and isinstance(record.get("id"), str) and record.get("id"), "REGION_ZONE_METADATA_INVALID", collection_name)
            _require(record["id"] not in seen, "DUPLICATE_REGION_ZONE_ID", record["id"])
            seen.add(record["id"])
            cells = record.get("cells")
            _require(isinstance(cells, list) and cells, "REGION_ZONE_EMPTY", record["id"])
            normalized = [_cell_tuple(item, "REGION_ZONE_CELL_INVALID") for item in cells]
            _require(len(normalized) == len(set(normalized)), "REGION_ZONE_DUPLICATE_CELL", record["id"])
            for x, y in normalized:
                _validate_bounds(x, y, width, height, "REGION_ZONE_OUT_OF_BOUNDS")
            _require(normalized == sorted(normalized, key=lambda item: (item[1], item[0])), "REGION_ZONE_NONDETERMINISTIC_ORDER", record["id"])


def validate_markers(map_document: Mapping[str, Any]) -> None:
    width, height = map_document["width_tiles"], map_document["height_tiles"]
    ids: set[str] = set()
    for marker in map_document.get("markers", []):
        _require(isinstance(marker, Mapping) and isinstance(marker.get("marker_id"), str) and marker.get("marker_id"), "MARKER_ID_INVALID", str(marker))
        _require(marker["marker_id"] not in ids, "DUPLICATE_MARKER_ID", marker["marker_id"])
        ids.add(marker["marker_id"])
        _require(marker.get("marker_class") in MARKER_CLASSES, "MARKER_CLASS_INVALID", marker["marker_id"])
        _validate_bounds(marker.get("x"), marker.get("y"), width, height, "MARKER_OUT_OF_BOUNDS")
        _require(set(marker) <= {"marker_id", "marker_class", "x", "y", "label"}, "MARKER_PAYLOAD_FORBIDDEN", marker["marker_id"])


def _coordinate_transform(map_document: Mapping[str, Any]) -> tuple[float, float]:
    origin = map_document.get("coordinate_origin")
    orientation = map_document.get("grid_orientation")
    _require(origin in {"TOP_LEFT", "CENTER"}, "MAP_ORIGIN_INVALID", str(origin))
    _require(orientation in {"Y_DOWN", "Y_UP"}, "MAP_ORIENTATION_INVALID", str(orientation))
    projection = map_document.get("minimap", {}).get("projection", {})
    _require(projection.get("origin") == origin, "MINIMAP_ORIGIN_SEMANTICS_INVALID", str(projection))
    _require(projection.get("grid_orientation") == orientation, "MINIMAP_ORIENTATION_SEMANTICS_INVALID", str(projection))
    return (0.5 if origin == "CENTER" else 0.0), (1.0 if orientation == "Y_DOWN" else -1.0)


def _grid_to_projection_space(x: float, y: float, map_document: Mapping[str, Any]) -> tuple[float, float]:
    offset, direction = _coordinate_transform(map_document)
    return x + offset, (y + offset) * direction


def _projection_parameters(map_document: Mapping[str, Any]) -> dict[str, float]:
    projection = map_document["minimap"]["projection"]
    width_px, height_px = map_document["minimap"]["width_px"], map_document["minimap"]["height_px"]
    padding = projection["padding_px"]
    inner_width, inner_height = width_px - 2 * padding, height_px - 2 * padding
    left, top = _grid_to_projection_space(0.0, 0.0, map_document)
    right, bottom = _grid_to_projection_space(float(map_document["width_tiles"]), float(map_document["height_tiles"]), map_document)
    min_x, max_x = min(left, right), max(left, right)
    min_y, max_y = min(top, bottom), max(top, bottom)
    map_width, map_height = max_x - min_x, max_y - min_y
    scale = min(inner_width / map_width, inner_height / map_height)
    return {
        "scale": scale,
        "offset_x": padding + (inner_width - scale * map_width) / 2.0 - min_x * scale,
        "offset_y": padding + (inner_height - scale * map_height) / 2.0 - min_y * scale,
    }


def map_to_minimap(point: Mapping[str, Any], map_document: Mapping[str, Any]) -> tuple[float, float]:
    _require(map_document.get("minimap", {}).get("projection", {}).get("aspect_fit") == "CONTAIN", "MINIMAP_PROJECTION_INVALID", "only CONTAIN is canonical")
    x, y = point.get("x"), point.get("y")
    _require(isinstance(x, (int, float)) and isinstance(y, (int, float)), "MAP_POINT_INVALID", str(point))
    _require(0 <= x <= map_document["width_tiles"] and 0 <= y <= map_document["height_tiles"], "MAP_POINT_OUT_OF_BOUNDS", str(point))
    params = _projection_parameters(map_document)
    projection_x, projection_y = _grid_to_projection_space(float(x), float(y), map_document)
    return params["offset_x"] + projection_x * params["scale"], params["offset_y"] + projection_y * params["scale"]


def minimap_to_map(point: Mapping[str, Any], map_document: Mapping[str, Any]) -> tuple[float, float]:
    x, y = point.get("x"), point.get("y")
    _require(isinstance(x, (int, float)) and isinstance(y, (int, float)), "MINIMAP_POINT_INVALID", str(point))
    params = _projection_parameters(map_document)
    projection_x, projection_y = (float(x) - params["offset_x"]) / params["scale"], (float(y) - params["offset_y"]) / params["scale"]
    offset, direction = _coordinate_transform(map_document)
    map_x, map_y = projection_x - offset, projection_y / direction - offset
    _require(0 <= map_x <= map_document["width_tiles"] and 0 <= map_y <= map_document["height_tiles"], "MINIMAP_POINT_OUT_OF_BOUNDS", str(point))
    return map_x, map_y


def validate_visibility(map_document: Mapping[str, Any]) -> None:
    visibility = map_document.get("visibility", {})
    _require(visibility.get("state_order") == list(VISIBILITY_STATES), "VISIBILITY_STATE_CONTRACT_INVALID", str(visibility))
    width, height = map_document["width_tiles"], map_document["height_tiles"]
    masks = visibility.get("masks", {})
    _require(set(masks) == set(VISIBILITY_STATES), "VISIBILITY_MASK_STATE_SET_INVALID", str(masks))
    for state in VISIBILITY_STATES:
        rows = masks[state]
        _require(isinstance(rows, list) and len(rows) == height and all(isinstance(row, list) and len(row) == width for row in rows), "VISIBILITY_MASK_DIMENSIONS_INVALID", state)
        _require(all(value in (0, 1, False, True) for row in rows for value in row), "VISIBILITY_MASK_VALUE_INVALID", state)


def validate_map_document(
    map_document: Mapping[str, Any],
    environment_authority: Mapping[str, Any],
    items_props_authority: Mapping[str, Any],
    *,
    production_registry: bool = False,
) -> dict[str, Any]:
    _require(map_document.get("schema_version") == SCHEMA_VERSION, "MAP_SCHEMA_VERSION_INVALID", str(map_document.get("schema_version")))
    _require(map_document.get("manifest_type") == "maps-minimap-runtime-foundation", "MAP_SCHEMA_INVALID", str(map_document.get("manifest_type")))
    for key in ("map_id", "map_revision", "coordinate_origin", "grid_orientation", "chunk_width_tiles", "chunk_height_tiles", "layers", "cells", "regions", "zones", "markers", "minimap", "visibility", "provenance"):
        _require(key in map_document, "MAP_SCHEMA_REQUIRED_FIELD_MISSING", key)
    environment_binding = map_document.get("environment_authority")
    _require(isinstance(environment_binding, Mapping), "ENVIRONMENT_AUTHORITY_BINDING_INVALID", str(environment_binding))
    _require(environment_binding.get("authority_revision") == environment_authority.get("authority_revision") and environment_binding.get("authority_hash") == environment_authority.get("authority_hash"), "STALE_ENVIRONMENT_AUTHORITY_REF", str(environment_binding))
    prop_binding = map_document.get("items_props_authority")
    _require(isinstance(prop_binding, Mapping), "ITEM_PROP_AUTHORITY_BINDING_INVALID", str(prop_binding))
    _require(prop_binding.get("source_revision") == items_props_authority.get("source_revision") and prop_binding.get("authority_hash") == items_props_authority.get("authority_hash"), "STALE_ITEM_PROP_AUTHORITY_REF", str(prop_binding))
    _positive_int(map_document.get("width_tiles"), "MAP_DIMENSIONS_INVALID", "width_tiles")
    _positive_int(map_document.get("height_tiles"), "MAP_DIMENSIONS_INVALID", "height_tiles")
    _positive_int(map_document.get("chunk_width_tiles"), "CHUNK_DIMENSIONS_INVALID", "chunk_width_tiles")
    _positive_int(map_document.get("chunk_height_tiles"), "CHUNK_DIMENSIONS_INVALID", "chunk_height_tiles")
    _require(map_document.get("world_units_per_tile") == environment_authority.get("world_metrics", {}).get("world_units_per_tile"), "WORLD_UNITS_PER_TILE_AUTHORITY_MISMATCH", str(map_document.get("world_units_per_tile")))
    _require(map_document.get("coordinate_origin") in {"TOP_LEFT", "CENTER"}, "MAP_ORIGIN_INVALID", str(map_document.get("coordinate_origin")))
    _require(map_document.get("grid_orientation") in {"Y_DOWN", "Y_UP"}, "MAP_ORIENTATION_INVALID", str(map_document.get("grid_orientation")))
    _require(map_document.get("test_only") is True and map_document.get("production_safe") is False, "MAP_PRODUCTION_BOUNDARY_INVALID", str(map_document.get("map_id")))
    if production_registry:
        raise MapsMinimapContractError("TEST_FIXTURE_IN_PRODUCTION_REGISTRY", str(map_document.get("map_id")))
    _require(map_document.get("production_routing") == PRODUCTION_ROUTING_BLOCKED, "PRODUCTION_ROUTING_ENABLED", str(map_document.get("map_id")))
    _require(map_document.get("layers") == list(MAP_LAYERS), "LAYER_CONTRACT_INVALID", str(map_document.get("layers")))
    cells = map_document.get("cells")
    _require(isinstance(cells, list), "MAP_CELLS_INVALID", "cells must be a list")
    coordinates: list[tuple[int, int]] = []
    for cell in cells:
        _require(isinstance(cell, Mapping), "MAP_CELL_INVALID", str(cell))
        x, y = cell.get("x"), cell.get("y")
        _validate_bounds(x, y, map_document["width_tiles"], map_document["height_tiles"], "CELL_OUT_OF_BOUNDS")
        coordinate = (x, y)
        _require(coordinate not in coordinates, "DUPLICATE_MAP_CELL", str(coordinate))
        coordinates.append(coordinate)
        layer_values = cell.get("layers")
        _require(isinstance(layer_values, Mapping) and set(layer_values) == set(MAP_LAYERS), "LAYER_CONTRACT_INVALID", str(coordinate))
        for layer_name in ("ground", "overlay", "structure", "liquid_cliff"):
            ref = layer_values[layer_name]
            if ref is None:
                _require(layer_name != "ground", "GROUND_IDENTITY_MISSING", str(coordinate))
            else:
                _validate_environment_ref(ref, environment_authority, layer_name)
                _require(ref.get("class_id") in ENVIRONMENT_LAYER_TO_CLASSES[layer_name], "ENVIRONMENT_TILE_CLASS_LAYER_CONTRADICTION", str(ref))
        prop_refs = layer_values["props"]
        _require(isinstance(prop_refs, list), "PROPS_LAYER_INVALID", str(coordinate))
        for ref in prop_refs:
            _validate_prop_ref(ref, items_props_authority, map_document=map_document, owner_cell=(x, y))
        _require(layer_values["markers"] == [], "CELL_MARKER_OWNERSHIP_INVALID", str(coordinate))
    expected = {(x, y) for y in range(map_document["height_tiles"]) for x in range(map_document["width_tiles"])}
    _require(set(coordinates) == expected, "MAP_CELL_COVERAGE_INVALID", str((len(coordinates), len(expected))))
    _require(coordinates == sorted(coordinates, key=lambda item: (item[1], item[0])), "MAP_CELL_ORDER_NONDETERMINISTIC", "cells must be row-major")
    validate_regions_zones(map_document)
    validate_markers(map_document)
    minimap = map_document["minimap"]
    _positive_int(minimap.get("width_px"), "MINIMAP_DIMENSIONS_INVALID", "width_px")
    _positive_int(minimap.get("height_px"), "MINIMAP_DIMENSIONS_INVALID", "height_px")
    projection = minimap.get("projection")
    _require(isinstance(projection, Mapping), "MINIMAP_PROJECTION_INVALID", "projection")
    _positive_int(projection.get("padding_px"), "MINIMAP_PROJECTION_INVALID", "padding_px")
    _require(projection.get("origin") == map_document.get("coordinate_origin") and projection.get("grid_orientation") == map_document.get("grid_orientation"), "MINIMAP_PROJECTION_INVALID", "origin/orientation mismatch")
    _require(projection.get("aspect_fit") == "CONTAIN", "MINIMAP_PROJECTION_INVALID", str(projection))
    _require(projection.get("renderer_revision") == "minimap-renderer-v0211-r1", "MINIMAP_RENDERER_REVISION_INVALID", str(projection.get("renderer_revision")))
    validate_visibility(map_document)
    _require(map_document.get("provenance", {}).get("map_hash") == map_manifest_hash(map_document), "MAP_PROVENANCE_HASH_MISMATCH", str(map_document.get("map_id")))
    return {"status": "MAP_DOCUMENT_VALID", "map_id": map_document["map_id"], "map_hash": map_manifest_hash(map_document), "cell_count": len(cells), "marker_count": len(map_document["markers"])}


def build_chunk_index(map_document: Mapping[str, Any]) -> list[dict[str, Any]]:
    chunks: dict[tuple[int, int], list[list[int]]] = {}
    for cell in map_document["cells"]:
        cx, cy, lx, ly = cell_to_chunk(cell["x"], cell["y"], map_document["chunk_width_tiles"], map_document["chunk_height_tiles"])
        chunks.setdefault((cx, cy), []).append([cell["x"], cell["y"], lx, ly])
    result = []
    for (cx, cy), cells in sorted(chunks.items()):
        result.append({"chunk_id": deterministic_chunk_id(map_document["map_id"], map_document["map_revision"], cx, cy), "chunk_x": cx, "chunk_y": cy, "chunk_width_tiles": map_document["chunk_width_tiles"], "chunk_height_tiles": map_document["chunk_height_tiles"], "cells": sorted(cells, key=lambda item: (item[1], item[0]))})
    return result


def validate_chunk_partition(map_document: Mapping[str, Any], chunks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    expected = {(x, y) for y in range(map_document["height_tiles"]) for x in range(map_document["width_tiles"])}
    observed: list[tuple[int, int]] = []
    for chunk in chunks:
        cx, cy = chunk.get("chunk_x"), chunk.get("chunk_y")
        _require(chunk.get("chunk_id") == deterministic_chunk_id(map_document["map_id"], map_document["map_revision"], cx, cy), "CHUNK_ID_INVALID", str(chunk))
        for entry in chunk.get("cells", []):
            _require(len(entry) == 4, "CHUNK_CELL_ENTRY_INVALID", str(entry))
            try:
                x, y = chunk_to_cell(cx, cy, entry[2], entry[3], map_document["chunk_width_tiles"], map_document["chunk_height_tiles"])
            except MapsMinimapContractError as exc:
                raise MapsMinimapContractError("CHUNK_ROUNDTRIP_INVALID", str(exc)) from exc
            _require((x, y) == (entry[0], entry[1]), "CHUNK_ROUNDTRIP_INVALID", str(entry))
            _require((x, y) not in observed, "CHUNK_CELL_DUPLICATE", str((x, y)))
            observed.append((x, y))
    _require(set(observed) == expected and len(observed) == len(expected), "CHUNK_PARTITION_COVERAGE_INVALID", str((len(observed), len(expected))))
    return {"status": "CHUNK_PARTITION_VALID", "chunk_count": len(chunks), "cell_count": len(observed), "map_hash": map_manifest_hash(map_document)}


def marker_set_hash(map_document: Mapping[str, Any]) -> str:
    return source_hash(map_document.get("markers", []))


def visibility_state_hash(map_document: Mapping[str, Any]) -> str:
    return source_hash(map_document.get("visibility", {}))


def map_cache_key(map_document: Mapping[str, Any], chunk_x: int, chunk_y: int, *, registry_mode: str = REGISTRY_TEST_ONLY) -> str:
    return source_hash({"kind": "map", "map_id": map_document["map_id"], "map_revision": map_document["map_revision"], "map_hash": map_manifest_hash(map_document), "chunk": [chunk_x, chunk_y], "chunk_size": [map_document["chunk_width_tiles"], map_document["chunk_height_tiles"]], "environment_authority_revision": map_document["environment_authority"]["authority_revision"], "prop_authority_revision": map_document["items_props_authority"]["source_revision"], "registry_mode": registry_mode})


def minimap_cache_key(map_document: Mapping[str, Any]) -> str:
    projection = map_document["minimap"]["projection"]
    return source_hash({"kind": "minimap", "map_hash": map_manifest_hash(map_document), "projection": projection, "marker_set_hash": marker_set_hash(map_document), "visibility_state_hash": visibility_state_hash(map_document), "renderer_revision": projection["renderer_revision"]})


@dataclass(frozen=True)
class CacheEntry:
    key: str
    map_hash: str
    kind: str
    chunk: tuple[int, int] | None = None


class MapMinimapCache:
    def __init__(self, *, production: bool = False):
        self.production = production
        self._entries: dict[str, CacheEntry] = {}

    def put_map_chunk(self, map_document: Mapping[str, Any], chunk_x: int, chunk_y: int) -> CacheEntry:
        if self.production:
            raise MapsMinimapContractError("TEST_FIXTURE_IN_PRODUCTION_CACHE", str(map_document.get("map_id")))
        key = map_cache_key(map_document, chunk_x, chunk_y)
        entry = CacheEntry(key, map_manifest_hash(map_document), "map", (chunk_x, chunk_y))
        self._entries[key] = entry
        return entry

    def put_minimap(self, map_document: Mapping[str, Any]) -> CacheEntry:
        if self.production:
            raise MapsMinimapContractError("TEST_FIXTURE_IN_PRODUCTION_CACHE", str(map_document.get("map_id")))
        key = minimap_cache_key(map_document)
        entry = CacheEntry(key, map_manifest_hash(map_document), "minimap")
        self._entries[key] = entry
        return entry

    def resolve_map_chunk(self, map_document: Mapping[str, Any], chunk_x: int, chunk_y: int) -> CacheEntry:
        key = map_cache_key(map_document, chunk_x, chunk_y)
        entry = self._entries.get(key)
        _require(entry is not None and entry.map_hash == map_manifest_hash(map_document), "STALE_MAP_MINIMAP_CACHE_CONTEXT", key)
        return entry

    def resolve_minimap(self, map_document: Mapping[str, Any]) -> CacheEntry:
        key = minimap_cache_key(map_document)
        entry = self._entries.get(key)
        _require(entry is not None and entry.map_hash == map_manifest_hash(map_document), "STALE_MAP_MINIMAP_CACHE_CONTEXT", key)
        return entry

    def cache_stats(self) -> dict[str, int]:
        return {"entries": len(self._entries)}


class MapRegistry:
    def __init__(self, *, production: bool = False, production_routing: str = PRODUCTION_ROUTING_BLOCKED, environment_authority: Mapping[str, Any], items_props_authority: Mapping[str, Any]):
        self.production = production
        self.production_routing = production_routing
        self.environment_authority = deepcopy(dict(environment_authority))
        self.items_props_authority = deepcopy(dict(items_props_authority))
        self._entries: dict[str, Mapping[str, Any]] = {}

    def register(self, map_document: Mapping[str, Any]) -> None:
        if self.production and map_document.get("test_only") is True:
            raise MapsMinimapContractError("TEST_FIXTURE_IN_PRODUCTION_REGISTRY", str(map_document.get("map_id")))
        if self.production or self.production_routing == PRODUCTION_ROUTING_ENABLED:
            raise MapsMinimapContractError("PRODUCTION_ROUTING_ENABLED", str(map_document.get("map_id")))
        validate_map_document(map_document, self.environment_authority, self.items_props_authority, production_registry=False)
        self._entries[str(map_document["map_id"])] = deepcopy(dict(map_document))

    def cache_stats(self) -> dict[str, int]:
        return {"entries": len(self._entries)}

    def snapshot(self) -> dict[str, Any]:
        records = [{"map_id": map_id, "map_hash": map_manifest_hash(document)} for map_id, document in sorted(self._entries.items())]
        return {
            "registry_mode": REGISTRY_PRODUCTION if self.production else REGISTRY_TEST_ONLY,
            "production_routing": self.production_routing,
            "entry_count": len(records),
            "entries": records,
        }

    @property
    def entries(self) -> list[Mapping[str, Any]]:
        return list(self._entries.values())


def render_minimap_base(map_document: Mapping[str, Any], output_path: Path) -> dict[str, Any]:
    width_px, height_px = map_document["minimap"]["width_px"], map_document["minimap"]["height_px"]
    image = Image.new("RGBA", (width_px, height_px), SEMANTIC_COLORS["empty"])
    draw = ImageDraw.Draw(image)
    for cell in map_document["cells"]:
        reference = cell["layers"].get("ground") or cell["layers"].get("overlay") or cell["layers"].get("structure") or cell["layers"].get("liquid_cliff")
        class_id = reference.get("class_id") if isinstance(reference, Mapping) else "empty"
        left, top = map_to_minimap({"x": cell["x"], "y": cell["y"]}, map_document)
        right, bottom = map_to_minimap({"x": cell["x"] + 1, "y": cell["y"] + 1}, map_document)
        draw.rectangle((round(left), round(top), max(round(left), round(right) - 1), max(round(top), round(bottom) - 1)), fill=SEMANTIC_COLORS.get(class_id, SEMANTIC_COLORS["empty"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG", optimize=False, compress_level=9)
    return {"path": output_path.name, "file_sha256": sha256_file(output_path), "decoded_pixel_hash": decoded_pixel_hash(output_path), "map_hash": map_manifest_hash(map_document), "label": "TEST_ONLY_MINIMAP_RASTER"}


def render_marker_overlay(map_document: Mapping[str, Any], output_path: Path) -> dict[str, Any]:
    width_px, height_px = map_document["minimap"]["width_px"], map_document["minimap"]["height_px"]
    image = Image.new("RGBA", (width_px, height_px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for marker in map_document["markers"]:
        x, y = map_to_minimap({"x": marker["x"] + 0.5, "y": marker["y"] + 0.5}, map_document)
        radius = 2
        color = MARKER_COLORS[marker["marker_class"]]
        draw.ellipse((round(x) - radius, round(y) - radius, round(x) + radius, round(y) + radius), fill=color)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG", optimize=False, compress_level=9)
    return {"path": output_path.name, "file_sha256": sha256_file(output_path), "decoded_pixel_hash": decoded_pixel_hash(output_path), "source_marker_set_hash": marker_set_hash(map_document), "label": "TEST_ONLY_MINIMAP_MARKER_OVERLAY"}


def render_visibility_sheet(map_document: Mapping[str, Any], output_path: Path) -> dict[str, Any]:
    cell_size = 8
    width = map_document["width_tiles"] * cell_size * 3
    height = map_document["height_tiles"] * cell_size
    image = Image.new("RGBA", (width, height), (18, 22, 28, 255))
    draw = ImageDraw.Draw(image)
    colors = {"UNKNOWN": (48, 54, 64, 255), "EXPLORED": (126, 126, 86, 255), "VISIBLE": (218, 230, 168, 255)}
    for state_index, state in enumerate(VISIBILITY_STATES):
        for y, row in enumerate(map_document["visibility"]["masks"][state]):
            for x, value in enumerate(row):
                color = colors[state] if value else (12, 14, 18, 255)
                draw.rectangle((state_index * map_document["width_tiles"] * cell_size + x * cell_size, y * cell_size, state_index * map_document["width_tiles"] * cell_size + (x + 1) * cell_size - 1, (y + 1) * cell_size - 1), fill=color)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG", optimize=False, compress_level=9)
    return {"path": output_path.name, "file_sha256": sha256_file(output_path), "decoded_pixel_hash": decoded_pixel_hash(output_path), "source_visibility_state_hash": visibility_state_hash(map_document), "label": "TEST_ONLY_VISIBILITY_STATE_SHEET"}


def render_qa_sheet(map_document: Mapping[str, Any], output_path: Path, *, title: str, width: int = 420, height: int = 160) -> dict[str, Any]:
    image = Image.new("RGB", (width, height), (24, 30, 40))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, width - 9, height - 9), outline=(115, 165, 210), width=2)
    draw.text((18, 20), title, fill=(255, 255, 255))
    draw.text((18, 48), "TEST_ONLY / semantic fixture / no production world design", fill=(220, 220, 220))
    draw.text((18, 78), f"map={map_document['map_id']}  dimensions={map_document['width_tiles']}x{map_document['height_tiles']}", fill=(220, 220, 220))
    draw.text((18, 104), f"chunks={len(build_chunk_index(map_document))}  markers={len(map_document['markers'])}", fill=(220, 220, 220))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG", optimize=False, compress_level=9)
    return {"path": output_path.name, "file_sha256": sha256_file(output_path), "decoded_pixel_hash": decoded_pixel_hash(output_path), "source_map_hash": map_manifest_hash(map_document), "label": "TEST_ONLY_QA_SHEET"}


def compare_generated_outputs(first: Path, second: Path) -> dict[str, Any]:
    first_files = sorted(path.relative_to(first).as_posix() for path in first.rglob("*") if path.is_file())
    second_files = sorted(path.relative_to(second).as_posix() for path in second.rglob("*") if path.is_file())
    differences = [relative for relative in sorted(set(first_files) | set(second_files)) if (first / relative).is_file() != (second / relative).is_file() or ((first / relative).is_file() and (first / relative).read_bytes() != (second / relative).read_bytes())]
    _require(first_files == second_files and not differences, "NONDETERMINISTIC_SECOND_MAP_MINIMAP_OUTPUT", ",".join(differences))
    return {"status": "TWO_RUN_DETERMINISM_PASSED", "equal": True, "differences": [], "files": first_files}


__all__ = [
    "ENVIRONMENT_AUTHORITY_VERSION", "ITEM_PROP_AUTHORITY_VERSION", "MAP_LAYERS", "MARKER_CLASSES", "MapsMinimapContractError", "MapMinimapCache", "MapRegistry", "PRODUCTION_ROUTING_BLOCKED", "REGISTRY_TEST_ONLY", "SCHEMA_VERSION", "VISIBILITY_STATES", "build_environment_authority", "build_items_props_authority", "build_chunk_index", "canonical_json", "cell_to_chunk", "chunk_to_cell", "compare_generated_outputs", "decoded_pixel_hash", "deterministic_chunk_id", "map_cache_key", "map_manifest_hash", "map_to_minimap", "marker_set_hash", "minimap_cache_key", "minimap_to_map", "render_marker_overlay", "render_minimap_base", "render_qa_sheet", "render_visibility_sheet", "sha256_bytes", "sha256_file", "source_hash", "validate_chunk_partition", "validate_map_document", "validate_markers", "validate_regions_zones", "validate_visibility", "visibility_state_hash",
]
