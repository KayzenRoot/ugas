"""Fail-closed VFX asset-family contracts for correction v0.23.1.

This module is deliberately independent from the v0.23.0 evidence producer.
It renders deterministic TEST_ONLY fixtures, but every semantic, pixel,
lifecycle, budget, fallback, cache and provenance claim is validated from the
runtime record itself.  It never routes a production asset or generation job.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping

from PIL import Image, ImageDraw, ImageFont

from . import vfx_asset_family_runtime_v0230 as legacy


VERSION = "0.23.1"
FAMILY_ID = "vfx_asset_family"
BASE_MAIN_SHA = "b08b9c3df74ef6a23046be396289e2fd72dc336b"
REJECTED_REVIEWED_HEAD = "c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72"
REGISTRY_MODE = "TEST_ONLY"
PRODUCTION_ROUTING = "BLOCKED"
EFFECT_CLASSES = legacy.EFFECT_CLASSES
BLEND_MODES = legacy.BLEND_MODES
ALPHA_MODES = legacy.ALPHA_MODES
SPACES = legacy.SPACES
REPRESENTATIONS = legacy.REPRESENTATIONS
READ_ONLY = legacy.READ_ONLY


class VFXAssetFamilyContractError(ValueError):
    def __init__(self, rejection_class: str, detail: str = "") -> None:
        self.rejection_class = rejection_class
        self.detail = detail
        super().__init__(f"{rejection_class}: {detail}" if detail else rejection_class)


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _require(condition: bool, rejection_class: str, detail: str) -> None:
    if not condition:
        raise VFXAssetFamilyContractError(rejection_class, detail)


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _positive(value: Any) -> bool:
    return _finite(value) and float(value) > 0


def _vector(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(_finite(item) for item in value)


def _spec(effect_class: str, *, stable_id: str, lifecycle: str, frame_count: int,
          duration_ms: int, representations: tuple[str, ...], space: str,
          anchor_kind: str, direction_policy: str, blend_mode: str,
          fallback: tuple[str, ...], semantic_role: str,
          required_semantics: tuple[str, ...]) -> dict[str, Any]:
    return {
        "effect_class": effect_class, "stable_id": stable_id,
        "lifecycle": lifecycle, "frame_count": frame_count,
        "duration_ms": duration_ms, "representations": list(representations),
        "space": space, "anchor_kind": anchor_kind,
        "direction_policy": direction_policy, "blend_mode": blend_mode,
        "alpha_mode": "STRAIGHT",  # the renderer emits straight-alpha bytes
        "fallback": list(fallback), "semantic_role": semantic_role,
        "required_semantics": list(required_semantics),
    }


CLASS_SPECS: dict[str, dict[str, Any]] = {
    "impact_burst": _spec("impact_burst", stable_id="VFX-CLS-IMPACT-BURST", lifecycle="ONE_SHOT", frame_count=6, duration_ms=240, representations=("SPRITE_SEQUENCE", "SPRITE_SHEET"), space="WORLD", anchor_kind="IMPACT_POINT", direction_policy="RADIAL", blend_mode="ADDITIVE", fallback=("REDUCE_FRAME_COUNT", "REDUCE_LAYER_COUNT", "REDUCE_VISUAL_AREA", "SKIP_VISUAL"), semantic_role="short readable impact response", required_semantics=("impact_origin", "radius_curve", "termination")),
    "weapon_arc": _spec("weapon_arc", stable_id="VFX-CLS-WEAPON-ARC", lifecycle="ONE_SHOT", frame_count=5, duration_ms=200, representations=("SPRITE_SEQUENCE", "SPRITE_SHEET"), space="ENTITY_ANCHOR", anchor_kind="WEAPON_SWEEP", direction_policy="EXPLICIT_FACING", blend_mode="ALPHA", fallback=("REDUCE_OPACITY", "REDUCE_FRAME_COUNT", "REDUCE_VISUAL_AREA", "SKIP_VISUAL"), semantic_role="directional weapon sweep accent", required_semantics=("weapon_anchor", "facing", "arc_span_degrees", "termination")),
    "projectile_trail": _spec("projectile_trail", stable_id="VFX-CLS-PROJECTILE-TRAIL", lifecycle="OWNER_BOUND_LOOP", frame_count=8, duration_ms=640, representations=("SPRITE_SEQUENCE", "PARTICLE_RECIPE"), space="ENTITY_ANCHOR", anchor_kind="PROJECTILE_OWNER", direction_policy="VELOCITY_VECTOR", blend_mode="ADDITIVE", fallback=("REDUCE_PARTICLE_COUNT", "REDUCE_LAYER_COUNT", "REDUCE_SPAWN_RATE", "REDUCE_VISUAL_AREA", "SKIP_VISUAL"), semantic_role="bounded projectile motion trail", required_semantics=("owner_anchor", "velocity_vector", "max_lifetime_ms", "termination")),
    "projectile_impact": _spec("projectile_impact", stable_id="VFX-CLS-PROJECTILE-IMPACT", lifecycle="ONE_SHOT", frame_count=5, duration_ms=200, representations=("SPRITE_SEQUENCE", "PARTICLE_RECIPE"), space="WORLD", anchor_kind="IMPACT_POINT", direction_policy="RADIAL", blend_mode="ADDITIVE", fallback=("REDUCE_PARTICLE_COUNT", "REDUCE_OPACITY", "REDUCE_VISUAL_AREA", "SKIP_VISUAL"), semantic_role="projectile arrival accent", required_semantics=("impact_origin", "projectile_type", "termination")),
    "cast_charge": _spec("cast_charge", stable_id="VFX-CLS-CAST-CHARGE", lifecycle="OWNER_BOUND_LOOP", frame_count=8, duration_ms=800, representations=("SPRITE_SEQUENCE", "SPRITE_SHEET"), space="ENTITY_ANCHOR", anchor_kind="CASTER", direction_policy="EXPLICIT_FACING", blend_mode="ALPHA", fallback=("REDUCE_RADIUS", "REDUCE_LAYER_COUNT", "REDUCE_VISUAL_AREA", "SKIP_VISUAL"), semantic_role="bounded charge-up readability", required_semantics=("caster_anchor", "charge_phase", "termination")),
    "persistent_aura": _spec("persistent_aura", stable_id="VFX-CLS-PERSISTENT-AURA", lifecycle="OWNER_BOUND_LOOP", frame_count=8, duration_ms=960, representations=("SPRITE_SEQUENCE", "PARTICLE_RECIPE"), space="ENTITY_ANCHOR", anchor_kind="AURA_OWNER", direction_policy="NONE", blend_mode="ADDITIVE", fallback=("REDUCE_PARTICLE_COUNT", "REDUCE_RADIUS", "REDUCE_VISUAL_AREA", "SKIP_VISUAL"), semantic_role="persistent owner-bound aura", required_semantics=("owner_anchor", "aura_radius", "termination_condition")),
    "area_telegraph": _spec("area_telegraph", stable_id="VFX-CLS-AREA-TELEGRAPH", lifecycle="OWNER_BOUND_LOOP", frame_count=8, duration_ms=1200, representations=("SPRITE_SEQUENCE", "SPRITE_SHEET"), space="WORLD", anchor_kind="AREA_ORIGIN", direction_policy="NONE", blend_mode="ALPHA", fallback=("REDUCE_OPACITY", "REDUCE_LAYER_COUNT", "REDUCE_SPAWN_RATE", "REDUCE_VISUAL_AREA", "SKIP_VISUAL"), semantic_role="read-only area warning", required_semantics=("area_origin", "shape", "duration_ms", "termination")),
    "status_loop": _spec("status_loop", stable_id="VFX-CLS-STATUS-LOOP", lifecycle="OWNER_BOUND_LOOP", frame_count=8, duration_ms=960, representations=("SPRITE_SEQUENCE", "PARTICLE_RECIPE"), space="ENTITY_ANCHOR", anchor_kind="STATUS_OWNER", direction_policy="NONE", blend_mode="ALPHA", fallback=("REDUCE_PARTICLE_COUNT", "REDUCE_OPACITY", "REDUCE_VISUAL_AREA", "SKIP_VISUAL"), semantic_role="owner-bound status readability", required_semantics=("owner_anchor", "status_kind", "termination_condition")),
    "buff_heal_burst": _spec("buff_heal_burst", stable_id="VFX-CLS-BUFF-HEAL-BURST", lifecycle="ONE_SHOT", frame_count=6, duration_ms=300, representations=("SPRITE_SEQUENCE", "SPRITE_SHEET"), space="ENTITY_ANCHOR", anchor_kind="TARGET_ENTITY", direction_policy="RADIAL", blend_mode="ADDITIVE", fallback=("REDUCE_OPACITY", "REDUCE_FRAME_COUNT", "REDUCE_VISUAL_AREA", "SKIP_VISUAL"), semantic_role="positive buff or heal feedback", required_semantics=("target_anchor", "feedback_kind", "termination")),
    "environment_ambient": _spec("environment_ambient", stable_id="VFX-CLS-ENVIRONMENT-AMBIENT", lifecycle="OWNER_BOUND_LOOP", frame_count=8, duration_ms=1600, representations=("SPRITE_SEQUENCE", "PARTICLE_RECIPE"), space="WORLD", anchor_kind="AMBIENT_REGION", direction_policy="NONE", blend_mode="ALPHA", fallback=("REDUCE_PARTICLE_COUNT", "REDUCE_LAYER_COUNT", "REDUCE_SPAWN_RATE", "REDUCE_VISUAL_AREA", "SKIP_VISUAL"), semantic_role="bounded environment atmosphere", required_semantics=("ambient_region", "seed", "termination_condition")),
}

# Every class has an explicit escape for both dimensions that a constrained
# runtime may report.  The class-specific order remains authoritative.
for _class_spec in CLASS_SPECS.values():
    _steps = _class_spec["fallback"]
    if "REDUCE_SPAWN_RATE" not in _steps:
        _steps.insert(-1, "REDUCE_SPAWN_RATE")
    if "REDUCE_VISUAL_AREA" not in _steps:
        _steps.insert(-1, "REDUCE_VISUAL_AREA")

SEMANTIC_SCHEMAS: dict[str, dict[str, Any]] = {
    "impact_burst": {"impact_origin": _vector, "radius_curve": lambda v: isinstance(v, list) and len(v) == 3 and all(_finite(x) and float(x) >= 0 for x in v), "termination": lambda v: v in {"FRAME_END", "OWNER_OR_EVENT_TERMINATION"}},
    "weapon_arc": {"weapon_anchor": lambda v: isinstance(v, str) and bool(v), "facing": lambda v: v in {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}, "arc_span_degrees": lambda v: _finite(v) and 15 <= float(v) <= 360, "termination": lambda v: v == "FRAME_END"},
    "projectile_trail": {"owner_anchor": lambda v: isinstance(v, str) and bool(v), "velocity_vector": _vector, "max_lifetime_ms": lambda v: _positive(v) and float(v) <= 5000, "termination": lambda v: v == "OWNER_OR_EVENT_TERMINATION"},
    "projectile_impact": {"impact_origin": _vector, "projectile_type": lambda v: v in {"ARROW", "BOLT", "ORB"}, "termination": lambda v: v == "FRAME_END"},
    "cast_charge": {"caster_anchor": lambda v: isinstance(v, str) and bool(v), "charge_phase": lambda v: v in {"START", "MID", "READY"}, "termination": lambda v: v == "OWNER_OR_EVENT_TERMINATION"},
    "persistent_aura": {"owner_anchor": lambda v: isinstance(v, str) and bool(v), "aura_radius": lambda v: _positive(v) and float(v) <= 12, "termination_condition": lambda v: v == "OWNER_DESPAWN_OR_EVENT"},
    "area_telegraph": {"area_origin": _vector, "shape": lambda v: v in {"CIRCLE", "RECTANGLE"}, "duration_ms": lambda v: isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 10000, "termination": lambda v: v == "OWNER_OR_EVENT_TERMINATION"},
    "status_loop": {"owner_anchor": lambda v: isinstance(v, str) and bool(v), "status_kind": lambda v: v in {"POISON", "FROST", "HASTE", "SHIELD"}, "termination_condition": lambda v: v == "OWNER_DESPAWN_OR_EVENT"},
    "buff_heal_burst": {"target_anchor": lambda v: isinstance(v, str) and bool(v), "feedback_kind": lambda v: v in {"BUFF", "HEAL", "CLEANSE"}, "termination": lambda v: v == "FRAME_END"},
    "environment_ambient": {"ambient_region": lambda v: isinstance(v, str) and bool(v), "seed": lambda v: isinstance(v, int) and not isinstance(v, bool) and v >= 0, "termination_condition": lambda v: v == "OWNER_DESPAWN_OR_EVENT"},
}

_FORBIDDEN_GAMEPLAY_TOKENS = {"damage", "damage_amount", "heal", "heal_amount", "hit_success", "crit_result", "gameplay_outcome", "combat_power", "economy_value"}


def _authority_identity() -> dict[str, str]:
    payload = {"authority_type": "VFX_RUNTIME_CONTRACT", "path": "src/ugas/vfx_asset_family_runtime_v0231.py", "revision": VERSION}
    return {**payload, "sha256": sha256_bytes(canonical_json(payload))}


def _budget_authority() -> dict[str, Any]:
    return {"profile_id": "vfx-runtime-safe-v2", "max_concurrent_effects": 64, "max_layers_per_effect": 4, "max_spawn_events_per_second": 120, "max_particles_per_effect": 96, "max_visual_area_ratio": 0.80}


DEFAULT_BUDGETS = {**_budget_authority(), "authority_sha256": sha256_bytes(canonical_json(_budget_authority()))}


def _walk_forbidden(value: Any, path: str = "") -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _FORBIDDEN_GAMEPLAY_TOKENS or any(token in normalized for token in ("damage", "heal_amount", "hit_success", "crit_result")):
                return f"{path}.{key}" if path else str(key)
            found = _walk_forbidden(child, f"{path}.{key}" if path else str(key))
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _walk_forbidden(child, f"{path}[{index}]")
            if found:
                return found
    return None


def _semantic_input(effect_class: str, index: int) -> dict[str, Any]:
    values: dict[str, dict[str, Any]] = {
        "impact_burst": {"impact_origin": [0.0, 0.0], "radius_curve": [0.25, 0.7, 1.0], "termination": "FRAME_END"},
        "weapon_arc": {"weapon_anchor": "weapon.fixture", "facing": "E", "arc_span_degrees": 110.0, "termination": "FRAME_END"},
        "projectile_trail": {"owner_anchor": "projectile.fixture", "velocity_vector": [4.0, 0.0], "max_lifetime_ms": 640.0, "termination": "OWNER_OR_EVENT_TERMINATION"},
        "projectile_impact": {"impact_origin": [3.0, -1.0], "projectile_type": "BOLT", "termination": "FRAME_END"},
        "cast_charge": {"caster_anchor": "caster.fixture", "charge_phase": "MID", "termination": "OWNER_OR_EVENT_TERMINATION"},
        "persistent_aura": {"owner_anchor": "aura-owner.fixture", "aura_radius": 3.5, "termination_condition": "OWNER_DESPAWN_OR_EVENT"},
        "area_telegraph": {"area_origin": [2.0, 2.0], "shape": "CIRCLE", "duration_ms": 1200, "termination": "OWNER_OR_EVENT_TERMINATION"},
        "status_loop": {"owner_anchor": "status-owner.fixture", "status_kind": "FROST", "termination_condition": "OWNER_DESPAWN_OR_EVENT"},
        "buff_heal_burst": {"target_anchor": "target.fixture", "feedback_kind": "HEAL", "termination": "FRAME_END"},
        "environment_ambient": {"ambient_region": "forest.fixture", "seed": 23001 + index, "termination_condition": "OWNER_DESPAWN_OR_EVENT"},
    }
    spec = CLASS_SPECS[effect_class]
    return {"effect_id": f"vfx-test-{effect_class}-v0231", "effect_class": effect_class, "semantic_revision": VERSION, "intent": "VISUAL_ONLY", "readability_role": spec["semantic_role"], "semantics": {**values[effect_class], "fixture_index": index, "fixture_seed": 23100 + index, "visual_only": True, "gameplay_authority": "NONE"}, "registry_mode": REGISTRY_MODE}


def validate_semantic_input(record: Mapping[str, Any]) -> None:
    effect_class = str(record.get("effect_class"))
    semantic = record.get("semantic_input")
    _require(isinstance(semantic, Mapping) and semantic.get("effect_class") == effect_class and semantic.get("intent") == "VISUAL_ONLY", "VFX_SEMANTIC_CLASS_INVALID", str(record.get("effect_id")))
    forbidden = _walk_forbidden(semantic)
    _require(forbidden is None, "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN", forbidden or str(record.get("effect_id")))
    semantics = semantic.get("semantics")
    schema = SEMANTIC_SCHEMAS.get(effect_class)
    _require(isinstance(semantics, Mapping) and isinstance(schema, Mapping), "VFX_SEMANTIC_CLASS_INVALID", effect_class)
    _require(semantics.get("gameplay_authority") == "NONE" and semantics.get("visual_only") is True, "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN", effect_class)
    for key, checker in schema.items():
        _require(key in semantics and checker(semantics[key]), "VFX_SEMANTIC_TYPE_INVALID", f"{effect_class}.{key}")


def validate_class_spec_table() -> None:
    _require(tuple(CLASS_SPECS) == EFFECT_CLASSES, "VFX_CLASS_TABLE_INVALID", "class order or class set changed")
    _require(len({spec["stable_id"] for spec in CLASS_SPECS.values()}) == len(EFFECT_CLASSES), "VFX_CLASS_ID_DUPLICATE", "stable ids")
    for effect_class, spec in CLASS_SPECS.items():
        _require(spec["effect_class"] == effect_class and spec["lifecycle"] in {"ONE_SHOT", "OWNER_BOUND_LOOP"}, "VFX_CLASS_IDENTITY_INVALID", effect_class)
        _require(isinstance(spec["frame_count"], int) and spec["frame_count"] >= 4 and isinstance(spec["duration_ms"], int) and spec["duration_ms"] > 0, "VFX_TIMING_INVALID", effect_class)
        _require(set(spec["representations"]).issubset(REPRESENTATIONS) and spec["space"] in SPACES and spec["blend_mode"] in BLEND_MODES and spec["alpha_mode"] == "STRAIGHT", "VFX_CLASS_SPEC_INVALID", effect_class)
        _require(spec["fallback"][-1] == "SKIP_VISUAL", "VFX_FALLBACK_INVALID", effect_class)


def _frame_metadata(path: Path, index: int, duration_ms: int) -> dict[str, Any]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        alpha_min, alpha_max = rgba.getchannel("A").getextrema()
    return {"index": index, "path": path.as_posix(), "sha256": sha256_file(path), "width": 96, "height": 96, "alpha_range": [alpha_min, alpha_max], "duration_ms": duration_ms}


def build_effect_fixture(effect_class: str, output_root: Path, index: int = 0) -> dict[str, Any]:
    validate_class_spec_table()
    _require(effect_class in CLASS_SPECS, "VFX_EFFECT_CLASS_UNKNOWN", effect_class)
    spec = CLASS_SPECS[effect_class]
    semantic = _semantic_input(effect_class, index)
    authority = _authority_identity()
    frames_dir = output_root / "frames" / effect_class
    frames_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, Any]] = []
    for frame_index in range(spec["frame_count"]):
        path = frames_dir / f"{frame_index:02d}.png"
        legacy._draw_fixture(effect_class, frame_index, spec["frame_count"]).save(path, format="PNG", optimize=False, compress_level=9)
        metadata = _frame_metadata(path, frame_index, spec["duration_ms"] // spec["frame_count"])
        metadata["path"] = path.relative_to(output_root).as_posix()
        frames.append(metadata)
    frame_set_hash = sha256_bytes(canonical_json([item["sha256"] for item in frames]))
    content_hash = sha256_bytes(canonical_json({"effect_id": semantic["effect_id"], "frame_set_hash": frame_set_hash, "frames": frames}))
    is_loop = spec["lifecycle"] == "OWNER_BOUND_LOOP"
    lifecycle = {"mode": spec["lifecycle"], "frame_count": spec["frame_count"], "duration_ms": spec["duration_ms"], "frame_duration_ms": spec["duration_ms"] // spec["frame_count"], "loop": is_loop, "loop_period_ms": spec["duration_ms"] if is_loop else None, "max_concurrent_instances": 2 if is_loop else 1, "owner_termination": "OWNER_DESPAWN_OR_EVENT" if is_loop else None, "safety_termination": "HARD_LIFETIME" if is_loop else "FRAME_END", "termination": "OWNER_OR_EVENT_TERMINATION" if is_loop else "FRAME_END", "max_lifetime_ms": spec["duration_ms"]}
    budget = {**DEFAULT_BUDGETS, "max_concurrent_instances": 2 if is_loop else 1, "max_layers": 3 if is_loop else 2, "max_spawn_events_per_second": 30 if is_loop else 12, "max_particles_per_instance": 48 if is_loop else 24, "max_visual_area_ratio": 0.60 if is_loop else 0.45}
    spatial = {"space": spec["space"], "anchor": {"kind": spec["anchor_kind"], "id": f"anchor-{effect_class}-fixture", "read_only": True}, "pivot": [0.5, 0.5], "direction_policy": spec["direction_policy"], "bounds_policy": "DECLARED_AND_BOUNDED", "max_visual_area_ratio": budget["max_visual_area_ratio"]}
    blend = {"blend_mode": spec["blend_mode"], "alpha_mode": "STRAIGHT", "premultiplied": False, "opacity_range": [0.0, 1.0], "pixel_proof": "DECODED_RGBA_FRAME_PIXELS"}
    fallback = {"ordered_steps": spec["fallback"], "deterministic": True, "changes_gameplay": False, "preserves_intent": True, "profile_selection": "DETERMINISTIC_CONSTRAINED_PROFILE", "unsupported_steps_rejected": True}
    representation = {"kind": spec["representations"][0], "frame_width": 96, "frame_height": 96, "frame_count": spec["frame_count"], "import_scale": 1.0, "pixel_snap": True, "color_space": "SRGB", "alpha_mode": "STRAIGHT", "premultiplied": False, "decoded_pixel_contract": "STRAIGHT_RGBA"}
    integration = {"mode": READ_ONLY, "authority": authority, "event_binding": {"source": "VFX_LOCAL_EVENT_BUS", "event_id": f"vfx.fixture.{effect_class}", "read_only": True, "gameplay_authoritative": False}, "no_gameplay_mutation": True, "integration_revision": "read-only-v1"}
    record: dict[str, Any] = {"effect_id": semantic["effect_id"], "family_id": FAMILY_ID, "schema_version": VERSION, "effect_class": effect_class, "stable_class_id": spec["stable_id"], "registry_mode": REGISTRY_MODE, "intent": "VISUAL_ONLY", "readability_role": spec["semantic_role"], "semantic_input": semantic, "semantic_input_hash": sha256_bytes(canonical_json(semantic)), "lifecycle": lifecycle, "blend_alpha": blend, "spatial": spatial, "budget_profile": budget, "fallback": fallback, "representation": representation, "integration": integration, "frames": frames, "frame_set_hash": frame_set_hash, "content_hash": content_hash, "authority_identity_hash": authority["sha256"], "test_only": True, "provenance": {"generator": "deterministic-test-fixture-renderer-v0231", "provider": None, "generation_model": None, "seed": 23100 + index, "source": "runtime_contract_fixture", "input_hash": sha256_bytes(canonical_json(semantic)), "output_hash": content_hash, "effective_semantic_hash": "", "production_claim": False}, "semantic_contract": {}, "semantic_contract_hash": "", "cache_key": ""}
    record["semantic_contract"] = build_effective_semantic_payload(record)
    record["semantic_contract_hash"] = sha256_bytes(canonical_json(record["semantic_contract"]))
    record["provenance"]["effective_semantic_hash"] = record["semantic_contract_hash"]
    record["cache_key"] = cache_key_for(record)
    validate_effect_record(record, output_root)
    return record


def build_effective_semantic_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    return {"family_id": record.get("family_id"), "schema_version": record.get("schema_version"), "effect_id": record.get("effect_id"), "effect_class": record.get("effect_class"), "stable_class_id": record.get("stable_class_id"), "intent": record.get("intent"), "semantic_input": record.get("semantic_input"), "lifecycle": record.get("lifecycle"), "blend_alpha": record.get("blend_alpha"), "spatial": record.get("spatial"), "budget_profile": record.get("budget_profile"), "fallback": record.get("fallback"), "representation": record.get("representation"), "integration": record.get("integration"), "authority_identity_hash": record.get("authority_identity_hash"), "frame_set_hash": record.get("frame_set_hash"), "content_hash": record.get("content_hash"), "test_only": record.get("test_only")}


def cache_key_for(record: Mapping[str, Any]) -> str:
    payload = {"semantic_contract": build_effective_semantic_payload(record), "semantic_input_hash": record.get("semantic_input_hash"), "content_hash": record.get("content_hash"), "authority_identity_hash": record.get("authority_identity_hash")}
    return sha256_bytes(canonical_json(payload))


def validate_lifecycle(record: Mapping[str, Any]) -> None:
    spec = CLASS_SPECS.get(str(record.get("effect_class"))); value = record.get("lifecycle")
    _require(spec is not None and isinstance(value, Mapping), "VFX_LIFECYCLE_MISSING", str(record.get("effect_id")))
    is_loop = spec["lifecycle"] == "OWNER_BOUND_LOOP"
    _require(value.get("mode") == spec["lifecycle"] and value.get("frame_count") == spec["frame_count"] and value.get("duration_ms") == spec["duration_ms"], "VFX_TIMING_INVALID", str(record.get("effect_id")))
    _require(value.get("frame_duration_ms") == value["duration_ms"] // value["frame_count"] and value.get("frame_duration_ms") > 0 and value.get("max_lifetime_ms") == value["duration_ms"], "VFX_TIMING_INVALID", str(record.get("effect_id")))
    _require(value.get("loop") is is_loop, "VFX_LOOP_POLICY_INVALID", str(record.get("effect_id")))
    if is_loop:
        _require(_positive(value.get("loop_period_ms")) and value.get("loop_period_ms") <= value.get("max_lifetime_ms"), "VFX_LOOP_PERIOD_INVALID", str(record.get("effect_id")))
        _require(isinstance(value.get("max_concurrent_instances"), int) and value["max_concurrent_instances"] >= 1 and value.get("owner_termination") == "OWNER_DESPAWN_OR_EVENT" and value.get("safety_termination") == "HARD_LIFETIME", "VFX_LOOP_POLICY_INVALID", str(record.get("effect_id")))
    else:
        _require(value.get("loop_period_ms") is None and value.get("max_concurrent_instances") == 1 and value.get("owner_termination") is None and value.get("safety_termination") == "FRAME_END", "VFX_LIFECYCLE_STATE_INVALID", str(record.get("effect_id")))


def validate_blend_alpha(record: Mapping[str, Any]) -> None:
    spec = CLASS_SPECS.get(str(record.get("effect_class"))); value = record.get("blend_alpha")
    _require(spec is not None and isinstance(value, Mapping) and value.get("blend_mode") == spec["blend_mode"] and value.get("alpha_mode") == "STRAIGHT" and value.get("premultiplied") is False and value.get("opacity_range") == [0.0, 1.0] and value.get("pixel_proof") == "DECODED_RGBA_FRAME_PIXELS", "VFX_BLEND_ALPHA_INVALID", str(record.get("effect_id")))


def validate_spatial_anchor(record: Mapping[str, Any]) -> None:
    spec = CLASS_SPECS.get(str(record.get("effect_class"))); value = record.get("spatial")
    _require(spec is not None and isinstance(value, Mapping) and value.get("space") == spec["space"] and value.get("direction_policy") == spec["direction_policy"], "VFX_SPATIAL_CONTRACT_INVALID", str(record.get("effect_id")))
    anchor = value.get("anchor"); pivot = value.get("pivot")
    _require(isinstance(anchor, Mapping) and anchor.get("kind") == spec["anchor_kind"] and anchor.get("id") and anchor.get("read_only") is True, "VFX_ANCHOR_BINDING_INVALID", str(record.get("effect_id")))
    _require(isinstance(pivot, list) and len(pivot) == 2 and all(_finite(x) and 0 <= float(x) <= 1 for x in pivot) and value.get("bounds_policy") == "DECLARED_AND_BOUNDED" and _finite(value.get("max_visual_area_ratio")) and 0 < float(value["max_visual_area_ratio"]) <= 1, "VFX_SPATIAL_CONTRACT_INVALID", str(record.get("effect_id")))


def validate_budget(record: Mapping[str, Any]) -> None:
    value = record.get("budget_profile")
    _require(isinstance(value, Mapping) and value.get("authority_sha256") == DEFAULT_BUDGETS["authority_sha256"], "VFX_BUDGET_AUTHORITY_STALE", str(record.get("effect_id")))
    for key in ("max_concurrent_instances", "max_layers", "max_spawn_events_per_second", "max_particles_per_instance"):
        _require(isinstance(value.get(key), int) and value[key] >= 1, "VFX_BUDGET_INVALID", key)
    _require(_finite(value.get("max_visual_area_ratio")) and 0 < float(value["max_visual_area_ratio"]) <= DEFAULT_BUDGETS["max_visual_area_ratio"], "VFX_BUDGET_EXCEEDED", "max_visual_area_ratio")
    _require(value["max_layers"] <= DEFAULT_BUDGETS["max_layers_per_effect"] and value["max_spawn_events_per_second"] <= DEFAULT_BUDGETS["max_spawn_events_per_second"] and value["max_particles_per_instance"] <= DEFAULT_BUDGETS["max_particles_per_effect"] and value["max_concurrent_instances"] <= DEFAULT_BUDGETS["max_concurrent_effects"], "VFX_BUDGET_EXCEEDED", str(record.get("effect_id")))


def validate_fallback(record: Mapping[str, Any]) -> None:
    spec = CLASS_SPECS.get(str(record.get("effect_class"))); value = record.get("fallback")
    _require(spec is not None and isinstance(value, Mapping) and value.get("ordered_steps") == spec["fallback"] and value.get("deterministic") is True and value.get("changes_gameplay") is False and value.get("preserves_intent") is True and value.get("profile_selection") == "DETERMINISTIC_CONSTRAINED_PROFILE" and value.get("unsupported_steps_rejected") is True, "VFX_FALLBACK_INVALID", str(record.get("effect_id")))


def validate_representation(record: Mapping[str, Any]) -> None:
    spec = CLASS_SPECS.get(str(record.get("effect_class"))); value = record.get("representation")
    _require(spec is not None and isinstance(value, Mapping) and value.get("kind") in spec["representations"] and value.get("frame_width") == 96 and value.get("frame_height") == 96 and value.get("frame_count") == spec["frame_count"], "VFX_REPRESENTATION_INVALID", str(record.get("effect_id")))
    _require(value.get("import_scale") == 1.0 and value.get("pixel_snap") is True and value.get("color_space") == "SRGB" and value.get("alpha_mode") == "STRAIGHT" and value.get("premultiplied") is False and value.get("decoded_pixel_contract") == "STRAIGHT_RGBA", "VFX_IMPORT_METADATA_INVALID", str(record.get("effect_id")))


def validate_integration(record: Mapping[str, Any]) -> None:
    value = record.get("integration"); authority = value.get("authority") if isinstance(value, Mapping) else None; event = value.get("event_binding") if isinstance(value, Mapping) else None
    _require(isinstance(value, Mapping) and value.get("mode") == READ_ONLY and value.get("integration_revision") == "read-only-v1", "VFX_INTEGRATION_MODE_INVALID", str(record.get("effect_id")))
    _require(isinstance(authority, Mapping) and authority.get("authority_type") == "VFX_RUNTIME_CONTRACT" and authority.get("sha256") == _authority_identity()["sha256"], "VFX_INTEGRATION_AUTHORITY_STALE", str(record.get("effect_id")))
    _require(isinstance(event, Mapping) and event.get("read_only") is True and event.get("gameplay_authoritative") is False and event.get("event_id"), "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN", str(record.get("effect_id")))
    _require(value.get("no_gameplay_mutation") is True, "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN", str(record.get("effect_id")))


def validate_decoded_alpha(record: Mapping[str, Any], root: Path) -> None:
    _require(record.get("blend_alpha", {}).get("alpha_mode") == "STRAIGHT", "VFX_ALPHA_PIXEL_MODE_INVALID", str(record.get("effect_id")))
    visible = False
    for frame in record.get("frames", []):
        path = root / Path(str(frame["path"]))
        with Image.open(path) as image:
            for red, green, blue, alpha in image.convert("RGBA").getdata():
                if alpha > 0:
                    visible = True
                    _require(max(red, green, blue) > 0, "VFX_ALPHA_PIXEL_MODE_INVALID", str(path))
    _require(visible, "VFX_ALPHA_PIXEL_MODE_INVALID", str(record.get("effect_id")))


def validate_provenance(record: Mapping[str, Any], root: Path) -> None:
    value = record.get("provenance")
    _require(isinstance(value, Mapping) and value.get("generator") == "deterministic-test-fixture-renderer-v0231" and value.get("provider") is None and value.get("generation_model") is None and value.get("production_claim") is False, "VFX_PROVENANCE_INVALID", str(record.get("effect_id")))
    _require(value.get("input_hash") == record.get("semantic_input_hash") and value.get("output_hash") == record.get("content_hash") and value.get("effective_semantic_hash") == record.get("semantic_contract_hash"), "VFX_PROVENANCE_HASH_INVALID", str(record.get("effect_id")))
    for frame in record.get("frames", []):
        path = root / Path(str(frame["path"]))
        _require(path.is_file() and sha256_file(path) == frame.get("sha256"), "VFX_FRAME_HASH_INVALID", str(path))


def validate_effect_record(record: Mapping[str, Any], root: Path) -> None:
    _require(record.get("family_id") == FAMILY_ID and record.get("schema_version") == VERSION and record.get("registry_mode") == REGISTRY_MODE and record.get("test_only") is True, "VFX_RECORD_IDENTITY_INVALID", str(record.get("effect_id")))
    effect_class = str(record.get("effect_class"))
    _require(effect_class in CLASS_SPECS and record.get("stable_class_id") == CLASS_SPECS[effect_class]["stable_id"], "VFX_CLASS_IDENTITY_INVALID", str(record.get("effect_id")))
    validate_semantic_input(record)
    semantic = record.get("semantic_input")
    _require(record.get("semantic_input_hash") == sha256_bytes(canonical_json(semantic)), "VFX_SEMANTIC_HASH_INVALID", str(record.get("effect_id")))
    validate_lifecycle(record); validate_blend_alpha(record); validate_spatial_anchor(record); validate_budget(record); validate_fallback(record); validate_representation(record); validate_integration(record)
    frame_set_hash = sha256_bytes(canonical_json([item.get("sha256") for item in record.get("frames", [])]))
    _require(frame_set_hash == record.get("frame_set_hash"), "VFX_FRAME_SET_HASH_INVALID", str(record.get("effect_id")))
    content_hash = sha256_bytes(canonical_json({"effect_id": record.get("effect_id"), "frame_set_hash": frame_set_hash, "frames": record.get("frames")}))
    _require(content_hash == record.get("content_hash"), "VFX_CONTENT_HASH_INVALID", str(record.get("effect_id")))
    validate_decoded_alpha(record, root)
    expected_contract = build_effective_semantic_payload(record)
    _require(record.get("semantic_contract") == expected_contract and record.get("semantic_contract_hash") == sha256_bytes(canonical_json(expected_contract)), "VFX_SEMANTIC_CONTRACT_HASH_INVALID", str(record.get("effect_id")))
    _require(record.get("cache_key") == cache_key_for(record), "VFX_CACHE_KEY_INVALID", str(record.get("effect_id")))
    validate_provenance(record, root)


def validate_vfx_manifest(manifest: Mapping[str, Any], root: Path | None = None) -> dict[str, Any]:
    validate_class_spec_table()
    _require(manifest.get("schema_version") == VERSION and manifest.get("family_id") == FAMILY_ID and manifest.get("registry_mode") == REGISTRY_MODE, "VFX_MANIFEST_IDENTITY_INVALID", "manifest")
    records = manifest.get("effects")
    _require(isinstance(records, list) and len(records) == len(EFFECT_CLASSES) and tuple(item.get("effect_class") for item in records) == EFFECT_CLASSES, "VFX_MANIFEST_CLASS_SET_INVALID", "manifest")
    _require(len({item.get("effect_id") for item in records}) == len(records), "VFX_EFFECT_ID_DUPLICATE", "manifest")
    if root is not None:
        for item in records:
            validate_effect_record(item, root)
    return {"status": "VFX_ASSET_FAMILY_MANIFEST_VALID", "effect_count": len(records), "classes": list(EFFECT_CLASSES)}


def validate_production_registry(entries: list[Mapping[str, Any]], *, production_approved: bool = False, production_routing: str = PRODUCTION_ROUTING, new_generation: int = 0) -> dict[str, Any]:
    _require(entries == [] and production_approved is False and production_routing == PRODUCTION_ROUTING and new_generation == 0, "VFX_PRODUCTION_BOUNDARY_REJECTED", "production must remain blocked")
    return {"status": "PASS", "registry": [], "production_approved": False, "production_routing": PRODUCTION_ROUTING, "new_generation": 0}


def strict_gate(gate_id: str, checker: Callable[[], Any]) -> dict[str, Any]:
    try:
        observed = checker(); detail = "checker returned"
    except Exception as exc:
        observed = False; detail = f"{type(exc).__name__}:{exc}"
    passed = type(observed) is bool and observed is True
    return {"gate_id": gate_id, "status": "PASS" if passed else "FAIL", "observed": observed, "observed_type": type(observed).__name__, "passed": passed, "detail": detail}


def strict_boolean_observation(observed: Any) -> bool:
    return type(observed) is bool and observed is True


def _fallback_state(record: Mapping[str, Any]) -> dict[str, Any]:
    budget = record["budget_profile"]
    return {"visible": True, "particles": budget["max_particles_per_instance"], "layers": budget["max_layers"], "spawn_rate": budget["max_spawn_events_per_second"], "visual_area_ratio": budget["max_visual_area_ratio"], "opacity": 1.0, "frame_count": record["lifecycle"]["frame_count"], "radius": 1.0}


def _apply_step(state: dict[str, Any], step: str, profile: Mapping[str, Any]) -> None:
    if step == "REDUCE_PARTICLE_COUNT": state["particles"] = min(state["particles"], int(profile["max_particles_per_instance"]))
    elif step == "REDUCE_LAYER_COUNT": state["layers"] = min(state["layers"], int(profile["max_layers"]))
    elif step == "REDUCE_SPAWN_RATE": state["spawn_rate"] = min(state["spawn_rate"], int(profile["max_spawn_events_per_second"]))
    elif step == "REDUCE_VISUAL_AREA": state["visual_area_ratio"] = min(state["visual_area_ratio"], float(profile["max_visual_area_ratio"]))
    elif step == "REDUCE_OPACITY": state["opacity"] = min(state["opacity"], 0.5)
    elif step == "REDUCE_FRAME_COUNT": state["frame_count"] = max(1, state["frame_count"] // 2)
    elif step == "REDUCE_RADIUS": state["radius"] = 0.5
    elif step == "SKIP_VISUAL": state["visible"] = False
    else: raise VFXAssetFamilyContractError("VFX_FALLBACK_UNSUPPORTED_STEP", step)


def select_fallback(record: Mapping[str, Any], constraint_profile: Mapping[str, Any]) -> dict[str, Any]:
    validate_effect_record(record, Path(constraint_profile.get("fixture_root", "."))) if constraint_profile.get("fixture_root") else None
    required = ("profile_id", "max_particles_per_instance", "max_layers", "max_spawn_events_per_second", "max_visual_area_ratio", "supported_steps")
    _require(all(key in constraint_profile for key in required), "VFX_FALLBACK_PROFILE_INVALID", str(record.get("effect_id")))
    _require(all(isinstance(constraint_profile[key], (int, float)) and float(constraint_profile[key]) > 0 for key in required[1:5]), "VFX_FALLBACK_PROFILE_INVALID", str(record.get("effect_id")))
    _require(isinstance(constraint_profile["supported_steps"], list), "VFX_FALLBACK_PROFILE_INVALID", str(record.get("effect_id")))
    ordered = record["fallback"]["ordered_steps"]; unsupported = [step for step in ordered if step not in constraint_profile["supported_steps"]]
    _require(not unsupported, "VFX_FALLBACK_UNSUPPORTED_STEP", ",".join(unsupported))
    before = _fallback_state(record); after = deepcopy(before); applied: list[str] = []
    for step in ordered:
        if after["particles"] > constraint_profile["max_particles_per_instance"] or after["layers"] > constraint_profile["max_layers"] or after["spawn_rate"] > constraint_profile["max_spawn_events_per_second"] or after["visual_area_ratio"] > constraint_profile["max_visual_area_ratio"]:
            _apply_step(after, step, constraint_profile); applied.append(step)
    _require(after["particles"] <= constraint_profile["max_particles_per_instance"] and after["layers"] <= constraint_profile["max_layers"] and after["spawn_rate"] <= constraint_profile["max_spawn_events_per_second"] and after["visual_area_ratio"] <= constraint_profile["max_visual_area_ratio"], "VFX_FALLBACK_CONSTRAINT_UNSATISFIED", str(record.get("effect_id")))
    result = {"effect_id": record["effect_id"], "profile_id": constraint_profile["profile_id"], "deterministic": True, "fallback_order": ordered, "applied_steps": applied, "before": before, "after": after, "visual_degraded": bool(applied), "semantic_preserved": True, "changes_gameplay": False}
    validate_fallback_result(record, result, constraint_profile)
    return result


def validate_fallback_result(record: Mapping[str, Any], result: Mapping[str, Any], constraint_profile: Mapping[str, Any]) -> None:
    _require(result.get("effect_id") == record.get("effect_id") and result.get("profile_id") == constraint_profile.get("profile_id"), "VFX_FALLBACK_RESULT_INVALID", str(record.get("effect_id")))
    _require(result.get("deterministic") is True and result.get("semantic_preserved") is True and result.get("changes_gameplay") is False and result.get("fallback_order") == record["fallback"]["ordered_steps"], "VFX_FALLBACK_RESULT_INVALID", str(record.get("effect_id")))
    applied = result.get("applied_steps"); _require(isinstance(applied, list) and all(step in result["fallback_order"] for step in applied), "VFX_FALLBACK_RESULT_INVALID", str(record.get("effect_id")))
    before, after = result.get("before"), result.get("after")
    _require(isinstance(before, Mapping) and isinstance(after, Mapping) and after.get("particles", 0) <= constraint_profile["max_particles_per_instance"] and after.get("layers", 0) <= constraint_profile["max_layers"] and after.get("spawn_rate", 0) <= constraint_profile["max_spawn_events_per_second"] and after.get("visual_area_ratio", 0) <= constraint_profile["max_visual_area_ratio"], "VFX_FALLBACK_RESULT_INVALID", str(record.get("effect_id")))
    _require(result.get("visual_degraded") is (before != after), "VFX_FALLBACK_RESULT_INVALID", str(record.get("effect_id")))


def generate_fixture_pack(output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    records = [build_effect_fixture(effect_class, output_root, index) for index, effect_class in enumerate(EFFECT_CLASSES)]
    manifest = {"schema_version": VERSION, "family_id": FAMILY_ID, "registry_mode": REGISTRY_MODE, "effect_classes": list(EFFECT_CLASSES), "effects": records, "production_routing": PRODUCTION_ROUTING, "production_approved": False, "new_generation": 0, "real_vfx_asset_coverage": "NONE", "synthetic_vfx_fixture": REGISTRY_MODE}
    validate_vfx_manifest(manifest, output_root)
    return {"manifest": manifest, "records": records}


def _label(draw: ImageDraw.ImageDraw, text: str, position: tuple[int, int]) -> None:
    draw.text(position, text, fill=(235, 235, 235, 255), font=ImageFont.load_default())


def build_contact_sheets(records: list[Mapping[str, Any]], root: Path, output_root: Path) -> tuple[Path, Path]:
    contact = Image.new("RGBA", (5 * 128, 2 * 128), (18, 22, 34, 255)); timing = Image.new("RGBA", (5 * 180, 2 * 108), (18, 22, 34, 255)); cdraw, tdraw = ImageDraw.Draw(contact), ImageDraw.Draw(timing)
    for index, record in enumerate(records):
        x, y = index % 5, index // 5; frames = record["frames"]
        for target_index in (0, len(frames) // 2, len(frames) - 1):
            with Image.open(root / Path(frames[target_index]["path"])) as source:
                contact.alpha_composite(source.convert("RGBA").resize((96, 96), Image.Resampling.NEAREST), (x * 128 + 16, y * 128 + 16))
        _label(cdraw, record["effect_class"], (x * 128 + 4, y * 128 + 4)); tx, ty = x, y; y0 = ty * 108 + 20
        for frame in frames:
            fx = tx * 180 + 8 + int((frame["index"] / max(1, len(frames) - 1)) * 160); tdraw.ellipse((fx - 3, y0 - 3, fx + 3, y0 + 3), fill=(230, 230, 230, 230))
        _label(tdraw, f"{record['effect_class']} {record['lifecycle']['duration_ms']}ms", (tx * 180 + 5, ty * 108 + 4))
    contact_path = output_root / "vfx-effect-contact-sheet-v0231.png"; timing_path = output_root / "vfx-timing-qa-sheet-v0231.png"; contact.save(contact_path, format="PNG", optimize=False, compress_level=9); timing.save(timing_path, format="PNG", optimize=False, compress_level=9); return contact_path, timing_path


def build_budget_fallback_sheet(full: Mapping[str, Any], degraded: Mapping[str, Any], output_path: Path) -> Path:
    image = Image.new("RGBA", (640, 160), (18, 22, 34, 255)); draw = ImageDraw.Draw(image); _label(draw, f"FULL: {full['effect_id']} budget", (12, 12)); _label(draw, f"DEGRADED: {degraded['profile_id']} steps={','.join(degraded['applied_steps'])}", (12, 48)); _label(draw, "semantic_preserved=True gameplay_mutation=False", (12, 84)); _label(draw, "constrained visual output is deterministic", (12, 120)); output_path.parent.mkdir(parents=True, exist_ok=True); image.save(output_path, format="PNG", optimize=False, compress_level=9); return output_path
