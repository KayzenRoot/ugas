"""QA and governance integrity helpers for UGAS v0.20.3.

The v0.20.2 runtime remains the semantic source of truth for TEST_ONLY
tilesets.  This module makes that same semantic contract reusable for an
isolated production-shaped candidate, and supplies real injected rejection
paths for the v0.20.3 governance controls.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .environment_tileset_runtime_v0202 import (
    CARDINAL_SUPPORTED_MASKS,
    EIGHT_SUPPORTED_MASKS,
    TILE_CLASSES,
    EnvironmentTileRegistry as _RuntimeRegistry,
    EnvironmentTilesetContractError,
    canonical_json,
    sha256_bytes,
    validate_tileset_manifest as _validate_test_only_manifest,
    tile_to_world,
    world_to_tile,
    validate_metrics,
)


SCHEMA_VERSION = "0.20.3"


def _require(condition: bool, rejection_class: str, detail: str) -> None:
    if not condition:
        raise EnvironmentTilesetContractError(rejection_class, detail)


def _manifest_hash(manifest: Mapping[str, Any]) -> str:
    value = {key: item for key, item in manifest.items() if key != "provenance"}
    return sha256_bytes(canonical_json(value))


def recompute_manifest_provenance(manifest: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(manifest))
    value["provenance"] = {"manifest_hash": _manifest_hash(value)}
    return value


def validate_autotile_matrix(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the exact class x supported-mask matrix used by all gates."""

    families: list[dict[str, Any]] = []
    for family in manifest.get("terrain_families", []):
        family_id = str(family.get("terrain_family_id"))
        policy = family.get("adjacency_policy")
        supported_masks = family.get("supported_masks")
        _require(isinstance(supported_masks, list), "AUTOTILE_MATRIX_INVALID", family_id)
        expected = {(class_id, mask) for class_id in TILE_CLASSES for mask in supported_masks}
        observed: set[tuple[str, int]] = set()
        for record in family.get("autotile_variants", []):
            pair = (record.get("target_class_id"), record.get("adjacency_mask"))
            _require(pair not in observed, "DUPLICATE_AUTOTILE_MASK", f"{family_id}:{pair}")
            _require(pair[1] in supported_masks, "AUTOTILE_MASK_NOT_DECLARED", f"{family_id}:{pair}")
            observed.add(pair)
        _require(observed == expected, "AUTOTILE_MATRIX_INCOMPLETE", family_id)
        families.append({"terrain_family_id": family_id, "expected_count": len(expected), "observed_count": len(observed), "status": "PASS"})
    _require(bool(families), "AUTOTILE_MATRIX_INVALID", "no terrain families")
    return {"status": "AUTOTILE_MATRIX_VALID", "families": families}


def _as_test_only_semantic_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(manifest))
    value.update(
        {
            "production_approved": False,
            "production_routing": "BLOCKED",
            "production_registry_empty": True,
            "test_only": True,
            "production_safe": False,
        }
    )
    value["provenance"] = {"manifest_hash": _manifest_hash(value)}
    return value


def validate_production_tileset_candidate(
    root: Path,
    manifest: Mapping[str, Any],
    system_policy: "ProductionRoutingPolicy",
) -> dict[str, Any]:
    """Validate a production-shaped candidate through the TEST_ONLY semantic core."""

    _require(system_policy.production_routing == "ENABLED", "PRODUCTION_ROUTING_BLOCKED", "system production routing is BLOCKED")
    _require(manifest.get("production_routing") == "ENABLED", "PRODUCTION_ROUTING_BLOCKED", "candidate routing is not enabled")
    _require(manifest.get("production_approved") is True, "PRODUCTION_APPROVAL_REQUIRED", "production approval is required")
    _require(manifest.get("production_safe") is True, "PRODUCTION_SAFETY_REQUIRED", "production_safe must be true")
    _require(manifest.get("test_only") is False, "TEST_FIXTURE_IN_PRODUCTION_REGISTRY", "production candidate cannot be TEST_ONLY")
    _require(root.is_dir(), "MANIFEST_VALIDATION_REQUIRED", str(root))
    _require(manifest.get("provenance", {}).get("manifest_hash") == _manifest_hash(manifest), "MANIFEST_PROVENANCE_HASH_MISMATCH", "candidate provenance is not authoritative")
    _require(manifest.get("manifest_type") == "environment-tileset-runtime-qa-integrity", "MANIFEST_TYPE_INVALID", str(manifest.get("manifest_type")))
    normalized = _as_test_only_semantic_manifest(manifest)
    matrix = validate_autotile_matrix(normalized)
    semantic = _validate_test_only_manifest(root, normalized)
    return {"status": "PRODUCTION_CANDIDATE_VALID", "semantic_status": semantic["status"], "matrix": matrix, "mode": "ISOLATED_TEST_POLICY"}


@dataclass(frozen=True)
class ProductionRoutingPolicy:
    production_routing: str = "BLOCKED"


class EnvironmentTileRegistry(_RuntimeRegistry):
    """Registry with a reusable production semantic boundary."""

    def __init__(self, *, production: bool = False, production_policy: ProductionRoutingPolicy | None = None, root: Path | None = None):
        super().__init__(production=production, production_policy=production_policy or ProductionRoutingPolicy(), root=root)
        self.production_policy = production_policy or ProductionRoutingPolicy()

    def register(self, manifest: Mapping[str, Any]) -> None:
        if not self.production:
            return super().register(manifest)
        if manifest.get("test_only") is True:
            raise EnvironmentTilesetContractError("TEST_FIXTURE_IN_PRODUCTION_REGISTRY", "TEST_ONLY environment fixture rejected")
        result = validate_production_tileset_candidate(self.root or Path("."), manifest, self.production_policy)
        self._entries[str(manifest.get("tileset_id"))] = dict(manifest)
        self._last_validation = result


def validate_origin_semantics(transform: Callable[[int, int, Mapping[str, Any]], tuple[float, float]], metrics: Mapping[str, Any]) -> dict[str, Any]:
    """Reject a transform that ignores the declared origin."""

    top_left = dict(metrics)
    center = dict(metrics)
    top_left["origin"] = "TOP_LEFT"
    center["origin"] = "CENTER"
    top_position = transform(0, 0, top_left)
    center_position = transform(0, 0, center)
    _require(top_position != center_position, "ORIGIN_SEMANTICS_IGNORED", f"TOP_LEFT={top_position}; CENTER={center_position}")
    return {"status": "ORIGIN_SEMANTICS_DISTINCT", "top_left": list(top_position), "center": list(center_position)}


def validate_origin_roundtrips(
    metrics: Mapping[str, Any],
    coordinates: Sequence[tuple[int, int]],
    forward: Callable[[int, int, Mapping[str, Any]], tuple[float, float]] = tile_to_world,
    inverse: Callable[[float, float, Mapping[str, Any]], tuple[int, int]] = world_to_tile,
) -> dict[str, Any]:
    """Run round-trip proof and reject an injected broken inverse/offset."""

    validate_metrics(metrics)
    failures: list[dict[str, Any]] = []
    for origin in ("TOP_LEFT", "CENTER"):
        for orientation in ("Y_DOWN", "Y_UP"):
            candidate = dict(metrics)
            candidate.update({"origin": origin, "grid_orientation": orientation})
            for x, y in coordinates:
                world = forward(x, y, candidate)
                observed = inverse(world[0], world[1], candidate)
                if observed != (x, y):
                    failures.append({"origin": origin, "grid_orientation": orientation, "coordinate": [x, y], "observed": list(observed)})
    _require(not failures, "GRID_ORIGIN_ROUNDTRIP_FAILED", str(failures))
    return {"status": "GRID_ORIGIN_ROUNDTRIPS_VALID", "coordinates": [list(item) for item in coordinates]}


__all__ = [
    "EnvironmentTileRegistry",
    "EnvironmentTilesetContractError",
    "ProductionRoutingPolicy",
    "SCHEMA_VERSION",
    "recompute_manifest_provenance",
    "validate_autotile_matrix",
    "validate_origin_roundtrips",
    "validate_origin_semantics",
    "validate_production_tileset_candidate",
]
