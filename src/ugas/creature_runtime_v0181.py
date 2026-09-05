"""v0.18.1 creature runtime and QA-integrity contracts.

This module is deliberately versioned beside the rejected v0.18.0 runtime.
It adds executable directional identity, derived-variant materialization,
strict geometry, state-route identity, and a real production-routing policy.
All fixtures accepted by this module are TEST_ONLY synthetic evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from numbers import Real
from typing import Any, Mapping

from ugas.creature_runtime import ARCHETYPES, ARCHETYPE_RULES, CANONICAL_STATES
from ugas.direction_runtime import CANONICAL_DIRECTIONS, normalize_direction_result


SCHEMA_VERSION = "0.18.1"
STATE_VALUES = ("REQUIRED", "OPTIONAL", "UNSUPPORTED")
COLLISION_SHAPES = frozenset({"box", "capsule", "ellipse", "hull"})
ALLOWED_VARIANT_OVERRIDES = frozenset(
    {
        "base_scale",
        "footprint",
        "collision_profile",
        "anchors",
        "animation_state_contract",
        "direction_bindings",
        "state_routes",
        "asset_revision",
        "provenance",
    }
)
IMMUTABLE_VARIANT_FIELDS = frozenset(
    {
        "creature_id",
        "species_id",
        "archetype",
        "topology_id",
        "locomotion_class",
        "support_model",
        "rig_family",
        "test_only",
        "production_safe",
    }
)


class CreatureContractError(ValueError):
    """Semantic rejection with stable error code and rejection class."""

    def __init__(self, error_code: str, detail: str = "", rejection_class: str = "CONTRACT_REJECTION") -> None:
        self.error_code = error_code
        self.rejection_class = rejection_class
        super().__init__(f"{error_code}{':' + detail if detail else ''}")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _record_hash(record: Mapping[str, Any]) -> str:
    value = copy.deepcopy(dict(record))
    value.pop("provenance_hash", None)
    provenance = value.get("provenance")
    if isinstance(provenance, dict):
        provenance.pop("record_hash", None)
    return sha256_json(value)


def _finite_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value))


def enforce_production_routing(production_routing: Any) -> str:
    """Enforce the executable production policy at the runtime boundary."""
    if production_routing != "BLOCKED":
        raise CreatureContractError("PRODUCTION_ROUTING_BLOCKED", "only BLOCKED is authorized", "RUNTIME_REJECTION")
    return "BLOCKED"


def _required(value: Mapping[str, Any], key: str) -> Any:
    if key not in value or value[key] in (None, "", [], {}):
        raise CreatureContractError(f"{key.upper()}_EXPLICIT_REQUIRED")
    return value[key]


def _positive_mapping(value: Any, keys: tuple[str, ...], error_code: str) -> dict[str, float]:
    if not isinstance(value, Mapping) or any(key not in value for key in keys):
        raise CreatureContractError(error_code)
    output: dict[str, float] = {}
    for key in keys:
        if not _finite_number(value[key]) or float(value[key]) <= 0:
            raise CreatureContractError(error_code)
        output[key] = float(value[key])
    return output


def _validate_collision_geometry(profile: Any) -> dict[str, Any]:
    if not isinstance(profile, Mapping) or not profile:
        raise CreatureContractError("COLLISION_PROFILE_EXPLICIT_REQUIRED")
    shape = profile.get("shape")
    if shape not in COLLISION_SHAPES:
        raise CreatureContractError("COLLISION_SHAPE_UNSUPPORTED")
    if not _finite_number(profile.get("width")) or float(profile["width"]) <= 0:
        raise CreatureContractError("COLLISION_GEOMETRY_INVALID")
    if not _finite_number(profile.get("height")) or float(profile["height"]) <= 0:
        raise CreatureContractError("COLLISION_GEOMETRY_INVALID")
    pivot = profile.get("pivot")
    bounds = profile.get("bounds")
    if not isinstance(pivot, Mapping) or not all(_finite_number(pivot.get(key)) for key in ("x", "y")):
        raise CreatureContractError("PIVOT_GEOMETRY_INVALID")
    if not isinstance(bounds, Mapping) or not all(_finite_number(bounds.get(key)) for key in ("left", "top", "right", "bottom")):
        raise CreatureContractError("BOUNDS_GEOMETRY_INVALID")
    if float(bounds["left"]) >= float(bounds["right"]) or float(bounds["top"]) >= float(bounds["bottom"]):
        raise CreatureContractError("BOUNDS_GEOMETRY_INVALID")
    if not (float(bounds["left"]) <= float(pivot["x"]) <= float(bounds["right"]) and float(bounds["top"]) <= float(pivot["y"]) <= float(bounds["bottom"])):
        raise CreatureContractError("PIVOT_BOUNDS_RELATIONSHIP_INVALID")
    return {
        "shape": str(shape),
        "width": float(profile["width"]),
        "height": float(profile["height"]),
        "pivot": {"x": float(pivot["x"]), "y": float(pivot["y"])},
        "bounds": {key: float(bounds[key]) for key in ("left", "top", "right", "bottom")},
    }


def _validate_anchors(anchors: Any) -> dict[str, dict[str, float]]:
    if not isinstance(anchors, Mapping) or not anchors:
        raise CreatureContractError("ANCHORS_EXPLICIT_REQUIRED")
    output: dict[str, dict[str, float]] = {}
    for anchor_id, anchor in anchors.items():
        if not isinstance(anchor_id, str) or not isinstance(anchor, Mapping) or not all(_finite_number(anchor.get(key)) for key in ("x", "y")):
            raise CreatureContractError("ANCHOR_GEOMETRY_INVALID")
        output[anchor_id] = {"x": float(anchor["x"]), "y": float(anchor["y"])}
    return output


def _validate_direction_bindings(record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    bindings = record.get("direction_bindings")
    if not isinstance(bindings, Mapping) or set(bindings) != set(CANONICAL_DIRECTIONS):
        raise CreatureContractError("DIRECTION_BINDING_SET_INVALID")
    asset_ids: set[str] = set()
    hashes: set[str] = set()
    output: dict[str, dict[str, Any]] = {}
    for direction in CANONICAL_DIRECTIONS:
        item = bindings[direction]
        if not isinstance(item, Mapping) or item.get("direction") != direction:
            raise CreatureContractError("DIRECTION_ASSET_BINDING_INVALID")
        asset_id = item.get("direction_asset_id")
        content_hash = item.get("direction_content_hash")
        if not isinstance(asset_id, str) or not asset_id or asset_id in asset_ids:
            raise CreatureContractError("DIRECTION_ASSET_BINDING_INVALID")
        if not isinstance(content_hash, str) or len(content_hash) != 64 or any(ch not in "0123456789abcdef" for ch in content_hash) or (content_hash in hashes and item.get("identity_class") != "SHARED_TEST_IDENTITY"):
            raise CreatureContractError("DIRECTION_ASSET_BINDING_INVALID")
        if item.get("asset_revision") != record.get("asset_revision"):
            raise CreatureContractError("DIRECTION_ASSET_REVISION_MISMATCH")
        if item.get("test_only") is not True or item.get("production_safe") is not False:
            raise CreatureContractError("DIRECTION_PRODUCTION_BOUNDARY_INVALID")
        if not isinstance(item.get("path"), str) or not item["path"]:
            raise CreatureContractError("DIRECTION_ASSET_BINDING_INVALID")
        asset_ids.add(asset_id)
        hashes.add(content_hash)
        output[direction] = dict(item)
    return output


def _validate_state_routes(record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    contract = record.get("animation_state_contract")
    routes = record.get("state_routes")
    if not isinstance(contract, Mapping) or set(contract) != set(CANONICAL_STATES) or any(value not in STATE_VALUES for value in contract.values()):
        raise CreatureContractError("ANIMATION_STATE_CONTRACT_INVALID")
    if not any(value == "REQUIRED" for value in contract.values()):
        raise CreatureContractError("REQUIRED_ANIMATION_STATE_MISSING")
    if not isinstance(routes, Mapping) or set(routes) != set(CANONICAL_STATES):
        raise CreatureContractError("STATE_ROUTE_CONTRACT_INVALID")
    output: dict[str, dict[str, Any]] = {}
    for state in CANONICAL_STATES:
        route = routes[state]
        if not isinstance(route, Mapping) or route.get("state") != state or route.get("availability") != contract[state]:
            raise CreatureContractError("STATE_ROUTE_BINDING_INVALID")
        if contract[state] == "UNSUPPORTED":
            if route.get("state_route_id") is not None or route.get("timing_phase") is not None:
                raise CreatureContractError("STATE_ROUTE_BINDING_INVALID")
        else:
            route_id = route.get("state_route_id")
            timing = route.get("timing_phase")
            if not isinstance(route_id, str) or not route_id or not isinstance(timing, Mapping):
                raise CreatureContractError("STATE_ROUTE_BINDING_INVALID")
            if not _finite_number(timing.get("fps")) or float(timing["fps"]) <= 0 or not _finite_number(timing.get("duration_ms")) or float(timing["duration_ms"]) <= 0 or not isinstance(timing.get("phase"), str) or not timing["phase"]:
                raise CreatureContractError("STATE_ROUTE_TIMING_INVALID")
            if route.get("test_only") is not True or route.get("production_safe") is not False:
                raise CreatureContractError("STATE_ROUTE_PRODUCTION_BOUNDARY_INVALID")
        output[state] = dict(route)
    return output


def validate_creature_definition(record: Mapping[str, Any]) -> None:
    archetype = _required(record, "archetype")
    if archetype not in ARCHETYPES:
        raise CreatureContractError("ARCHETYPE_UNSUPPORTED", str(archetype))
    rules = ARCHETYPE_RULES[archetype]
    if record.get("topology_id") != rules["topology_id"]:
        raise CreatureContractError("TOPOLOGY_ARCHETYPE_MISMATCH")
    if record.get("locomotion_class") != rules["locomotion_class"]:
        raise CreatureContractError("LOCOMOTION_ARCHETYPE_MISMATCH")
    if record.get("support_model") != rules["support_model"]:
        raise CreatureContractError("SUPPORT_MODEL_ARCHETYPE_MISMATCH")
    for key in ("creature_id", "species_id", "rig_family", "asset_revision"):
        _required(record, key)
    _positive_mapping(record.get("base_scale"), ("x", "y"), "BASE_SCALE_INVALID")
    _positive_mapping(record.get("footprint"), ("width", "depth"), "FOOTPRINT_INVALID")
    _validate_collision_geometry(record.get("collision_profile"))
    _validate_anchors(record.get("anchors"))
    _validate_direction_bindings(record)
    _validate_state_routes(record)
    provenance = record.get("provenance")
    if not isinstance(provenance, Mapping) or provenance.get("source_kind") != "TEST_ONLY_SYNTHETIC" or provenance.get("production_safe") is not False:
        raise CreatureContractError("PROVENANCE_BOUNDARY_INVALID")
    if record.get("test_only") is not True or record.get("production_safe") is not False:
        raise CreatureContractError("TEST_ONLY_PRODUCTION_BOUNDARY_INVALID")
    expected_hash = _record_hash(record)
    if record.get("provenance_hash") != expected_hash or provenance.get("record_hash") != expected_hash:
        raise CreatureContractError("PROVENANCE_HASH_MISMATCH")


def validate_variant_lineage(variants: list[Mapping[str, Any]], creatures: list[Mapping[str, Any]] | None = None) -> None:
    ids = [item.get("variant_id") for item in variants]
    if len(ids) != len(set(ids)) or any(not isinstance(item, str) or not item for item in ids):
        raise CreatureContractError("VARIANT_LINEAGE_ID_INVALID")
    by_id = {item["variant_id"]: item for item in variants}
    creature_ids = {item.get("creature_id") for item in creatures or []}
    for item in variants:
        if not isinstance(item, Mapping) or item.get("creature_id") not in creature_ids:
            raise CreatureContractError("VARIANT_CREATURE_ID_INVALID")
        parent = item.get("parent_id")
        kind = item.get("kind")
        if kind not in {"base", "derived"}:
            raise CreatureContractError("VARIANT_LINEAGE_INVALID")
        if kind == "base" and parent is not None:
            raise CreatureContractError("VARIANT_BASE_PARENT_INVALID")
        if kind == "derived" and (parent is None or parent not in by_id):
            raise CreatureContractError("VARIANT_LINEAGE_PARENT_MISSING")
        overrides = item.get("overrides", [])
        values = item.get("override_values", {})
        if not isinstance(overrides, list) or not isinstance(values, Mapping) or set(values) != set(overrides) or any(value not in ALLOWED_VARIANT_OVERRIDES for value in overrides):
            raise CreatureContractError("VARIANT_OVERRIDE_NOT_ALLOWLISTED")
        if kind == "base" and overrides:
            raise CreatureContractError("VARIANT_BASE_OVERRIDE_INVALID")
    for variant_id in by_id:
        seen: set[str] = set()
        cursor: str | None = variant_id
        while cursor is not None:
            if cursor in seen:
                raise CreatureContractError("VARIANT_LINEAGE_CYCLE")
            seen.add(cursor)
            parent = by_id[cursor].get("parent_id")
            if parent is not None and parent not in by_id:
                raise CreatureContractError("VARIANT_LINEAGE_PARENT_MISSING")
            cursor = parent
    for item in variants:
        if item.get("kind") == "derived":
            parent = by_id[item["parent_id"]]
            if parent.get("creature_id") != item.get("creature_id"):
                raise CreatureContractError("VARIANT_PARENT_CREATURE_MISMATCH")


def validate_creature_manifest(manifest: Mapping[str, Any], *, production_registry: bool | None = None) -> None:
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("manifest_type") != "creatures-monsters-runtime-qa-integrity":
        raise CreatureContractError("CREATURE_SCHEMA_INVALID")
    enforce_production_routing(manifest.get("production_routing"))
    creatures = manifest.get("creatures")
    variants = manifest.get("variants")
    if not isinstance(creatures, list) or not isinstance(variants, list):
        raise CreatureContractError("CREATURE_SCHEMA_INVALID")
    validate_variant_lineage(variants, creatures)
    seen: set[str] = set()
    for creature in creatures:
        if not isinstance(creature, Mapping) or creature.get("creature_id") in seen:
            raise CreatureContractError("CREATURE_ID_DUPLICATE")
        seen.add(str(creature.get("creature_id")))
        validate_creature_definition(creature)
        variant_id = creature.get("variant_lineage", {}).get("variant_id") if isinstance(creature.get("variant_lineage"), Mapping) else None
        if variant_id not in {item.get("variant_id") for item in variants}:
            raise CreatureContractError("VARIANT_LINEAGE_PARENT_MISSING")
    if creatures and {item.get("archetype") for item in creatures if isinstance(item, Mapping)} != set(ARCHETYPES):
        raise CreatureContractError("ARCHETYPE_SET_INCOMPLETE")
    is_production = bool(manifest.get("production_registry")) if production_registry is None else production_registry
    if is_production and creatures:
        raise CreatureContractError("TEST_ONLY_CREATURE_IN_PRODUCTION_REGISTRY")
    if is_production and manifest.get("registry_authority") != "PRODUCTION_APPROVED_ASSETS_ONLY":
        raise CreatureContractError("PRODUCTION_REGISTRY_AUTHORITY_INVALID")


def _merge_variant(base: Mapping[str, Any], variant: Mapping[str, Any], by_id: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], str | None, str | None, str]:
    parent_id = variant.get("parent_id")
    if parent_id is None:
        effective = copy.deepcopy(dict(base))
        parent_creature_id = None
        parent_variant_id = None
    else:
        effective, parent_creature_id, parent_variant_id, _ = _merge_variant(base, by_id[parent_id], by_id)
        if parent_creature_id is None:
            parent_creature_id = str(base.get("creature_id"))
        if parent_variant_id is None:
            parent_variant_id = str(parent_id)
    for key in variant.get("overrides", []):
        if key in IMMUTABLE_VARIANT_FIELDS:
            raise CreatureContractError("VARIANT_IMMUTABLE_FIELD_OVERRIDE")
        effective[key] = copy.deepcopy(variant["override_values"][key])
    lineage = copy.deepcopy(effective.get("variant_lineage", {}))
    lineage.update({"variant_id": variant["variant_id"], "kind": variant["kind"], "parent_id": parent_id, "inherits": list(variant.get("inherits", [])), "overrides": list(variant.get("overrides", []))})
    effective["variant_lineage"] = lineage
    if variant.get("kind") == "derived":
        effective["provenance"] = copy.deepcopy(effective.get("provenance", {}))
        effective["provenance"]["source_id"] = f"{effective['provenance'].get('source_id', 'synthetic')}-{variant['variant_id']}"
        effective["provenance"]["source_revision"] = SCHEMA_VERSION
        effective["provenance_hash"] = _record_hash(effective)
        effective["provenance"]["record_hash"] = effective["provenance_hash"]
    return effective, parent_creature_id, parent_variant_id, variant["variant_id"]


def materialize_variant(creature: Mapping[str, Any], variant_id: str, variants: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], str | None, str | None, str]:
    variant = variants.get(variant_id)
    if variant is None or variant.get("creature_id") != creature.get("creature_id"):
        raise CreatureContractError("CREATURE_VARIANT_UNAVAILABLE")
    return _merge_variant(creature, variant, variants)


def _cache_key(*, creature_id: str, variant_id: str, direction: str, state: str, direction_asset_id: str, state_route_id: str, topology_revision: str, asset_revision: str, normalization: str, request_mode: str, registry_mode: str) -> str:
    return "|".join(
        (
            f"creature_id={creature_id}",
            f"variant={variant_id}",
            f"direction={direction}",
            f"state={state}",
            f"direction_asset_id={direction_asset_id}",
            f"state_route_id={state_route_id}",
            f"rig_topology_revision={topology_revision}",
            f"asset_revision={asset_revision}",
            f"normalization={normalization}",
            f"request_mode={request_mode}",
            f"registry_mode={registry_mode}",
        )
    )


@dataclass(frozen=True)
class CreatureResolution:
    result: str
    creature_id: str | None
    variant: str | None
    variant_kind: str | None
    parent_creature_id: str | None
    parent_variant_id: str | None
    requested_direction: str | None
    resolved_direction: str | None
    direction_asset_id: str | None
    direction_content_hash: str | None
    requested_state: str | None
    resolved_state: str | None
    state_route_id: str | None
    timing_phase: dict[str, Any] | None
    topology_id: str | None
    locomotion_class: str | None
    support_model: str | None
    rig_family: str | None
    base_scale: dict[str, float] | None
    footprint: dict[str, float] | None
    collision_profile: dict[str, Any] | None
    anchors: dict[str, dict[str, float]] | None
    effective_overrides: dict[str, Any] | None
    asset_revision: str | None
    provenance_hash: str | None
    fallback_mode: str
    cache_key: str
    cache_hit: bool
    error_code: str | None
    rejection_class: str | None
    production_routing: str
    production_safe: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in self.__dict__.items()}


def _reject(error_code: str, *, creature_id: str | None = None, variant: str | None = None, requested_direction: str | None = None, requested_state: str | None = None, cache_key: str = "", production_routing: str = "BLOCKED", rejection_class: str = "RUNTIME_REJECTION", detail: str = "") -> CreatureResolution:
    return CreatureResolution(
        result="REJECTED", creature_id=creature_id, variant=variant, variant_kind=None,
        parent_creature_id=None, parent_variant_id=None, requested_direction=requested_direction,
        resolved_direction=None, direction_asset_id=None, direction_content_hash=None,
        requested_state=requested_state, resolved_state=None, state_route_id=None, timing_phase=None,
        topology_id=None, locomotion_class=None, support_model=None, rig_family=None,
        base_scale=None, footprint=None, collision_profile=None, anchors=None, effective_overrides=None,
        asset_revision=None, provenance_hash=None, fallback_mode="NONE", cache_key=cache_key,
        cache_hit=False, error_code=error_code, rejection_class=rejection_class,
        production_routing=production_routing, production_safe=False, detail=detail,
    )


class CreatureRegistry:
    """Fail-closed v0.18.1 registry for TEST_ONLY and empty production data."""

    def __init__(self, manifest: Mapping[str, Any], *, production_registry: bool | None = None, production_routing: str | None = None) -> None:
        self.manifest = copy.deepcopy(dict(manifest))
        self.production_routing = production_routing if production_routing is not None else self.manifest.get("production_routing")
        enforce_production_routing(self.production_routing)
        self.production_registry = bool(self.manifest.get("production_registry")) if production_registry is None else production_registry
        validate_creature_manifest(self.manifest, production_registry=self.production_registry)
        self._creatures = {item["creature_id"]: item for item in self.manifest.get("creatures", [])}
        self._variants = {item["variant_id"]: item for item in self.manifest.get("variants", [])}
        self._cache: dict[str, CreatureResolution] = {}

    def poison_cache_for_test(self, cache_key: str, resolution: CreatureResolution) -> None:
        self._cache[cache_key] = resolution

    def cache_stats(self) -> dict[str, int]:
        return {"entries": len(self._cache)}

    def resolve(self, creature_id: str, variant: str, direction: Any, state: str = "idle", *, request_mode: str = "direct", topology_revision: str = "creature-topology-v0181", production_routing: str | None = None) -> CreatureResolution:
        routing = production_routing if production_routing is not None else self.production_routing
        try:
            enforce_production_routing(routing)
        except CreatureContractError as exc:
            return _reject(exc.error_code, creature_id=creature_id, variant=variant, requested_state=state, production_routing=str(routing), rejection_class=exc.rejection_class, detail=str(exc))
        normalization = normalize_direction_result(direction)
        creature = self._creatures.get(creature_id)
        if creature is None:
            return _reject("CREATURE_UNKNOWN", creature_id=creature_id, variant=variant, requested_state=state, production_routing=routing)
        try:
            effective, parent_creature_id, parent_variant_id, effective_variant_id = materialize_variant(creature, variant, self._variants)
        except CreatureContractError as exc:
            return _reject(exc.error_code, creature_id=creature_id, variant=variant, requested_direction=normalization.direction, requested_state=state, production_routing=routing, rejection_class=exc.rejection_class, detail=str(exc))
        if normalization.direction is None:
            return _reject(normalization.error_code or "DIRECTION_UNRESOLVED", creature_id=creature_id, variant=variant, requested_state=state, production_routing=routing, detail=normalization.outcome)
        bindings = effective["direction_bindings"]
        binding = bindings.get(normalization.direction)
        route = effective["state_routes"].get(state) if state in CANONICAL_STATES else None
        if binding is None:
            return _reject("CREATURE_DIRECTION_UNAVAILABLE", creature_id=creature_id, variant=variant, requested_direction=normalization.direction, requested_state=state, production_routing=routing)
        if state not in CANONICAL_STATES or effective["animation_state_contract"].get(state) == "UNSUPPORTED":
            return _reject("CREATURE_STATE_UNSUPPORTED", creature_id=creature_id, variant=variant, requested_direction=normalization.direction, requested_state=state, production_routing=routing)
        if not isinstance(route, Mapping) or route.get("state_route_id") is None:
            return _reject("STATE_ROUTE_BINDING_INVALID", creature_id=creature_id, variant=variant, requested_direction=normalization.direction, requested_state=state, production_routing=routing)
        key = _cache_key(
            creature_id=creature_id,
            variant_id=effective_variant_id,
            direction=normalization.direction,
            state=state,
            direction_asset_id=str(binding["direction_asset_id"]),
            state_route_id=str(route["state_route_id"]),
            topology_revision=topology_revision,
            asset_revision=str(effective["asset_revision"]),
            normalization=normalization.outcome,
            request_mode=request_mode,
            registry_mode="production" if self.production_registry else "test",
        )
        cached = self._cache.get(key)
        if cached is not None:
            expected = (cached.creature_id, cached.variant, cached.requested_direction, cached.requested_state, cached.direction_asset_id, cached.state_route_id, cached.asset_revision)
            actual = (creature_id, effective_variant_id, normalization.direction, state, binding["direction_asset_id"], route["state_route_id"], effective["asset_revision"])
            if expected != actual or cached.result != "RESOLVED":
                return _reject("STALE_CREATURE_CACHE_CONTEXT", creature_id=creature_id, variant=effective_variant_id, requested_direction=normalization.direction, requested_state=state, cache_key=key, production_routing=routing, detail="cached identity does not match the requested creature/variant/direction/state")
            return copy.copy(cached).__class__(**{**cached.to_dict(), "cache_hit": True})
        result = CreatureResolution(
            result="RESOLVED", creature_id=creature_id, variant=effective_variant_id,
            variant_kind=effective["variant_lineage"]["kind"], parent_creature_id=parent_creature_id,
            parent_variant_id=parent_variant_id, requested_direction=normalization.direction,
            resolved_direction=normalization.direction, direction_asset_id=binding["direction_asset_id"],
            direction_content_hash=binding["direction_content_hash"], requested_state=state,
            resolved_state=state, state_route_id=route["state_route_id"],
            timing_phase=copy.deepcopy(route["timing_phase"]), topology_id=effective["topology_id"],
            locomotion_class=effective["locomotion_class"], support_model=effective["support_model"],
            rig_family=effective["rig_family"], base_scale=copy.deepcopy(effective["base_scale"]),
            footprint=copy.deepcopy(effective["footprint"]),
            collision_profile=copy.deepcopy(effective["collision_profile"]),
            anchors=copy.deepcopy(effective["anchors"]),
            effective_overrides={key: copy.deepcopy(self._variants[effective_variant_id]["override_values"][key]) for key in self._variants[effective_variant_id].get("overrides", [])},
            asset_revision=str(effective["asset_revision"]), provenance_hash=effective["provenance_hash"],
            fallback_mode="NONE", cache_key=key, cache_hit=False, error_code=None,
            rejection_class=None, production_routing=routing, production_safe=False, detail="",
        )
        self._cache[key] = result
        return result


def clone_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(manifest))
