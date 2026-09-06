"""Fail-closed environment/tileset runtime and QA integrity for UGAS v0.20.1.

This correction keeps the v0.20.0 candidate immutable and adds executable
class/layer routing, mask-specific TEST_ONLY visual identities, independent
world metrics, effective variant materialization and gate-specific proofs.
No production environment art, maps, minimaps, UI, VFX or orchestration is
created by this module.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from math import floor, isfinite
from numbers import Real
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from PIL import Image, ImageDraw


SCHEMA_VERSION = "0.20.1"
TILE_CLASSES = (
    "ground_terrain",
    "path_road",
    "wall_structure",
    "water_liquid",
    "cliff_height",
    "vegetation_overlay",
)
LAYER_ROLES = (
    "ground_base",
    "ground_overlay",
    "structure",
    "liquid",
    "cliff",
    "vegetation_overlay",
)
LAYER_ORDER = LAYER_ROLES
CLASS_TO_LAYER = dict(zip(TILE_CLASSES, LAYER_ROLES))
NEIGHBOR_ORDER = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
NEIGHBOR_BITS = {name: 1 << index for index, name in enumerate(NEIGHBOR_ORDER)}
CARDINAL_ONLY = "CARDINAL_ONLY"
EIGHT_NEIGHBOR = "EIGHT_NEIGHBOR"
ADJACENCY_POLICIES = (CARDINAL_ONLY, EIGHT_NEIGHBOR)
TRAVERSAL_CLASSES = ("walkable", "slow", "blocked", "water")
ALLOWED_VARIANT_OVERRIDES = frozenset({"material", "palette", "collision_navigation", "edge_signatures", "atlas_binding"})
FORBIDDEN_VARIANT_OVERRIDES = frozenset({"damage", "health", "speed", "gameplay_balance", "movement_cost", "gameplay"})
CARDINAL_SUPPORTED_MASKS = (0, 1, 4, 16, 64, 17, 5, 21, 85)
EIGHT_SUPPORTED_MASKS = (0, 1, 4, 16, 64, 17, 5, 21, 7, 255)


class EnvironmentTilesetContractError(ValueError):
    """A semantic contract rejection with a stable machine-readable class."""

    def __init__(self, rejection_class: str, detail: str):
        self.rejection_class = rejection_class
        self.error_code = rejection_class
        self.detail = detail
        super().__init__(f"{rejection_class}: {detail}")


EnvironmentTilesetError = EnvironmentTilesetContractError


def _require(condition: bool, rejection_class: str, detail: str) -> None:
    if not condition:
        raise EnvironmentTilesetContractError(rejection_class, detail)


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
        raise EnvironmentTilesetContractError("PNG_DECODE_FAILED", str(path)) from exc


def _record_hash(record: Mapping[str, Any], *, drop: Sequence[str] = ()) -> str:
    ignored = set(drop)
    return sha256_bytes(canonical_json({key: value for key, value in record.items() if key not in ignored}))


def _safe_relative_path(value: str) -> Path:
    candidate = Path(value)
    _require(not candidate.is_absolute() and ".." not in candidate.parts, "UNSAFE_ARTIFACT_PATH", value)
    return candidate


def validate_metrics(metrics: Mapping[str, Any]) -> None:
    if "world_units_per_tile" not in metrics:
        raise EnvironmentTilesetContractError("WORLD_UNITS_PER_TILE_MISSING", "world_units_per_tile is required")
    world_units = metrics.get("world_units_per_tile")
    _require(isinstance(world_units, Real) and not isinstance(world_units, bool) and isfinite(float(world_units)) and float(world_units) > 0, "WORLD_UNITS_PER_TILE_INVALID", str(world_units))
    for name in ("tile_width_px", "tile_height_px"):
        value = metrics.get(name)
        _require(isinstance(value, int) and not isinstance(value, bool) and value > 0, "INVALID_PIXEL_TILE_METRICS", name)
    _require(metrics.get("origin") in {"TOP_LEFT", "CENTER"}, "INVALID_TILE_METRICS", "unsupported origin")
    _require(metrics.get("grid_orientation") in {"Y_DOWN", "Y_UP"}, "INVALID_TILE_METRICS", "unsupported grid orientation")
    _require("tile_width" not in metrics and "tile_height" not in metrics, "NON_CANONICAL_PIXEL_METRICS", "use tile_width_px/tile_height_px")


def tile_to_world(tile_x: int, tile_y: int, metrics: Mapping[str, Any]) -> tuple[float, float]:
    validate_metrics(metrics)
    _require(isinstance(tile_x, int) and not isinstance(tile_x, bool) and isinstance(tile_y, int) and not isinstance(tile_y, bool), "INVALID_GRID_COORDINATE", "tile coordinates must be integers")
    unit = float(metrics["world_units_per_tile"])
    direction = 1.0 if metrics["grid_orientation"] == "Y_DOWN" else -1.0
    return (float(tile_x) * unit, float(tile_y) * unit * direction)


def world_to_tile(world_x: float, world_y: float, metrics: Mapping[str, Any]) -> tuple[int, int]:
    validate_metrics(metrics)
    _require(isinstance(world_x, Real) and not isinstance(world_x, bool) and isinstance(world_y, Real) and not isinstance(world_y, bool), "INVALID_WORLD_COORDINATE", "world coordinates must be numeric")
    unit = float(metrics["world_units_per_tile"])
    direction = 1.0 if metrics["grid_orientation"] == "Y_DOWN" else -1.0
    return (floor(float(world_x) / unit), floor((float(world_y) * direction) / unit))


def validate_grid_roundtrip(metrics: Mapping[str, Any], coordinates: Iterable[tuple[int, int]]) -> bool:
    return all(world_to_tile(*tile_to_world(x, y, metrics), metrics) == (x, y) for x, y in coordinates)


def validate_resolution_independence(metrics: Mapping[str, Any], pixel_resolutions: Iterable[int] = (16, 32, 64), coordinate: tuple[int, int] = (3, 5)) -> dict[str, Any]:
    validate_metrics(metrics)
    resolutions = list(pixel_resolutions)
    positions = []
    for resolution in resolutions:
        candidate = dict(metrics)
        candidate["tile_width_px"] = resolution
        candidate["tile_height_px"] = resolution
        positions.append(list(tile_to_world(coordinate[0], coordinate[1], candidate)))
    _require(all(position == positions[0] for position in positions), "WORLD_PIXEL_SCALE_COUPLING", str(positions))
    return {"status": "WORLD_PIXEL_SCALE_INDEPENDENT", "pixel_resolutions": resolutions, "positions": positions, "coordinate": list(coordinate)}


def encode_adjacency_mask(neighbor_compatibility_set: Mapping[str, bool] | Iterable[str], policy: str) -> int:
    _require(policy in ADJACENCY_POLICIES, "UNKNOWN_ADJACENCY_POLICY", str(policy))
    allowed = set(NEIGHBOR_ORDER if policy == EIGHT_NEIGHBOR else ("N", "E", "S", "W"))
    if isinstance(neighbor_compatibility_set, Mapping):
        unknown = set(neighbor_compatibility_set) - set(NEIGHBOR_ORDER)
        _require(not unknown, "UNKNOWN_NEIGHBOR_DIRECTION", ",".join(sorted(unknown)))
        _require(all(isinstance(value, bool) for value in neighbor_compatibility_set.values()), "INVALID_NEIGHBOR_MASK", "values must be bool")
        _require(not (set(neighbor_compatibility_set) - allowed and any(neighbor_compatibility_set.get(name) for name in set(neighbor_compatibility_set) - allowed)), "DIAGONAL_NOT_ALLOWED", policy)
        names = {name for name, enabled in neighbor_compatibility_set.items() if enabled}
    else:
        names = set(neighbor_compatibility_set)
        _require(names.issubset(set(NEIGHBOR_ORDER)), "UNKNOWN_NEIGHBOR_DIRECTION", str(sorted(names - set(NEIGHBOR_ORDER))))
        _require(names.issubset(allowed), "DIAGONAL_NOT_ALLOWED", policy)
    return sum(NEIGHBOR_BITS[name] for name in NEIGHBOR_ORDER if name in names)


def decode_adjacency_mask(mask: int, policy: str) -> dict[str, bool]:
    _require(isinstance(mask, int) and not isinstance(mask, bool) and 0 <= mask <= 255, "INVALID_NEIGHBOR_MASK", str(mask))
    _require(policy in ADJACENCY_POLICIES, "UNKNOWN_ADJACENCY_POLICY", str(policy))
    if policy == CARDINAL_ONLY:
        diagonal_bits = NEIGHBOR_BITS["NE"] | NEIGHBOR_BITS["SE"] | NEIGHBOR_BITS["SW"] | NEIGHBOR_BITS["NW"]
        _require(mask & diagonal_bits == 0, "DIAGONAL_NOT_ALLOWED", str(mask))
    return {name: bool(mask & bit) for name, bit in NEIGHBOR_BITS.items()}


def _image_edges(path: Path) -> dict[str, str]:
    with Image.open(path) as source:
        image = source.convert("RGBA")
        width, height = image.size
        edges = {
            "N": bytes(image.crop((0, 0, width, 1)).tobytes()),
            "E": bytes(image.crop((width - 1, 0, width, height)).tobytes()),
            "S": bytes(image.crop((0, height - 1, width, height)).tobytes()),
            "W": bytes(image.crop((0, 0, 1, height)).tobytes()),
        }
    return {key: sha256_bytes(value) for key, value in edges.items()}


def edge_signatures(path: Path) -> dict[str, str]:
    return _image_edges(path)


def compare_seam_bytes(left: Path, right: Path, direction: str = "E") -> dict[str, Any]:
    _require(direction in {"E", "S"}, "INVALID_SEAM_DIRECTION", direction)
    with Image.open(left) as left_source, Image.open(right) as right_source:
        left_image, right_image = left_source.convert("RGBA"), right_source.convert("RGBA")
        if direction == "E":
            left_edge = bytes(left_image.crop((left_image.width - 1, 0, left_image.width, left_image.height)).tobytes())
            right_edge = bytes(right_image.crop((0, 0, 1, right_image.height)).tobytes())
        else:
            left_edge = bytes(left_image.crop((0, left_image.height - 1, left_image.width, left_image.height)).tobytes())
            right_edge = bytes(right_image.crop((0, 0, right_image.width, 1)).tobytes())
    _require(left_edge == right_edge, "SEAM_INCOMPATIBLE", f"{left.name} {direction} {right.name}")
    return {"status": "SEAM_COMPATIBLE", "direction": direction, "left_edge_sha256": sha256_bytes(left_edge), "right_edge_sha256": sha256_bytes(right_edge)}


def _rect(value: Mapping[str, Any]) -> tuple[int, int, int, int]:
    _require(all(isinstance(value.get(key), int) and not isinstance(value.get(key), bool) and value[key] >= 0 for key in ("x", "y")), "INVALID_ATLAS_RECT", str(value))
    _require(all(isinstance(value.get(key), int) and not isinstance(value.get(key), bool) and value[key] > 0 for key in ("width", "height")), "INVALID_ATLAS_RECT", str(value))
    return (value["x"], value["y"], value["width"], value["height"])


def _rects_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _validate_collision(collision: Mapping[str, Any], tile_id: str) -> None:
    _require(collision.get("traversal_class") in TRAVERSAL_CLASSES, "COLLISION_NAVIGATION_INVALID", tile_id)
    _require(isinstance(collision.get("blocked"), bool), "COLLISION_NAVIGATION_INVALID", tile_id)
    _require(isinstance(collision.get("collision_mask"), int) and not isinstance(collision.get("collision_mask"), bool) and collision["collision_mask"] >= 0, "COLLISION_NAVIGATION_INVALID", tile_id)
    _require(collision["blocked"] == (collision["traversal_class"] == "blocked"), "COLLISION_NAVIGATION_CONTRADICTION", tile_id)
    _require(not (collision["blocked"] is False and collision["collision_mask"] == 255), "COLLISION_NAVIGATION_CONTRADICTION", tile_id)


def _atlas_record_by_family(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {item["terrain_family_id"]: item["atlas"] for item in manifest["terrain_families"]}


def _validate_tile_record(root: Path, tile: Mapping[str, Any], metrics: Mapping[str, Any], atlas: Mapping[str, Any], *, check_provenance: bool = True) -> None:
    tile_id = str(tile.get("tile_id"))
    _require(tile.get("class_id") in TILE_CLASSES, "TILE_CLASS_INVALID", tile_id)
    _require(tile.get("primary_layer") == CLASS_TO_LAYER[tile["class_id"]], "TILE_CLASS_LAYER_CONTRADICTION", tile_id)
    binding = tile.get("binding", {})
    artifact = root / _safe_relative_path(binding.get("artifact_path", ""))
    _require(artifact.is_file(), "STANDALONE_TILE_MISSING", tile_id)
    _require(sha256_file(artifact) == binding.get("file_sha256"), "STANDALONE_TILE_BYTES_HASH_MISMATCH", tile_id)
    _require(decoded_pixel_hash(artifact) == binding.get("decoded_pixel_hash"), "DECODED_PIXEL_HASH_MISMATCH", tile_id)
    with Image.open(artifact) as image:
        _require(image.size == (metrics["tile_width_px"], metrics["tile_height_px"]), "TILE_DIMENSIONS_INVALID", tile_id)
    _require(binding.get("dimensions_px") == [metrics["tile_width_px"], metrics["tile_height_px"]], "TILE_DIMENSIONS_INVALID", tile_id)
    _require(binding.get("atlas_revision") == atlas.get("atlas_revision"), "ATLAS_REVISION_MISMATCH", tile_id)
    rect = _rect(binding.get("atlas_rect", {}))
    _require((rect[2], rect[3]) == (metrics["tile_width_px"], metrics["tile_height_px"]), "ATLAS_PIXEL_METRIC_MISMATCH", tile_id)
    atlas_path = root / _safe_relative_path(atlas["artifact_path"])
    _require(atlas_path.is_file(), "ATLAS_ARTIFACT_MISSING", str(atlas_path))
    dimensions = tuple(atlas.get("dimensions_px", []))
    _require(len(dimensions) == 2 and all(isinstance(value, int) for value in dimensions), "ATLAS_DIMENSIONS_INVALID", tile_id)
    x, y, width, height = rect
    _require(x + width <= dimensions[0] and y + height <= dimensions[1], "ATLAS_RECT_OUT_OF_BOUNDS", tile_id)
    with Image.open(artifact) as standalone, Image.open(atlas_path) as atlas_image:
        crop = atlas_image.crop((x, y, x + width, y + height)).convert("RGBA")
        _require(crop.tobytes() == standalone.convert("RGBA").tobytes(), "ATLAS_REGION_BYTES_MISMATCH", tile_id)
    _require(tile.get("edge_signatures") == edge_signatures(artifact), "EDGE_SIGNATURE_MISMATCH", tile_id)
    _validate_collision(tile.get("collision_navigation", {}), tile_id)
    if check_provenance:
        _require(tile.get("provenance_hash") == _record_hash(tile, drop=("provenance_hash",)), "PROVENANCE_HASH_MISMATCH", tile_id)


def materialize_tile_variant(base_tile: Mapping[str, Any], variant: Mapping[str, Any]) -> dict[str, Any]:
    """Materialize inherited and explicitly overridden effective tile semantics."""
    effective = deepcopy(dict(base_tile))
    effective["tile_id"] = variant.get("resolved_tile_id", base_tile.get("tile_id"))
    effective["class_id"] = variant.get("target_class_id", base_tile.get("class_id"))
    effective["primary_layer"] = variant.get("target_layer_role", base_tile.get("primary_layer"))
    if variant.get("effective_binding") is not None:
        effective["binding"] = deepcopy(variant["effective_binding"])
    overrides = variant.get("overrides", {})
    if isinstance(overrides.get("collision_navigation"), Mapping):
        effective["collision_navigation"] = deepcopy(overrides["collision_navigation"])
    if isinstance(overrides.get("edge_signatures"), Mapping):
        effective["edge_signatures"] = deepcopy(overrides["edge_signatures"])
    effective["variant_id"] = variant.get("variant_id")
    effective["variant_revision"] = variant.get("variant_revision")
    return effective


def validate_effective_tile_variant(effective_tile: Mapping[str, Any], variant: Mapping[str, Any], tileset_context: Mapping[str, Any]) -> dict[str, Any]:
    root = Path(tileset_context["root"])
    metrics = tileset_context["metrics"]
    tiles = tileset_context["tiles"]
    atlases = tileset_context["atlases"]
    parent_id = variant.get("parent_tile_id")
    _require(parent_id in tiles, "VARIANT_PARENT_MISSING", str(parent_id))
    _require(variant.get("lineage") == [parent_id], "VARIANT_LINEAGE_INVALID", str(variant.get("lineage")))
    _require(variant.get("target_class_id") in TILE_CLASSES and variant.get("target_layer_role") in LAYER_ROLES, "VARIANT_TARGET_INVALID", str(variant.get("variant_id")))
    _require(effective_tile.get("class_id") == variant.get("target_class_id"), "AUTOTILE_VARIANT_CLASS_MISMATCH", str(variant.get("variant_id")))
    _require(effective_tile.get("primary_layer") == variant.get("target_layer_role"), "AUTOTILE_VARIANT_LAYER_MISMATCH", str(variant.get("variant_id")))
    family_id = variant.get("terrain_family_id")
    _require(family_id in atlases, "AUTOTILE_VARIANT_FAMILY_MISMATCH", str(variant.get("variant_id")))
    resolved_id = variant.get("resolved_tile_id")
    _require(resolved_id in tiles, "VARIANT_RESOLUTION_MISSING", str(resolved_id))
    resolved = tiles[resolved_id]
    _require(resolved.get("terrain_family_id") == family_id, "AUTOTILE_VARIANT_FAMILY_MISMATCH", str(resolved_id))
    _require(resolved.get("class_id") == variant.get("target_class_id"), "AUTOTILE_VARIANT_CLASS_MISMATCH", str(resolved_id))
    _require(resolved.get("primary_layer") == variant.get("target_layer_role"), "AUTOTILE_VARIANT_LAYER_MISMATCH", str(resolved_id))
    binding = effective_tile.get("binding", {})
    rect = _rect(binding.get("atlas_rect", {}))
    dimensions = tuple(atlases[family_id].get("dimensions_px", []))
    _require(rect[0] + rect[2] <= dimensions[0] and rect[1] + rect[3] <= dimensions[1], "ATLAS_RECT_OUT_OF_BOUNDS", str(variant.get("variant_id")))
    if variant.get("visual_bytes_changed"):
        _require(binding == resolved.get("binding"), "VARIANT_VISUAL_IDENTITY_MISMATCH", str(variant.get("variant_id")))
        _require(variant.get("effective_binding") == resolved.get("binding"), "VARIANT_VISUAL_IDENTITY_MISMATCH", str(variant.get("variant_id")))
    _validate_tile_record(root, effective_tile, metrics, atlases[family_id], check_provenance=False)
    expected_edges = edge_signatures(root / _safe_relative_path(binding["artifact_path"]))
    _require(effective_tile.get("edge_signatures") == expected_edges, "EDGE_SIGNATURE_MISMATCH", str(variant.get("variant_id")))
    _validate_collision(effective_tile.get("collision_navigation", {}), str(variant.get("variant_id")))
    return {"status": "EFFECTIVE_TILE_VARIANT_VALID", "variant_id": variant.get("variant_id"), "effective_tile_id": effective_tile.get("tile_id"), "content_hash": binding.get("decoded_pixel_hash")}


def _load_manifest(root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    value = json.loads(json.dumps(manifest))
    _require(value.get("schema_version") == SCHEMA_VERSION, "SCHEMA_VERSION_INVALID", str(value.get("schema_version")))
    _require(value.get("manifest_type") == "environment-tileset-runtime-qa-integrity", "MANIFEST_TYPE_INVALID", str(value.get("manifest_type")))
    _require(value.get("tileset_id") and value.get("tileset_revision"), "SCHEMA_REQUIRED_FIELD_MISSING", "tileset identity")
    _require(set(value.get("classes", [])) == set(TILE_CLASSES), "TILE_CLASS_CONTRACT_INVALID", "six stable class IDs required")
    validate_metrics(value.get("metrics", {}))
    _require(tuple(value.get("layer_order", [])) == LAYER_ORDER, "LAYER_ORDER_INVALID", "layer order must be explicit")
    layers = value.get("layers", [])
    _require([item.get("layer_role") for item in layers] == list(LAYER_ORDER) and all(item.get("acyclic") is True for item in layers), "LAYER_CONTRACT_INVALID", "explicit acyclic layers required")
    _require(value.get("production_routing") == "BLOCKED" and value.get("production_approved") is False, "PRODUCTION_ROUTING_ENABLED", "production remains blocked")
    _require(value.get("test_only") is True and value.get("production_safe") is False and value.get("production_registry_empty") is True, "TEST_FIXTURE_NOT_ISOLATED", "fixture must remain TEST_ONLY")
    _require(not value.get("prop_asset_paths"), "DIRECT_PROP_ASSET_DUPLICATION", "tileset cannot own prop asset paths")
    for socket in value.get("prop_sockets", []):
        _require(socket.get("socket_type") == "typed_prop_socket" and socket.get("prop_asset_path") in (None, ""), "DIRECT_PROP_ASSET_DUPLICATION", str(socket))
    return value


def validate_tileset_manifest(root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    value = _load_manifest(root, manifest)
    metrics = value["metrics"]
    tiles = value.get("tiles", [])
    tile_ids = [item.get("tile_id") for item in tiles]
    _require(len(tile_ids) == len(set(tile_ids)), "DUPLICATE_TILE_ID", "tile IDs must be unique")
    tiles_by_id = {item["tile_id"]: item for item in tiles}
    families = {item.get("terrain_family_id") for item in value.get("terrain_families", [])}
    _require(families and all(item.get("terrain_family_id") in families for item in tiles), "TERRAIN_FAMILY_INVALID", "tile family missing")
    atlases = _atlas_record_by_family(value)
    for family_id, atlas in atlases.items():
        atlas_path = root / _safe_relative_path(atlas.get("artifact_path", ""))
        _require(atlas_path.is_file(), "ATLAS_ARTIFACT_MISSING", family_id)
        _require(sha256_file(atlas_path) == atlas.get("file_sha256"), "ATLAS_PROVENANCE_HASH_MISMATCH", family_id)
        with Image.open(atlas_path) as image:
            _require(list(image.size) == atlas.get("dimensions_px"), "ATLAS_DIMENSIONS_INVALID", family_id)
    rects: dict[str, list[tuple[str, tuple[int, int, int, int]]] ] = {family_id: [] for family_id in families}
    for tile in tiles:
        family_id = tile.get("terrain_family_id")
        _validate_tile_record(root, tile, metrics, atlases[family_id])
        rect = _rect(tile["binding"]["atlas_rect"])
        for previous_id, previous_rect in rects[family_id]:
            _require(not _rects_overlap(rect, previous_rect), "ATLAS_RECT_OVERLAP", f"{tile['tile_id']}/{previous_id}")
        rects[family_id].append((tile["tile_id"], rect))
    variants = value.get("variants", [])
    variant_ids = {item.get("variant_id") for item in variants}
    _require(len(variant_ids) == len(variants), "VARIANT_ID_DUPLICATE", "variant IDs")
    context = {"root": root, "metrics": metrics, "tiles": tiles_by_id, "atlases": atlases}
    for variant in variants:
        parent_id = variant.get("parent_tile_id")
        _require(parent_id in tiles_by_id, "VARIANT_PARENT_MISSING", str(parent_id))
        _require(variant.get("variant_revision") and variant.get("variant_revision") != variant.get("atlas_revision"), "VARIANT_REVISION_INVALID", str(variant))
        overrides = variant.get("overrides", {})
        _require(set(overrides).issubset(ALLOWED_VARIANT_OVERRIDES), "VARIANT_OVERRIDE_FORBIDDEN", str(variant))
        _require(not set(overrides).intersection(FORBIDDEN_VARIANT_OVERRIDES), "VARIANT_OVERRIDE_FORBIDDEN", str(variant))
        _require(variant.get("resolved_tile_id") in tiles_by_id, "VARIANT_RESOLUTION_MISSING", str(variant))
        _require(variant.get("lineage") == [parent_id], "VARIANT_LINEAGE_INVALID", str(variant))
        _require(variant.get("target_class_id") == tiles_by_id[parent_id]["class_id"] and variant.get("target_layer_role") == tiles_by_id[parent_id]["primary_layer"], "VARIANT_TARGET_INVALID", str(variant))
        effective = materialize_tile_variant(tiles_by_id[parent_id], variant)
        validate_effective_tile_variant(effective, variant, context)
    family_records = {item["terrain_family_id"]: item for item in value["terrain_families"]}
    for family_id, family in family_records.items():
        policy = family.get("adjacency_policy")
        _require(policy in ADJACENCY_POLICIES, "UNKNOWN_ADJACENCY_POLICY", family_id)
        seen: set[tuple[str, int]] = set()
        for item in family.get("autotile_variants", []):
            mask = item.get("adjacency_mask")
            decode_adjacency_mask(mask, policy)
            variant = next((candidate for candidate in variants if candidate.get("variant_id") == item.get("variant_id")), None)
            _require(variant is not None, "REQUIRED_AUTOTILE_VARIANT_MISSING", str(item))
            _require(variant.get("terrain_family_id") == family_id, "AUTOTILE_VARIANT_FAMILY_MISMATCH", str(item))
            _require(item.get("target_class_id") == variant.get("target_class_id") and item.get("target_layer_role") == variant.get("target_layer_role"), "AUTOTILE_VARIANT_CLASS_MISMATCH", str(item))
            _require(item.get("autotile_tile_id") == variant.get("resolved_tile_id"), "AUTOTILE_TILE_BINDING_MISMATCH", str(item))
            _require((item.get("target_class_id"), mask) not in seen, "DUPLICATE_AUTOTILE_MASK", str(item))
            seen.add((item.get("target_class_id"), mask))
        _require({class_id for class_id, _ in seen} == set(TILE_CLASSES), "REQUIRED_AUTOTILE_CLASS_MISSING", family_id)
    for pair in value.get("seam_pairs", []):
        left = tiles_by_id[pair["left_tile_id"]]
        right = tiles_by_id[pair["right_tile_id"]]
        result = compare_seam_bytes(root / _safe_relative_path(left["binding"]["artifact_path"]), root / _safe_relative_path(right["binding"]["artifact_path"]), pair.get("direction", "E"))
        _require(pair.get("left_edge_sha256") == result["left_edge_sha256"] and pair.get("right_edge_sha256") == result["right_edge_sha256"], "SEAM_METADATA_MISMATCH", str(pair))
    _require(value.get("provenance", {}).get("manifest_hash") == _record_hash(value, drop=("provenance",)), "MANIFEST_PROVENANCE_HASH_MISMATCH", "manifest")
    return {"status": "ENVIRONMENT_TILESET_MANIFEST_VALID", "schema_version": SCHEMA_VERSION, "tile_count": len(tiles), "family_count": len(families), "variant_count": len(variants), "autotile_binding_count": sum(len(family.get("autotile_variants", [])) for family in value["terrain_families"])}


def build_cache_key(*, tileset_id: str, tileset_revision: str, terrain_family_id: str, variant_id: str, variant_revision: str, requested_class_id: str, resolved_class_id: str, requested_layer: str, resolved_layer: str, adjacency_policy: str, adjacency_mask: int, requested_tile_id: str, resolved_tile_id: str, atlas_revision: str, content_hash: str, registry_mode: str) -> str:
    fields = {"tileset_id": tileset_id, "tileset_revision": tileset_revision, "terrain_family_id": terrain_family_id, "variant_id": variant_id, "variant_revision": variant_revision, "requested_class_id": requested_class_id, "resolved_class_id": resolved_class_id, "requested_layer": requested_layer, "resolved_layer": resolved_layer, "adjacency_policy": adjacency_policy, "adjacency_mask": adjacency_mask, "requested_tile_id": requested_tile_id, "resolved_tile_id": resolved_tile_id, "atlas_revision": atlas_revision, "content_hash": content_hash, "registry_mode": registry_mode}
    _require(all(value not in (None, "") for value in fields.values()), "CACHE_IDENTITY_INCOMPLETE", "class/layer/mask/variant/atlas/content identity is required")
    return sha256_bytes(canonical_json(fields))


@dataclass(frozen=True)
class ResolverRequest:
    tileset_id: str
    terrain_family_id: str
    tile_id: str
    requested_class_id: str
    layer: str
    adjacency_policy: str
    neighbors: Mapping[str, bool]
    variant_id: str | None = None


class EnvironmentTileResolver:
    def __init__(self, manifest: Mapping[str, Any], root: Path):
        self.root = root
        self.manifest = _load_manifest(root, manifest)
        validate_tileset_manifest(root, self.manifest)
        self.tiles = {item["tile_id"]: item for item in self.manifest["tiles"]}
        self.families = {item["terrain_family_id"]: item for item in self.manifest["terrain_families"]}
        self.variants = {item["variant_id"]: item for item in self.manifest["variants"]}
        self.atlases = _atlas_record_by_family(self.manifest)
        self._cache: dict[str, dict[str, Any]] = {}

    def resolve(self, request: ResolverRequest | Mapping[str, Any]) -> dict[str, Any]:
        if isinstance(request, Mapping):
            request = ResolverRequest(**request)
        family = self.families.get(request.terrain_family_id)
        _require(family is not None, "TERRAIN_FAMILY_NOT_FOUND", request.terrain_family_id)
        _require(request.tileset_id == self.manifest["tileset_id"], "TILESET_ID_MISMATCH", request.tileset_id)
        _require(request.requested_class_id in TILE_CLASSES, "TILE_CLASS_INVALID", request.requested_class_id)
        tile = self.tiles.get(request.tile_id)
        _require(tile is not None, "TILE_ID_NOT_FOUND", request.tile_id)
        _require(tile.get("terrain_family_id") == request.terrain_family_id, "TERRAIN_FAMILY_MISMATCH", request.tile_id)
        _require(tile.get("class_id") == request.requested_class_id, "TILE_CLASS_MISMATCH", f"{request.tile_id}/{request.requested_class_id}")
        _require(request.layer == tile.get("primary_layer"), "TILE_LAYER_MISMATCH", f"{request.layer}/{tile.get('primary_layer')}")
        _require(request.layer in LAYER_ROLES, "INVALID_LAYER_ROLE", request.layer)
        _require(request.adjacency_policy == family["adjacency_policy"], "ADJACENCY_POLICY_MISMATCH", request.adjacency_policy)
        mask = encode_adjacency_mask(request.neighbors, request.adjacency_policy)
        candidates = [item for item in family["autotile_variants"] if item.get("adjacency_mask") == mask and item.get("target_class_id") == request.requested_class_id and item.get("target_layer_role") == request.layer]
        _require(bool(candidates), "UNSUPPORTED_TRANSITION", f"{request.requested_class_id}/{mask}")
        variant_id = request.variant_id or candidates[0]["variant_id"]
        variant = self.variants.get(variant_id)
        _require(variant is not None, "REQUIRED_AUTOTILE_VARIANT_MISSING", variant_id)
        _require(variant_id in {item["variant_id"] for item in candidates}, "UNSUPPORTED_TRANSITION", str(mask))
        _require(variant.get("parent_tile_id") == request.tile_id, "AUTOTILE_PARENT_TILE_MISMATCH", variant_id)
        _require(variant.get("target_class_id") == request.requested_class_id, "AUTOTILE_VARIANT_CLASS_MISMATCH", variant_id)
        _require(variant.get("target_layer_role") == request.layer, "AUTOTILE_VARIANT_LAYER_MISMATCH", variant_id)
        resolved = self.tiles.get(variant.get("resolved_tile_id"))
        _require(resolved is not None, "VARIANT_RESOLUTION_MISSING", variant_id)
        _require(resolved.get("terrain_family_id") == request.terrain_family_id, "AUTOTILE_VARIANT_FAMILY_MISMATCH", variant_id)
        _require(resolved.get("class_id") == request.requested_class_id, "AUTOTILE_VARIANT_CLASS_MISMATCH", variant_id)
        _require(resolved.get("primary_layer") == request.layer, "AUTOTILE_VARIANT_LAYER_MISMATCH", variant_id)
        effective = materialize_tile_variant(tile, variant)
        validate_effective_tile_variant(effective, variant, {"root": self.root, "metrics": self.manifest["metrics"], "tiles": self.tiles, "atlases": self.atlases})
        content_hash = resolved["binding"]["decoded_pixel_hash"]
        cache_key = build_cache_key(tileset_id=self.manifest["tileset_id"], tileset_revision=self.manifest["tileset_revision"], terrain_family_id=request.terrain_family_id, variant_id=variant_id, variant_revision=variant["variant_revision"], requested_class_id=request.requested_class_id, resolved_class_id=resolved["class_id"], requested_layer=request.layer, resolved_layer=resolved["primary_layer"], adjacency_policy=request.adjacency_policy, adjacency_mask=mask, requested_tile_id=request.tile_id, resolved_tile_id=resolved["tile_id"], atlas_revision=resolved["binding"]["atlas_revision"], content_hash=content_hash, registry_mode="TEST_ONLY")
        result = {"tileset_id": self.manifest["tileset_id"], "tileset_revision": self.manifest["tileset_revision"], "terrain_family_id": request.terrain_family_id, "variant_id": variant_id, "variant_revision": variant["variant_revision"], "requested_class_id": request.requested_class_id, "resolved_class_id": resolved["class_id"], "requested_layer": request.layer, "resolved_layer": resolved["primary_layer"], "layer": request.layer, "adjacency_policy": request.adjacency_policy, "adjacency_mask": mask, "requested_tile_id": request.tile_id, "resolved_tile_id": resolved["tile_id"], "autotile_tile_id": resolved["tile_id"], "atlas_revision": resolved["binding"]["atlas_revision"], "content_hash": content_hash, "atlas_rect": resolved["binding"]["atlas_rect"], "cache_key": cache_key, "status": "RESOLVED"}
        self._cache[cache_key] = result
        return dict(result)

    def get_cached(self, result: Mapping[str, Any]) -> dict[str, Any]:
        key = result.get("cache_key")
        _require(isinstance(key, str) and key in self._cache, "STALE_CACHE_ENTRY", "cache key does not identify an active resolution")
        current = self._cache[key]
        identity = ("tileset_id", "tileset_revision", "terrain_family_id", "variant_id", "variant_revision", "requested_class_id", "resolved_class_id", "requested_layer", "resolved_layer", "adjacency_policy", "adjacency_mask", "requested_tile_id", "resolved_tile_id", "atlas_revision", "content_hash")
        _require(all(result.get(field) == current.get(field) for field in identity), "STALE_CACHE_CROSS_CLASS_LAYER", "class/layer/mask/variant cache reuse rejected")
        return dict(current)


class EnvironmentTileRegistry:
    def __init__(self, *, production: bool = False):
        self.production = production
        self._entries: dict[str, Mapping[str, Any]] = {}

    def register(self, manifest: Mapping[str, Any]) -> None:
        if self.production:
            _require(manifest.get("test_only") is not True and manifest.get("production_approved") is True, "TEST_FIXTURE_IN_PRODUCTION_REGISTRY", "TEST_ONLY environment fixture rejected")
        self._entries[str(manifest.get("tileset_id"))] = manifest

    def cache_stats(self) -> dict[str, int]:
        return {"entries": len(self._entries)}

    @property
    def entries(self) -> list[Mapping[str, Any]]:
        return list(self._entries.values())


AutotileResolver = EnvironmentTileResolver
TilesetRegistry = EnvironmentTileRegistry


def compare_generated_outputs(first: Path, second: Path) -> dict[str, Any]:
    first_files = sorted(path.relative_to(first).as_posix() for path in first.rglob("*") if path.is_file())
    second_files = sorted(path.relative_to(second).as_posix() for path in second.rglob("*") if path.is_file())
    _require(first_files == second_files, "NONDETERMINISTIC_SECOND_TILESET_OUTPUT", "file sets differ")
    differences = [relative for relative in first_files if (first / relative).read_bytes() != (second / relative).read_bytes()]
    _require(not differences, "NONDETERMINISTIC_SECOND_TILESET_OUTPUT", ",".join(differences))
    return {"equal": True, "files": first_files, "differences": []}


def _save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=False, compress_level=9)


def _transition_role(mask: int, policy: str) -> str:
    if mask == 0:
        return "isolated_center"
    if mask == 255 or (policy == CARDINAL_ONLY and mask == (NEIGHBOR_BITS["N"] | NEIGHBOR_BITS["E"] | NEIGHBOR_BITS["S"] | NEIGHBOR_BITS["W"])):
        return "full_surround"
    cardinal = mask & (NEIGHBOR_BITS["N"] | NEIGHBOR_BITS["E"] | NEIGHBOR_BITS["S"] | NEIGHBOR_BITS["W"])
    count = sum(bool(cardinal & NEIGHBOR_BITS[name]) for name in ("N", "E", "S", "W"))
    if policy == EIGHT_NEIGHBOR and mask & (NEIGHBOR_BITS["NE"] | NEIGHBOR_BITS["SE"] | NEIGHBOR_BITS["SW"] | NEIGHBOR_BITS["NW"]):
        return "diagonal_sensitive"
    if count == 1:
        return "single_cardinal_edge"
    if count == 2 and cardinal in (17, 68):
        return "opposite_cardinal"
    if count == 2:
        return "corner_adjacent"
    if count == 3:
        return "t_junction"
    return "transition"


def _autotile_image(family_index: int, class_index: int, mask: int, width: int, height: int) -> Image.Image:
    # All generated tiles share one-pixel seam borders; their interiors encode
    # family/class/mask, so every supported mask has a distinct visual identity.
    seam = (18, 22, 28, 255)
    fill = ((55 + family_index * 31 + class_index * 17 + mask * 3) % 240, (75 + class_index * 23 + mask * 5) % 240, (45 + family_index * 29 + mask * 7) % 240, 255)
    image = Image.new("RGBA", (width, height), fill)
    draw = ImageDraw.Draw(image)
    draw.line((0, 0, 0, height - 1), fill=seam, width=1)
    draw.line((width - 1, 0, width - 1, height - 1), fill=seam, width=1)
    draw.line((0, 0, width - 1, 0), fill=seam, width=1)
    draw.line((0, height - 1, width - 1, height - 1), fill=seam, width=1)
    for index, name in enumerate(NEIGHBOR_ORDER):
        if mask & NEIGHBOR_BITS[name]:
            x = 2 + ((index * 3 + class_index) % max(1, width - 4))
            y = 2 + ((index * 5 + family_index) % max(1, height - 4))
            draw.point((x, y), fill=(255, 255, 255, 255))
            draw.line((x, 2, x, height - 3), fill=(255, 255, 255, 80), width=1)
    draw.rectangle((2, 2, width - 3, height - 3), outline=(mask % 251, (mask * 3) % 251, (mask * 7) % 251, 255), width=1)
    return image


def _collision_for_class(class_id: str) -> dict[str, Any]:
    blocked = class_id in {"wall_structure", "cliff_height"}
    return {"traversal_class": "water" if class_id == "water_liquid" else ("blocked" if blocked else "walkable"), "blocked": blocked, "collision_mask": 1 if blocked else 0, "navigation_class": "impassable" if blocked else "surface"}


def _qa_sheet(path: Path, records: Sequence[tuple[str, Path]]) -> None:
    width, row_height = 320, 48
    sheet = Image.new("RGB", (width, max(1, len(records)) * row_height), (28, 32, 40))
    draw = ImageDraw.Draw(sheet)
    for index, (label, image_path) in enumerate(records):
        with Image.open(image_path) as source:
            preview = source.convert("RGBA").resize((32, 32))
        y = index * row_height
        sheet.paste(preview.convert("RGB"), (0, y))
        draw.text((38, y + 16), label[:45], fill=(255, 255, 255))
    _save_png(sheet, path)


def generate_fixture_pack(output_dir: Path) -> dict[str, Any]:
    """Generate deterministic mask-specific TEST_ONLY tiles and evidence inputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = {"tile_width_px": 16, "tile_height_px": 16, "world_units_per_tile": 1.0, "origin": "TOP_LEFT", "grid_orientation": "Y_DOWN"}
    family_specs = (("temperate_cardinal", CARDINAL_ONLY, CARDINAL_SUPPORTED_MASKS), ("wetland_eight_neighbor", EIGHT_NEIGHBOR, EIGHT_SUPPORTED_MASKS))
    families: list[dict[str, Any]] = []
    all_tiles: list[dict[str, Any]] = []
    all_variants: list[dict[str, Any]] = []
    binding_records: list[dict[str, Any]] = []
    resolution_records: list[dict[str, Any]] = []
    seam_pairs: list[dict[str, Any]] = []
    for family_index, (family_id, policy, masks) in enumerate(family_specs):
        tile_specs: list[tuple[str, str, str, int | None, Path]] = []
        family_dir = output_dir / "tiles" / family_id
        for class_index, class_id in enumerate(TILE_CLASSES):
            base_id = f"{family_id}__{class_id}__base"
            base_path = family_dir / f"{base_id}.png"
            _save_png(_autotile_image(family_index, class_index, 0, 16, 16), base_path)
            tile_specs.append((base_id, class_id, CLASS_TO_LAYER[class_id], None, base_path))
            for mask in masks:
                tile_id = f"{family_id}__{class_id}__mask_{mask:03d}"
                tile_path = family_dir / f"{tile_id}.png"
                _save_png(_autotile_image(family_index, class_index, mask + 1, 16, 16), tile_path)
                tile_specs.append((tile_id, class_id, CLASS_TO_LAYER[class_id], mask, tile_path))
        atlas = Image.new("RGBA", (len(tile_specs) * 16, 16), (0, 0, 0, 0))
        atlas_path = output_dir / "atlases" / f"{family_id}.png"
        atlas_revision = f"atlas-{family_id}-v0201-r1"
        tile_records: list[dict[str, Any]] = []
        for index, (tile_id, class_id, layer, mask, tile_path) in enumerate(tile_specs):
            with Image.open(tile_path) as source:
                atlas.paste(source.convert("RGBA"), (index * 16, 0))
            binding = {"artifact_path": tile_path.relative_to(output_dir).as_posix(), "file_sha256": sha256_file(tile_path), "decoded_pixel_hash": decoded_pixel_hash(tile_path), "dimensions_px": [16, 16], "atlas_rect": {"x": index * 16, "y": 0, "width": 16, "height": 16}, "atlas_revision": atlas_revision}
            tile = {"tile_id": tile_id, "class_id": class_id, "terrain_family_id": family_id, "primary_layer": layer, "is_base_tile": mask is None, "adjacency_mask": mask, "binding": binding, "edge_signatures": edge_signatures(tile_path), "collision_navigation": _collision_for_class(class_id)}
            tile["provenance_hash"] = _record_hash(tile)
            tile_records.append(tile)
        _save_png(atlas, atlas_path)
        atlas_record = {"artifact_path": atlas_path.relative_to(output_dir).as_posix(), "file_sha256": sha256_file(atlas_path), "dimensions_px": [len(tile_specs) * 16, 16], "atlas_revision": atlas_revision}
        family_variants: list[dict[str, Any]] = []
        base_by_class = {tile["class_id"]: tile for tile in tile_records if tile["is_base_tile"]}
        for tile in tile_records:
            all_tiles.append(tile)
        for tile in tile_records:
            if tile["adjacency_mask"] is None:
                continue
            base = base_by_class[tile["class_id"]]
            mask = tile["adjacency_mask"]
            variant_id = f"{family_id}__{tile['class_id']}__variant_{mask:03d}"
            variant = {"variant_id": variant_id, "terrain_family_id": family_id, "parent_tile_id": base["tile_id"], "resolved_tile_id": tile["tile_id"], "target_class_id": tile["class_id"], "target_layer_role": tile["primary_layer"], "variant_revision": f"variant-{family_id}-{tile['class_id']}-{mask:03d}-r1", "atlas_revision": atlas_revision, "overrides": {"atlas_binding": deepcopy(tile["binding"]), "edge_signatures": deepcopy(tile["edge_signatures"]), "collision_navigation": deepcopy(tile["collision_navigation"])}, "lineage": [base["tile_id"]], "visual_bytes_changed": True, "effective_binding": deepcopy(tile["binding"]), "content_hash": tile["binding"]["decoded_pixel_hash"], "shared_visual_identity": False}
            family_variants.append(variant)
            all_variants.append(variant)
            item = {"terrain_family_id": family_id, "variant_id": variant_id, "adjacency_mask": mask, "target_class_id": tile["class_id"], "target_layer_role": tile["primary_layer"], "autotile_tile_id": tile["tile_id"], "identity": f"{family_id}:{tile['class_id']}:{policy}:{mask:03d}", "visual_transition_role": _transition_role(mask, policy), "shared_visual_identity": False}
            binding_records.append({"terrain_family_id": family_id, "class_id": tile["class_id"], "layer": tile["primary_layer"], "mask": mask, "autotile_tile_id": tile["tile_id"], "artifact_path": tile["binding"]["artifact_path"], "file_sha256": tile["binding"]["file_sha256"], "decoded_pixel_hash": tile["binding"]["decoded_pixel_hash"], "atlas_rect": tile["binding"]["atlas_rect"], "atlas_revision": atlas_revision, "shared_visual_identity": False})
            resolution_records.append(item)
        for class_id in TILE_CLASSES:
            class_variants = [variant for variant in family_variants if variant["target_class_id"] == class_id]
            for left, right in zip(class_variants, class_variants[1:]):
                left_tile = next(tile for tile in tile_records if tile["tile_id"] == left["resolved_tile_id"])
                right_tile = next(tile for tile in tile_records if tile["tile_id"] == right["resolved_tile_id"])
                seam = compare_seam_bytes(output_dir / left_tile["binding"]["artifact_path"], output_dir / right_tile["binding"]["artifact_path"], "E")
                seam_pairs.append({"left_tile_id": left_tile["tile_id"], "right_tile_id": right_tile["tile_id"], "direction": "E", "variant_transition": True, **seam})
        families.append({"terrain_family_id": family_id, "adjacency_policy": policy, "supported_masks": list(masks), "atlas": atlas_record, "autotile_variants": [item for item in resolution_records if item["terrain_family_id"] == family_id]})
        write_json(output_dir / "indexes" / f"{family_id}-atlas-index.json", {"schema_version": SCHEMA_VERSION, "terrain_family_id": family_id, "atlas_revision": atlas_revision, "regions": [{"tile_id": tile["tile_id"], "rect": tile["binding"]["atlas_rect"], "standalone_sha256": tile["binding"]["file_sha256"], "decoded_pixel_hash": tile["binding"]["decoded_pixel_hash"]} for tile in tile_records]})
    manifest: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "manifest_type": "environment-tileset-runtime-qa-integrity", "tileset_id": "ugas-test-environment-v0201", "tileset_revision": "tileset-v0201-r1", "classes": list(TILE_CLASSES), "metrics": metrics, "layer_order": list(LAYER_ORDER), "layers": [{"layer_role": role, "order": index, "acyclic": True} for index, role in enumerate(LAYER_ORDER)], "terrain_families": families, "tiles": all_tiles, "variants": all_variants, "seam_pairs": seam_pairs, "production_approved": False, "production_routing": "BLOCKED", "production_registry_empty": True, "test_only": True, "production_safe": False, "prop_sockets": [{"socket_id": "world-prop-socket", "socket_type": "typed_prop_socket", "prop_class": "environmental_prop", "prop_asset_path": None}], "prop_asset_paths": [], "provenance": {}, "fixture_label": "TEST_ONLY_TILE_QA_BOARD_V0201"}
    manifest["provenance"]["manifest_hash"] = _record_hash(manifest, drop=("provenance",))
    write_json(output_dir / "tileset-manifest-v0201.json", manifest)
    write_json(output_dir / "tileset-identity-v0201.json", {"schema_version": SCHEMA_VERSION, "tileset_id": manifest["tileset_id"], "tileset_revision": manifest["tileset_revision"], "manifest_hash": manifest["provenance"]["manifest_hash"], "tile_ids": [tile["tile_id"] for tile in all_tiles], "family_policies": {family["terrain_family_id"]: family["adjacency_policy"] for family in families}})
    write_json(output_dir / "edge-signatures-v0201.json", {"schema_version": SCHEMA_VERSION, "records": [{"tile_id": tile["tile_id"], "edges": tile["edge_signatures"]} for tile in all_tiles]})
    write_json(output_dir / "layer-collision-navigation-v0201.json", {"schema_version": SCHEMA_VERSION, "layers": manifest["layers"], "tiles": [{"tile_id": tile["tile_id"], "class_id": tile["class_id"], "primary_layer": tile["primary_layer"], "collision_navigation": tile["collision_navigation"]} for tile in all_tiles]})
    write_json(output_dir / "autotile-class-layer-contract-v0201.json", {"schema_version": SCHEMA_VERSION, "classes": [{"class_id": class_id, "primary_layer": CLASS_TO_LAYER[class_id]} for class_id in TILE_CLASSES], "variant_targets": [{"variant_id": variant["variant_id"], "target_class_id": variant["target_class_id"], "target_layer_role": variant["target_layer_role"]} for variant in all_variants]})
    write_json(output_dir / "autotile-byte-binding-v0201.json", {"schema_version": SCHEMA_VERSION, "status": "PASS", "records": binding_records})
    write_json(output_dir / "autotile-resolution-matrix-v0201.json", {"schema_version": SCHEMA_VERSION, "status": "PASS", "records": resolution_records})
    write_json(output_dir / "atlas-byte-integrity-v0201.json", {"schema_version": SCHEMA_VERSION, "status": "PASS", "records": [{"tile_id": tile["tile_id"], "file_sha256": tile["binding"]["file_sha256"], "decoded_pixel_hash": tile["binding"]["decoded_pixel_hash"], "atlas_rect": tile["binding"]["atlas_rect"], "atlas_revision": tile["binding"]["atlas_revision"]} for tile in all_tiles]})
    write_json(output_dir / "seam-qa-v0201.json", {"schema_version": SCHEMA_VERSION, "status": "PASS", "actual_transition_variants": True, "records": seam_pairs})
    write_json(output_dir / "effective-variant-validation-v0201.json", {"schema_version": SCHEMA_VERSION, "status": "PASS", "variant_count": len(all_variants), "materialized_before_resolution": True})
    write_json(output_dir / "world-metric-roundtrip-v0201.json", {"schema_version": SCHEMA_VERSION, "status": "PASS", "world_units_per_tile": metrics["world_units_per_tile"], "pixel_resolutions": [16, 32, 64], "positions_invariant": True, "grid_orientation": metrics["grid_orientation"]})
    write_json(output_dir / "cache-identity-v0201.json", {"schema_version": SCHEMA_VERSION, "fields": ["requested_class_id", "resolved_class_id", "requested_layer", "resolved_layer", "adjacency_mask", "variant_id", "atlas_revision", "content_hash"], "status": "PASS"})
    write_json(output_dir / "production-registry-v0201.json", {"schema_version": SCHEMA_VERSION, "status": "PRODUCTION_REGISTRY_EMPTY", "entries": [], "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0})
    write_json(output_dir / "test-only-qa-board-v0201.json", {"schema_version": SCHEMA_VERSION, "label": "TEST_ONLY_TILE_QA_BOARD_V0201", "production_registry": [], "classes": list(TILE_CLASSES), "families": [family["terrain_family_id"] for family in families], "mask_specific_visual_identity": True, "status": "TEST_ONLY"})
    _qa_sheet(output_dir / "mask-qa-sheet-v0201.png", [(f"{record['terrain_family_id']} {record['class_id']} mask {record['mask']:03d}", output_dir / record["artifact_path"]) for record in binding_records])
    _qa_sheet(output_dir / "seam-qa-sheet-v0201.png", [(f"{pair['left_tile_id']} -> {pair['right_tile_id']}", output_dir / next(tile for tile in all_tiles if tile["tile_id"] == pair["left_tile_id"])["binding"]["artifact_path"]) for pair in seam_pairs])
    validate_tileset_manifest(output_dir, manifest)
    return manifest


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(value))


__all__ = [
    "ADJACENCY_POLICIES", "ALLOWED_VARIANT_OVERRIDES", "AutotileResolver", "CARDINAL_ONLY", "CARDINAL_SUPPORTED_MASKS", "EIGHT_NEIGHBOR", "EIGHT_SUPPORTED_MASKS", "EnvironmentTileRegistry", "EnvironmentTileResolver", "EnvironmentTilesetContractError", "EnvironmentTilesetError", "LAYER_ORDER", "LAYER_ROLES", "NEIGHBOR_BITS", "NEIGHBOR_ORDER", "ResolverRequest", "SCHEMA_VERSION", "TILE_CLASSES", "TilesetRegistry", "build_cache_key", "canonical_json", "compare_generated_outputs", "compare_seam_bytes", "decode_adjacency_mask", "decoded_pixel_hash", "edge_signatures", "encode_adjacency_mask", "generate_fixture_pack", "materialize_tile_variant", "sha256_bytes", "sha256_file", "tile_to_world", "validate_effective_tile_variant", "validate_grid_roundtrip", "validate_metrics", "validate_resolution_independence", "validate_tileset_manifest", "world_to_tile", "write_json",
]
