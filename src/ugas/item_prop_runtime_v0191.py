"""Fail-closed item/prop runtime contract for the v0.19.1 correction.

This module is forward-only from v0.19.0.  It resolves TEST_ONLY item/prop
identity, verifies every resolved representation against bytes on disk, binds
equipment references to the frozen v0.17.1 authority, and keeps stack identity
at item-family granularity.  It deliberately contains no production asset
generation or equipment compositor logic.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "0.19.1"
ITEM_CLASSES = (
    "weapon_item",
    "consumable_item",
    "material_item",
    "quest_key_item",
    "container_prop",
    "environmental_prop",
)
CONTEXTS = ("inventory", "world", "equipment-preview")
REPRESENTATION_FIELDS = ("inventory_icon", "world_sprite_prop", "equipment_ref")
AVAILABILITIES = {"REQUIRED", "OPTIONAL", "UNSUPPORTED"}
STACK_POLICIES = {"STACKABLE", "NON_STACKABLE", "UNIQUE_INSTANCE_REQUIRED"}
ALLOWED_VARIANT_OVERRIDES = frozenset(
    {
        "representation_binding",
        "scale",
        "collision",
        "footprint",
        "anchors",
        "material_palette",
        "equipment_ref",
        "stack_family_id",
        "provenance",
    }
)
FORBIDDEN_VARIANT_OVERRIDES = frozenset(
    {"stats", "rarity", "power", "value", "combat", "economy", "balance", "damage", "display_name", "lore"}
)
EXPECTED_WORLD_CLASSES = {"container_prop", "environmental_prop"}
GENERIC_STACK_KEYS = set(ITEM_CLASSES)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_blob_id(value: bytes) -> str:
    # Git's normal text filter hashes the LF-normalized blob while the
    # filesystem authority hash below intentionally remains the exact bytes.
    normalized = value.replace(b"\r\n", b"\n")
    return hashlib.sha1(f"blob {len(normalized)}\0".encode("ascii") + normalized).hexdigest()


class ItemPropRuntimeError(ValueError):
    """Base runtime exception."""


class ItemPropContractError(ItemPropRuntimeError):
    """A malformed, stale, or unsafe item/prop contract."""

    rejection_class = "CONTRACT_REJECTION"

    def __init__(self, error_code: str, detail: str | None = None) -> None:
        self.error_code = error_code
        super().__init__(f"{error_code}{': ' + detail if detail else ''}")


def _require(condition: bool, error_code: str, detail: str | None = None) -> None:
    if not condition:
        raise ItemPropContractError(error_code, detail)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _positive_extent(value: Any, error_code: str) -> None:
    _require(_number(value) and value > 0, error_code)


def _point(value: Any, error_code: str) -> None:
    _require(isinstance(value, Mapping) and _number(value.get("x")) and _number(value.get("y")), error_code)


def _bounds(value: Any, error_code: str) -> None:
    _require(isinstance(value, Mapping), error_code)
    for key in ("x", "y", "width", "height"):
        _require(_number(value.get(key)), error_code)
    _positive_extent(value["width"], error_code)
    _positive_extent(value["height"], error_code)


def _point_inside(point: Mapping[str, Any], bounds: Mapping[str, Any]) -> bool:
    return bounds["x"] <= point["x"] <= bounds["x"] + bounds["width"] and bounds["y"] <= point["y"] <= bounds["y"] + bounds["height"]


def _record_without_hash(record: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(record))
    result.pop("provenance_hash", None)
    return result


def _record_hash(record: Mapping[str, Any]) -> str:
    return sha256_json(_record_without_hash(record))


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdefABCDEF" for char in value)


def _safe_artifact_path(root: Path, relative: Any) -> Path:
    _require(isinstance(relative, str) and bool(relative), "REPRESENTATION_ARTIFACT_PATH_INVALID")
    candidate = Path(relative)
    _require(not candidate.is_absolute() and ".." not in candidate.parts, "REPRESENTATION_ARTIFACT_PATH_INVALID")
    root_resolved = root.resolve()
    resolved = (root_resolved / candidate).resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ItemPropContractError("REPRESENTATION_ARTIFACT_PATH_INVALID") from exc
    return resolved


def _decoded_pixel_hash(raw: bytes) -> tuple[str, dict[str, int]]:
    try:
        from PIL import Image

        with Image.open(BytesIO(raw)) as image:
            rgba = image.convert("RGBA")
            return sha256_bytes(rgba.tobytes()), {"width": rgba.width, "height": rgba.height}
    except Exception as exc:  # pragma: no cover - exact library error is not contract surface
        raise ItemPropContractError("REPRESENTATION_ARTIFACT_INVALID", str(exc)) from exc


def _validate_representation_binding(binding: Mapping[str, Any], *, artifact_root: Path | None = None) -> None:
    required = (
        "representation_id",
        "asset_revision",
        "representation_revision",
        "content_hash",
        "file_sha256",
        "decoded_pixel_hash",
        "artifact_path",
        "byte_size",
        "dimensions",
        "pivot",
        "provenance",
    )
    _require(all(key in binding for key in required), "REPRESENTATION_BINDING_INCOMPLETE")
    _require(isinstance(binding["representation_id"], str) and bool(binding["representation_id"]), "REPRESENTATION_ID_INVALID")
    _require(isinstance(binding["asset_revision"], str) and bool(binding["asset_revision"]), "REPRESENTATION_REVISION_INVALID")
    _require(binding["representation_revision"] == binding["asset_revision"], "REPRESENTATION_REVISION_MISMATCH")
    _require(_is_sha256(binding["content_hash"]) and _is_sha256(binding["file_sha256"]), "REPRESENTATION_CONTENT_HASH_INVALID")
    _require(_is_sha256(binding["decoded_pixel_hash"]), "REPRESENTATION_PIXEL_HASH_INVALID")
    _require(isinstance(binding["byte_size"], int) and binding["byte_size"] > 0, "REPRESENTATION_BYTE_SIZE_INVALID")
    dimensions = binding["dimensions"]
    _require(isinstance(dimensions, Mapping), "REPRESENTATION_DIMENSIONS_INVALID")
    _positive_extent(dimensions.get("width"), "REPRESENTATION_DIMENSIONS_INVALID")
    _positive_extent(dimensions.get("height"), "REPRESENTATION_DIMENSIONS_INVALID")
    _point(binding["pivot"], "REPRESENTATION_PIVOT_INVALID")
    _require(isinstance(binding["provenance"], Mapping) and isinstance(binding["provenance"].get("provenance_hash"), str), "REPRESENTATION_PROVENANCE_INVALID")
    _require(binding["provenance"]["provenance_hash"] == _record_hash({key: value for key, value in binding.items() if key != "provenance"}), "REPRESENTATION_PROVENANCE_INVALID")
    if artifact_root is not None:
        path = _safe_artifact_path(artifact_root, binding["artifact_path"])
        _require(path.is_file(), "REPRESENTATION_ARTIFACT_MISSING")
        raw = path.read_bytes()
        file_hash = sha256_bytes(raw)
        _require(len(raw) == binding["byte_size"], "REPRESENTATION_ARTIFACT_BYTE_SIZE_MISMATCH")
        _require(file_hash.casefold() == str(binding["file_sha256"]).casefold() == str(binding["content_hash"]).casefold(), "REPRESENTATION_ARTIFACT_HASH_MISMATCH")
        pixels, actual_dimensions = _decoded_pixel_hash(raw)
        _require(pixels.casefold() == str(binding["decoded_pixel_hash"]).casefold(), "REPRESENTATION_ARTIFACT_PIXEL_HASH_MISMATCH")
        _require(actual_dimensions == {"width": int(dimensions["width"]), "height": int(dimensions["height"])}, "REPRESENTATION_ARTIFACT_DIMENSIONS_MISMATCH")


def _validate_representation_profile(record: Mapping[str, Any], *, artifact_root: Path | None = None) -> None:
    profile = record.get("representation_profile")
    representations = record.get("representations")
    _require(isinstance(profile, Mapping), "REPRESENTATION_PROFILE_INVALID")
    _require(isinstance(representations, Mapping), "REPRESENTATIONS_INVALID")
    for field in REPRESENTATION_FIELDS:
        item = profile.get(field)
        _require(isinstance(item, Mapping) and item.get("availability") in AVAILABILITIES, "REPRESENTATION_PROFILE_INVALID")
        availability = item["availability"]
        binding = representations.get(field)
        if availability == "UNSUPPORTED":
            _require(binding is None, "UNSUPPORTED_REPRESENTATION_HAS_HIDDEN_BINDING")
            _require(not any(key in item for key in ("asset_path", "asset_id", "representation_id", "content_hash", "artifact_path")), "UNSUPPORTED_REPRESENTATION_HAS_HIDDEN_BINDING")
        elif availability == "REQUIRED":
            _require(isinstance(binding, Mapping), "REQUIRED_REPRESENTATION_MISSING")
        elif binding is not None:
            _require(isinstance(binding, Mapping), "OPTIONAL_REPRESENTATION_INVALID")
        if isinstance(binding, Mapping):
            _validate_representation_binding(binding, artifact_root=artifact_root)


def _validate_world_geometry(record: Mapping[str, Any]) -> None:
    profile = record["representation_profile"]
    geometry = record.get("world_geometry")
    has_world = profile["world_sprite_prop"]["availability"] != "UNSUPPORTED"
    if not has_world:
        _require(geometry is None, "INVENTORY_ONLY_WORLD_GEOMETRY_FORBIDDEN")
        return
    _require(isinstance(geometry, Mapping), "WORLD_GEOMETRY_MISSING")
    for key in ("visual_bounds", "collision_bounds"):
        _bounds(geometry.get(key), "WORLD_GEOMETRY_INVALID")
    _point(geometry.get("pivot"), "WORLD_PIVOT_INVALID")
    _point(geometry.get("origin"), "WORLD_ORIGIN_INVALID")
    _positive_extent(geometry.get("footprint", {}).get("width") if isinstance(geometry.get("footprint"), Mapping) else None, "WORLD_FOOTPRINT_INVALID")
    _positive_extent(geometry.get("footprint", {}).get("height") if isinstance(geometry.get("footprint"), Mapping) else None, "WORLD_FOOTPRINT_INVALID")
    _positive_extent(geometry.get("scale"), "WORLD_SCALE_INVALID")
    _require(_point_inside(geometry["pivot"], geometry["visual_bounds"]), "PIVOT_OUTSIDE_VISUAL_BOUNDS")
    _require(_point_inside(geometry["pivot"], geometry["collision_bounds"]), "PIVOT_OUTSIDE_COLLISION_BOUNDS")
    anchors = geometry.get("anchors")
    _require(isinstance(anchors, list) and anchors, "INTERACTION_ANCHORS_MISSING")
    seen: set[str] = set()
    for anchor in anchors:
        _require(isinstance(anchor, Mapping) and isinstance(anchor.get("anchor_id"), str) and anchor["anchor_id"] not in seen, "INTERACTION_ANCHOR_INVALID")
        seen.add(anchor["anchor_id"])
        _require(anchor.get("kind") in {"interaction", "pickup", "open", "place"}, "INTERACTION_ANCHOR_INVALID")
        _point(anchor.get("point"), "INTERACTION_ANCHOR_INVALID")
        _require(_point_inside(anchor["point"], geometry["visual_bounds"]), "INTERACTION_ANCHOR_OUTSIDE_BOUNDS")


def _validate_stack_identity(record: Mapping[str, Any]) -> None:
    policy = record.get("stack_policy")
    _require(policy in STACK_POLICIES, "STACK_POLICY_INVALID")
    display_variant_id = record.get("display_variant_id")
    _require(isinstance(display_variant_id, str) and bool(display_variant_id), "DISPLAY_VARIANT_ID_INVALID")
    family = record.get("stack_family_id")
    stack_key = record.get("stack_key")
    if record.get("class_id") == "quest_key_item":
        _require(policy == "UNIQUE_INSTANCE_REQUIRED", "QUEST_KEY_MUST_BE_UNIQUE")
    if policy == "UNIQUE_INSTANCE_REQUIRED":
        _require(stack_key is None and family is None, "UNIQUE_ITEM_GENERIC_STACK_FORBIDDEN")
    elif policy == "STACKABLE":
        _require(isinstance(family, str) and bool(family), "STACK_FAMILY_MISSING")
        _require(family not in GENERIC_STACK_KEYS and not family.endswith("_item"), "STACK_IDENTITY_TOO_COARSE")
        _require(isinstance(stack_key, str) and stack_key == family, "STACK_IDENTITY_TOO_COARSE")
    else:
        _require(stack_key is None and family is None, "NON_STACKABLE_FAMILY_FORBIDDEN")


def _validate_equipment_ref(record: Mapping[str, Any], authority: EquipmentAuthority | None = None) -> Mapping[str, Any] | None:
    ref = record.get("equipment_ref")
    profile = record["representation_profile"]["equipment_ref"]["availability"]
    if ref is None:
        _require(profile in {"OPTIONAL", "UNSUPPORTED"}, "EQUIPMENT_REF_PROFILE_MISMATCH")
        _require(record["representations"].get("equipment_ref") is None, "EQUIPMENT_REF_WITHOUT_IDENTITY")
        return None
    _require(profile == "REQUIRED", "EQUIPMENT_REF_PROFILE_MISMATCH")
    _require(isinstance(ref, Mapping), "EQUIPMENT_REF_INVALID")
    for key in ("equipment_id", "slot", "variant", "equipment_revision", "compatibility"):
        _require(isinstance(ref.get(key), str) and bool(ref[key]), "EQUIPMENT_REF_INVALID")
    _require(ref["compatibility"] == record.get("class_id"), "EQUIPMENT_REF_INCOMPATIBLE")
    if authority is not None:
        _require(ref.get("test_only") is True and ref.get("production_safe") is False, "EQUIPMENT_REF_BOUNDARY_MISMATCH")
    else:
        _require(ref.get("test_only") is True and ref.get("production_safe") is False, "EQUIPMENT_REF_PRODUCTION_UNSAFE")
    if authority is not None:
        asset = authority.index.get((ref["equipment_id"], ref["slot"], ref["variant"], ref["equipment_revision"]))
        if asset is None:
            same_id = [candidate for candidate in authority.assets if candidate.get("equipment_id") == ref["equipment_id"]]
            if not same_id:
                raise ItemPropContractError("EQUIPMENT_REF_NOT_FOUND")
            if not any(candidate.get("slot") == ref["slot"] for candidate in same_id):
                raise ItemPropContractError("EQUIPMENT_REF_SLOT_MISMATCH")
            if not any(candidate.get("variant") == ref["variant"] for candidate in same_id):
                raise ItemPropContractError("EQUIPMENT_REF_VARIANT_MISMATCH")
            raise ItemPropContractError("EQUIPMENT_REF_REVISION_MISMATCH")
        _require(asset.get("test_only") is True and asset.get("production_safe") is False and ref.get("test_only") is True and ref.get("production_safe") is False, "EQUIPMENT_REF_BOUNDARY_MISMATCH")
        _require(ref.get("compatibility") in {"weapon_item"}, "EQUIPMENT_REF_INCOMPATIBLE")
        return asset
    return None


def validate_item_record(record: Mapping[str, Any], *, production_registry: bool = False, artifact_root: Path | None = None, equipment_authority: EquipmentAuthority | None = None) -> None:
    _require(isinstance(record, Mapping), "ITEM_PROP_RECORD_INVALID")
    for key in ("item_or_prop_id", "class_id", "representation_profile", "representations", "stack_policy", "stack_key", "stack_family_id", "display_variant_id", "equipment_ref", "provenance", "provenance_hash", "test_only", "production_safe"):
        _require(key in record, "ITEM_PROP_REQUIRED_FIELD_MISSING")
    _require(isinstance(record["item_or_prop_id"], str) and bool(record["item_or_prop_id"]), "ITEM_PROP_ID_INVALID")
    _require(record["class_id"] in ITEM_CLASSES, "UNKNOWN_ITEM_PROP_CLASS")
    _require(isinstance(record["test_only"], bool) and isinstance(record["production_safe"], bool), "PRODUCTION_SAFETY_FLAGS_INVALID")
    if production_registry:
        _require(record["test_only"] is False and record["production_safe"] is True, "TEST_ONLY_FIXTURE_IN_PRODUCTION_REGISTRY")
    else:
        _require(record["test_only"] is True and record["production_safe"] is False, "NON_TEST_FIXTURE_MISSING_TEST_BOUNDARY")
    _require(isinstance(record["provenance"], Mapping), "PROVENANCE_INVALID")
    _require(_is_sha256(record["provenance_hash"]), "PROVENANCE_HASH_INVALID")
    _require(record["provenance_hash"] == _record_hash(record), "PROVENANCE_HASH_MISMATCH")
    _validate_representation_profile(record, artifact_root=artifact_root)
    _validate_world_geometry(record)
    _validate_stack_identity(record)
    _validate_equipment_ref(record, equipment_authority)
    if record["class_id"] in EXPECTED_WORLD_CLASSES:
        _require(record["representation_profile"]["world_sprite_prop"]["availability"] == "REQUIRED", "CLASS_WORLD_REPRESENTATION_REQUIRED")


def validate_variant_lineage(variants: list[Mapping[str, Any]], items: list[Mapping[str, Any]]) -> None:
    _require(isinstance(variants, list), "VARIANT_LINEAGE_INVALID")
    item_ids = {item.get("item_or_prop_id") for item in items}
    item_by_id = {item.get("item_or_prop_id"): item for item in items}
    ids = [item.get("variant_id") if isinstance(item, Mapping) else None for item in variants]
    _require(len(ids) == len(set(ids)) and all(isinstance(item, str) and item for item in ids), "VARIANT_ID_INVALID")
    revisions = [item.get("variant_revision") if isinstance(item, Mapping) else None for item in variants]
    _require(len(revisions) == len(set(revisions)) and all(isinstance(item, str) and item for item in revisions), "VARIANT_REVISION_INVALID")
    by_id = {item["variant_id"]: item for item in variants}
    for variant in variants:
        _require(isinstance(variant, Mapping) and variant.get("item_or_prop_id") in item_ids, "VARIANT_ITEM_ID_INVALID")
        kind = variant.get("kind")
        parent = variant.get("parent_id")
        _require(kind in {"base", "derived"}, "VARIANT_LINEAGE_INVALID")
        _require((kind == "base" and parent is None) or (kind == "derived" and isinstance(parent, str) and parent in by_id), "VARIANT_PARENT_MISSING")
        if kind == "derived":
            _require(by_id[parent].get("item_or_prop_id") == variant.get("item_or_prop_id"), "VARIANT_PARENT_ITEM_MISMATCH")
        overrides = variant.get("overrides")
        values = variant.get("override_values")
        _require(isinstance(overrides, list) and isinstance(values, Mapping) and set(overrides) == set(values), "VARIANT_OVERRIDE_NOT_ALLOWLISTED")
        for name in overrides:
            if name in FORBIDDEN_VARIANT_OVERRIDES:
                raise ItemPropContractError("VARIANT_FORBIDDEN_OVERRIDE")
            _require(name in ALLOWED_VARIANT_OVERRIDES, "VARIANT_OVERRIDE_NOT_ALLOWLISTED")
        if kind == "base":
            _require(not overrides, "VARIANT_BASE_OVERRIDE_INVALID")
        if "stack_family_id" in overrides and item_by_id[variant["item_or_prop_id"]].get("stack_policy") == "STACKABLE":
            _require(variant["override_values"].get("stack_family_id") == item_by_id[variant["item_or_prop_id"]].get("stack_family_id"), "STACK_FAMILY_VARIANT_MISMATCH")
    for variant_id in by_id:
        seen: set[str] = set()
        cursor: str | None = variant_id
        while cursor is not None:
            _require(cursor not in seen, "VARIANT_LINEAGE_CYCLE")
            seen.add(cursor)
            cursor = by_id[cursor].get("parent_id")


def _validate_stack_collisions(items: list[Mapping[str, Any]], policy: Mapping[str, Any] | None) -> None:
    explicit = set((policy or {}).get("explicit_cross_item_stack_families", []))
    by_family: dict[str, list[str]] = {}
    for item in items:
        if item.get("stack_policy") == "STACKABLE":
            by_family.setdefault(str(item.get("stack_family_id")), []).append(str(item.get("item_or_prop_id")))
    for family, ids in by_family.items():
        if len(set(ids)) > 1 and family not in explicit:
            raise ItemPropContractError("STACK_FAMILY_COLLISION")


def validate_item_prop_manifest(manifest: Mapping[str, Any], *, production_registry: bool | None = None, artifact_root: Path | None = None, equipment_authority: EquipmentAuthority | None = None) -> None:
    _require(manifest.get("schema_version") == SCHEMA_VERSION, "ITEM_PROP_SCHEMA_VERSION_INVALID")
    _require(manifest.get("manifest_type") == "items-props-runtime-foundation", "ITEM_PROP_MANIFEST_TYPE_INVALID")
    _require(manifest.get("production_routing") == "BLOCKED", "PRODUCTION_ROUTING_BLOCKED")
    registry = bool(manifest.get("production_registry")) if production_registry is None else production_registry
    items = manifest.get("items")
    variants = manifest.get("variants")
    _require(isinstance(items, list) and isinstance(variants, list), "ITEM_PROP_SCHEMA_INVALID")
    if registry:
        _require(items == [] and variants == [], "PRODUCTION_REGISTRY_NOT_EMPTY")
    if equipment_authority is not None and items:
        metadata = manifest.get("equipment_authority")
        _require(isinstance(metadata, Mapping), "EQUIPMENT_AUTHORITY_METADATA_MISSING")
        _require(metadata.get("version") == equipment_authority.version, "EQUIPMENT_AUTHORITY_VERSION_MISMATCH")
        _require(str(metadata.get("sha256", "")).casefold() == equipment_authority.sha256.casefold(), "EQUIPMENT_AUTHORITY_HASH_MISMATCH")
        _require(metadata.get("blob_id") == equipment_authority.blob_id, "EQUIPMENT_AUTHORITY_BLOB_MISMATCH")
    seen: set[str] = set()
    for item in items:
        _require(item.get("item_or_prop_id") not in seen, "DUPLICATE_ITEM_PROP_ID")
        seen.add(item.get("item_or_prop_id"))
        validate_item_record(item, production_registry=registry, artifact_root=artifact_root, equipment_authority=equipment_authority)
    validate_variant_lineage(variants, items)
    _validate_stack_collisions(items, manifest.get("stack_compatibility_policy"))
    if registry:
        _require(manifest.get("registry_authority") == "PRODUCTION_APPROVED_ASSETS_ONLY", "PRODUCTION_REGISTRY_AUTHORITY_INVALID")


def load_equipment_authority(path: str | Path) -> EquipmentAuthority:
    source = Path(path)
    raw = source.read_bytes()
    document = json.loads(raw.decode("utf-8"))
    _require(document.get("schema_version") == "0.17.1", "EQUIPMENT_AUTHORITY_VERSION_INVALID")
    _require(document.get("manifest_type") == "equipment-outfits-runtime", "EQUIPMENT_AUTHORITY_MANIFEST_INVALID")
    _require(document.get("production_registry") is False and document.get("registry_authority") == "TEST_ONLY_SYNTHETIC_FIXTURES", "EQUIPMENT_AUTHORITY_BOUNDARY_INVALID")
    assets = document.get("assets")
    _require(isinstance(assets, list) and len(assets) == 8, "EQUIPMENT_AUTHORITY_ASSET_SET_INVALID")
    index: dict[tuple[str, str, str, str], Mapping[str, Any]] = {}
    for asset in assets:
        _require(all(isinstance(asset.get(key), str) and bool(asset[key]) for key in ("equipment_id", "slot", "variant", "asset_revision")), "EQUIPMENT_AUTHORITY_ASSET_INVALID")
        _require(asset.get("test_only") is True and asset.get("production_safe") is False, "EQUIPMENT_AUTHORITY_BOUNDARY_MISMATCH")
        key = (asset["equipment_id"], asset["slot"], asset["variant"], asset["asset_revision"])
        _require(key not in index, "EQUIPMENT_AUTHORITY_DUPLICATE_IDENTITY")
        index[key] = copy.deepcopy(asset)
    return EquipmentAuthority("0.17.1", source, sha256_bytes(raw).upper(), git_blob_id(raw), copy.deepcopy(assets), index)


@dataclass(frozen=True)
class EquipmentAuthority:
    version: str
    path: Path
    sha256: str
    blob_id: str
    assets: list[Mapping[str, Any]]
    index: Mapping[tuple[str, str, str, str], Mapping[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "path": str(self.path), "sha256": self.sha256, "blob_id": self.blob_id, "asset_count": len(self.assets)}


def _apply_variant_override(effective: dict[str, Any], key: str, value: Any) -> None:
    if key == "representation_binding":
        effective["representations"] = copy.deepcopy(value)
    elif key in {"scale", "collision", "footprint", "anchors"}:
        geometry = copy.deepcopy(effective.get("world_geometry") or {})
        target = {"scale": "scale", "collision": "collision_bounds", "footprint": "footprint", "anchors": "anchors"}[key]
        geometry[target] = copy.deepcopy(value)
        effective["world_geometry"] = geometry
    else:
        effective[key] = copy.deepcopy(value)


def materialize_variant(item: Mapping[str, Any], variant_id: str, variants: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], Mapping[str, Any]]:
    variant = variants.get(variant_id)
    _require(isinstance(variant, Mapping) and variant.get("item_or_prop_id") == item.get("item_or_prop_id"), "ITEM_PROP_VARIANT_UNAVAILABLE")
    parent_id = variant.get("parent_id")
    if parent_id is None:
        effective = copy.deepcopy(dict(item))
    else:
        effective, _ = materialize_variant(item, parent_id, variants)
    for key in variant.get("overrides", []):
        _apply_variant_override(effective, key, variant["override_values"][key])
    lineage = copy.deepcopy(effective.get("variant_lineage") or {})
    lineage.update({"variant_id": variant["variant_id"], "kind": variant["kind"], "parent_id": parent_id, "overrides": list(variant.get("overrides", []))})
    effective["variant_lineage"] = lineage
    provenance = copy.deepcopy(dict(effective.get("provenance") or {}))
    provenance["source_revision"] = SCHEMA_VERSION
    provenance["source_id"] = f"{provenance.get('source_id', 'synthetic')}-{variant['variant_id']}"
    effective["provenance"] = provenance
    effective["provenance_hash"] = _record_hash(effective)
    return effective, variant


def validate_effective_variant(effective: Mapping[str, Any], variant: Mapping[str, Any], *, artifact_root: Path | None = None, equipment_authority: EquipmentAuthority | None = None) -> None:
    validate_item_record(effective, artifact_root=artifact_root, equipment_authority=equipment_authority)
    _require(effective.get("variant_lineage", {}).get("variant_id") == variant.get("variant_id"), "VARIANT_LINEAGE_INVALID")
    _require(isinstance(variant.get("variant_revision"), str) and bool(variant["variant_revision"]), "VARIANT_REVISION_INVALID")
    declared = variant.get("provenance_hash")
    if declared is not None:
        _require(declared == effective.get("provenance_hash"), "PROVENANCE_HASH_MISMATCH")


def _equipment_identity(ref: Any) -> str:
    if not isinstance(ref, Mapping):
        return "NONE"
    return ":".join(str(ref.get(key, "")) for key in ("equipment_id", "slot", "variant", "equipment_revision"))


def _cache_key(*, item_id: str, class_id: str, variant_id: str, variant_revision: str, context: str, binding: Mapping[str, Any], equipment_ref: Any, stack_family_id: str | None, authority: EquipmentAuthority | None, registry_mode: str) -> str:
    return "|".join(
        (
            f"item_or_prop_id={item_id}",
            f"class_id={class_id}",
            f"variant_id={variant_id}",
            f"variant_revision={variant_revision}",
            f"context={context}",
            f"representation_id={binding['representation_id']}",
            f"representation_revision={binding['representation_revision']}",
            f"content_hash={binding['content_hash']}",
            f"artifact_path={binding['artifact_path']}",
            f"stack_family_id={stack_family_id or 'NONE'}",
            f"equipment_link_revision={_equipment_identity(equipment_ref)}",
            f"equipment_authority_hash={authority.sha256 if authority else 'NONE'}",
            f"registry_mode={registry_mode}",
        )
    )


@dataclass(frozen=True)
class ItemPropResolution:
    result: str
    item_or_prop_id: str | None = None
    class_id: str | None = None
    variant_id: str | None = None
    variant_revision: str | None = None
    requested_context: str | None = None
    representation_id: str | None = None
    representation_revision: str | None = None
    content_hash: str | None = None
    artifact_path: str | None = None
    byte_size: int | None = None
    dimensions: Mapping[str, Any] | None = None
    decoded_pixel_hash: str | None = None
    stack_policy: str | None = None
    stack_family_id: str | None = None
    equipment_ref: Mapping[str, Any] | None = None
    resolved_equipment: Mapping[str, Any] | None = None
    equipment_authority_version: str | None = None
    equipment_authority_hash: str | None = None
    equipment_authority_blob_id: str | None = None
    cache_key: str = ""
    provenance_hash: str | None = None
    production_safe: bool = False
    error_code: str | None = None
    rejection_class: str | None = None
    cache_hit: bool = False
    fallback_mode: str = "NONE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "item_or_prop_id": self.item_or_prop_id,
            "class_id": self.class_id,
            "variant_id": self.variant_id,
            "variant_revision": self.variant_revision,
            "requested_context": self.requested_context,
            "representation_id": self.representation_id,
            "representation_revision": self.representation_revision,
            "content_hash": self.content_hash,
            "artifact_path": self.artifact_path,
            "byte_size": self.byte_size,
            "dimensions": dict(self.dimensions) if isinstance(self.dimensions, Mapping) else self.dimensions,
            "decoded_pixel_hash": self.decoded_pixel_hash,
            "stack_policy": self.stack_policy,
            "stack_family_id": self.stack_family_id,
            "equipment_ref": dict(self.equipment_ref) if isinstance(self.equipment_ref, Mapping) else self.equipment_ref,
            "resolved_equipment": dict(self.resolved_equipment) if isinstance(self.resolved_equipment, Mapping) else self.resolved_equipment,
            "equipment_authority_version": self.equipment_authority_version,
            "equipment_authority_hash": self.equipment_authority_hash,
            "equipment_authority_blob_id": self.equipment_authority_blob_id,
            "cache_key": self.cache_key,
            "provenance_hash": self.provenance_hash,
            "production_safe": self.production_safe,
            "error_code": self.error_code,
            "rejection_class": self.rejection_class,
            "cache_hit": self.cache_hit,
            "fallback_mode": self.fallback_mode,
        }


def _rejected(error_code: str, *, item_id: str | None = None, class_id: str | None = None, variant_id: str | None = None, context: str | None = None, cache_key: str = "", rejection_class: str = "RUNTIME_REJECTION") -> ItemPropResolution:
    return ItemPropResolution(result="REJECTED", item_or_prop_id=item_id, class_id=class_id, variant_id=variant_id, requested_context=context, cache_key=cache_key, error_code=error_code, rejection_class=rejection_class)


class ItemPropRegistry:
    """Resolve item/prop identities with byte, authority, and cache isolation."""

    def __init__(self, manifest: Mapping[str, Any], *, artifact_root: str | Path | None = None, production_registry: bool | None = None, equipment_authority: EquipmentAuthority | None = None) -> None:
        self.manifest = copy.deepcopy(dict(manifest))
        self.production_registry = bool(self.manifest.get("production_registry")) if production_registry is None else production_registry
        self.artifact_root = Path(artifact_root).resolve() if artifact_root is not None else None
        self.equipment_authority = equipment_authority
        if not self.production_registry:
            _require(self.artifact_root is not None, "REPRESENTATION_ARTIFACT_ROOT_REQUIRED")
        validate_item_prop_manifest(self.manifest, production_registry=self.production_registry, artifact_root=self.artifact_root, equipment_authority=equipment_authority)
        self._items = {item["item_or_prop_id"]: item for item in self.manifest.get("items", [])}
        self._variants = {item["variant_id"]: item for item in self.manifest.get("variants", [])}
        self._cache: dict[str, ItemPropResolution] = {}

    def cache_stats(self) -> dict[str, int]:
        return {"entries": len(self._cache), "hits": sum(1 for item in self._cache.values() if item.cache_hit), "misses": len(self._cache)}

    def clear_cache(self) -> None:
        self._cache.clear()

    def poison_cache_for_test(self, cache_key: str, resolution: ItemPropResolution) -> None:
        self._cache[cache_key] = resolution

    def resolve(self, item_or_prop_id: str, variant_id: str, context: str, *, request_mode: str = "direct", allow_preview_fallback: bool = False) -> ItemPropResolution:
        item = self._items.get(item_or_prop_id)
        if item is None:
            return _rejected("ITEM_PROP_UNKNOWN", item_id=item_or_prop_id, variant_id=variant_id, context=context)
        if context not in CONTEXTS:
            return _rejected("REQUEST_CONTEXT_INVALID", item_id=item_or_prop_id, class_id=item["class_id"], variant_id=variant_id, context=context)
        try:
            effective, variant = materialize_variant(item, variant_id, self._variants)
            validate_effective_variant(effective, variant, artifact_root=self.artifact_root, equipment_authority=self.equipment_authority)
            resolved_equipment = _validate_equipment_ref(effective, self.equipment_authority)
        except ItemPropContractError as exc:
            return _rejected(exc.error_code, item_id=item_or_prop_id, class_id=item["class_id"], variant_id=variant_id, context=context, rejection_class=exc.rejection_class)
        field = {"inventory": "inventory_icon", "world": "world_sprite_prop", "equipment-preview": "equipment_ref"}[context]
        availability = effective["representation_profile"][field]["availability"]
        binding = effective["representations"].get(field)
        if availability == "UNSUPPORTED":
            return _rejected("REPRESENTATION_CONTEXT_UNSUPPORTED", item_id=item_or_prop_id, class_id=item["class_id"], variant_id=variant["variant_id"], context=context)
        if binding is None:
            return _rejected("REPRESENTATION_OPTIONAL_UNAVAILABLE", item_id=item_or_prop_id, class_id=item["class_id"], variant_id=variant["variant_id"], context=context)
        try:
            _validate_representation_binding(binding, artifact_root=self.artifact_root)
        except ItemPropContractError as exc:
            return _rejected(exc.error_code, item_id=item_or_prop_id, class_id=item["class_id"], variant_id=variant["variant_id"], context=context, rejection_class=exc.rejection_class)
        key = _cache_key(item_id=item_or_prop_id, class_id=effective["class_id"], variant_id=variant["variant_id"], variant_revision=variant["variant_revision"], context=context, binding=binding, equipment_ref=effective.get("equipment_ref"), stack_family_id=effective.get("stack_family_id"), authority=self.equipment_authority, registry_mode="production" if self.production_registry else "test")
        cached = self._cache.get(key)
        identity = (item_or_prop_id, effective["class_id"], variant["variant_id"], variant["variant_revision"], context, binding["representation_id"], binding["representation_revision"], binding["content_hash"], binding["artifact_path"], binding.get("decoded_pixel_hash"), effective.get("stack_family_id"), _equipment_identity(effective.get("equipment_ref")), self.equipment_authority.sha256 if self.equipment_authority else None)
        if cached is not None:
            cached_identity = (cached.item_or_prop_id, cached.class_id, cached.variant_id, cached.variant_revision, cached.requested_context, cached.representation_id, cached.representation_revision, cached.content_hash, cached.artifact_path, cached.decoded_pixel_hash, cached.stack_family_id, _equipment_identity(cached.equipment_ref), cached.equipment_authority_hash)
            if cached.result != "RESOLVED" or cached_identity != identity:
                return _rejected("STALE_ITEM_PROP_CACHE_CONTEXT", item_id=item_or_prop_id, class_id=effective["class_id"], variant_id=variant["variant_id"], context=context, cache_key=key)
            return replace(cached, cache_hit=True)
        result = ItemPropResolution(
            result="RESOLVED",
            item_or_prop_id=item_or_prop_id,
            class_id=effective["class_id"],
            variant_id=variant["variant_id"],
            variant_revision=variant["variant_revision"],
            requested_context=context,
            representation_id=binding["representation_id"],
            representation_revision=binding["representation_revision"],
            content_hash=binding["content_hash"],
            artifact_path=binding["artifact_path"],
            byte_size=binding["byte_size"],
            dimensions=copy.deepcopy(binding["dimensions"]),
            decoded_pixel_hash=binding["decoded_pixel_hash"],
            stack_policy=effective["stack_policy"],
            stack_family_id=effective.get("stack_family_id"),
            equipment_ref=copy.deepcopy(effective.get("equipment_ref")),
            resolved_equipment=copy.deepcopy(resolved_equipment),
            equipment_authority_version=self.equipment_authority.version if self.equipment_authority else None,
            equipment_authority_hash=self.equipment_authority.sha256 if self.equipment_authority else None,
            equipment_authority_blob_id=self.equipment_authority.blob_id if self.equipment_authority else None,
            cache_key=key,
            provenance_hash=effective["provenance_hash"],
            production_safe=False,
        )
        self._cache[key] = result
        return result


def compare_deterministic_outputs(first: bytes, second: bytes) -> dict[str, Any]:
    first_hash = sha256_bytes(first)
    second_hash = sha256_bytes(second)
    if first != second:
        raise ItemPropContractError("NONDETERMINISTIC_SECOND_ITEM_PROP_OUTPUT")
    return {"result": "ACCEPTED", "first_sha256": first_hash, "second_sha256": second_hash, "equal": True}


def compare_deterministic_file_sets(first: str | Path, second: str | Path) -> dict[str, Any]:
    first_root, second_root = Path(first), Path(second)
    first_files = sorted(path.relative_to(first_root).as_posix() for path in first_root.rglob("*") if path.is_file())
    second_files = sorted(path.relative_to(second_root).as_posix() for path in second_root.rglob("*") if path.is_file())
    differences: list[dict[str, Any]] = []
    for relative in sorted(set(first_files) | set(second_files)):
        a, b = first_root / relative, second_root / relative
        if not a.is_file():
            differences.append({"path": relative, "kind": "missing_first"})
        elif not b.is_file():
            differences.append({"path": relative, "kind": "missing_second"})
        elif a.read_bytes() != b.read_bytes():
            differences.append({"path": relative, "kind": "bytes", "first_sha256": sha256_bytes(a.read_bytes()), "second_sha256": sha256_bytes(b.read_bytes())})
    if differences:
        identity = any("identity" in item["path"] or "lineage" in item["path"] for item in differences)
        raise ItemPropContractError("NONDETERMINISTIC_SECOND_ITEM_PROP_IDENTITY" if identity else "NONDETERMINISTIC_SECOND_ITEM_PROP_OUTPUT")
    return {"result": "ACCEPTED", "file_count": len(first_files), "first_files": first_files, "second_files": second_files, "differences": differences, "equal": True, "second_run_reads_first_run": False}


def clone_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(manifest))


__all__ = [
    "ALLOWED_VARIANT_OVERRIDES",
    "CONTEXTS",
    "EquipmentAuthority",
    "ITEM_CLASSES",
    "ItemPropContractError",
    "ItemPropRegistry",
    "ItemPropResolution",
    "SCHEMA_VERSION",
    "canonical_json",
    "clone_manifest",
    "compare_deterministic_file_sets",
    "compare_deterministic_outputs",
    "git_blob_id",
    "load_equipment_authority",
    "materialize_variant",
    "sha256_bytes",
    "sha256_json",
    "validate_effective_variant",
    "validate_item_prop_manifest",
    "validate_item_record",
    "validate_variant_lineage",
]
