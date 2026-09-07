"""Deterministic, engine-neutral VFX asset-family runtime contracts for v0.23.0.

This module deliberately renders only TEST_ONLY synthetic fixtures.  It owns
the semantic contract, deterministic fixture pixels, read-only integration
identity, cache/provenance binding, and fail-closed validators used by the
v0.23.0 review slice.  It does not route production assets or invoke a
provider/generation service.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping

from PIL import Image, ImageDraw, ImageFont


VERSION = "0.23.0"
FAMILY_ID = "vfx_asset_family"
BASE_MAIN_SHA = "b08b9c3df74ef6a23046be396289e2fd72dc336b"
REGISTRY_MODE = "TEST_ONLY"
PRODUCTION_ROUTING = "BLOCKED"

EFFECT_CLASSES = (
    "impact_burst",
    "weapon_arc",
    "projectile_trail",
    "projectile_impact",
    "cast_charge",
    "persistent_aura",
    "area_telegraph",
    "status_loop",
    "buff_heal_burst",
    "environment_ambient",
)

BLEND_MODES = ("ALPHA", "ADDITIVE", "MULTIPLY")
ALPHA_MODES = ("STRAIGHT", "PREMULTIPLIED")
SPACES = ("WORLD", "ENTITY_ANCHOR", "SCREEN_OVERLAY")
REPRESENTATIONS = ("SPRITE_SEQUENCE", "SPRITE_SHEET", "PARTICLE_RECIPE")
READ_ONLY = "READ_ONLY"


class VFXAssetFamilyContractError(ValueError):
    """A semantic contract rejection with a stable machine class."""

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


def _spec(
    effect_class: str,
    *,
    stable_id: str,
    lifecycle: str,
    frame_count: int,
    duration_ms: int,
    representations: tuple[str, ...],
    space: str,
    anchor_kind: str,
    direction_policy: str,
    blend_mode: str,
    alpha_mode: str,
    fallback: tuple[str, ...],
    semantic_role: str,
    required_semantics: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "effect_class": effect_class,
        "stable_id": stable_id,
        "lifecycle": lifecycle,
        "frame_count": frame_count,
        "duration_ms": duration_ms,
        "representations": list(representations),
        "space": space,
        "anchor_kind": anchor_kind,
        "direction_policy": direction_policy,
        "blend_mode": blend_mode,
        "alpha_mode": alpha_mode,
        "fallback": list(fallback),
        "semantic_role": semantic_role,
        "required_semantics": list(required_semantics),
    }


CLASS_SPECS: dict[str, dict[str, Any]] = {
    "impact_burst": _spec("impact_burst", stable_id="VFX-CLS-IMPACT-BURST", lifecycle="ONE_SHOT", frame_count=6, duration_ms=240, representations=("SPRITE_SEQUENCE", "SPRITE_SHEET"), space="WORLD", anchor_kind="IMPACT_POINT", direction_policy="RADIAL", blend_mode="ADDITIVE", alpha_mode="STRAIGHT", fallback=("REDUCE_FRAME_COUNT", "REDUCE_LAYER_COUNT", "SKIP_VISUAL"), semantic_role="short readable impact response", required_semantics=("impact_origin", "radius_curve", "termination")),
    "weapon_arc": _spec("weapon_arc", stable_id="VFX-CLS-WEAPON-ARC", lifecycle="ONE_SHOT", frame_count=5, duration_ms=200, representations=("SPRITE_SEQUENCE", "SPRITE_SHEET"), space="ENTITY_ANCHOR", anchor_kind="WEAPON_SWEEP", direction_policy="EXPLICIT_FACING", blend_mode="ALPHA", alpha_mode="STRAIGHT", fallback=("REDUCE_OPACITY", "REDUCE_FRAME_COUNT", "SKIP_VISUAL"), semantic_role="directional weapon sweep accent", required_semantics=("weapon_anchor", "facing", "arc_span_degrees", "termination")),
    "projectile_trail": _spec("projectile_trail", stable_id="VFX-CLS-PROJECTILE-TRAIL", lifecycle="OWNER_BOUND_LOOP", frame_count=8, duration_ms=640, representations=("SPRITE_SEQUENCE", "PARTICLE_RECIPE"), space="ENTITY_ANCHOR", anchor_kind="PROJECTILE_OWNER", direction_policy="VELOCITY_VECTOR", blend_mode="ADDITIVE", alpha_mode="PREMULTIPLIED", fallback=("REDUCE_PARTICLE_COUNT", "REDUCE_LAYER_COUNT", "SKIP_VISUAL"), semantic_role="bounded projectile motion trail", required_semantics=("owner_anchor", "velocity_vector", "max_lifetime", "termination")),
    "projectile_impact": _spec("projectile_impact", stable_id="VFX-CLS-PROJECTILE-IMPACT", lifecycle="ONE_SHOT", frame_count=5, duration_ms=200, representations=("SPRITE_SEQUENCE", "PARTICLE_RECIPE"), space="WORLD", anchor_kind="IMPACT_POINT", direction_policy="RADIAL", blend_mode="ADDITIVE", alpha_mode="STRAIGHT", fallback=("REDUCE_PARTICLE_COUNT", "REDUCE_OPACITY", "SKIP_VISUAL"), semantic_role="projectile arrival accent", required_semantics=("impact_origin", "projectile_type", "termination")),
    "cast_charge": _spec("cast_charge", stable_id="VFX-CLS-CAST-CHARGE", lifecycle="OWNER_BOUND_LOOP", frame_count=8, duration_ms=800, representations=("SPRITE_SEQUENCE", "SPRITE_SHEET"), space="ENTITY_ANCHOR", anchor_kind="CASTER", direction_policy="EXPLICIT_FACING", blend_mode="ALPHA", alpha_mode="STRAIGHT", fallback=("REDUCE_RADIUS", "REDUCE_LAYER_COUNT", "SKIP_VISUAL"), semantic_role="bounded charge-up readability", required_semantics=("caster_anchor", "charge_phase", "termination")),
    "persistent_aura": _spec("persistent_aura", stable_id="VFX-CLS-PERSISTENT-AURA", lifecycle="OWNER_BOUND_LOOP", frame_count=8, duration_ms=960, representations=("SPRITE_SEQUENCE", "PARTICLE_RECIPE"), space="ENTITY_ANCHOR", anchor_kind="AURA_OWNER", direction_policy="NONE", blend_mode="ADDITIVE", alpha_mode="PREMULTIPLIED", fallback=("REDUCE_PARTICLE_COUNT", "REDUCE_RADIUS", "SKIP_VISUAL"), semantic_role="persistent owner-bound aura", required_semantics=("owner_anchor", "aura_radius", "termination_condition")),
    "area_telegraph": _spec("area_telegraph", stable_id="VFX-CLS-AREA-TELEGRAPH", lifecycle="OWNER_BOUND_LOOP", frame_count=8, duration_ms=1200, representations=("SPRITE_SEQUENCE", "SPRITE_SHEET"), space="WORLD", anchor_kind="AREA_ORIGIN", direction_policy="NONE", blend_mode="ALPHA", alpha_mode="STRAIGHT", fallback=("REDUCE_OPACITY", "REDUCE_LAYER_COUNT", "SKIP_VISUAL"), semantic_role="read-only area warning", required_semantics=("area_origin", "shape", "duration", "termination")),
    "status_loop": _spec("status_loop", stable_id="VFX-CLS-STATUS-LOOP", lifecycle="OWNER_BOUND_LOOP", frame_count=8, duration_ms=960, representations=("SPRITE_SEQUENCE", "PARTICLE_RECIPE"), space="ENTITY_ANCHOR", anchor_kind="STATUS_OWNER", direction_policy="NONE", blend_mode="ALPHA", alpha_mode="STRAIGHT", fallback=("REDUCE_PARTICLE_COUNT", "REDUCE_OPACITY", "SKIP_VISUAL"), semantic_role="owner-bound status readability", required_semantics=("owner_anchor", "status_kind", "termination_condition")),
    "buff_heal_burst": _spec("buff_heal_burst", stable_id="VFX-CLS-BUFF-HEAL-BURST", lifecycle="ONE_SHOT", frame_count=6, duration_ms=300, representations=("SPRITE_SEQUENCE", "SPRITE_SHEET"), space="ENTITY_ANCHOR", anchor_kind="TARGET_ENTITY", direction_policy="RADIAL", blend_mode="ADDITIVE", alpha_mode="STRAIGHT", fallback=("REDUCE_OPACITY", "REDUCE_FRAME_COUNT", "SKIP_VISUAL"), semantic_role="positive buff or heal feedback", required_semantics=("target_anchor", "feedback_kind", "termination")),
    "environment_ambient": _spec("environment_ambient", stable_id="VFX-CLS-ENVIRONMENT-AMBIENT", lifecycle="OWNER_BOUND_LOOP", frame_count=8, duration_ms=1600, representations=("SPRITE_SEQUENCE", "PARTICLE_RECIPE"), space="WORLD", anchor_kind="AMBIENT_REGION", direction_policy="NONE", blend_mode="ALPHA", alpha_mode="STRAIGHT", fallback=("REDUCE_PARTICLE_COUNT", "REDUCE_LAYER_COUNT", "SKIP_VISUAL"), semantic_role="bounded environment atmosphere", required_semantics=("ambient_region", "seed", "termination_condition")),
}

PALETTES = {
    "impact_burst": (255, 176, 72), "weapon_arc": (142, 212, 255), "projectile_trail": (252, 226, 93),
    "projectile_impact": (255, 106, 74), "cast_charge": (185, 122, 255), "persistent_aura": (92, 228, 190),
    "area_telegraph": (255, 115, 154), "status_loop": (255, 217, 101), "buff_heal_burst": (104, 255, 162),
    "environment_ambient": (152, 197, 255),
}

DEFAULT_BUDGETS = {
    "profile_id": "vfx-runtime-safe-v1",
    "max_concurrent_effects": 64,
    "max_layers_per_effect": 4,
    "max_spawn_events_per_second": 120,
    "max_particles_per_effect": 96,
    "max_visual_area_ratio": 0.80,
    "authority_sha256": sha256_bytes(canonical_json({"profile_id": "vfx-runtime-safe-v1", "max_concurrent_effects": 64, "max_layers_per_effect": 4, "max_spawn_events_per_second": 120, "max_particles_per_effect": 96, "max_visual_area_ratio": 0.80})),
}


def validate_class_spec_table() -> None:
    _require(tuple(CLASS_SPECS) == EFFECT_CLASSES, "VFX_CLASS_TABLE_INVALID", "class order or class set changed")
    stable_ids = [str(item.get("stable_id")) for item in CLASS_SPECS.values()]
    _require(len(set(stable_ids)) == len(EFFECT_CLASSES), "VFX_CLASS_ID_DUPLICATE", "stable ids must be unique")
    for effect_class, spec in CLASS_SPECS.items():
        _require(spec.get("effect_class") == effect_class, "VFX_CLASS_IDENTITY_INVALID", effect_class)
        _require(spec.get("lifecycle") in {"ONE_SHOT", "OWNER_BOUND_LOOP"}, "VFX_LIFECYCLE_INVALID", effect_class)
        _require(isinstance(spec.get("frame_count"), int) and spec["frame_count"] >= 4, "VFX_TIMING_INVALID", effect_class)
        _require(isinstance(spec.get("duration_ms"), int) and spec["duration_ms"] > 0, "VFX_TIMING_INVALID", effect_class)
        _require(set(spec.get("representations", ())).issubset(REPRESENTATIONS), "VFX_REPRESENTATION_INVALID", effect_class)
        _require(spec.get("space") in SPACES, "VFX_SPACE_INVALID", effect_class)
        _require(spec.get("blend_mode") in BLEND_MODES and spec.get("alpha_mode") in ALPHA_MODES, "VFX_BLEND_ALPHA_INVALID", effect_class)
        _require(spec.get("fallback") and spec["fallback"][-1] == "SKIP_VISUAL", "VFX_FALLBACK_INVALID", effect_class)
        _require(spec.get("required_semantics"), "VFX_SEMANTICS_MISSING", effect_class)


def _authority_identity() -> dict[str, str]:
    payload = {"authority_type": "VFX_RUNTIME_CONTRACT", "path": "src/ugas/vfx_asset_family_runtime_v0230.py", "revision": VERSION}
    return {**payload, "sha256": sha256_bytes(canonical_json(payload))}


def _semantic_input(effect_class: str, index: int) -> dict[str, Any]:
    spec = CLASS_SPECS[effect_class]
    semantics = {key: f"fixture-{effect_class}-{key}" for key in spec["required_semantics"]}
    semantics.update({"fixture_index": index, "fixture_seed": 23000 + index, "visual_only": True, "gameplay_authority": "NONE"})
    return {
        "effect_id": f"vfx-test-{effect_class}-v0230",
        "effect_class": effect_class,
        "semantic_revision": VERSION,
        "intent": "VISUAL_ONLY",
        "readability_role": spec["semantic_role"],
        "semantics": semantics,
        "registry_mode": REGISTRY_MODE,
    }


def _rgba_for(effect_class: str, alpha: int) -> tuple[int, int, int, int]:
    color = PALETTES[effect_class]
    return (*color, max(0, min(255, int(alpha))))


def _draw_fixture(effect_class: str, frame_index: int, frame_count: int, size: tuple[int, int] = (96, 96)) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    color = PALETTES[effect_class]
    progress = frame_index / max(1, frame_count - 1)
    cx, cy = width // 2, height // 2
    pulse = 0.55 + 0.45 * math.sin(progress * math.pi)
    if effect_class in {"impact_burst", "projectile_impact", "buff_heal_burst"}:
        radius = int(8 + 28 * progress)
        for ray in range(8):
            angle = ray * math.pi / 4.0
            x = cx + int(math.cos(angle) * radius)
            y = cy + int(math.sin(angle) * radius)
            draw.line((cx, cy, x, y), fill=_rgba_for(effect_class, 90 + int(120 * pulse)), width=3)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=_rgba_for(effect_class, 190), width=4)
        if effect_class == "buff_heal_burst":
            draw.line((cx - 17, cy, cx + 17, cy), fill=_rgba_for(effect_class, 240), width=5)
            draw.line((cx, cy - 17, cx, cy + 17), fill=_rgba_for(effect_class, 240), width=5)
    elif effect_class == "weapon_arc":
        box = (12, 12, width - 12, height - 12)
        draw.arc(box, start=-55 + int(progress * 80), end=80 + int(progress * 80), fill=_rgba_for(effect_class, 220), width=6)
        draw.line((cx - 6, height - 22, cx + 12, cy + 3), fill=_rgba_for(effect_class, 170), width=3)
    elif effect_class == "projectile_trail":
        x = 14 + int(68 * progress)
        draw.line((10, cy, x, cy), fill=_rgba_for(effect_class, 160), width=5)
        for offset in (0, -8, 8):
            draw.ellipse((x - 5, cy + offset - 5, x + 5, cy + offset + 5), fill=_rgba_for(effect_class, 220 - abs(offset) * 8))
    elif effect_class == "cast_charge":
        radius = int(14 + 15 * pulse)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=_rgba_for(effect_class, 220), width=4)
        for angle in range(0, 360, 45):
            rad = math.radians(angle + frame_index * 9)
            x = cx + int(math.cos(rad) * (radius + 7))
            y = cy + int(math.sin(rad) * (radius + 7))
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=_rgba_for(effect_class, 210))
    elif effect_class == "persistent_aura":
        radius = int(26 + 4 * math.sin(progress * math.pi * 2))
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=_rgba_for(effect_class, 170), width=4)
        draw.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill=_rgba_for(effect_class, 125))
    elif effect_class == "area_telegraph":
        box = (10, 28, width - 10, height - 28)
        draw.ellipse(box, outline=_rgba_for(effect_class, 210), width=4)
        draw.arc(box, start=int(progress * 80), end=180 + int(progress * 80), fill=_rgba_for(effect_class, 115), width=8)
    elif effect_class == "status_loop":
        for orbit in range(4):
            angle = progress * math.tau + orbit * math.tau / 4
            x = cx + int(math.cos(angle) * 24)
            y = cy + int(math.sin(angle) * 18)
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=_rgba_for(effect_class, 180 + orbit * 15))
    elif effect_class == "environment_ambient":
        for particle in range(9):
            seed = particle * 17 + frame_index * 5
            x = 8 + (seed * 13) % (width - 16)
            y = 8 + (seed * 7) % (height - 16)
            alpha = 90 + ((seed * 11) % 120)
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=_rgba_for(effect_class, alpha))
    else:  # pragma: no cover - class table prevents this path
        raise VFXAssetFamilyContractError("VFX_EFFECT_CLASS_UNKNOWN", effect_class)
    return image


def _frame_metadata(path: Path, index: int, duration_ms: int) -> dict[str, Any]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        alpha_min, alpha_max = rgba.getchannel("A").getextrema()
        return {"index": index, "path": path.as_posix(), "sha256": sha256_file(path), "width": rgba.width, "height": rgba.height, "alpha_range": [alpha_min, alpha_max], "duration_ms": duration_ms}


def build_effect_fixture(effect_class: str, output_root: Path, index: int = 0) -> dict[str, Any]:
    validate_class_spec_table()
    _require(effect_class in CLASS_SPECS, "VFX_EFFECT_CLASS_UNKNOWN", effect_class)
    spec = CLASS_SPECS[effect_class]
    semantic = _semantic_input(effect_class, index)
    semantic_hash = sha256_bytes(canonical_json(semantic))
    authority = _authority_identity()
    budget = deepcopy(DEFAULT_BUDGETS)
    frames_dir = output_root / "frames" / effect_class
    frames_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, Any]] = []
    for frame_index in range(spec["frame_count"]):
        path = frames_dir / f"{frame_index:02d}.png"
        _draw_fixture(effect_class, frame_index, spec["frame_count"]).save(path, format="PNG", optimize=False, compress_level=9)
        metadata = _frame_metadata(path, frame_index, spec["duration_ms"] // spec["frame_count"])
        metadata["path"] = path.relative_to(output_root).as_posix()
        frames.append(metadata)
    frame_hashes = [item["sha256"] for item in frames]
    frame_set_hash = sha256_bytes(canonical_json(frame_hashes))
    content_hash = sha256_bytes(canonical_json({"effect_id": semantic["effect_id"], "frame_set_hash": frame_set_hash, "frames": frames}))
    representation = {"kind": spec["representations"][0], "frame_width": 96, "frame_height": 96, "frame_count": spec["frame_count"], "import_scale": 1.0, "pixel_snap": True, "color_space": "SRGB", "alpha_mode": spec["alpha_mode"], "premultiplied": spec["alpha_mode"] == "PREMULTIPLIED"}
    spatial = {"space": spec["space"], "anchor": {"kind": spec["anchor_kind"], "id": f"anchor-{effect_class}-fixture", "read_only": True}, "pivot": [0.5, 0.5], "direction_policy": spec["direction_policy"], "bounds_policy": "DECLARED_AND_BOUNDED", "max_visual_area_ratio": DEFAULT_BUDGETS["max_visual_area_ratio"]}
    lifecycle = {"mode": spec["lifecycle"], "frame_count": spec["frame_count"], "duration_ms": spec["duration_ms"], "frame_duration_ms": spec["duration_ms"] // spec["frame_count"], "loop": spec["lifecycle"] == "OWNER_BOUND_LOOP", "termination": "OWNER_OR_EVENT_TERMINATION" if spec["lifecycle"] == "OWNER_BOUND_LOOP" else "FRAME_END", "max_lifetime_ms": spec["duration_ms"]}
    fallback = {"ordered_steps": spec["fallback"], "deterministic": True, "changes_gameplay": False, "preserves_intent": True}
    integration = {"mode": READ_ONLY, "authority": authority, "event_binding": {"source": "VFX_LOCAL_EVENT_BUS", "event_id": f"vfx.fixture.{effect_class}", "read_only": True, "gameplay_authoritative": False}, "no_gameplay_mutation": True}
    record = {"effect_id": semantic["effect_id"], "family_id": FAMILY_ID, "schema_version": VERSION, "effect_class": effect_class, "stable_class_id": spec["stable_id"], "registry_mode": REGISTRY_MODE, "intent": semantic["intent"], "readability_role": semantic["readability_role"], "semantic_input": semantic, "semantic_input_hash": semantic_hash, "lifecycle": lifecycle, "blend_alpha": {"blend_mode": spec["blend_mode"], "alpha_mode": spec["alpha_mode"], "premultiplied": spec["alpha_mode"] == "PREMULTIPLIED", "opacity_range": [0.0, 1.0]}, "spatial": spatial, "budget_profile": budget, "fallback": fallback, "representation": representation, "integration": integration, "frames": frames, "frame_set_hash": frame_set_hash, "content_hash": content_hash, "authority_identity_hash": authority["sha256"], "provenance": {"generator": "deterministic-test-fixture-renderer-v0230", "provider": None, "generation_model": None, "seed": 23000 + index, "source": "runtime_contract_fixture", "input_hash": semantic_hash, "output_hash": content_hash, "production_claim": False}, "cache_key": "", "test_only": True}
    record["cache_key"] = cache_key_for(record)
    validate_effect_record(record, output_root)
    return record


def cache_key_for(record: Mapping[str, Any]) -> str:
    keys = {"family_id": record.get("family_id"), "effect_id": record.get("effect_id"), "schema_version": record.get("schema_version"), "effect_class": record.get("effect_class"), "semantic_input_hash": record.get("semantic_input_hash"), "authority_identity_hash": record.get("authority_identity_hash"), "budget_profile": record.get("budget_profile", {}).get("authority_sha256"), "representation": record.get("representation"), "content_hash": record.get("content_hash")}
    return sha256_bytes(canonical_json(keys))


def validate_lifecycle(record: Mapping[str, Any]) -> None:
    spec = CLASS_SPECS.get(str(record.get("effect_class")))
    _require(spec is not None, "VFX_EFFECT_CLASS_UNKNOWN", str(record.get("effect_class")))
    value = record.get("lifecycle")
    _require(isinstance(value, Mapping), "VFX_LIFECYCLE_MISSING", str(record.get("effect_id")))
    _require(value.get("mode") == spec["lifecycle"], "VFX_LIFECYCLE_CLASS_MISMATCH", str(record.get("effect_id")))
    _require(value.get("frame_count") == spec["frame_count"] and value.get("duration_ms") == spec["duration_ms"], "VFX_TIMING_INVALID", str(record.get("effect_id")))
    _require(value.get("frame_duration_ms") == value["duration_ms"] // value["frame_count"] and value.get("frame_duration_ms") > 0, "VFX_TIMING_INVALID", str(record.get("effect_id")))
    _require(value.get("loop") is (spec["lifecycle"] == "OWNER_BOUND_LOOP"), "VFX_LOOP_POLICY_INVALID", str(record.get("effect_id")))
    _require(value.get("termination") in {"FRAME_END", "OWNER_OR_EVENT_TERMINATION"}, "VFX_TERMINATION_INVALID", str(record.get("effect_id")))


def validate_blend_alpha(record: Mapping[str, Any]) -> None:
    spec = CLASS_SPECS.get(str(record.get("effect_class")))
    value = record.get("blend_alpha")
    _require(spec is not None and isinstance(value, Mapping), "VFX_BLEND_ALPHA_INVALID", str(record.get("effect_id")))
    _require(value.get("blend_mode") == spec["blend_mode"] and value.get("alpha_mode") == spec["alpha_mode"], "VFX_BLEND_ALPHA_INVALID", str(record.get("effect_id")))
    _require(value.get("premultiplied") is (value.get("alpha_mode") == "PREMULTIPLIED"), "VFX_PREMULTIPLIED_METADATA_INVALID", str(record.get("effect_id")))
    _require(value.get("opacity_range") == [0.0, 1.0], "VFX_ALPHA_RANGE_INVALID", str(record.get("effect_id")))


def validate_spatial_anchor(record: Mapping[str, Any]) -> None:
    spec = CLASS_SPECS.get(str(record.get("effect_class")))
    value = record.get("spatial")
    _require(spec is not None and isinstance(value, Mapping), "VFX_SPATIAL_CONTRACT_INVALID", str(record.get("effect_id")))
    _require(value.get("space") == spec["space"] and value.get("direction_policy") == spec["direction_policy"], "VFX_SPATIAL_CONTRACT_INVALID", str(record.get("effect_id")))
    anchor = value.get("anchor")
    _require(isinstance(anchor, Mapping) and anchor.get("kind") == spec["anchor_kind"] and anchor.get("id") and anchor.get("read_only") is True, "VFX_ANCHOR_BINDING_INVALID", str(record.get("effect_id")))
    pivot = value.get("pivot")
    _require(isinstance(pivot, list) and len(pivot) == 2 and all(_finite(item) and 0.0 <= float(item) <= 1.0 for item in pivot), "VFX_PIVOT_INVALID", str(record.get("effect_id")))
    _require(value.get("bounds_policy") == "DECLARED_AND_BOUNDED", "VFX_BOUNDS_POLICY_INVALID", str(record.get("effect_id")))


def validate_budget(record: Mapping[str, Any]) -> None:
    value = record.get("budget_profile")
    _require(isinstance(value, Mapping), "VFX_BUDGET_MISSING", str(record.get("effect_id")))
    for key in ("max_concurrent_effects", "max_layers_per_effect", "max_spawn_events_per_second", "max_particles_per_effect"):
        _require(value.get(key) == DEFAULT_BUDGETS[key], "VFX_BUDGET_EXCEEDED", key)
    _require(value.get("max_visual_area_ratio") == DEFAULT_BUDGETS["max_visual_area_ratio"], "VFX_BUDGET_EXCEEDED", "max_visual_area_ratio")
    _require(value.get("authority_sha256") == DEFAULT_BUDGETS["authority_sha256"], "VFX_BUDGET_AUTHORITY_STALE", str(record.get("effect_id")))


def validate_fallback(record: Mapping[str, Any]) -> None:
    spec = CLASS_SPECS.get(str(record.get("effect_class")))
    value = record.get("fallback")
    _require(spec is not None and isinstance(value, Mapping), "VFX_FALLBACK_INVALID", str(record.get("effect_id")))
    _require(value.get("ordered_steps") == spec["fallback"] and value.get("deterministic") is True and value.get("changes_gameplay") is False and value.get("preserves_intent") is True, "VFX_FALLBACK_INVALID", str(record.get("effect_id")))


def validate_representation(record: Mapping[str, Any]) -> None:
    spec = CLASS_SPECS.get(str(record.get("effect_class")))
    value = record.get("representation")
    _require(spec is not None and isinstance(value, Mapping) and value.get("kind") in spec["representations"], "VFX_REPRESENTATION_INVALID", str(record.get("effect_id")))
    _require(value.get("frame_width") == 96 and value.get("frame_height") == 96 and value.get("frame_count") == spec["frame_count"], "VFX_REPRESENTATION_INVALID", str(record.get("effect_id")))
    _require(value.get("import_scale") == 1.0 and value.get("pixel_snap") is True and value.get("color_space") == "SRGB", "VFX_IMPORT_METADATA_INVALID", str(record.get("effect_id")))
    _require(value.get("alpha_mode") == spec["alpha_mode"] and value.get("premultiplied") is (value.get("alpha_mode") == "PREMULTIPLIED"), "VFX_IMPORT_ALPHA_METADATA_INVALID", str(record.get("effect_id")))


def validate_integration(record: Mapping[str, Any]) -> None:
    value = record.get("integration")
    _require(isinstance(value, Mapping) and value.get("mode") == READ_ONLY, "VFX_INTEGRATION_MODE_INVALID", str(record.get("effect_id")))
    authority = value.get("authority")
    event = value.get("event_binding")
    _require(isinstance(authority, Mapping) and authority.get("authority_type") == "VFX_RUNTIME_CONTRACT" and authority.get("sha256") == _authority_identity()["sha256"], "VFX_INTEGRATION_AUTHORITY_STALE", str(record.get("effect_id")))
    _require(isinstance(event, Mapping) and event.get("read_only") is True and event.get("gameplay_authoritative") is False and event.get("event_id"), "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN", str(record.get("effect_id")))
    _require(value.get("no_gameplay_mutation") is True, "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN", str(record.get("effect_id")))


def validate_provenance(record: Mapping[str, Any], root: Path) -> None:
    value = record.get("provenance")
    _require(isinstance(value, Mapping) and value.get("generator") == "deterministic-test-fixture-renderer-v0230" and value.get("provider") is None and value.get("generation_model") is None, "VFX_PROVENANCE_INVALID", str(record.get("effect_id")))
    _require(value.get("input_hash") == record.get("semantic_input_hash") and value.get("output_hash") == record.get("content_hash") and value.get("production_claim") is False, "VFX_PROVENANCE_HASH_INVALID", str(record.get("effect_id")))
    for frame in record.get("frames", []):
        path = root / Path(str(frame["path"]))
        _require(path.is_file() and sha256_file(path) == frame.get("sha256"), "VFX_FRAME_HASH_INVALID", str(path))


def validate_effect_record(record: Mapping[str, Any], root: Path) -> None:
    _require(record.get("family_id") == FAMILY_ID and record.get("schema_version") == VERSION and record.get("registry_mode") == REGISTRY_MODE, "VFX_RECORD_IDENTITY_INVALID", str(record.get("effect_id")))
    effect_class = str(record.get("effect_class"))
    _require(effect_class in CLASS_SPECS and record.get("stable_class_id") == CLASS_SPECS[effect_class]["stable_id"], "VFX_CLASS_IDENTITY_INVALID", str(record.get("effect_id")))
    _require(record.get("intent") == "VISUAL_ONLY" and record.get("semantic_input", {}).get("gameplay_authority") is None, "VFX_INTENT_NOT_VISUAL_ONLY", str(record.get("effect_id")))
    semantic = record.get("semantic_input")
    _require(isinstance(semantic, Mapping) and record.get("semantic_input_hash") == sha256_bytes(canonical_json(semantic)), "VFX_SEMANTIC_HASH_INVALID", str(record.get("effect_id")))
    _require(record.get("test_only") is True, "VFX_TEST_ONLY_BOUNDARY_INVALID", str(record.get("effect_id")))
    validate_lifecycle(record); validate_blend_alpha(record); validate_spatial_anchor(record); validate_budget(record); validate_fallback(record); validate_representation(record); validate_integration(record)
    frame_set_hash = sha256_bytes(canonical_json([item.get("sha256") for item in record.get("frames", [])]))
    _require(frame_set_hash == record.get("frame_set_hash"), "VFX_FRAME_SET_HASH_INVALID", str(record.get("effect_id")))
    content_hash = sha256_bytes(canonical_json({"effect_id": record.get("effect_id"), "frame_set_hash": frame_set_hash, "frames": record.get("frames")}))
    _require(content_hash == record.get("content_hash"), "VFX_CONTENT_HASH_INVALID", str(record.get("effect_id")))
    _require(record.get("cache_key") == cache_key_for(record), "VFX_CACHE_KEY_INVALID", str(record.get("effect_id")))
    validate_provenance(record, root)


def validate_vfx_manifest(manifest: Mapping[str, Any], root: Path | None = None) -> dict[str, Any]:
    validate_class_spec_table()
    _require(manifest.get("schema_version") == VERSION and manifest.get("family_id") == FAMILY_ID, "VFX_MANIFEST_IDENTITY_INVALID", "manifest")
    records = manifest.get("effects")
    _require(isinstance(records, list) and len(records) == len(EFFECT_CLASSES), "VFX_MANIFEST_CLASS_COUNT_INVALID", "manifest")
    _require(tuple(item.get("effect_class") for item in records) == EFFECT_CLASSES, "VFX_MANIFEST_CLASS_SET_INVALID", "manifest")
    ids = [item.get("effect_id") for item in records]
    _require(len(set(ids)) == len(ids), "VFX_EFFECT_ID_DUPLICATE", "manifest")
    if root is not None:
        for item in records:
            validate_effect_record(item, root)
    return {"status": "VFX_ASSET_FAMILY_MANIFEST_VALID", "effect_count": len(records), "classes": list(EFFECT_CLASSES)}


def validate_production_registry(entries: list[Mapping[str, Any]], *, production_approved: bool = False, production_routing: str = PRODUCTION_ROUTING, new_generation: int = 0) -> dict[str, Any]:
    _require(entries == [] and production_approved is False and production_routing == PRODUCTION_ROUTING and new_generation == 0, "VFX_PRODUCTION_BOUNDARY_REJECTED", "production must remain blocked")
    return {"status": "PASS", "registry": [], "production_approved": False, "production_routing": PRODUCTION_ROUTING, "new_generation": 0}


def strict_gate(gate_id: str, checker: Callable[[], Any]) -> dict[str, Any]:
    try:
        observed = checker()
        detail = "checker returned"
    except Exception as exc:  # fail closed and preserve the exception as context
        observed = False
        detail = f"{type(exc).__name__}:{exc}"
    passed = type(observed) is bool and observed is True
    return {"gate_id": gate_id, "status": "PASS" if passed else "FAIL", "observed": observed, "observed_type": type(observed).__name__, "passed": passed, "detail": detail}


def strict_boolean_observation(observed: Any) -> bool:
    return type(observed) is bool and observed is True


def generate_fixture_pack(output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    records = [build_effect_fixture(effect_class, output_root, index) for index, effect_class in enumerate(EFFECT_CLASSES)]
    manifest = {"schema_version": VERSION, "family_id": FAMILY_ID, "registry_mode": REGISTRY_MODE, "effect_classes": list(EFFECT_CLASSES), "effects": records, "production_routing": PRODUCTION_ROUTING, "production_approved": False, "new_generation": 0, "real_vfx_asset_coverage": "NONE", "synthetic_vfx_fixture": REGISTRY_MODE}
    validate_vfx_manifest(manifest, output_root)
    return {"manifest": manifest, "records": records}


def _label(draw: ImageDraw.ImageDraw, text: str, position: tuple[int, int]) -> None:
    try:
        draw.text(position, text, fill=(235, 235, 235, 255), font=ImageFont.load_default())
    except Exception:
        pass


def build_contact_sheets(records: list[Mapping[str, Any]], root: Path, output_root: Path) -> tuple[Path, Path]:
    contact = Image.new("RGBA", (5 * 128, 2 * 128), (18, 22, 34, 255))
    timing = Image.new("RGBA", (5 * 180, 2 * 108), (18, 22, 34, 255))
    cdraw, tdraw = ImageDraw.Draw(contact), ImageDraw.Draw(timing)
    for index, record in enumerate(records):
        x, y = index % 5, index // 5
        frames = record["frames"]
        for target_index, target_name in ((0, "start"), (len(frames) // 2, "mid"), (len(frames) - 1, "end")):
            path = root / Path(frames[target_index]["path"])
            with Image.open(path) as source:
                thumb = source.convert("RGBA").resize((96, 96), Image.Resampling.NEAREST)
                contact.alpha_composite(thumb, (x * 128 + 16, y * 128 + 16))
        _label(cdraw, record["effect_class"], (x * 128 + 4, y * 128 + 4))
        tx, ty = index % 5, index // 5
        y0 = ty * 108 + 20
        for frame in frames:
            fx = tx * 180 + 8 + int((frame["index"] / max(1, len(frames) - 1)) * 160)
            tdraw.line((tx * 180 + 8, y0, fx, y0), fill=_rgba_for(record["effect_class"], 150), width=4)
            tdraw.ellipse((fx - 3, y0 - 3, fx + 3, y0 + 3), fill=_rgba_for(record["effect_class"], 230))
        _label(tdraw, f"{record['effect_class']} {record['lifecycle']['duration_ms']}ms", (tx * 180 + 5, ty * 108 + 4))
    contact_path = output_root / "vfx-effect-contact-sheet-v0230.png"
    timing_path = output_root / "vfx-timing-qa-sheet-v0230.png"
    contact.save(contact_path, format="PNG", optimize=False, compress_level=9)
    timing.save(timing_path, format="PNG", optimize=False, compress_level=9)
    return contact_path, timing_path
