"""Generic creature/monster runtime contracts for v0.18.0.

This module owns creature topology, support, scale, animation-state and
variant semantics.  It intentionally does not import equipment composition or
write to the production asset registry.  A resolver result is either an
explicitly addressed TEST_ONLY fixture or an auditable fail-closed rejection.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from ugas.direction_runtime import CANONICAL_DIRECTIONS, normalize_direction_result


SCHEMA_VERSION = "0.18.0"
ARCHETYPES = (
    "humanoid_biped",
    "quadruped",
    "flying_winged",
    "serpentine",
    "amorphous",
    "stationary_structure",
)
CANONICAL_STATES = ("idle", "locomotion", "attack_primary", "hit_reaction", "death")
STATE_VALUES = ("REQUIRED", "OPTIONAL", "UNSUPPORTED")
ALLOWED_VARIANT_OVERRIDES = frozenset(
    {"base_scale", "footprint", "collision_profile", "anchors", "animation_state_contract", "direction_coverage", "provenance"}
)
ARCHETYPE_RULES: dict[str, dict[str, str]] = {
    "humanoid_biped": {"topology_id": "topology_humanoid_biped_v1", "locomotion_class": "bipedal", "support_model": "two_foot_contact"},
    "quadruped": {"topology_id": "topology_quadruped_v1", "locomotion_class": "quadrupedal", "support_model": "four_foot_contact"},
    "flying_winged": {"topology_id": "topology_flying_winged_v1", "locomotion_class": "flying", "support_model": "wing_or_airborne"},
    "serpentine": {"topology_id": "topology_serpentine_v1", "locomotion_class": "serpentine", "support_model": "belly_contact"},
    "amorphous": {"topology_id": "topology_amorphous_v1", "locomotion_class": "sliding", "support_model": "mass_contact"},
    "stationary_structure": {"topology_id": "topology_stationary_structure_v1", "locomotion_class": "stationary", "support_model": "fixed_contact"},
}


class CreatureContractError(ValueError):
    """Raised for a semantic contract rejection with a stable error code."""

    def __init__(self, error_code: str, detail: str = "") -> None:
        self.error_code = error_code
        self.rejection_class = "CONTRACT_REJECTION"
        super().__init__(f"{error_code}{':' + detail if detail else ''}")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _reject(error_code: str, *, cache_key: str = "", requested_direction: str | None = None, requested_state: str | None = None, creature_id: str | None = None, variant: str | None = None, production_safe: bool = False, detail: str = "") -> "CreatureResolution":
    return CreatureResolution(
        result="REJECTED", creature_id=creature_id, variant=variant, requested_direction=requested_direction,
        resolved_direction=None, requested_state=requested_state, resolved_state=None, topology_id=None,
        locomotion_class=None, support_model=None, rig_family=None, base_scale=None, footprint=None,
        collision_profile=None, anchors=None, fallback_mode="NONE", cache_key=cache_key,
        cache_hit=False, error_code=error_code, rejection_class="RUNTIME_REJECTION" if error_code.startswith("CREATURE_") or error_code.startswith("STALE_") else "CONTRACT_REJECTION",
        provenance_hash=None, production_safe=production_safe, detail=detail,
    )


@dataclass(frozen=True)
class CreatureResolution:
    result: str
    creature_id: str | None
    variant: str | None
    requested_direction: str | None
    resolved_direction: str | None
    requested_state: str | None
    resolved_state: str | None
    topology_id: str | None
    locomotion_class: str | None
    support_model: str | None
    rig_family: str | None
    base_scale: dict[str, float] | None
    footprint: dict[str, float] | None
    collision_profile: dict[str, Any] | None
    anchors: dict[str, dict[str, float]] | None
    fallback_mode: str
    cache_key: str
    cache_hit: bool
    error_code: str | None
    rejection_class: str | None
    provenance_hash: str | None
    production_safe: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in self.__dict__.items()}


def _required(value: Mapping[str, Any], key: str) -> Any:
    if key not in value or value[key] in (None, "", [], {}):
        raise CreatureContractError(f"{key.upper()}_EXPLICIT_REQUIRED")
    return value[key]


def _validate_positive_mapping(value: Any, error_code: str, keys: tuple[str, ...]) -> dict[str, float]:
    if not isinstance(value, Mapping) or any(key not in value for key in keys):
        raise CreatureContractError(error_code)
    output: dict[str, float] = {}
    for key in keys:
        number = value[key]
        if isinstance(number, bool) or not isinstance(number, (int, float)) or number <= 0:
            raise CreatureContractError(error_code)
        output[key] = float(number)
    return output


def _record_hash(record: Mapping[str, Any]) -> str:
    value = copy.deepcopy(dict(record))
    value.pop("provenance_hash", None)
    provenance = value.get("provenance")
    if isinstance(provenance, dict):
        provenance.pop("record_hash", None)
    return sha256_json(value)


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
    _required(record, "creature_id")
    _required(record, "species_id")
    _required(record, "rig_family")
    _validate_positive_mapping(record.get("base_scale"), "BASE_SCALE_EXPLICIT_REQUIRED", ("x", "y"))
    _validate_positive_mapping(record.get("footprint"), "FOOTPRINT_EXPLICIT_REQUIRED", ("width", "depth"))
    collision = record.get("collision_profile")
    if not isinstance(collision, Mapping) or not collision.get("shape") or not collision.get("width") or not collision.get("height"):
        raise CreatureContractError("COLLISION_PROFILE_EXPLICIT_REQUIRED")
    anchors = record.get("anchors")
    if not isinstance(anchors, Mapping) or not anchors:
        raise CreatureContractError("ANCHORS_EXPLICIT_REQUIRED")
    for anchor_id, anchor in anchors.items():
        if not isinstance(anchor_id, str) or not isinstance(anchor, Mapping) or not all(isinstance(anchor.get(key), (int, float)) and not isinstance(anchor.get(key), bool) for key in ("x", "y")):
            raise CreatureContractError("ANCHOR_GEOMETRY_INVALID")
    directions = record.get("direction_coverage")
    if not isinstance(directions, list) or not directions or any(direction not in CANONICAL_DIRECTIONS for direction in directions):
        raise CreatureContractError("DIRECTION_COVERAGE_INVALID")
    states = record.get("animation_state_contract")
    if not isinstance(states, Mapping) or set(states) != set(CANONICAL_STATES) or any(value not in STATE_VALUES for value in states.values()):
        raise CreatureContractError("ANIMATION_STATE_CONTRACT_INVALID")
    if not any(value == "REQUIRED" for value in states.values()):
        raise CreatureContractError("REQUIRED_ANIMATION_STATE_MISSING")
    lineage = record.get("variant_lineage")
    if not isinstance(lineage, Mapping) or not lineage.get("variant_id") or lineage.get("kind") not in {"base", "derived"}:
        raise CreatureContractError("VARIANT_LINEAGE_INVALID")
    provenance = record.get("provenance")
    if not isinstance(provenance, Mapping) or provenance.get("source_kind") != "TEST_ONLY_SYNTHETIC" or provenance.get("production_safe") is not False:
        raise CreatureContractError("PROVENANCE_BOUNDARY_INVALID")
    if record.get("test_only") is not True or record.get("production_safe") is not False:
        raise CreatureContractError("TEST_ONLY_PRODUCTION_BOUNDARY_INVALID")
    expected_hash = _record_hash(record)
    if record.get("provenance_hash") != expected_hash or provenance.get("record_hash") != expected_hash:
        raise CreatureContractError("PROVENANCE_HASH_MISMATCH")


def validate_variant_lineage(variants: list[Mapping[str, Any]]) -> None:
    ids = [item.get("variant_id") for item in variants]
    if len(ids) != len(set(ids)) or any(not isinstance(item, str) or not item for item in ids):
        raise CreatureContractError("VARIANT_LINEAGE_ID_INVALID")
    by_id = {item["variant_id"]: item for item in variants}
    for item in variants:
        parent = item.get("parent_id")
        if parent is not None and parent not in by_id:
            raise CreatureContractError("VARIANT_LINEAGE_PARENT_MISSING")
        overrides = item.get("overrides", [])
        if not isinstance(overrides, list) or any(value not in ALLOWED_VARIANT_OVERRIDES for value in overrides):
            raise CreatureContractError("VARIANT_OVERRIDE_NOT_ALLOWLISTED")
    for variant_id in by_id:
        seen: set[str] = set()
        cursor: str | None = variant_id
        while cursor is not None:
            if cursor in seen:
                raise CreatureContractError("VARIANT_LINEAGE_CYCLE")
            seen.add(cursor)
            cursor = by_id[cursor].get("parent_id")


def validate_creature_manifest(manifest: Mapping[str, Any], *, production_registry: bool | None = None) -> None:
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("manifest_type") != "creatures-monsters-runtime-foundation":
        raise CreatureContractError("CREATURE_SCHEMA_INVALID")
    creatures = manifest.get("creatures")
    variants = manifest.get("variants")
    if not isinstance(creatures, list) or not isinstance(variants, list):
        raise CreatureContractError("CREATURE_SCHEMA_INVALID")
    validate_variant_lineage(variants)
    seen: set[str] = set()
    for creature in creatures:
        if not isinstance(creature, Mapping) or creature.get("creature_id") in seen:
            raise CreatureContractError("CREATURE_ID_DUPLICATE")
        seen.add(str(creature.get("creature_id")))
        validate_creature_definition(creature)
        if creature["variant_lineage"]["variant_id"] not in {item["variant_id"] for item in variants}:
            raise CreatureContractError("VARIANT_LINEAGE_PARENT_MISSING")
    is_production = manifest.get("production_registry") if production_registry is None else production_registry
    if is_production and creatures:
        raise CreatureContractError("TEST_ONLY_CREATURE_IN_PRODUCTION_REGISTRY")
    if is_production and manifest.get("registry_authority") != "PRODUCTION_APPROVED_ASSETS_ONLY":
        raise CreatureContractError("PRODUCTION_REGISTRY_AUTHORITY_INVALID")


def _cache_key(creature_id: str, archetype: str, variant: str, direction: str | None, state: str, topology_revision: str, asset_revision: str, normalization_outcome: str, request_mode: str, registry_mode: str) -> str:
    return "|".join(
        (f"creature_id={creature_id}", f"archetype={archetype}", f"variant={variant}", f"direction={direction or 'UNRESOLVED'}", f"state={state}", f"rig_topology_revision={topology_revision}", f"asset_revision={asset_revision}", f"normalization={normalization_outcome}", f"request_mode={request_mode}", f"registry_mode={registry_mode}")
    )


class CreatureRegistry:
    """In-memory resolver with explicit TEST_ONLY and production modes."""

    def __init__(self, manifest: Mapping[str, Any], *, production_registry: bool = False) -> None:
        self.manifest = copy.deepcopy(dict(manifest))
        self.production_registry = production_registry
        validate_creature_manifest(self.manifest, production_registry=production_registry)
        self._creatures = {item["creature_id"]: item for item in self.manifest["creatures"]}
        self._cache: dict[str, CreatureResolution] = {}

    def poison_cache_for_test(self, cache_key: str, resolution: CreatureResolution) -> None:
        self._cache[cache_key] = resolution

    def cache_stats(self) -> dict[str, int]:
        return {"entries": len(self._cache)}

    def resolve(
        self,
        creature_id: str,
        variant: str,
        direction: Any,
        state: str = "idle",
        *,
        request_mode: str = "preview",
        registry_mode: str = "test",
        allow_preview_fallback: bool = False,
        topology_revision: str = "creature-topology-v0180",
    ) -> CreatureResolution:
        normalized = normalize_direction_result(direction)
        creature = self._creatures.get(creature_id)
        if creature is None:
            return _reject("CREATURE_UNKNOWN", requested_state=state, creature_id=creature_id, variant=variant)
        if registry_mode == "production" and (self.production_registry or creature.get("test_only")):
            return _reject("TEST_ONLY_CREATURE_IN_PRODUCTION_REGISTRY", requested_state=state, creature_id=creature_id, variant=variant)
        if variant != creature.get("variant_lineage", {}).get("variant_id"):
            return _reject("CREATURE_VARIANT_UNAVAILABLE", requested_state=state, creature_id=creature_id, variant=variant)
        asset_revision = str(creature.get("asset_revision"))
        cache_key = _cache_key(creature_id, creature["archetype"], variant, normalized.direction, state, topology_revision, asset_revision, normalized.outcome, request_mode, registry_mode)
        cached = self._cache.get(cache_key)
        if cached is not None:
            if cached.creature_id != creature_id or cached.variant != variant or cached.requested_state != state or cached.resolved_direction != normalized.direction:
                return _reject("STALE_CREATURE_CACHE_CONTEXT", cache_key=cache_key, requested_direction=normalized.direction, requested_state=state, creature_id=creature_id, variant=variant)
            return copy.copy(cached).__class__(**{**cached.to_dict(), "cache_hit": True})
        if normalized.direction is None:
            result = _reject(normalized.error_code or "CREATURE_DIRECTION_UNRESOLVED", cache_key=cache_key, requested_direction=None, requested_state=state, creature_id=creature_id, variant=variant, detail=normalized.outcome)
            self._cache[cache_key] = result
            return result
        states = creature["animation_state_contract"]
        if state not in CANONICAL_STATES or states.get(state) == "UNSUPPORTED":
            result = _reject("CREATURE_STATE_UNSUPPORTED", cache_key=cache_key, requested_direction=normalized.direction, requested_state=state, creature_id=creature_id, variant=variant)
            self._cache[cache_key] = result
            return result
        fallback = "NONE"
        if normalized.direction not in creature["direction_coverage"]:
            if allow_preview_fallback and request_mode == "preview" and registry_mode != "production":
                fallback = "TEST_ONLY_PREVIEW_FALLBACK"
            else:
                result = _reject("CREATURE_DIRECTION_UNAVAILABLE", cache_key=cache_key, requested_direction=normalized.direction, requested_state=state, creature_id=creature_id, variant=variant)
                self._cache[cache_key] = result
                return result
        result = CreatureResolution(
            result="RESOLVED", creature_id=creature_id, variant=variant, requested_direction=normalized.direction,
            resolved_direction=normalized.direction, requested_state=state, resolved_state=state, topology_id=creature["topology_id"],
            locomotion_class=creature["locomotion_class"], support_model=creature["support_model"], rig_family=creature["rig_family"],
            base_scale=copy.deepcopy(creature["base_scale"]), footprint=copy.deepcopy(creature["footprint"]), collision_profile=copy.deepcopy(creature["collision_profile"]),
            anchors=copy.deepcopy(creature["anchors"]), fallback_mode=fallback, cache_key=cache_key, cache_hit=False,
            error_code=None, rejection_class=None, provenance_hash=creature["provenance_hash"], production_safe=False, detail="",
        )
        self._cache[cache_key] = result
        return result


def clone_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep copy for negative-control mutations."""
    return copy.deepcopy(dict(manifest))
