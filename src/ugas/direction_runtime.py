"""Deterministic, fail-closed direction selection for animation assets.

The runtime deliberately separates direction identity from artwork coverage.  A
direction can be normalized and addressed before an asset exists, but missing
production coverage never silently becomes a mirror or another direction.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from typing import Any, Iterable, Mapping


class DirectionRuntimeError(ValueError):
    """Base error for malformed direction contracts or manifests."""


class DirectionManifestError(DirectionRuntimeError):
    """Raised when a coverage manifest is ambiguous or internally invalid."""


CANONICAL_DIRECTIONS = (
    "south",
    "south_east",
    "east",
    "north_east",
    "north",
    "north_west",
    "west",
    "south_west",
)

_TEXT_SUFFIXES = {".json", ".md", ".txt", ".py", ".toml", ".js", ".html", ".css"}
_SUPPORTED_MANIFEST_VERSIONS = {"0.16.0", "0.16.1"}


def _provenance_digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.casefold() in _TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()

# Screen-space convention: +x is east/right and +y is south/down.  The sector
# table is ordered clockwise from east and uses half-open [lower, upper) bins.
_SECTOR_ORDER = ("east", "south_east", "south", "south_west", "west", "north_west", "north", "north_east")
_SECTOR_CENTERS = {direction: index * 45 for index, direction in enumerate(_SECTOR_ORDER)}

ALIASES = {
    "front": "south",
    "down": "south",
    "s": "south",
    "front_right": "south_east",
    "front-right": "south_east",
    "southeast": "south_east",
    "se": "south_east",
    "right": "east",
    "e": "east",
    "back_right": "north_east",
    "back-right": "north_east",
    "northeast": "north_east",
    "ne": "north_east",
    "back": "north",
    "up": "north",
    "n": "north",
    "back_left": "north_west",
    "back-left": "north_west",
    "northwest": "north_west",
    "nw": "north_west",
    "left": "west",
    "w": "west",
    "front_left": "south_west",
    "front-left": "south_west",
    "southwest": "south_west",
    "sw": "south_west",
}


def _token(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def canonicalize_direction(value: Any) -> str | None:
    """Canonicalize a direction identifier; return ``None`` for unknown input."""
    if not isinstance(value, str):
        return None
    token = _token(value)
    if token in CANONICAL_DIRECTIONS:
        return token
    return ALIASES.get(token)


def quantize_vector(dx: float, dy: float) -> str | None:
    """Quantize a vector with deterministic 45-degree sectors.

    Zero, non-finite and non-numeric vectors are explicit unresolved input.  At
    an exact boundary the upper clockwise sector wins, e.g. +22.5 degrees is
    ``south_east`` under the screen-space convention documented above.
    """
    if not _is_numeric_component(dx) or not _is_numeric_component(dy):
        return None
    try:
        x, y = float(dx), float(dy)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or not math.isfinite(y) or (x == 0.0 and y == 0.0):
        return None
    angle = math.degrees(math.atan2(y, x)) % 360.0
    index = int(math.floor((angle + 22.5) / 45.0)) % 8
    return _SECTOR_ORDER[index]


@dataclass(frozen=True)
class DirectionNormalization:
    """Auditable result of normalizing a direction identifier or vector."""

    direction: str | None
    outcome: str
    error_code: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"direction": self.direction, "outcome": self.outcome, "error_code": self.error_code}


def _is_numeric_component(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _normalize_vector(dx: Any, dy: Any, retained_facing: Any) -> DirectionNormalization:
    """Normalize a present vector without allowing invalid input to retain facing."""
    if not _is_numeric_component(dx) or not _is_numeric_component(dy):
        return DirectionNormalization(None, "INVALID_VECTOR_UNRESOLVED", "INVALID_VECTOR_UNRESOLVED")
    x, y = float(dx), float(dy)
    if not math.isfinite(x) or not math.isfinite(y):
        return DirectionNormalization(None, "INVALID_VECTOR_UNRESOLVED", "INVALID_VECTOR_UNRESOLVED")
    if x == 0.0 and y == 0.0:
        retained = canonicalize_direction(retained_facing)
        if retained is not None:
            return DirectionNormalization(retained, "ZERO_VECTOR_RETAINED_FACING", None)
        return DirectionNormalization(None, "ZERO_VECTOR_UNRESOLVED", "DIRECTION_UNRESOLVED")
    return DirectionNormalization(quantize_vector(x, y), "VECTOR_QUANTIZED", None)


def normalize_direction_result(value: Any, retained_facing: Any = None) -> DirectionNormalization:
    """Return a typed normalization outcome, including invalid-vector rejection."""
    if isinstance(value, Mapping):
        has_dx = "dx" in value
        has_dy = "dy" in value
        has_x = "x" in value
        has_y = "y" in value
        if has_dx or has_dy:
            if not (has_dx and has_dy):
                return DirectionNormalization(None, "INVALID_VECTOR_UNRESOLVED", "INVALID_VECTOR_UNRESOLVED")
            return _normalize_vector(value["dx"], value["dy"], retained_facing)
        if has_x or has_y:
            if not (has_x and has_y):
                return DirectionNormalization(None, "INVALID_VECTOR_UNRESOLVED", "INVALID_VECTOR_UNRESOLVED")
            return _normalize_vector(value["x"], value["y"], retained_facing)
        return DirectionNormalization(None, "INVALID_VECTOR_UNRESOLVED", "INVALID_VECTOR_UNRESOLVED")
    if isinstance(value, (tuple, list)):
        if len(value) != 2:
            return DirectionNormalization(None, "INVALID_VECTOR_UNRESOLVED", "INVALID_VECTOR_UNRESOLVED")
        return _normalize_vector(value[0], value[1], retained_facing)
    if value is None:
        return DirectionNormalization(None, "DIRECTION_UNRESOLVED", "DIRECTION_UNRESOLVED")
    direction = canonicalize_direction(value)
    if direction is None:
        return DirectionNormalization(None, "UNKNOWN_DIRECTION_UNRESOLVED", "DIRECTION_UNRESOLVED")
    return DirectionNormalization(direction, "DIRECTION_ID", None)


def normalize_direction(value: Any, retained_facing: Any = None) -> str | None:
    """Normalize a canonical ID, alias or ``(dx, dy)`` vector.

    A zero vector may use an explicitly supplied retained facing.  Without one
    it returns ``None`` rather than guessing from the previous asset or a
    default direction.
    """
    return normalize_direction_result(value, retained_facing).direction


def direction_contract() -> dict[str, Any]:
    """Return the serializable frozen direction convention."""
    return {
        "coordinate_convention": {"x_positive": "east", "y_positive": "south", "angle_zero": "east", "angle_positive": "clockwise"},
        "canonical_directions": list(CANONICAL_DIRECTIONS),
        "aliases": dict(sorted(ALIASES.items())),
        "sector_order_clockwise_from_east": list(_SECTOR_ORDER),
        "sector_width_degrees": 45,
        "boundary_policy": "lower-inclusive-upper-exclusive-after-22.5-degree-clockwise-offset",
        "zero_vector_policy": "retained_facing_only-or-explicit-unresolved-never-defaults",
        "normalization_outcomes": ["DIRECTION_ID", "VECTOR_QUANTIZED", "ZERO_VECTOR_RETAINED_FACING", "ZERO_VECTOR_UNRESOLVED", "UNKNOWN_DIRECTION_UNRESOLVED", "INVALID_VECTOR_UNRESOLVED"],
        "invalid_vector_policy": "non-finite-non-numeric-missing-components-and-malformed-tuples-never-use-retained-facing",
    }


@dataclass(frozen=True)
class DirectionResolution:
    requested_direction: str | None
    resolved_direction: str | None
    asset_id: str | None
    path: str | None
    provenance_hash: str | None
    fallback_mode: str
    mirror_mode: str
    capability_id: str
    variant: str
    asset_revision_id: str | None
    cache_key: str
    error_code: str | None
    production_safe: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_direction": self.requested_direction,
            "resolved_direction": self.resolved_direction,
            "asset_id": self.asset_id,
            "path": self.path,
            "provenance_hash": self.provenance_hash,
            "fallback_mode": self.fallback_mode,
            "mirror_mode": self.mirror_mode,
            "capability_id": self.capability_id,
            "variant": self.variant,
            "asset_revision_id": self.asset_revision_id,
            "cache_key": self.cache_key,
            "error_code": self.error_code,
            "production_safe": self.production_safe,
        }


def _cache_key(capability_id: str, direction: str | None, variant: str, asset_revision_id: str | None, *, mode: str) -> str:
    return "|".join((capability_id, direction or "UNRESOLVED", variant, asset_revision_id or "ANY", mode))


class DirectionResolver:
    """Resolve direction-aware assets from a declarative coverage manifest."""

    def __init__(self, assets: Iterable[Mapping[str, Any]], *, mirror_pairs: Mapping[str, str] | None = None, production_registry: bool = True):
        self._assets: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self._mirror_pairs = {canonicalize_direction(k): canonicalize_direction(v) for k, v in (mirror_pairs or {}).items()}
        self.production_registry = production_registry
        self._cache: dict[str, DirectionResolution] = {}
        for raw in assets:
            item = dict(raw)
            capability = str(item.get("capability_id", ""))
            direction = canonicalize_direction(item.get("direction"))
            variant = str(item.get("variant", ""))
            revision = str(item.get("asset_revision_id", ""))
            if not capability or direction is None or not variant or not revision:
                raise DirectionManifestError("asset_identity_fields_required")
            if item.get("test_only") and production_registry:
                raise DirectionManifestError("test_only_fixture_cannot_enter_production_registry")
            if item.get("direction") != direction:
                raise DirectionManifestError("asset_direction_must_be_canonical")
            metadata = item.get("metadata")
            if not isinstance(metadata, Mapping) or metadata.get("capability_id") != capability or metadata.get("direction") != direction or metadata.get("asset_revision_id") != revision:
                raise DirectionManifestError("capability_and_direction_match_asset_metadata")
            key = (capability, direction, variant, revision)
            if key in self._assets:
                raise DirectionManifestError("duplicate_direction_asset_key")
            self._assets[key] = item

    @classmethod
    def from_manifest(cls, path: Path, *, production_registry: bool = True) -> "DirectionResolver":
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if value.get("schema_version") not in _SUPPORTED_MANIFEST_VERSIONS:
            raise DirectionManifestError("direction_manifest_version_invalid")
        return cls(value.get("assets", []), mirror_pairs=value.get("mirror_pairs", {}), production_registry=production_registry)

    def cache_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._cache))

    def clear_cache(self) -> None:
        self._cache.clear()

    def _result(self, *, requested: str | None, resolved: str | None, item: Mapping[str, Any] | None, capability_id: str, variant: str, revision: str | None, fallback_mode: str, mirror_mode: str, cache_key: str, error_code: str | None, production_safe: bool) -> DirectionResolution:
        return DirectionResolution(requested, resolved, item.get("asset_id") if item else None, item.get("path") if item else None, item.get("provenance_hash") if item else None, fallback_mode, mirror_mode, capability_id, variant, revision, cache_key, error_code, production_safe)

    def resolve(self, capability_id: str, direction: Any, *, variant: str = "default", asset_revision_id: str | None = None, retained_facing: Any = None, allow_preview_fallback: bool = False, allow_mirror: bool = False) -> DirectionResolution:
        normalization = normalize_direction_result(direction, retained_facing)
        requested = normalization.direction
        mode = "production" if not allow_preview_fallback and not allow_mirror else f"preview:{int(allow_preview_fallback)}:{int(allow_mirror)}"
        key = _cache_key(str(capability_id), requested, str(variant), asset_revision_id, mode=mode)
        if key in self._cache:
            return self._cache[key]
        if requested is None:
            unresolved_mode = "INVALID_VECTOR_UNRESOLVED" if normalization.outcome == "INVALID_VECTOR_UNRESOLVED" else "UNRESOLVED"
            result = self._result(requested=None, resolved=None, item=None, capability_id=str(capability_id), variant=str(variant), revision=asset_revision_id, fallback_mode=unresolved_mode, mirror_mode="NONE", cache_key=key, error_code=normalization.error_code or "DIRECTION_UNRESOLVED", production_safe=False)
            self._cache[key] = result
            return result

        candidates = [item for (cap, direct, item_variant, revision), item in self._assets.items() if cap == str(capability_id) and direct == requested and item_variant == str(variant) and (asset_revision_id is None or revision == asset_revision_id)]
        if len(candidates) == 1:
            item = candidates[0]
            result = self._result(requested=requested, resolved=requested, item=item, capability_id=str(capability_id), variant=str(variant), revision=str(item["asset_revision_id"]), fallback_mode="NONE", mirror_mode="NONE", cache_key=key, error_code=None, production_safe=self.production_registry and item.get("test_only") is not True)
            self._cache[key] = result
            return result
        if len(candidates) > 1:
            result = self._result(requested=requested, resolved=None, item=None, capability_id=str(capability_id), variant=str(variant), revision=asset_revision_id, fallback_mode="FAIL_CLOSED", mirror_mode="NONE", cache_key=key, error_code="DIRECTION_ASSET_AMBIGUOUS", production_safe=False)
            self._cache[key] = result
            return result

        if allow_mirror:
            source_direction = self._mirror_pairs.get(requested)
            mirror_candidates = [item for (cap, direct, item_variant, revision), item in self._assets.items() if cap == str(capability_id) and direct == source_direction and item_variant == str(variant) and (asset_revision_id is None or revision == asset_revision_id) and item.get("mirror_safe") is True and item.get("mirror_pair") == requested]
            if len(mirror_candidates) == 1:
                item = mirror_candidates[0]
                result = self._result(requested=requested, resolved=source_direction, item=item, capability_id=str(capability_id), variant=str(variant), revision=str(item["asset_revision_id"]), fallback_mode="EXPLICIT_PREVIEW_MIRROR", mirror_mode="HORIZONTAL_EXPLICIT", cache_key=key, error_code=None, production_safe=False)
                self._cache[key] = result
                return result

        if allow_preview_fallback:
            fallback = [item for (cap, direct, item_variant, revision), item in self._assets.items() if cap == str(capability_id) and direct == "south" and item_variant == str(variant) and (asset_revision_id is None or revision == asset_revision_id)]
            if len(fallback) == 1:
                item = fallback[0]
                result = self._result(requested=requested, resolved="south", item=item, capability_id=str(capability_id), variant=str(variant), revision=str(item["asset_revision_id"]), fallback_mode="EXPLICIT_PREVIEW_FALLBACK", mirror_mode="NONE", cache_key=key, error_code=None, production_safe=False)
                self._cache[key] = result
                return result

        result = self._result(requested=requested, resolved=None, item=None, capability_id=str(capability_id), variant=str(variant), revision=asset_revision_id, fallback_mode="FAIL_CLOSED", mirror_mode="NONE", cache_key=key, error_code="DIRECTION_ASSET_UNAVAILABLE", production_safe=False)
        self._cache[key] = result
        return result


def validate_coverage_manifest(path: Path, root: Path) -> dict[str, Any]:
    """Validate manifest identity, file hashes and production/test separation."""
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    failures: list[str] = []
    if value.get("schema_version") not in _SUPPORTED_MANIFEST_VERSIONS:
        failures.append("schema_version")
    if value.get("production_registry") is not True:
        failures.append("production_registry_must_be_true")
    seen: set[tuple[str, str, str, str]] = set()
    for item in value.get("assets", []):
        direct = canonicalize_direction(item.get("direction"))
        identity = (str(item.get("capability_id")), str(direct), str(item.get("variant")), str(item.get("asset_revision_id")))
        if identity in seen:
            failures.append(f"duplicate:{identity}")
        seen.add(identity)
        if direct != item.get("direction"):
            failures.append(f"noncanonical:{identity}")
        metadata = item.get("metadata", {})
        if any(metadata.get(k) != item.get(k) for k in ("capability_id", "direction", "variant", "asset_revision_id")):
            failures.append(f"metadata:{identity}")
        if item.get("test_only") is True:
            failures.append(f"test_fixture_in_production:{identity}")
        target = root / str(item.get("path", ""))
        if not target.is_file():
            failures.append(f"missing:{item.get('path')}")
        else:
            digest = _provenance_digest(target)
            if digest != item.get("provenance_hash"):
                failures.append(f"hash:{item.get('path')}")
    return {"status": "DIRECTION_COVERAGE_MANIFEST_PASSED" if not failures else "DIRECTION_COVERAGE_MANIFEST_FAILED", "failures": failures, "asset_count": len(value.get("assets", [])), "production_direction_coverage": sorted({item.get("direction") for item in value.get("assets", [])}), "test_only_fixture_present": any(item.get("test_only") is True for item in value.get("assets", []))}
