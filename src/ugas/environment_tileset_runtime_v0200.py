"""Fail-closed environment and tileset runtime foundation for UGAS v0.20.0.

This module intentionally stops at runtime contracts and deterministic TEST_ONLY
fixtures.  It does not contain production art, maps, minimaps, UI, VFX or game
orchestration.  Every visual claim is checked against the exact PNG bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from math import floor
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from PIL import Image, ImageDraw


SCHEMA_VERSION = "0.20.0"
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
NEIGHBOR_ORDER = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
NEIGHBOR_BITS = {name: 1 << index for index, name in enumerate(NEIGHBOR_ORDER)}
CARDINAL_ONLY = "CARDINAL_ONLY"
EIGHT_NEIGHBOR = "EIGHT_NEIGHBOR"
ADJACENCY_POLICIES = (CARDINAL_ONLY, EIGHT_NEIGHBOR)
TRAVERSAL_CLASSES = ("walkable", "slow", "blocked", "water")
ALLOWED_VARIANT_OVERRIDES = frozenset({"palette", "edge_profile", "decoration", "material"})
FORBIDDEN_VARIANT_OVERRIDES = frozenset({"damage", "health", "speed", "gameplay_balance", "movement_cost"})


class EnvironmentTilesetContractError(ValueError):
    """A semantic contract rejection with a stable machine-readable class."""

    def __init__(self, rejection_class: str, detail: str):
        self.rejection_class = rejection_class
        self.error_code = rejection_class
        self.detail = detail
        super().__init__(f"{rejection_class}: {detail}")


# Short alias useful to callers that use the PDF's contract terminology.
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
            payload = f"{rgba.width}x{rgba.height}:RGBA:".encode("ascii") + rgba.tobytes()
    except Exception as exc:  # pragma: no cover - Pillow supplies the useful cause
        raise EnvironmentTilesetContractError("PNG_DECODE_FAILED", str(path)) from exc
    return sha256_bytes(payload)


def _safe_relative_path(value: str) -> Path:
    candidate = Path(value)
    _require(not candidate.is_absolute() and ".." not in candidate.parts, "UNSAFE_ARTIFACT_PATH", value)
    return candidate


def validate_metrics(metrics: Mapping[str, Any]) -> None:
    for name in ("tile_width", "tile_height", "atlas_width", "atlas_height"):
        value = metrics.get(name)
        _require(isinstance(value, int) and not isinstance(value, bool) and value > 0, "INVALID_TILE_METRICS", name)
    _require(metrics["atlas_width"] % metrics["tile_width"] == 0, "INVALID_TILE_METRICS", "atlas width must be a tile multiple")
    _require(metrics["atlas_height"] % metrics["tile_height"] == 0, "INVALID_TILE_METRICS", "atlas height must be a tile multiple")
    _require(metrics.get("origin") in {"TOP_LEFT", "CENTER"}, "INVALID_TILE_METRICS", "unsupported origin")
    _require(metrics.get("grid_orientation") in {"Y_DOWN", "Y_UP"}, "INVALID_TILE_METRICS", "unsupported grid orientation")


def tile_to_world(tile_x: int, tile_y: int, metrics: Mapping[str, Any]) -> tuple[float, float]:
    validate_metrics(metrics)
    _require(isinstance(tile_x, int) and isinstance(tile_y, int), "INVALID_GRID_COORDINATE", "tile coordinates must be integers")
    direction = 1 if metrics["grid_orientation"] == "Y_DOWN" else -1
    return (float(tile_x * metrics["tile_width"]), float(tile_y * metrics["tile_height"] * direction))


def world_to_tile(world_x: float, world_y: float, metrics: Mapping[str, Any]) -> tuple[int, int]:
    validate_metrics(metrics)
    direction = 1 if metrics["grid_orientation"] == "Y_DOWN" else -1
    return (floor(world_x / metrics["tile_width"]), floor((world_y * direction) / metrics["tile_height"]))


def validate_grid_roundtrip(metrics: Mapping[str, Any], coordinates: Iterable[tuple[int, int]]) -> bool:
    return all(world_to_tile(*tile_to_world(x, y, metrics), metrics) == (x, y) for x, y in coordinates)


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
    _require(isinstance(mask, int) and 0 <= mask <= 255, "INVALID_NEIGHBOR_MASK", str(mask))
    _require(policy in ADJACENCY_POLICIES, "UNKNOWN_ADJACENCY_POLICY", str(policy))
    if policy == CARDINAL_ONLY:
        _require(mask & (NEIGHBOR_BITS["NE"] | NEIGHBOR_BITS["SE"] | NEIGHBOR_BITS["SW"] | NEIGHBOR_BITS["NW"]) == 0, "DIAGONAL_NOT_ALLOWED", str(mask))
    return {name: bool(mask & bit) for name, bit in NEIGHBOR_BITS.items()}


def _image_edges(path: Path) -> dict[str, str]:
    with Image.open(path) as source:
        image = source.convert("RGBA")
        width, height = image.size
        edge_bytes = {
            "N": bytes(image.crop((0, 0, width, 1)).tobytes()),
            "E": bytes(image.crop((width - 1, 0, width, height)).tobytes()),
            "S": bytes(image.crop((0, height - 1, width, height)).tobytes()),
            "W": bytes(image.crop((0, 0, 1, height)).tobytes()),
        }
    return {key: sha256_bytes(value) for key, value in edge_bytes.items()}


def edge_signatures(path: Path) -> dict[str, str]:
    """Derive signatures from decoded pixel bytes, never from metadata."""
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
    compatible = left_edge == right_edge
    _require(compatible, "SEAM_INCOMPATIBLE", f"{left.name} {direction} {right.name}")
    return {"status": "SEAM_COMPATIBLE", "direction": direction, "left_edge_sha256": sha256_bytes(left_edge), "right_edge_sha256": sha256_bytes(right_edge)}


def _record_hash(record: Mapping[str, Any], *, drop: Sequence[str] = ()) -> str:
    value = {key: item for key, item in record.items() if key not in set(drop)}
    return sha256_bytes(canonical_json(value))


def _atlas_dimensions(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def _rect(value: Mapping[str, Any]) -> tuple[int, int, int, int]:
    keys = ("x", "y", "width", "height")
    _require(all(isinstance(value.get(key), int) and value[key] >= 0 for key in ("x", "y")), "INVALID_ATLAS_RECT", str(value))
    _require(all(isinstance(value.get(key), int) and value[key] > 0 for key in ("width", "height")), "INVALID_ATLAS_RECT", str(value))
    return tuple(value[key] for key in keys)  # type: ignore[return-value]


def _rects_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _load_manifest(root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    value = json.loads(json.dumps(manifest))
    _require(value.get("schema_version") == SCHEMA_VERSION, "SCHEMA_VERSION_INVALID", str(value.get("schema_version")))
    _require(value.get("tileset_id") and value.get("tileset_revision"), "SCHEMA_REQUIRED_FIELD_MISSING", "tileset identity")
    _require(set(value.get("classes", [])) == set(TILE_CLASSES), "TILE_CLASS_CONTRACT_INVALID", "six stable class IDs required")
    validate_metrics(value.get("metrics", {}))
    _require(tuple(value.get("layer_order", [])) == LAYER_ORDER, "LAYER_ORDER_INVALID", "layer order must be explicit and acyclic")
    layers = value.get("layers", [])
    _require({item.get("layer_role") for item in layers} == set(LAYER_ROLES), "LAYER_CONTRACT_INVALID", "all layer roles are required")
    _require([item.get("layer_role") for item in layers] == list(LAYER_ORDER), "LAYER_ORDER_INVALID", "layer records must follow order")
    _require(value.get("production_routing") == "BLOCKED" and value.get("production_approved") is False, "PRODUCTION_ROUTING_ENABLED", "production remains blocked")
    _require(value.get("test_only") is True and value.get("production_safe") is False, "TEST_FIXTURE_NOT_ISOLATED", "fixture must remain TEST_ONLY")
    _require(value.get("production_registry_empty") is True, "PRODUCTION_REGISTRY_NOT_EMPTY", "production registry must be empty")
    _require(not value.get("prop_asset_paths"), "DIRECT_PROP_ASSET_DUPLICATION", "tileset cannot own prop asset paths")
    for socket in value.get("prop_sockets", []):
        _require(socket.get("socket_type") == "typed_prop_socket" and socket.get("prop_asset_path") in (None, ""), "DIRECT_PROP_ASSET_DUPLICATION", str(socket))
    return value


def validate_tileset_manifest(root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate semantic, pixel, atlas, layer, collision, variant and provenance contracts."""
    value = _load_manifest(root, manifest)
    metrics = value["metrics"]
    tiles = value.get("tiles", [])
    ids = [item.get("tile_id") for item in tiles]
    _require(len(ids) == len(set(ids)), "DUPLICATE_TILE_ID", "tile IDs must be unique")
    families = {item.get("terrain_family_id") for item in value.get("terrain_families", [])}
    _require(families and all(item.get("terrain_family_id") in families for item in tiles), "TERRAIN_FAMILY_INVALID", "tile family missing")
    by_id = {item["tile_id"]: item for item in tiles}
    family_rects: dict[str, list[tuple[str, tuple[int, int, int, int], str | None]]] = {}
    for family in value["terrain_families"]:
        family_id = family["terrain_family_id"]
        atlas_path = root / _safe_relative_path(family["atlas"]["artifact_path"])
        _require(atlas_path.is_file(), "ATLAS_ARTIFACT_MISSING", str(atlas_path))
        _require(sha256_file(atlas_path) == family["atlas"]["file_sha256"], "ATLAS_PROVENANCE_HASH_MISMATCH", family_id)
        _require(_atlas_dimensions(atlas_path) == (metrics["atlas_width"], metrics["atlas_height"]), "ATLAS_DIMENSIONS_INVALID", family_id)
        family_rects[family_id] = []
    for tile in tiles:
        _require(tile.get("class_id") in TILE_CLASSES, "TILE_CLASS_INVALID", str(tile.get("class_id")))
        _require(tile.get("primary_layer") in LAYER_ROLES, "INVALID_LAYER_ROLE", str(tile.get("primary_layer")))
        binding = tile.get("binding", {})
        artifact_path = root / _safe_relative_path(binding.get("artifact_path", ""))
        _require(artifact_path.is_file(), "STANDALONE_TILE_MISSING", str(artifact_path))
        actual_bytes_hash = sha256_file(artifact_path)
        _require(actual_bytes_hash == binding.get("file_sha256"), "STANDALONE_TILE_BYTES_HASH_MISMATCH", tile["tile_id"])
        actual_pixel_hash = decoded_pixel_hash(artifact_path)
        _require(actual_pixel_hash == binding.get("decoded_pixel_hash"), "DECODED_PIXEL_HASH_MISMATCH", tile["tile_id"])
        with Image.open(artifact_path) as image:
            _require(image.size == (metrics["tile_width"], metrics["tile_height"]), "TILE_DIMENSIONS_INVALID", tile["tile_id"])
        _require(binding.get("dimensions") == [metrics["tile_width"], metrics["tile_height"]], "TILE_DIMENSIONS_INVALID", tile["tile_id"])
        _require(binding.get("atlas_revision"), "ATLAS_REVISION_MISSING", tile["tile_id"])
        computed_edges = edge_signatures(artifact_path)
        _require(computed_edges == tile.get("edge_signatures"), "EDGE_SIGNATURE_MISMATCH", tile["tile_id"])
        family_id = tile["terrain_family_id"]
        rect = _rect(binding.get("atlas_rect", {}))
        x, y, width, height = rect
        _require(x + width <= metrics["atlas_width"] and y + height <= metrics["atlas_height"], "ATLAS_RECT_OUT_OF_BOUNDS", tile["tile_id"])
        for previous_id, previous_rect, previous_alias in family_rects[family_id]:
            _require(not _rects_overlap(rect, previous_rect) or binding.get("alias_of") == previous_id or previous_alias == tile["tile_id"], "ATLAS_RECT_OVERLAP", f"{tile['tile_id']}/{previous_id}")
        family_rects[family_id].append((tile["tile_id"], rect, binding.get("alias_of")))
        atlas_path = root / _safe_relative_path(next(item for item in value["terrain_families"] if item["terrain_family_id"] == family_id)["atlas"]["artifact_path"])
        with Image.open(artifact_path) as standalone, Image.open(atlas_path) as atlas:
            cropped = atlas.crop((rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3])).convert("RGBA")
            _require(cropped.tobytes() == standalone.convert("RGBA").tobytes(), "ATLAS_REGION_BYTES_MISMATCH", tile["tile_id"])
    for family_id, rects in family_rects.items():
        for index, (tile_id, first, alias) in enumerate(rects):
            x, y, width, height = first
            _require(x + width <= metrics["atlas_width"] and y + height <= metrics["atlas_height"], "ATLAS_RECT_OUT_OF_BOUNDS", tile_id)
            for other_id, second, other_alias in rects[index + 1:]:
                if _rects_overlap(first, second):
                    _require(alias == other_id or other_alias == tile_id, "ATLAS_RECT_OVERLAP", f"{tile_id}/{other_id}")
    for pair in value.get("seam_pairs", []):
        left, right = by_id[pair["left_tile_id"]], by_id[pair["right_tile_id"]]
        left_path = root / _safe_relative_path(left["binding"]["artifact_path"])
        right_path = root / _safe_relative_path(right["binding"]["artifact_path"])
        result = compare_seam_bytes(left_path, right_path, pair.get("direction", "E"))
        _require(pair.get("left_edge_sha256") == result["left_edge_sha256"] and pair.get("right_edge_sha256") == result["right_edge_sha256"], "SEAM_METADATA_MISMATCH", str(pair))
    for tile in tiles:
        collision = tile.get("collision_navigation", {})
        _require(collision.get("traversal_class") in TRAVERSAL_CLASSES, "COLLISION_NAVIGATION_INVALID", tile["tile_id"])
        blocked = collision.get("blocked") is True
        _require(isinstance(collision.get("collision_mask"), int) and collision["collision_mask"] >= 0, "COLLISION_NAVIGATION_INVALID", tile["tile_id"])
        _require(blocked == (collision["traversal_class"] == "blocked"), "COLLISION_NAVIGATION_CONTRADICTION", tile["tile_id"])
        _require(not (blocked is False and collision["collision_mask"] == 255), "COLLISION_NAVIGATION_CONTRADICTION", tile["tile_id"])
        expected_provenance = _record_hash({key: item for key, item in tile.items() if key != "provenance_hash"})
        _require(tile.get("provenance_hash") == expected_provenance, "PROVENANCE_HASH_MISMATCH", tile["tile_id"])
    variants = value.get("variants", [])
    variant_ids = {variant.get("variant_id") for variant in variants}
    _require(len(variant_ids) == len(variants), "VARIANT_ID_DUPLICATE", "variant IDs")
    for variant in variants:
        _require(variant.get("parent_tile_id") in by_id, "VARIANT_PARENT_MISSING", str(variant))
        _require(variant.get("variant_revision") and variant.get("variant_revision") != variant.get("atlas_revision"), "VARIANT_REVISION_INVALID", str(variant))
        _require(set(variant.get("overrides", {})).issubset(ALLOWED_VARIANT_OVERRIDES), "VARIANT_OVERRIDE_FORBIDDEN", str(variant))
        _require(not set(variant.get("overrides", {})).intersection(FORBIDDEN_VARIANT_OVERRIDES), "VARIANT_OVERRIDE_FORBIDDEN", str(variant))
        _require(variant.get("resolved_tile_id") in by_id, "VARIANT_RESOLUTION_MISSING", str(variant))
        _require(variant.get("lineage") == [variant["parent_tile_id"]], "VARIANT_LINEAGE_INVALID", str(variant))
        if variant.get("visual_bytes_changed"):
            _require(variant.get("content_hash") and variant.get("atlas_revision"), "VARIANT_VISUAL_IDENTITY_MISSING", str(variant))
    terrain_families = {item["terrain_family_id"]: item for item in value["terrain_families"]}
    for family_id, family in terrain_families.items():
        policy = family["adjacency_policy"]
        _require(policy in ADJACENCY_POLICIES, "UNKNOWN_ADJACENCY_POLICY", family_id)
        _require(family.get("autotile_variants"), "REQUIRED_AUTOTILE_VARIANT_MISSING", family_id)
        for item in family.get("autotile_variants", []):
            mask = item.get("adjacency_mask")
            decode_adjacency_mask(mask, policy)
            _require(item.get("variant_id") in variant_ids, "REQUIRED_AUTOTILE_VARIANT_MISSING", str(item))
    provenance = value.get("provenance", {})
    _require(provenance.get("manifest_hash") == _record_hash(value, drop=("provenance",)), "MANIFEST_PROVENANCE_HASH_MISMATCH", "manifest")
    return {"status": "ENVIRONMENT_TILESET_MANIFEST_VALID", "schema_version": SCHEMA_VERSION, "tile_count": len(tiles), "family_count": len(families), "variant_count": len(variants)}


def build_cache_key(*, tileset_id: str, tileset_revision: str, terrain_family_id: str, variant_id: str, variant_revision: str, layer: str, adjacency_policy: str, adjacency_mask: int, tile_id: str, atlas_revision: str, content_hash: str, registry_mode: str) -> str:
    fields = {"tileset_id": tileset_id, "tileset_revision": tileset_revision, "terrain_family_id": terrain_family_id, "variant_id": variant_id, "variant_revision": variant_revision, "layer": layer, "adjacency_policy": adjacency_policy, "adjacency_mask": adjacency_mask, "tile_id": tile_id, "atlas_revision": atlas_revision, "content_hash": content_hash, "registry_mode": registry_mode}
    _require(all(value not in (None, "") for value in fields.values()), "CACHE_IDENTITY_INCOMPLETE", "all cache identity fields are required")
    return sha256_bytes(canonical_json(fields))


@dataclass(frozen=True)
class ResolverRequest:
    tileset_id: str
    terrain_family_id: str
    tile_id: str
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
        self._cache: dict[str, dict[str, Any]] = {}

    def resolve(self, request: ResolverRequest | Mapping[str, Any]) -> dict[str, Any]:
        if isinstance(request, Mapping):
            request = ResolverRequest(**request)
        family = self.families.get(request.terrain_family_id)
        _require(family is not None, "TERRAIN_FAMILY_NOT_FOUND", request.terrain_family_id)
        _require(request.tileset_id == self.manifest["tileset_id"], "TILESET_ID_MISMATCH", request.tileset_id)
        _require(request.layer in LAYER_ROLES, "INVALID_LAYER_ROLE", request.layer)
        _require(request.adjacency_policy == family["adjacency_policy"], "ADJACENCY_POLICY_MISMATCH", request.adjacency_policy)
        mask = encode_adjacency_mask(request.neighbors, request.adjacency_policy)
        tile = self.tiles.get(request.tile_id)
        _require(tile is not None and tile["terrain_family_id"] == request.terrain_family_id, "TILE_ID_NOT_FOUND", request.tile_id)
        matching_variants = [item["variant_id"] for item in family["autotile_variants"] if item["adjacency_mask"] == mask]
        _require(bool(matching_variants), "UNSUPPORTED_TRANSITION", str(mask))
        variant_id = request.variant_id or matching_variants[0]
        variant = self.variants.get(variant_id)
        _require(variant is not None, "REQUIRED_AUTOTILE_VARIANT_MISSING", variant_id)
        _require(variant_id in matching_variants, "UNSUPPORTED_TRANSITION", str(mask))
        resolved = self.tiles[variant["resolved_tile_id"]]
        content_hash = resolved["binding"]["decoded_pixel_hash"]
        cache_key = build_cache_key(tileset_id=self.manifest["tileset_id"], tileset_revision=self.manifest["tileset_revision"], terrain_family_id=request.terrain_family_id, variant_id=variant_id, variant_revision=variant["variant_revision"], layer=request.layer, adjacency_policy=request.adjacency_policy, adjacency_mask=mask, tile_id=resolved["tile_id"], atlas_revision=resolved["binding"]["atlas_revision"], content_hash=content_hash, registry_mode="TEST_ONLY")
        result = {"tileset_id": self.manifest["tileset_id"], "tileset_revision": self.manifest["tileset_revision"], "terrain_family_id": request.terrain_family_id, "variant_id": variant_id, "variant_revision": variant["variant_revision"], "layer": request.layer, "adjacency_policy": request.adjacency_policy, "adjacency_mask": mask, "tile_id": resolved["tile_id"], "atlas_revision": resolved["binding"]["atlas_revision"], "content_hash": content_hash, "atlas_rect": resolved["binding"]["atlas_rect"], "cache_key": cache_key, "status": "RESOLVED"}
        self._cache[cache_key] = result
        return dict(result)

    def get_cached(self, result: Mapping[str, Any]) -> dict[str, Any]:
        key = result.get("cache_key")
        _require(isinstance(key, str) and key in self._cache, "STALE_CACHE_ENTRY", "cache key does not identify an active resolution")
        current = self._cache[key]
        identity_fields = ("tileset_id", "tileset_revision", "terrain_family_id", "variant_id", "variant_revision", "layer", "adjacency_policy", "adjacency_mask", "tile_id", "atlas_revision", "content_hash")
        _require(all(result.get(field) == current.get(field) for field in identity_fields), "STALE_CACHE_CROSS_IDENTITY", "cross-mask/tileset/layer/revision cache reuse rejected")
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


# Public names used by the runtime contract and by downstream validators.
AutotileResolver = EnvironmentTileResolver
TilesetRegistry = EnvironmentTileRegistry


def compare_generated_outputs(first: Path, second: Path) -> dict[str, Any]:
    first_files = sorted(path.relative_to(first).as_posix() for path in first.rglob("*") if path.is_file())
    second_files = sorted(path.relative_to(second).as_posix() for path in second.rglob("*") if path.is_file())
    _require(first_files == second_files, "NONDETERMINISTIC_SECOND_TILESET_OUTPUT", "file sets differ")
    differences: list[str] = []
    identity_differences: list[str] = []
    for relative in first_files:
        if (first / relative).read_bytes() != (second / relative).read_bytes():
            differences.append(relative)
            if "identity" in relative:
                identity_differences.append(relative)
    if identity_differences:
        raise EnvironmentTilesetContractError("NONDETERMINISTIC_SECOND_TILESET_IDENTITY", ",".join(identity_differences))
    _require(not differences, "NONDETERMINISTIC_SECOND_TILESET_OUTPUT", ",".join(differences))
    return {"equal": True, "files": first_files, "differences": []}


def _save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=False, compress_level=9)


def _tile_image(family_index: int, class_index: int, width: int, height: int) -> Image.Image:
    border = (32 + family_index * 20, 70 + family_index * 18, 90 + family_index * 17, 255)
    fill = (70 + class_index * 25, 115 + class_index * 17, 55 + class_index * 23, 255)
    image = Image.new("RGBA", (width, height), border)
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 2, width - 3, height - 3), fill=fill)
    draw.line((3, height // 2, width - 4, height // 2), fill=(255, 255, 255, 80), width=1)
    draw.line((width // 2, 3, width // 2, height - 4), fill=(0, 0, 0, 60), width=1)
    return image


def generate_fixture_pack(output_dir: Path) -> dict[str, Any]:
    """Generate a deterministic, non-production fixture pack into ``output_dir``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = {"tile_width": 16, "tile_height": 16, "atlas_width": 96, "atlas_height": 16, "origin": "TOP_LEFT", "grid_orientation": "Y_DOWN"}
    tiles: list[dict[str, Any]] = []
    families: list[dict[str, Any]] = []
    family_specs = (("temperate_cardinal", CARDINAL_ONLY), ("wetland_eight_neighbor", EIGHT_NEIGHBOR))
    for family_index, (family_id, policy) in enumerate(family_specs):
        atlas = Image.new("RGBA", (metrics["atlas_width"], metrics["atlas_height"]), (0, 0, 0, 0))
        family_tiles: list[dict[str, Any]] = []
        for class_index, class_id in enumerate(TILE_CLASSES):
            tile_id = f"{family_id}__{class_id}"
            image = _tile_image(family_index, class_index, metrics["tile_width"], metrics["tile_height"])
            tile_path = output_dir / "tiles" / f"{tile_id}.png"
            _save_png(image, tile_path)
            x = class_index * metrics["tile_width"]
            atlas.paste(image, (x, 0))
            layer = {"ground_terrain": "ground_base", "path_road": "ground_overlay", "wall_structure": "structure", "water_liquid": "liquid", "cliff_height": "cliff", "vegetation_overlay": "vegetation_overlay"}[class_id]
            collision = {"traversal_class": "water" if class_id == "water_liquid" else ("blocked" if class_id in {"wall_structure", "cliff_height"} else "walkable"), "blocked": class_id in {"wall_structure", "cliff_height"}, "collision_mask": 1 if class_id in {"wall_structure", "cliff_height"} else 0, "navigation_class": "impassable" if class_id in {"wall_structure", "cliff_height"} else "surface"}
            tile = {"tile_id": tile_id, "class_id": class_id, "terrain_family_id": family_id, "primary_layer": layer, "binding": {"artifact_path": tile_path.relative_to(output_dir).as_posix(), "file_sha256": sha256_file(tile_path), "decoded_pixel_hash": decoded_pixel_hash(tile_path), "dimensions": [16, 16], "atlas_rect": {"x": x, "y": 0, "width": 16, "height": 16}, "atlas_revision": f"atlas-{family_id}-r1", "provenance": {"source": "v0.20.0-deterministic-test-fixture"}}, "edge_signatures": edge_signatures(tile_path), "collision_navigation": collision}
            tile["provenance_hash"] = _record_hash(tile)
            tiles.append(tile)
            family_tiles.append(tile)
        atlas_path = output_dir / "atlases" / f"{family_id}.png"
        _save_png(atlas, atlas_path)
        atlas_record = {"artifact_path": atlas_path.relative_to(output_dir).as_posix(), "file_sha256": sha256_file(atlas_path), "dimensions": [96, 16], "atlas_revision": f"atlas-{family_id}-r1"}
        required_masks = [0, NEIGHBOR_BITS["N"], NEIGHBOR_BITS["E"], NEIGHBOR_BITS["S"], NEIGHBOR_BITS["W"], NEIGHBOR_BITS["N"] | NEIGHBOR_BITS["E"] | NEIGHBOR_BITS["S"], NEIGHBOR_BITS["N"] | NEIGHBOR_BITS["E"]]
        if policy == EIGHT_NEIGHBOR:
            required_masks[-1] = NEIGHBOR_BITS["N"] | NEIGHBOR_BITS["NE"] | NEIGHBOR_BITS["E"]
            required_masks += [NEIGHBOR_BITS["NE"] | NEIGHBOR_BITS["SW"], 255]
        variants: list[dict[str, Any]] = []
        autotile_variants: list[dict[str, Any]] = []
        for mask_index, mask in enumerate(required_masks):
            base = family_tiles[mask_index % len(family_tiles)]
            variant_id = f"{family_id}__mask_{mask:03d}"
            variant = {"variant_id": variant_id, "parent_tile_id": base["tile_id"], "variant_revision": f"variant-{family_id}-r{mask_index + 1}", "atlas_revision": atlas_record["atlas_revision"], "overrides": {"edge_profile": f"mask-{mask:03d}"}, "lineage": [base["tile_id"]], "resolved_tile_id": base["tile_id"], "visual_bytes_changed": False, "content_hash": base["binding"]["decoded_pixel_hash"]}
            variants.append(variant)
            autotile_variants.append({"variant_id": variant_id, "adjacency_mask": mask, "identity": f"{family_id}:{policy}:{mask:03d}"})
        families.append({"terrain_family_id": family_id, "adjacency_policy": policy, "atlas": atlas_record, "autotile_variants": autotile_variants})
        write_json(output_dir / "indexes" / f"{family_id}-atlas-index.json", {"schema_version": SCHEMA_VERSION, "terrain_family_id": family_id, "atlas_revision": atlas_record["atlas_revision"], "regions": [{"tile_id": tile["tile_id"], "rect": tile["binding"]["atlas_rect"], "standalone_sha256": tile["binding"]["file_sha256"]} for tile in family_tiles]})
    manifest: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "manifest_type": "environment-tileset-runtime-foundation", "tileset_id": "ugas-test-environment-v0200", "tileset_revision": "tileset-r1", "classes": list(TILE_CLASSES), "metrics": metrics, "layer_order": list(LAYER_ORDER), "layers": [{"layer_role": role, "order": index, "acyclic": True} for index, role in enumerate(LAYER_ORDER)], "terrain_families": families, "tiles": tiles, "variants": [variant for family in families for variant in []], "production_approved": False, "production_routing": "BLOCKED", "production_registry_empty": True, "test_only": True, "production_safe": False, "prop_sockets": [{"socket_id": "world-prop-socket", "socket_type": "typed_prop_socket", "prop_class": "environmental_prop", "prop_asset_path": None}], "prop_asset_paths": [], "seam_pairs": [], "provenance": {}, "fixture_label": "TEST_ONLY_TILE_QA_BOARD"}
    # Keep variant order stable and pair matching edges from the same family.
    all_variants: list[dict[str, Any]] = []
    for family in families:
        family_tiles = [tile for tile in tiles if tile["terrain_family_id"] == family["terrain_family_id"]]
        family_variants = []
        for mask_item in family["autotile_variants"]:
            base = family_tiles[len(family_variants) % len(family_tiles)]
            variant = {"variant_id": mask_item["variant_id"], "parent_tile_id": base["tile_id"], "variant_revision": f"variant-{family['terrain_family_id']}-r{len(family_variants) + 1}", "atlas_revision": family["atlas"]["atlas_revision"], "overrides": {"edge_profile": f"mask-{mask_item['adjacency_mask']:03d}"}, "lineage": [base["tile_id"]], "resolved_tile_id": base["tile_id"], "visual_bytes_changed": False, "content_hash": base["binding"]["decoded_pixel_hash"]}
            all_variants.append(variant)
            family_variants.append(variant)
        # Adjacent regions in each atlas share their exact generated border.
        for left, right in zip(family_tiles, family_tiles[1:]):
            left_path = output_dir / left["binding"]["artifact_path"]
            right_path = output_dir / right["binding"]["artifact_path"]
            seam = compare_seam_bytes(left_path, right_path, "E")
            manifest["seam_pairs"].append({"left_tile_id": left["tile_id"], "right_tile_id": right["tile_id"], "direction": "E", **seam})
    manifest["variants"] = all_variants
    manifest["provenance"]["manifest_hash"] = _record_hash(manifest, drop=("provenance",))
    write_json(output_dir / "tileset-manifest-v0200.json", manifest)
    write_json(output_dir / "tileset-identity.json", {"schema_version": SCHEMA_VERSION, "tileset_id": manifest["tileset_id"], "tileset_revision": manifest["tileset_revision"], "manifest_hash": manifest["provenance"]["manifest_hash"], "tile_ids": [tile["tile_id"] for tile in tiles], "family_policies": {family["terrain_family_id"]: family["adjacency_policy"] for family in families}})
    write_json(output_dir / "edge-signatures-v0200.json", {"schema_version": SCHEMA_VERSION, "records": [{"tile_id": tile["tile_id"], "edges": tile["edge_signatures"]} for tile in tiles]})
    write_json(output_dir / "layer-collision-navigation-v0200.json", {"schema_version": SCHEMA_VERSION, "layers": manifest["layers"], "tiles": [{"tile_id": tile["tile_id"], "primary_layer": tile["primary_layer"], "collision_navigation": tile["collision_navigation"]} for tile in tiles]})
    write_json(output_dir / "autotile-identities-v0200.json", {"schema_version": SCHEMA_VERSION, "families": [{"terrain_family_id": family["terrain_family_id"], "adjacency_policy": family["adjacency_policy"], "identities": family["autotile_variants"]} for family in families]})
    write_json(output_dir / "collision-sheet-v0200.json", {"schema_version": SCHEMA_VERSION, "status": "COLLISION_NAVIGATION_CONTRACT_VALID", "records": [{"tile_id": tile["tile_id"], **tile["collision_navigation"]} for tile in tiles]})
    write_json(output_dir / "seam-sheet-v0200.json", {"schema_version": SCHEMA_VERSION, "status": "SEAM_COMPATIBILITY_VERIFIED", "records": manifest["seam_pairs"]})
    _write_qa_sheet(output_dir / "atlas-qa-sheet-v0200.png", [(family["terrain_family_id"], output_dir / family["atlas"]["artifact_path"]) for family in families])
    _write_qa_sheet(output_dir / "mask-qa-sheet-v0200.png", [(family["terrain_family_id"], output_dir / "atlases" / f"{family['terrain_family_id']}.png") for family in families])
    _write_qa_sheet(output_dir / "layer-qa-sheet-v0200.png", [(tile["tile_id"], output_dir / tile["binding"]["artifact_path"]) for tile in tiles])
    _write_qa_sheet(output_dir / "collision-qa-sheet-v0200.png", [(tile["tile_id"], output_dir / tile["binding"]["artifact_path"]) for tile in tiles])
    tiles_by_id = {item["tile_id"]: item for item in tiles}
    _write_qa_sheet(output_dir / "seam-qa-sheet-v0200.png", [(pair["left_tile_id"], output_dir / tiles_by_id[pair["left_tile_id"]]["binding"]["artifact_path"]) for pair in manifest["seam_pairs"]])
    validate_tileset_manifest(output_dir, manifest)
    return manifest


def _write_qa_sheet(path: Path, entries: Sequence[tuple[str, Path]]) -> None:
    width, height, label_height = 192, 64, 16
    sheet = Image.new("RGB", (width, max(1, len(entries)) * height), (28, 32, 40))
    draw = ImageDraw.Draw(sheet)
    for index, (label, image_path) in enumerate(entries):
        with Image.open(image_path) as source:
            preview = source.convert("RGBA").resize((min(160, source.width * 4), min(40, source.height * 4)))
        y = index * height
        sheet.paste(preview.convert("RGB"), (0, y))
        draw.text((2, y + height - label_height), label[:28], fill=(255, 255, 255))
    _save_png(sheet, path)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(value))


__all__ = [
    "ADJACENCY_POLICIES", "ALLOWED_VARIANT_OVERRIDES", "AutotileResolver", "CARDINAL_ONLY", "EIGHT_NEIGHBOR", "EnvironmentTileRegistry", "EnvironmentTileResolver", "EnvironmentTilesetContractError", "EnvironmentTilesetError", "LAYER_ORDER", "LAYER_ROLES", "NEIGHBOR_BITS", "NEIGHBOR_ORDER", "ResolverRequest", "SCHEMA_VERSION", "TILE_CLASSES", "TilesetRegistry", "build_cache_key", "canonical_json", "compare_generated_outputs", "compare_seam_bytes", "decode_adjacency_mask", "decoded_pixel_hash", "edge_signatures", "encode_adjacency_mask", "generate_fixture_pack", "sha256_bytes", "sha256_file", "tile_to_world", "validate_grid_roundtrip", "validate_metrics", "validate_tileset_manifest", "world_to_tile", "write_json"
]
