"""v0.18.2 derived-variant and locomotion-state contract integrity.

This layer is forward-only from the rejected v0.18.1 runtime.  It revalidates
the fully materialized record before resolution/cache construction, keeps
metadata-only variant revisions separate from directional asset revisions,
and makes archetype/state compatibility executable.  All accepted fixtures
remain TEST_ONLY synthetic evidence.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import Any, Mapping

from ugas.creature_runtime import ARCHETYPES, ARCHETYPE_RULES, CANONICAL_STATES
from ugas.direction_runtime import CANONICAL_DIRECTIONS, normalize_direction_result
from ugas.creature_runtime_v0181 import (
    ALLOWED_VARIANT_OVERRIDES,
    COLLISION_SHAPES,
    CreatureContractError,
    CreatureResolution as _V0181Resolution,
    _record_hash,
    canonical_json,
    enforce_production_routing,
    sha256_json,
    validate_creature_definition as _validate_base_definition,
)


SCHEMA_VERSION = "0.18.2"
STATE_VALUES = ("REQUIRED", "OPTIONAL", "UNSUPPORTED")
ARCHETYPE_STATE_RULES: dict[str, dict[str, str]] = {
    "humanoid_biped": {"locomotion": "REQUIRED"},
    "quadruped": {"locomotion": "REQUIRED"},
    "flying_winged": {"locomotion": "REQUIRED"},
    "serpentine": {"locomotion": "REQUIRED"},
    "amorphous": {"locomotion": "REQUIRED"},
    "stationary_structure": {"locomotion": "UNSUPPORTED"},
}
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


def validate_archetype_state_compatibility(record: Mapping[str, Any]) -> None:
    """Enforce the reviewed moving-versus-stationary state rule."""
    archetype = record.get("archetype")
    expected = ARCHETYPE_STATE_RULES.get(archetype, {}).get("locomotion")
    if expected is None:
        raise CreatureContractError("ARCHETYPE_UNSUPPORTED", str(archetype))
    contract = record.get("animation_state_contract")
    routes = record.get("state_routes")
    if not isinstance(contract, Mapping) or not isinstance(routes, Mapping):
        raise CreatureContractError("LOCOMOTION_STATE_ARCHETYPE_MISMATCH")
    if contract.get("locomotion") != expected:
        raise CreatureContractError("LOCOMOTION_STATE_ARCHETYPE_MISMATCH")
    route = routes.get("locomotion")
    if not isinstance(route, Mapping) or route.get("availability") != expected:
        raise CreatureContractError("LOCOMOTION_STATE_ROUTE_MISMATCH")
    if expected == "REQUIRED":
        if not isinstance(route.get("state_route_id"), str) or not route.get("state_route_id") or not isinstance(route.get("timing_phase"), Mapping):
            raise CreatureContractError("LOCOMOTION_STATE_ROUTE_MISSING")
    elif route.get("state_route_id") is not None or route.get("timing_phase") is not None:
        raise CreatureContractError("LOCOMOTION_STATE_ROUTE_MISMATCH")


def validate_creature_definition(record: Mapping[str, Any]) -> None:
    """Run the v0.18.1 semantic contract plus v0.18.2 state compatibility."""
    _validate_base_definition(record)
    validate_archetype_state_compatibility(record)


def validate_variant_lineage(variants: list[Mapping[str, Any]], creatures: list[Mapping[str, Any]] | None = None) -> None:
    """Validate lineage shape and metadata without trusting raw override values."""
    if not isinstance(variants, list):
        raise CreatureContractError("VARIANT_LINEAGE_INVALID")
    ids = [item.get("variant_id") if isinstance(item, Mapping) else None for item in variants]
    if len(ids) != len(set(ids)) or any(not isinstance(item, str) or not item for item in ids):
        raise CreatureContractError("VARIANT_LINEAGE_ID_INVALID")
    revisions = [item.get("variant_revision") if isinstance(item, Mapping) else None for item in variants]
    if any(not isinstance(item, str) or not item for item in revisions) or len(revisions) != len(set(revisions)):
        raise CreatureContractError("VARIANT_REVISION_INVALID")
    by_id = {item["variant_id"]: item for item in variants}
    creature_ids = {item.get("creature_id") for item in creatures or [] if isinstance(item, Mapping)}
    for item in variants:
        if not isinstance(item, Mapping) or item.get("creature_id") not in creature_ids:
            raise CreatureContractError("VARIANT_CREATURE_ID_INVALID")
        kind = item.get("kind")
        parent = item.get("parent_id")
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
    variant_ids = {item["variant_id"] for item in variants}
    seen: set[str] = set()
    for creature in creatures:
        if not isinstance(creature, Mapping) or creature.get("creature_id") in seen:
            raise CreatureContractError("CREATURE_ID_DUPLICATE")
        seen.add(str(creature.get("creature_id")))
        validate_creature_definition(creature)
        lineage = creature.get("variant_lineage")
        if not isinstance(lineage, Mapping) or lineage.get("variant_id") not in variant_ids:
            raise CreatureContractError("VARIANT_LINEAGE_PARENT_MISSING")
    if creatures and {item.get("archetype") for item in creatures if isinstance(item, Mapping)} != set(ARCHETYPES):
        raise CreatureContractError("ARCHETYPE_SET_INCOMPLETE")
    is_production = bool(manifest.get("production_registry")) if production_registry is None else production_registry
    if is_production and creatures:
        raise CreatureContractError("TEST_ONLY_CREATURE_IN_PRODUCTION_REGISTRY")
    if is_production and manifest.get("registry_authority") != "PRODUCTION_APPROVED_ASSETS_ONLY":
        raise CreatureContractError("PRODUCTION_REGISTRY_AUTHORITY_INVALID")


def _materialize_chain(base: Mapping[str, Any], variant: Mapping[str, Any], by_id: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], str | None, str | None, str]:
    parent_id = variant.get("parent_id")
    if parent_id is None:
        effective = copy.deepcopy(dict(base))
        parent_creature_id = None
        parent_variant_id = None
    else:
        effective, parent_creature_id, parent_variant_id, _ = _materialize_chain(base, by_id[parent_id], by_id)
        if parent_creature_id is None:
            parent_creature_id = str(base.get("creature_id"))
        if parent_variant_id is None:
            parent_variant_id = str(parent_id)
    for key in variant.get("overrides", []):
        if key in IMMUTABLE_VARIANT_FIELDS:
            raise CreatureContractError("VARIANT_IMMUTABLE_FIELD_OVERRIDE")
        if key not in variant.get("override_values", {}):
            raise CreatureContractError("VARIANT_OVERRIDE_NOT_ALLOWLISTED")
        effective[key] = copy.deepcopy(variant["override_values"][key])
    lineage = copy.deepcopy(effective.get("variant_lineage", {}))
    lineage.update({"variant_id": variant["variant_id"], "kind": variant["kind"], "parent_id": parent_id, "inherits": list(variant.get("inherits", [])), "overrides": list(variant.get("overrides", []))})
    effective["variant_lineage"] = lineage
    if variant.get("kind") == "derived":
        provenance = effective.get("provenance")
        if not isinstance(provenance, Mapping):
            raise CreatureContractError("PROVENANCE_BOUNDARY_INVALID")
        provenance = copy.deepcopy(dict(provenance))
        provenance["source_id"] = f"{provenance.get('source_id', 'synthetic')}-{variant['variant_id']}"
        provenance["source_revision"] = SCHEMA_VERSION
        effective["provenance"] = provenance
        effective["provenance_hash"] = _record_hash(effective)
        provenance["record_hash"] = effective["provenance_hash"]
    return effective, parent_creature_id, parent_variant_id, variant["variant_id"]


def materialize_variant(creature: Mapping[str, Any], variant_id: str, variants: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], str | None, str | None, str]:
    variant = variants.get(variant_id)
    if variant is None or variant.get("creature_id") != creature.get("creature_id"):
        raise CreatureContractError("CREATURE_VARIANT_UNAVAILABLE")
    return _materialize_chain(creature, variant, variants)


def validate_effective_variant(effective: Mapping[str, Any], variant: Mapping[str, Any]) -> None:
    """Validate the final materialized record before cache construction/output."""
    validate_creature_definition(effective)
    lineage = effective.get("variant_lineage")
    if not isinstance(lineage, Mapping) or lineage.get("variant_id") != variant.get("variant_id"):
        raise CreatureContractError("VARIANT_LINEAGE_INVALID")
    variant_revision = variant.get("variant_revision")
    if not isinstance(variant_revision, str) or not variant_revision:
        raise CreatureContractError("VARIANT_REVISION_INVALID")
    declared_hash = variant.get("provenance_hash")
    if declared_hash is not None and declared_hash != effective.get("provenance_hash"):
        raise CreatureContractError("PROVENANCE_HASH_MISMATCH")
    direction_revision = effective.get("asset_revision")
    for binding in effective.get("direction_bindings", {}).values():
        if binding.get("asset_revision") != direction_revision:
            raise CreatureContractError("DIRECTION_ASSET_REVISION_MISMATCH")


def _cache_key(*, creature_id: str, variant_id: str, variant_revision: str, direction: str, state: str, direction_asset_id: str, direction_asset_revision: str, state_route_id: str, topology_revision: str, asset_revision: str, normalization: str, request_mode: str, registry_mode: str) -> str:
    return "|".join(
        (
            f"creature_id={creature_id}",
            f"variant={variant_id}",
            f"variant_revision={variant_revision}",
            f"direction={direction}",
            f"state={state}",
            f"direction_asset_id={direction_asset_id}",
            f"direction_asset_revision={direction_asset_revision}",
            f"state_route_id={state_route_id}",
            f"rig_topology_revision={topology_revision}",
            f"asset_revision={asset_revision}",
            f"normalization={normalization}",
            f"request_mode={request_mode}",
            f"registry_mode={registry_mode}",
        )
    )


@dataclass(frozen=True)
class CreatureResolution(_V0181Resolution):
    variant_revision: str | None = None
    direction_asset_revision: str | None = None


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
        variant_revision=None, direction_asset_revision=None,
    )


class CreatureRegistry:
    """Fail-closed v0.18.2 registry with effective-variant validation."""

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

    def resolve(self, creature_id: str, variant: str, direction: Any, state: str = "idle", *, request_mode: str = "direct", topology_revision: str = "creature-topology-v0182", production_routing: str | None = None) -> CreatureResolution:
        routing = production_routing if production_routing is not None else self.production_routing
        try:
            enforce_production_routing(routing)
        except CreatureContractError as exc:
            return _reject(exc.error_code, creature_id=creature_id, variant=variant, requested_state=state, production_routing=str(routing), rejection_class=exc.rejection_class, detail=str(exc))
        normalization = normalize_direction_result(direction)
        creature = self._creatures.get(creature_id)
        if creature is None:
            return _reject("CREATURE_UNKNOWN", creature_id=creature_id, variant=variant, requested_state=state, production_routing=routing)
        variant_record = self._variants.get(variant)
        try:
            effective, parent_creature_id, parent_variant_id, effective_variant_id = materialize_variant(creature, variant, self._variants)
            variant_record = self._variants[effective_variant_id]
            validate_effective_variant(effective, variant_record)
        except CreatureContractError as exc:
            return _reject(exc.error_code, creature_id=creature_id, variant=variant, requested_direction=normalization.direction, requested_state=state, production_routing=routing, rejection_class=exc.rejection_class, detail=str(exc))
        if normalization.direction is None:
            return _reject(normalization.error_code or "DIRECTION_UNRESOLVED", creature_id=creature_id, variant=variant, requested_state=state, production_routing=routing, detail=normalization.outcome)
        bindings = effective["direction_bindings"]
        binding = bindings.get(normalization.direction)
        route = effective["state_routes"].get(state) if state in CANONICAL_STATES else None
        if binding is None:
            return _reject("CREATURE_DIRECTION_UNAVAILABLE", creature_id=creature_id, variant=effective_variant_id, requested_direction=normalization.direction, requested_state=state, production_routing=routing)
        if state not in CANONICAL_STATES or effective["animation_state_contract"].get(state) == "UNSUPPORTED":
            return _reject("CREATURE_STATE_UNSUPPORTED", creature_id=creature_id, variant=effective_variant_id, requested_direction=normalization.direction, requested_state=state, production_routing=routing)
        if not isinstance(route, Mapping) or route.get("state_route_id") is None:
            return _reject("STATE_ROUTE_BINDING_INVALID", creature_id=creature_id, variant=effective_variant_id, requested_direction=normalization.direction, requested_state=state, production_routing=routing)
        variant_revision = str(variant_record["variant_revision"])
        direction_asset_revision = str(binding["asset_revision"])
        key = _cache_key(
            creature_id=creature_id, variant_id=effective_variant_id, variant_revision=variant_revision,
            direction=normalization.direction, state=state, direction_asset_id=str(binding["direction_asset_id"]),
            direction_asset_revision=direction_asset_revision, state_route_id=str(route["state_route_id"]),
            topology_revision=topology_revision, asset_revision=str(effective["asset_revision"]),
            normalization=normalization.outcome, request_mode=request_mode,
            registry_mode="production" if self.production_registry else "test",
        )
        cached = self._cache.get(key)
        if cached is not None:
            expected = (cached.creature_id, cached.variant, cached.variant_revision, cached.requested_direction, cached.requested_state, cached.direction_asset_id, cached.direction_asset_revision, cached.state_route_id, cached.asset_revision)
            actual = (creature_id, effective_variant_id, variant_revision, normalization.direction, state, binding["direction_asset_id"], direction_asset_revision, route["state_route_id"], effective["asset_revision"])
            if expected != actual or cached.result != "RESOLVED":
                return _reject("STALE_CREATURE_CACHE_CONTEXT", creature_id=creature_id, variant=effective_variant_id, requested_direction=normalization.direction, requested_state=state, cache_key=key, production_routing=routing, detail="cached identity does not match creature/variant/revision/direction/state")
            return replace(cached, cache_hit=True)
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
            footprint=copy.deepcopy(effective["footprint"]), collision_profile=copy.deepcopy(effective["collision_profile"]),
            anchors=copy.deepcopy(effective["anchors"]),
            effective_overrides={key: copy.deepcopy(variant_record["override_values"][key]) for key in variant_record.get("overrides", [])},
            asset_revision=str(effective["asset_revision"]), provenance_hash=effective["provenance_hash"],
            fallback_mode="NONE", cache_key=key, cache_hit=False, error_code=None,
            rejection_class=None, production_routing=routing, production_safe=False, detail="",
            variant_revision=variant_revision, direction_asset_revision=direction_asset_revision,
        )
        self._cache[key] = result
        return result


def clone_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(manifest))


__all__ = [
    "ARCHETYPE_STATE_RULES",
    "ALLOWED_VARIANT_OVERRIDES",
    "CANONICAL_DIRECTIONS",
    "CANONICAL_STATES",
    "CreatureContractError",
    "CreatureRegistry",
    "CreatureResolution",
    "SCHEMA_VERSION",
    "canonical_json",
    "clone_manifest",
    "enforce_production_routing",
    "materialize_variant",
    "sha256_json",
    "validate_archetype_state_compatibility",
    "validate_creature_definition",
    "validate_creature_manifest",
    "validate_effective_variant",
    "validate_variant_lineage",
]
