"""Fail-closed equipment and outfit composition for the v0.17.1 correction.

The runtime is deliberately a contract and composition layer, not an art
generator.  Production registries may contain only explicitly approved
assets; the repository's v0.17.x fixtures are synthetic and TEST_ONLY.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from PIL import Image, ImageDraw

from .direction_runtime import canonicalize_direction


SCHEMA_VERSION = "0.17.1"
SUPPORTED_SCHEMA_VERSIONS = {"0.17.0", SCHEMA_VERSION}
RIG_REVISION = "r4-cutout-rig-v071"
CANONICAL_DIRECTIONS = ("south", "south_east", "east", "north_east", "north", "north_west", "west", "south_west")
PRODUCTION_DIRECTIONS = {"south"}
ANIMATION_PROFILES = {
    "idle-front-v1",
    "walk-front-v1",
    "run-front-v1",
    "attack-front-v2",
    "hit-front-v1",
    "death-front-v151",
}
VALID_SLOTS = {"head", "torso", "arms", "legs", "feet", "back", "accessory"}
VALID_MODES = {"overlay", "replace"}
VALID_LAYER_GROUPS = {
    "behind_legs",
    "behind_torso",
    "behind_head",
    "back",
    "torso_replace_or_overlay",
    "arm_left",
    "arm_right",
    "leg_overlays",
    "feet",
    "head",
    "front_torso",
    "front_head",
    "accessory",
}
VALID_JOINTS = {
    "nose",
    "neck",
    "shoulder_center",
    "shoulder_left",
    "shoulder_right",
    "elbow_left",
    "elbow_right",
    "wrist_left",
    "wrist_right",
    "pelvis",
    "hip_left",
    "hip_right",
    "knee_left",
    "knee_right",
    "ankle_left",
    "ankle_right",
}
VALID_PARTS = {
    "head",
    "torso_pelvis",
    "left_upper_arm",
    "left_forearm_hand",
    "right_upper_arm",
    "right_forearm_hand",
    "left_thigh",
    "left_shin_foot",
    "right_thigh",
    "right_shin_foot",
    "sword",
}

# These are deterministic fallback masks for test-only base frames. Production
# callers should provide the same named masks in frame metadata. Keeping the
# fallback here makes replacement/hide behavior explicit and reproducible for
# the historical v0.17.0 fixtures, which predate the v0.17.1 mask binding.
DEFAULT_PART_MASKS: dict[str, tuple[tuple[int, int, int, int], ...]] = {
    "head": ((220, 38, 320, 122),),
    "torso_pelvis": ((202, 108, 338, 286),),
    "left_upper_arm": ((292, 112, 346, 234),),
    "left_forearm_hand": ((326, 204, 376, 302),),
    "right_upper_arm": ((190, 112, 244, 234),),
    "right_forearm_hand": ((164, 202, 214, 302),),
    "left_thigh": ((260, 260, 316, 386),),
    "left_shin_foot": ((276, 360, 332, 476),),
    "right_thigh": ((224, 260, 280, 386),),
    "right_shin_foot": ((208, 360, 264, 476),),
    "sword": ((340, 136, 404, 420),),
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_image(image: Image.Image) -> str:
    rgba = image.convert("RGBA")
    return hashlib.sha256(rgba.tobytes()).hexdigest()


def compare_base_immutability(before: Image.Image, after: Image.Image) -> dict[str, Any]:
    """Shared postcondition used by production and negative-control QA."""
    before_hash = sha256_image(before)
    after_hash = sha256_image(after)
    if before_hash != after_hash:
        raise EquipmentContractError("BASE_PIXEL_MUTATION")
    return {"result": "ACCEPTED", "error_code": None, "rejection_class": None, "before_sha256": before_hash, "after_sha256": after_hash}


def compare_compositions(first: Image.Image, second: Image.Image) -> dict[str, Any]:
    """Shared byte comparator for equivalent composition requests."""
    first_hash = sha256_image(first)
    second_hash = sha256_image(second)
    if first_hash != second_hash:
        raise EquipmentContractError("NONDETERMINISTIC_SECOND_COMPOSITION")
    return {"result": "ACCEPTED", "error_code": None, "rejection_class": None, "first_sha256": first_hash, "second_sha256": second_hash}


class EquipmentRuntimeError(ValueError):
    """Base class for an equipment contract or resolution failure."""


class EquipmentContractError(EquipmentRuntimeError):
    """Raised for a malformed or unsafe equipment manifest."""

    def __init__(self, error_code: str, detail: str | None = None) -> None:
        self.error_code = error_code
        super().__init__(f"{error_code}{': ' + detail if detail else ''}")


@dataclass(frozen=True)
class EquipmentResolution:
    result: str
    equipment_id: str
    slot: str | None
    variant: str
    requested_direction: str | None
    resolved_direction: str | None
    animation_profile: str
    animation_capability: str
    rig_revision: str
    asset_revision: str | None
    cache_key: str
    fallback_mode: str
    mirror_mode: str
    error_code: str | None
    production_safe: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "equipment_id": self.equipment_id,
            "slot": self.slot,
            "variant": self.variant,
            "requested_direction": self.requested_direction,
            "resolved_direction": self.resolved_direction,
            "animation_profile": self.animation_profile,
            "animation_capability": self.animation_capability,
            "rig_revision": self.rig_revision,
            "asset_revision": self.asset_revision,
            "cache_key": self.cache_key,
            "fallback_mode": self.fallback_mode,
            "mirror_mode": self.mirror_mode,
            "error_code": self.error_code,
            "rejection_class": "RUNTIME_REJECTION" if self.result == "REJECTED" else None,
            "production_safe": self.production_safe,
        }


@dataclass(frozen=True)
class CompositionResult:
    image: Image.Image
    result: str
    cache_key: str
    layer_trace: tuple[dict[str, Any], ...]
    base_sha256_before: str
    base_sha256_after: str
    approved_frame_hash: str | None
    base_animation_metadata_preserved: bool
    production_safe: bool
    occlusion_trace: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "cache_key": self.cache_key,
            "layer_trace": [dict(item) for item in self.layer_trace],
            "base_sha256_before": self.base_sha256_before,
            "base_sha256_after": self.base_sha256_after,
            "approved_frame_hash": self.approved_frame_hash,
            "base_animation_metadata_preserved": self.base_animation_metadata_preserved,
            "production_safe": self.production_safe,
            "occlusion_trace": [dict(item) for item in self.occlusion_trace],
            "composed_sha256": sha256_image(self.image),
        }


def _require(condition: bool, code: str, detail: str | None = None) -> None:
    if not condition:
        raise EquipmentContractError(code, detail)


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(char in "0123456789abcdef" for char in value)


def _topological_layer_order(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    order = manifest.get("layer_order")
    _require(isinstance(order, list) and order and len(order) == len(set(order)), "LAYER_ORDER_INVALID")
    _require(set(order) == VALID_LAYER_GROUPS, "LAYER_ORDER_INCOMPLETE")
    dependencies = manifest.get("layer_dependencies", {})
    _require(isinstance(dependencies, Mapping), "LAYER_DEPENDENCIES_INVALID")
    graph = {name: set() for name in order}
    for child, parents in dependencies.items():
        _require(child in graph and isinstance(parents, list), "LAYER_DEPENDENCY_INVALID")
        for parent in parents:
            _require(parent in graph and parent != child, "LAYER_DEPENDENCY_INVALID")
            graph[child].add(parent)
    position = {name: index for index, name in enumerate(order)}
    for child, parents in graph.items():
        _require(all(position[parent] < position[child] for parent in parents), "LAYER_ORDER_CYCLE")
    visited: dict[str, int] = {}

    def visit(node: str) -> None:
        state = visited.get(node, 0)
        _require(state != 1, "LAYER_ORDER_CYCLE")
        if state == 2:
            return
        visited[node] = 1
        for parent in graph[node]:
            visit(parent)
        visited[node] = 2

    for node in order:
        visit(node)
    return tuple(order)


def _record_without_provenance_hash(record: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(record)
    value.pop("provenance_hash", None)
    return value


def validate_equipment_manifest(manifest: Mapping[str, Any], *, production_registry: bool | None = None) -> tuple[str, ...]:
    """Validate all contract and safety gates, raising on the first failure."""
    _require(isinstance(manifest, Mapping), "EQUIPMENT_MANIFEST_NOT_OBJECT")
    schema_version = manifest.get("schema_version")
    _require(schema_version in SUPPORTED_SCHEMA_VERSIONS, "EQUIPMENT_SCHEMA_VERSION_INVALID")
    _require(manifest.get("manifest_type") == "equipment-outfits-runtime", "EQUIPMENT_MANIFEST_TYPE_INVALID")
    registry_mode = manifest.get("production_registry") if production_registry is None else production_registry
    _require(isinstance(registry_mode, bool), "PRODUCTION_REGISTRY_FLAG_INVALID")
    _require(manifest.get("rig_revision") == RIG_REVISION, "RIG_REVISION_INVALID")
    _require(isinstance(manifest.get("rig_manifest"), str) and manifest["rig_manifest"].endswith("r4-cutout-rig-v071.json"), "RIG_MANIFEST_BINDING_INVALID")
    _require(manifest.get("replacement_conflict_policy") == "highest_priority_then_equipment_id", "REPLACEMENT_CONFLICT_POLICY_MISSING")
    _topological_layer_order(manifest)
    mirror_policy = manifest.get("mirror_policy")
    _require(mirror_policy == "manifest-permission-only", "MIRROR_POLICY_INVALID")
    assets = manifest.get("assets")
    _require(isinstance(assets, list), "EQUIPMENT_ASSETS_INVALID")
    seen: set[tuple[str, str, str]] = set()
    for raw in assets:
        _require(isinstance(raw, Mapping), "EQUIPMENT_RECORD_NOT_OBJECT")
        item = dict(raw)
        required = ("equipment_id", "slot", "variant", "layer_group", "priority", "anchors", "direction_coverage", "animation_compatibility", "rig_revision_compatibility", "replacement_rules", "occlusion_masks", "provenance_hash", "asset_revision", "test_only", "production_safe", "mirror_safe", "asymmetry_flags")
        _require(all(field in item for field in required), "EQUIPMENT_SCHEMA_REQUIRED_FIELD_MISSING")
        identity = (str(item["equipment_id"]), str(item["slot"]), str(item["variant"]))
        _require(all(identity), "EQUIPMENT_IDENTITY_INVALID")
        _require(identity not in seen, "DUPLICATE_EQUIPMENT_IDENTITY")
        seen.add(identity)
        _require(item["slot"] in VALID_SLOTS, "UNKNOWN_EQUIPMENT_SLOT")
        _require(item["layer_group"] in VALID_LAYER_GROUPS, "UNKNOWN_LAYER_GROUP")
        _require(isinstance(item["priority"], int) and not isinstance(item["priority"], bool), "EQUIPMENT_PRIORITY_INVALID")
        _require(isinstance(item["test_only"], bool) and isinstance(item["production_safe"], bool), "PRODUCTION_SAFETY_FLAGS_INVALID")
        if registry_mode:
            _require(item["test_only"] is False and item["production_safe"] is True, "TEST_ONLY_FIXTURE_IN_PRODUCTION_REGISTRY")
        else:
            _require(item["test_only"] is True and item["production_safe"] is False, "NON_TEST_FIXTURE_MISSING_TEST_BOUNDARY")
        _require(isinstance(item["asset_revision"], str) and bool(item["asset_revision"]), "ASSET_REVISION_INVALID")
        _require(_is_sha256(item["provenance_hash"]), "PROVENANCE_HASH_INVALID")
        _require(item["provenance_hash"] == sha256_json(_record_without_provenance_hash(item)), "PROVENANCE_HASH_MISMATCH")
        directions = item["direction_coverage"]
        _require(isinstance(directions, list) and directions and all(canonicalize_direction(value) == value and value in CANONICAL_DIRECTIONS for value in directions), "DIRECTION_COVERAGE_NOT_CANONICAL")
        _require(len(directions) == len(set(directions)), "DIRECTION_COVERAGE_DUPLICATE")
        animation = item["animation_compatibility"]
        _require(isinstance(animation, Mapping) and isinstance(animation.get("capability_id"), str) and animation["capability_id"] == "front-compatible", "ANIMATION_CAPABILITY_INVALID")
        _require(isinstance(animation.get("profiles"), list) and animation["profiles"] and set(animation["profiles"]).issubset(ANIMATION_PROFILES), "ANIMATION_PROFILE_COMPATIBILITY_INVALID")
        _require(animation.get("base_timing_immutable") is True and animation.get("event_markers_immutable") is True, "ANIMATION_IMMUTABILITY_BINDING_MISSING")
        _require(item["rig_revision_compatibility"] == [RIG_REVISION], "RIG_COMPATIBILITY_INVALID")
        anchors = item["anchors"]
        _require(isinstance(anchors, list) and anchors, "ANCHORS_MISSING")
        anchor_ids: set[str] = set()
        for anchor in anchors:
            _require(isinstance(anchor, Mapping), "ANCHOR_RECORD_INVALID")
            _require(isinstance(anchor.get("anchor_id"), str) and anchor["anchor_id"] not in anchor_ids, "ANCHOR_ID_INVALID")
            anchor_ids.add(anchor["anchor_id"])
            _require(anchor.get("joint") in VALID_JOINTS, "ANCHOR_JOINT_UNKNOWN")
            offset = anchor.get("offset")
            _require(isinstance(offset, Mapping) and isinstance(offset.get("x"), (int, float)) and isinstance(offset.get("y"), (int, float)), "ANCHOR_OFFSET_INVALID")
            _require(anchor.get("rotation_inheritance") in {True, False}, "ANCHOR_ROTATION_POLICY_INVALID")
            _require(anchor.get("scale_policy") == "uniform", "ANCHOR_SCALE_POLICY_INVALID")
            if "secondary_anchor" in anchor:
                secondary = anchor["secondary_anchor"]
                _require(isinstance(secondary, Mapping) and secondary.get("joint") in VALID_JOINTS, "SECONDARY_ANCHOR_INVALID")
                if schema_version == SCHEMA_VERSION:
                    raise EquipmentContractError("SECONDARY_ANCHOR_UNSUPPORTED")
        replacement = item["replacement_rules"]
        _require(isinstance(replacement, Mapping) and replacement.get("mode") in VALID_MODES, "REPLACEMENT_RULE_INVALID")
        _require(isinstance(replacement.get("hide_parts"), list) and all(part in VALID_PARTS for part in replacement["hide_parts"]), "HIDE_PART_RULE_INVALID")
        if replacement["mode"] == "replace":
            _require(isinstance(replacement.get("replace_group"), str) and bool(replacement["replace_group"]), "REPLACE_GROUP_MISSING")
            _require(replacement["hide_parts"], "REPLACE_HIDE_PARTS_MISSING")
        else:
            _require(replacement.get("replace_group") in {None, ""}, "OVERLAY_REPLACE_GROUP_FORBIDDEN")
        masks = item["occlusion_masks"]
        _require(isinstance(masks, list) and masks, "OCCLUSION_MASK_MISSING")
        for mask in masks:
            _require(isinstance(mask, Mapping) and mask.get("binding") == "asset-bound" and mask.get("target_part") in VALID_PARTS and isinstance(mask.get("mask_id"), str), "OCCLUSION_MASK_BINDING_INVALID")
            if schema_version == SCHEMA_VERSION:
                _require(mask.get("policy") == "explicit-layer-alpha", "OCCLUSION_MASK_POLICY_INVALID")
                geometry = mask.get("geometry")
                _require(isinstance(geometry, Mapping) and geometry.get("type") == "rectangle", "OCCLUSION_MASK_GEOMETRY_INVALID")
                _require(all(isinstance(geometry.get(key), int) and not isinstance(geometry.get(key), bool) for key in ("x", "y", "width", "height")), "OCCLUSION_MASK_GEOMETRY_INVALID")
                _require(geometry["width"] > 0 and geometry["height"] > 0, "OCCLUSION_MASK_GEOMETRY_INVALID")
                mask_hash = mask.get("mask_hash")
                _require(_is_sha256(mask_hash), "OCCLUSION_MASK_HASH_INVALID")
                _require(mask_hash == sha256_json({key: value for key, value in mask.items() if key != "mask_hash"}), "OCCLUSION_MASK_HASH_MISMATCH")
        asymmetry = item["asymmetry_flags"]
        _require(isinstance(asymmetry, list), "ASYMMETRY_FLAGS_INVALID")
        if asymmetry:
            _require(item["mirror_safe"] is False, "ASYMMETRIC_MIRROR_UNSAFE")
        else:
            _require(item["mirror_safe"] in {True, False}, "MIRROR_PERMISSION_INVALID")
        if item["mirror_safe"]:
            permission = item.get("mirror_permission")
            _require(isinstance(permission, Mapping) and permission.get("allowed") is True and permission.get("from") in directions and permission.get("to") in CANONICAL_DIRECTIONS, "MIRROR_PERMISSION_INVALID")
        if item["test_only"]:
            fixture = item.get("fixture")
            _require(isinstance(fixture, Mapping) and fixture.get("shape") in {"rectangle", "ellipse", "capsule", "diamond", "panel"}, "TEST_FIXTURE_INVALID")
        else:
            _require(isinstance(item.get("asset_path"), str) and bool(item["asset_path"]), "PRODUCTION_ASSET_PATH_MISSING")
    if registry_mode:
        _require(not any(item.get("test_only") for item in assets), "TEST_ONLY_FIXTURE_IN_PRODUCTION_REGISTRY")
    return _topological_layer_order(manifest)


def _cache_key(item: Mapping[str, Any], *, direction: str | None, animation_profile: str, rig_revision: str, registry_mode: str, request_mode: str) -> str:
    animation = item.get("animation_compatibility", {})
    return "|".join(
        (
            f"equipment_id={item.get('equipment_id')}",
            f"slot={item.get('slot')}",
            f"variant={item.get('variant')}",
            f"rig_revision={rig_revision}",
            f"direction={direction or 'UNRESOLVED'}",
            f"animation_capability={animation.get('capability_id', 'UNKNOWN')}",
            f"animation_profile={animation_profile}",
            f"asset_revision={item.get('asset_revision', 'UNKNOWN')}",
            f"request_mode={request_mode}",
            f"registry_mode={registry_mode}",
        )
    )


class EquipmentRegistry:
    """Resolve and compose declarative wearables with an isolated cache."""

    def __init__(self, manifest: Mapping[str, Any], *, production_registry: bool | None = None) -> None:
        self.manifest = dict(manifest)
        self.production_registry = self.manifest.get("production_registry") if production_registry is None else production_registry
        self.layer_order = validate_equipment_manifest(self.manifest, production_registry=self.production_registry)
        self._assets = {(item["equipment_id"], item["slot"], item["variant"]): dict(item) for item in self.manifest.get("assets", [])}
        self._cache: dict[str, EquipmentResolution] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    @classmethod
    def from_manifest(cls, path: Path, *, production_registry: bool | None = None) -> "EquipmentRegistry":
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(value, production_registry=production_registry)

    def cache_stats(self) -> dict[str, int]:
        return {"hits": self._cache_hits, "misses": self._cache_misses, "entries": len(self._cache)}

    def clear_cache(self) -> None:
        self._cache.clear()
        self._cache_hits = self._cache_misses = 0

    def poison_cache_for_test(self, cache_key: str, resolution: EquipmentResolution) -> None:
        """Inject one cache entry for the stale-context negative control.

        This deliberately uses the same runtime cache as normal resolution;
        it is exposed only as an explicit test hook so QA can prove that a
        poisoned entry is rejected instead of being treated as a cache hit.
        """
        _require(isinstance(cache_key, str) and cache_key, "CACHE_TEST_KEY_INVALID")
        _require(isinstance(resolution, EquipmentResolution), "CACHE_TEST_VALUE_INVALID")
        self._cache[cache_key] = resolution

    def _failure(self, *, equipment_id: str, slot: str | None, variant: str, requested: str | None, animation_profile: str, animation_capability: str, rig_revision: str, cache_key: str, error_code: str, fallback_mode: str = "FAIL_CLOSED", mirror_mode: str = "NONE", asset_revision: str | None = None) -> EquipmentResolution:
        return EquipmentResolution("REJECTED", equipment_id, slot, variant, requested, None, animation_profile, animation_capability, rig_revision, asset_revision, cache_key, fallback_mode, mirror_mode, error_code, False)

    def resolve(self, equipment_id: str, direction: Any, *, slot: str | None = None, variant: str = "default", animation_profile: str = "idle-front-v1", rig_revision: str = RIG_REVISION, allow_preview_fallback: bool = False, allow_mirror: bool = False) -> EquipmentResolution:
        requested = canonicalize_direction(direction)
        identity_matches = [item for (item_id, item_slot, item_variant), item in self._assets.items() if item_id == equipment_id and (variant == "default" or item_variant == variant) and (slot is None or item_slot == slot)]
        item = identity_matches[0] if len(identity_matches) == 1 else None
        if item is not None and variant == "default":
            variant = str(item["variant"])
        capability = str(item.get("animation_compatibility", {}).get("capability_id", "front-compatible")) if item else "front-compatible"
        asset_revision = item.get("asset_revision") if item else None
        request_mode = f"preview:{int(allow_preview_fallback)}:{int(allow_mirror)}"
        if not allow_preview_fallback and not allow_mirror:
            request_mode = "direct"
        key = _cache_key(item or {"equipment_id": equipment_id, "slot": slot or "UNKNOWN", "variant": variant, "asset_revision": asset_revision, "animation_compatibility": {"capability_id": capability}}, direction=requested, animation_profile=animation_profile, rig_revision=rig_revision, registry_mode="production" if self.production_registry else "test", request_mode=request_mode)
        if key in self._cache:
            cached = self._cache[key]
            expected_slot = item["slot"] if item is not None else slot
            if (
                cached.equipment_id != equipment_id
                or cached.slot != expected_slot
                or cached.variant != variant
                or cached.requested_direction != requested
                or cached.animation_profile != animation_profile
                or cached.rig_revision != rig_revision
            ):
                del self._cache[key]
                self._cache_misses += 1
                return self._failure(
                    equipment_id=equipment_id,
                    slot=expected_slot,
                    variant=variant,
                    requested=requested,
                    animation_profile=animation_profile,
                    animation_capability=capability,
                    rig_revision=rig_revision,
                    cache_key=key,
                    error_code="STALE_CACHE_CONTEXT",
                    asset_revision=asset_revision,
                )
            self._cache_hits += 1
            return cached
        self._cache_misses += 1
        if item is None:
            result = self._failure(equipment_id=equipment_id, slot=slot, variant=variant, requested=requested, animation_profile=animation_profile, animation_capability=capability, rig_revision=rig_revision, cache_key=key, error_code="EQUIPMENT_UNKNOWN")
        elif requested is None:
            result = self._failure(equipment_id=equipment_id, slot=item["slot"], variant=variant, requested=None, animation_profile=animation_profile, animation_capability=capability, rig_revision=rig_revision, cache_key=key, error_code="DIRECTION_UNRESOLVED", asset_revision=asset_revision)
        elif rig_revision not in item["rig_revision_compatibility"]:
            result = self._failure(equipment_id=equipment_id, slot=item["slot"], variant=variant, requested=requested, animation_profile=animation_profile, animation_capability=capability, rig_revision=rig_revision, cache_key=key, error_code="RIG_REVISION_INCOMPATIBLE", asset_revision=asset_revision)
        elif animation_profile not in item["animation_compatibility"]["profiles"]:
            result = self._failure(equipment_id=equipment_id, slot=item["slot"], variant=variant, requested=requested, animation_profile=animation_profile, animation_capability=capability, rig_revision=rig_revision, cache_key=key, error_code="ANIMATION_PROFILE_INCOMPATIBLE", asset_revision=asset_revision)
        elif requested in item["direction_coverage"]:
            result = EquipmentResolution("RESOLVED", equipment_id, item["slot"], variant, requested, requested, animation_profile, capability, rig_revision, asset_revision, key, "NONE", "NONE", None, bool(self.production_registry and item["production_safe"]))
        elif allow_mirror and item.get("mirror_safe") and item.get("mirror_permission", {}).get("from") in item["direction_coverage"] and item.get("mirror_permission", {}).get("to") == requested:
            # Resolver permission is not pixel mirroring. Until the compositor
            # has a real mirror operation, fail closed even for a permitted
            # test fixture and never claim HORIZONTAL_EXPLICIT resolution.
            result = self._failure(equipment_id=equipment_id, slot=item["slot"], variant=variant, requested=requested, animation_profile=animation_profile, animation_capability=capability, rig_revision=rig_revision, cache_key=key, error_code="MIRROR_RUNTIME_NOT_IMPLEMENTED", fallback_mode="FAIL_CLOSED", asset_revision=asset_revision)
        elif allow_preview_fallback and not self.production_registry and "south" in item["direction_coverage"]:
            result = EquipmentResolution("RESOLVED", equipment_id, item["slot"], variant, requested, "south", animation_profile, capability, rig_revision, asset_revision, key, "EXPLICIT_TEST_ONLY_PREVIEW_FALLBACK", "NONE", None, False)
        else:
            result = self._failure(equipment_id=equipment_id, slot=item["slot"], variant=variant, requested=requested, animation_profile=animation_profile, animation_capability=capability, rig_revision=rig_revision, cache_key=key, error_code="EQUIPMENT_DIRECTION_UNAVAILABLE", asset_revision=asset_revision)
        self._cache[key] = result
        return result

    def resolve_outfit(self, equipment_ids: Iterable[str], direction: Any, *, animation_profile: str = "idle-front-v1", rig_revision: str = RIG_REVISION, allow_preview_fallback: bool = False, allow_mirror: bool = False) -> tuple[EquipmentResolution, ...]:
        ordered_ids = tuple(sorted(str(value) for value in equipment_ids))
        resolutions: list[EquipmentResolution] = []
        for equipment_id in ordered_ids:
            matches = [item for (item_id, _slot, _variant), item in self._assets.items() if item_id == equipment_id]
            if len(matches) != 1:
                resolutions.append(self.resolve(equipment_id, direction, animation_profile=animation_profile, rig_revision=rig_revision, allow_preview_fallback=allow_preview_fallback, allow_mirror=allow_mirror))
                continue
            item = matches[0]
            resolutions.append(self.resolve(equipment_id, direction, slot=item["slot"], variant=item["variant"], animation_profile=animation_profile, rig_revision=rig_revision, allow_preview_fallback=allow_preview_fallback, allow_mirror=allow_mirror))
        return tuple(resolutions)

    @staticmethod
    def _fixture_image(fixture: Mapping[str, Any]) -> Image.Image:
        width, height = [int(value) for value in fixture.get("size", [48, 24])]
        _require(width > 0 and height > 0 and width <= 256 and height <= 256, "TEST_FIXTURE_SIZE_INVALID")
        color = tuple(int(value) for value in fixture.get("color", [255, 255, 255, 220]))
        _require(len(color) == 4 and all(0 <= value <= 255 for value in color), "TEST_FIXTURE_COLOR_INVALID")
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        bbox = (1, 1, width - 2, height - 2)
        if fixture["shape"] in {"rectangle", "panel"}:
            draw.rectangle(bbox, fill=color)
        elif fixture["shape"] == "ellipse":
            draw.ellipse(bbox, fill=color)
        elif fixture["shape"] == "capsule":
            draw.rounded_rectangle(bbox, radius=max(1, min(width, height) // 2), fill=color)
        elif fixture["shape"] == "diamond":
            draw.polygon([(width // 2, 1), (width - 2, height // 2), (width // 2, height - 2), (1, height // 2)], fill=color)
        return image

    @staticmethod
    def _part_rectangles(part: str, metadata: Mapping[str, Any]) -> tuple[tuple[int, int, int, int], ...]:
        masks = metadata.get("part_masks")
        if isinstance(masks, Mapping) and part in masks:
            values = masks[part]
        else:
            values = DEFAULT_PART_MASKS.get(part, ())
        _require(isinstance(values, (list, tuple)), "EXPLICIT_PART_MASK_INVALID")
        rectangles: list[tuple[int, int, int, int]] = []
        for rectangle in values:
            _require(isinstance(rectangle, (list, tuple)) and len(rectangle) == 4, "EXPLICIT_PART_MASK_INVALID")
            rectangles.append(tuple(int(value) for value in rectangle))
        return tuple(rectangles)

    @classmethod
    def _clear_part_masks(cls, image: Image.Image, parts: Iterable[str], metadata: Mapping[str, Any]) -> int:
        pixels_changed = 0
        pixel = image.load()
        width, height = image.size
        for part in parts:
            for left, top, right, bottom in cls._part_rectangles(part, metadata):
                left, top = max(0, left), max(0, top)
                right, bottom = min(width - 1, right), min(height - 1, bottom)
                if left > right or top > bottom:
                    continue
                for y in range(top, bottom + 1):
                    for x in range(left, right + 1):
                        if pixel[x, y][3] != 0:
                            pixel[x, y] = (0, 0, 0, 0)
                            pixels_changed += 1
        return pixels_changed

    @staticmethod
    def _apply_occlusion_mask(image: Image.Image, mask: Mapping[str, Any]) -> dict[str, Any]:
        geometry = mask.get("geometry")
        if not isinstance(geometry, Mapping):
            # v0.17.0 declarations are retained as historical data. The
            # corrected v0.17.1 manifest cannot reach this branch because its
            # contract requires deterministic geometry and a content hash.
            return {"mask_id": mask.get("mask_id"), "status": "DECLARATION_ONLY", "affected_pixel_count": 0}
        if geometry.get("type") != "rectangle":
            raise EquipmentContractError("OCCLUSION_MASK_GEOMETRY_INVALID")
        left = int(geometry["x"])
        top = int(geometry["y"])
        right = left + int(geometry["width"]) - 1
        bottom = top + int(geometry["height"]) - 1
        pixel = image.load()
        width, height = image.size
        affected = 0
        for y in range(max(0, top), min(height - 1, bottom) + 1):
            for x in range(max(0, left), min(width - 1, right) + 1):
                if pixel[x, y][3] != 0:
                    pixel[x, y] = (0, 0, 0, 0)
                    affected += 1
        return {
            "mask_id": mask["mask_id"],
            "target_part": mask["target_part"],
            "policy": mask["policy"],
            "mask_hash": mask.get("mask_hash"),
            "geometry": dict(geometry),
            "affected_pixel_count": affected,
            "status": "APPLIED",
        }

    def compose(self, base_image: Image.Image, base_frame_metadata: Mapping[str, Any], equipment_ids: Iterable[str], *, direction: Any, animation_profile: str = "idle-front-v1", rig_revision: str = RIG_REVISION, allow_preview_fallback: bool = False, allow_mirror: bool = False, production_routing: str = "BLOCKED") -> CompositionResult:
        _require(production_routing == "BLOCKED", "PRODUCTION_ROUTING_BLOCKED")
        before = base_image.convert("RGBA")
        before_digest = sha256_image(before)
        metadata_snapshot = canonical_json(dict(base_frame_metadata))
        resolutions = self.resolve_outfit(equipment_ids, direction, animation_profile=animation_profile, rig_revision=rig_revision, allow_preview_fallback=allow_preview_fallback, allow_mirror=allow_mirror)
        if any(item.result != "RESOLVED" for item in resolutions):
            failed = next(item for item in resolutions if item.result != "RESOLVED")
            raise EquipmentContractError(failed.error_code or "EQUIPMENT_RESOLUTION_FAILED")
        items: list[Mapping[str, Any]] = []
        resolution_by_id = {resolution.equipment_id: resolution for resolution in resolutions}
        for resolution in resolutions:
            candidates = [item for (item_id, _slot, _variant), item in self._assets.items() if item_id == resolution.equipment_id]
            _require(len(candidates) == 1, "EQUIPMENT_RESOLUTION_AMBIGUOUS")
            items.append(candidates[0])
        position = {name: index for index, name in enumerate(self.layer_order)}
        replacement_groups: dict[str, list[Mapping[str, Any]]] = {}
        for item in items:
            replacement = item["replacement_rules"]
            if replacement["mode"] == "replace":
                group = replacement["replace_group"]
                replacement_groups.setdefault(group, []).append(item)
        winners: dict[str, Mapping[str, Any]] = {
            group: max(candidates, key=lambda item: (item["priority"], item["equipment_id"]))
            for group, candidates in replacement_groups.items()
        }
        suppressed = [
            item
            for group, candidates in replacement_groups.items()
            for item in candidates
            if item is not winners[group]
        ]
        selected = [
            item
            for item in items
            if item["replacement_rules"]["mode"] != "replace"
            or item is winners[item["replacement_rules"]["replace_group"]]
        ]
        ordered = sorted(selected, key=lambda item: (position[item["layer_group"]], item["priority"], item["equipment_id"]))
        composed = before.copy()
        anchor_points = base_frame_metadata.get("anchor_points", {})
        _require(isinstance(anchor_points, Mapping), "ANCHOR_POINTS_MISSING")
        trace: list[dict[str, Any]] = []
        for item in sorted(suppressed, key=lambda candidate: (candidate["replacement_rules"]["replace_group"], candidate["equipment_id"])):
            replacement = item["replacement_rules"]
            group = replacement["replace_group"]
            winner = winners[group]
            candidates = sorted(candidate["equipment_id"] for candidate in replacement_groups[group])
            trace.append({
                "equipment_id": item["equipment_id"],
                "slot": item["slot"],
                "layer_group": item["layer_group"],
                "priority": item["priority"],
                "replace_group": group,
                "conflict_candidates": candidates,
                "winner": winner["equipment_id"],
                "hidden_parts": [],
                "loser_suppressed": True,
                "suppressed": True,
            })
        for item in ordered:
            anchor = item["anchors"][0]
            point = anchor_points.get(anchor["joint"])
            _require(isinstance(point, Mapping) and isinstance(point.get("x"), (int, float)) and isinstance(point.get("y"), (int, float)), "ANCHOR_POINT_UNAVAILABLE")
            fixture = item.get("fixture")
            _require(isinstance(fixture, Mapping), "COMPOSITION_ASSET_NOT_AVAILABLE")
            layer = self._fixture_image(fixture)
            replacement = item["replacement_rules"]
            hidden_parts = list(replacement.get("hide_parts", [])) if replacement["mode"] == "replace" else []
            hidden_pixel_count = self._clear_part_masks(composed, hidden_parts, base_frame_metadata) if hidden_parts else 0
            occlusion_trace = [self._apply_occlusion_mask(composed, mask) for mask in item.get("occlusion_masks", [])]
            rotation = 0.0
            if anchor["rotation_inheritance"]:
                rotation = float(base_frame_metadata.get("joint_rotations", {}).get(anchor["joint"], 0.0))
            if rotation:
                layer = layer.rotate(-rotation, resample=Image.Resampling.NEAREST, expand=True)
            offset = anchor["offset"]
            x = int(round(float(point["x"]) + float(offset["x"]) - layer.width / 2))
            y = int(round(float(point["y"]) + float(offset["y"]) - layer.height / 2))
            overlay = Image.new("RGBA", composed.size, (0, 0, 0, 0))
            overlay.alpha_composite(layer, (x, y))
            composed = Image.alpha_composite(composed, overlay)
            group = replacement.get("replace_group") if replacement["mode"] == "replace" else None
            candidates = sorted(candidate["equipment_id"] for candidate in replacement_groups.get(group, [])) if group else []
            trace.append({
                "equipment_id": item["equipment_id"],
                "slot": item["slot"],
                "layer_group": item["layer_group"],
                "priority": item["priority"],
                "anchor_id": anchor["anchor_id"],
                "joint": anchor["joint"],
                "direction": resolution_by_id[item["equipment_id"]].resolved_direction,
                "replace_group": group,
                "conflict_candidates": candidates,
                "winner": item["equipment_id"] if group else None,
                "hidden_parts": hidden_parts,
                "hidden_pixel_count": hidden_pixel_count,
                "loser_suppressed": False,
                "occlusion_masks": occlusion_trace,
            })
        after_digest = sha256_image(before)
        cache_key = "outfit=" + ",".join(sorted(item.equipment_id for item in resolutions)) + "|" + "|".join((f"direction={canonicalize_direction(direction) or 'UNRESOLVED'}", f"animation_profile={animation_profile}", f"rig_revision={rig_revision}", f"registry_mode={'production' if self.production_registry else 'test'}"))
        return CompositionResult(composed, "RESOLVED", cache_key, tuple(trace), before_digest, after_digest, base_frame_metadata.get("approved_frame_hash"), canonical_json(dict(base_frame_metadata)) == metadata_snapshot, all(item.production_safe for item in resolutions), tuple(item for item in trace if item.get("occlusion_masks")))
