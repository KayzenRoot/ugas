"""Fail-closed VFX runtime correction for F-23R, F-26R and F-27R.

The v0.23.1 implementation remains a historical producer.  This module
reuses its class authority and deterministic fixture renderer, but owns the
corrected semantic allowlist, byte-producing fallback path and provenance
contract.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont

from . import vfx_asset_family_runtime_v0231 as base

VERSION = "0.23.2"
FAMILY_ID = base.FAMILY_ID
BASE_MAIN_SHA = "b08b9c3df74ef6a23046be396289e2fd72dc336b"
REJECTED_REVIEWED_HEAD = "136079540f674c7467d93bd28e9834addbfce5c3"
REGISTRY_MODE = base.REGISTRY_MODE
PRODUCTION_ROUTING = base.PRODUCTION_ROUTING
EFFECT_CLASSES = base.EFFECT_CLASSES
CLASS_SPECS = base.CLASS_SPECS
SEMANTIC_SCHEMAS = base.SEMANTIC_SCHEMAS
BLEND_MODES = base.BLEND_MODES
ALPHA_MODES = base.ALPHA_MODES
SPACES = base.SPACES
REPRESENTATIONS = base.REPRESENTATIONS
READ_ONLY = base.READ_ONLY
TEST_ONLY_SEMANTIC_KEYS = frozenset({"fixture_index", "fixture_seed", "visual_only", "gameplay_authority"})


class VFXAssetFamilyContractError(ValueError):
    def __init__(self, rejection_class: str, detail: str = "") -> None:
        self.rejection_class = rejection_class
        self.detail = detail
        super().__init__(f"{rejection_class}: {detail}" if detail else rejection_class)


canonical_json = base.canonical_json
sha256_bytes = base.sha256_bytes
sha256_file = base.sha256_file
write_json = base.write_json
strict_gate = base.strict_gate
strict_boolean_observation = base.strict_boolean_observation
validate_class_spec_table = base.validate_class_spec_table
validate_lifecycle = base.validate_lifecycle
validate_blend_alpha = base.validate_blend_alpha
validate_spatial_anchor = base.validate_spatial_anchor
validate_budget = base.validate_budget
validate_fallback = base.validate_fallback
validate_representation = base.validate_representation
validate_decoded_alpha = base.validate_decoded_alpha
validate_production_registry = base.validate_production_registry


def _require(condition: bool, rejection_class: str, detail: str) -> None:
    if not condition:
        raise VFXAssetFamilyContractError(rejection_class, detail)


def _authority_identity() -> dict[str, str]:
    payload = {"authority_type": "VFX_RUNTIME_CONTRACT", "path": "src/ugas/vfx_asset_family_runtime_v0232.py", "revision": VERSION}
    return {**payload, "sha256": sha256_bytes(canonical_json(payload))}


def _walk_forbidden(value: Any, path: str = "") -> str | None:
    return base._walk_forbidden(value, path)


def _allowed_semantic_keys(effect_class: str) -> set[str]:
    schema = SEMANTIC_SCHEMAS.get(effect_class)
    _require(isinstance(schema, Mapping), "VFX_SEMANTIC_CLASS_INVALID", effect_class)
    return set(schema) | set(TEST_ONLY_SEMANTIC_KEYS)


def validate_semantic_input(record: Mapping[str, Any]) -> None:
    effect_class = str(record.get("effect_class"))
    semantic = record.get("semantic_input")
    _require(isinstance(semantic, Mapping), "VFX_SEMANTIC_CLASS_INVALID", str(record.get("effect_id")))
    _require(semantic.get("effect_class") == effect_class and semantic.get("intent") == "VISUAL_ONLY", "VFX_SEMANTIC_CLASS_INVALID", str(record.get("effect_id")))
    forbidden = _walk_forbidden(semantic)
    _require(forbidden is None, "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN", forbidden or str(record.get("effect_id")))
    top_allowed = {"effect_id", "effect_class", "semantic_revision", "intent", "readability_role", "semantics", "registry_mode"}
    unknown_top = sorted(set(semantic) - top_allowed)
    _require(not unknown_top, "VFX_SEMANTIC_UNKNOWN_FIELD", f"semantic_input.{unknown_top[0] if unknown_top else effect_class}")
    semantics = semantic.get("semantics")
    _require(isinstance(semantics, Mapping), "VFX_SEMANTIC_CLASS_INVALID", effect_class)
    unknown = sorted(set(semantics) - _allowed_semantic_keys(effect_class))
    _require(not unknown, "VFX_SEMANTIC_UNKNOWN_FIELD", f"{effect_class}.semantics.{unknown[0] if unknown else effect_class}")
    _require(semantics.get("gameplay_authority") == "NONE" and semantics.get("visual_only") is True, "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN", effect_class)
    schema = SEMANTIC_SCHEMAS[effect_class]
    for key, checker in schema.items():
        _require(key in semantics and checker(semantics[key]), "VFX_SEMANTIC_TYPE_INVALID", f"{effect_class}.{key}")
    _require(isinstance(semantics.get("fixture_index"), int) and not isinstance(semantics.get("fixture_index"), bool), "VFX_SEMANTIC_TYPE_INVALID", f"{effect_class}.fixture_index")
    _require(isinstance(semantics.get("fixture_seed"), int) and not isinstance(semantics.get("fixture_seed"), bool), "VFX_SEMANTIC_TYPE_INVALID", f"{effect_class}.fixture_seed")


def validate_integration(record: Mapping[str, Any]) -> None:
    value = record.get("integration")
    authority = value.get("authority") if isinstance(value, Mapping) else None
    event = value.get("event_binding") if isinstance(value, Mapping) else None
    _require(isinstance(value, Mapping) and value.get("mode") == READ_ONLY and value.get("integration_revision") == "read-only-v1", "VFX_INTEGRATION_MODE_INVALID", str(record.get("effect_id")))
    _require(isinstance(authority, Mapping) and authority.get("authority_type") == "VFX_RUNTIME_CONTRACT" and authority.get("sha256") == _authority_identity()["sha256"], "VFX_INTEGRATION_AUTHORITY_STALE", str(record.get("effect_id")))
    _require(isinstance(event, Mapping) and event.get("read_only") is True and event.get("gameplay_authoritative") is False and event.get("event_id"), "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN", str(record.get("effect_id")))
    _require(value.get("no_gameplay_mutation") is True, "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN", str(record.get("effect_id")))


def build_effective_semantic_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    return {"family_id": record.get("family_id"), "schema_version": record.get("schema_version"), "effect_id": record.get("effect_id"), "effect_class": record.get("effect_class"), "stable_class_id": record.get("stable_class_id"), "intent": record.get("intent"), "semantic_input": record.get("semantic_input"), "lifecycle": record.get("lifecycle"), "blend_alpha": record.get("blend_alpha"), "spatial": record.get("spatial"), "budget_profile": record.get("budget_profile"), "fallback": record.get("fallback"), "representation": record.get("representation"), "integration": record.get("integration"), "authority_identity_hash": record.get("authority_identity_hash"), "frame_set_hash": record.get("frame_set_hash"), "content_hash": record.get("content_hash"), "test_only": record.get("test_only")}


def cache_key_for(record: Mapping[str, Any]) -> str:
    payload = {"semantic_contract": build_effective_semantic_payload(record), "semantic_input_hash": record.get("semantic_input_hash"), "content_hash": record.get("content_hash"), "authority_identity_hash": record.get("authority_identity_hash")}
    return sha256_bytes(canonical_json(payload))


def build_effect_fixture(effect_class: str, output_root: Path, index: int = 0) -> dict[str, Any]:
    record = base.build_effect_fixture(effect_class, output_root, index)
    semantic = deepcopy(record["semantic_input"])
    semantic["effect_id"] = semantic["effect_id"].replace("v0231", "v0232")
    semantic["semantic_revision"] = VERSION
    semantic["semantics"]["fixture_seed"] = 23200 + index
    record["effect_id"] = semantic["effect_id"]
    record["schema_version"] = VERSION
    record["semantic_input"] = semantic
    record["semantic_input_hash"] = sha256_bytes(canonical_json(semantic))
    record["integration"]["authority"] = _authority_identity()
    record["authority_identity_hash"] = record["integration"]["authority"]["sha256"]
    record["content_hash"] = sha256_bytes(canonical_json({"effect_id": record["effect_id"], "frame_set_hash": record["frame_set_hash"], "frames": record["frames"]}))
    record["provenance"] = {**record["provenance"], "generator": "deterministic-test-fixture-renderer-v0232", "seed": 23200 + index, "input_hash": "", "raw_semantic_input_hash": record["semantic_input_hash"], "output_hash": record["content_hash"], "effective_semantic_hash": ""}
    record["semantic_contract"] = build_effective_semantic_payload(record)
    record["semantic_contract_hash"] = sha256_bytes(canonical_json(record["semantic_contract"]))
    record["provenance"]["input_hash"] = record["semantic_contract_hash"]
    record["provenance"]["effective_semantic_hash"] = record["semantic_contract_hash"]
    record["cache_key"] = cache_key_for(record)
    validate_effect_record(record, output_root)
    return record


def validate_provenance(record: Mapping[str, Any], root: Path) -> None:
    value = record.get("provenance")
    _require(isinstance(value, Mapping) and value.get("generator") == "deterministic-test-fixture-renderer-v0232" and value.get("provider") is None and value.get("generation_model") is None and value.get("production_claim") is False, "VFX_PROVENANCE_INVALID", str(record.get("effect_id")))
    _require(value.get("input_hash") == record.get("semantic_contract_hash") and value.get("raw_semantic_input_hash") == record.get("semantic_input_hash") and value.get("output_hash") == record.get("content_hash") and value.get("effective_semantic_hash") == record.get("semantic_contract_hash"), "VFX_PROVENANCE_HASH_INVALID", str(record.get("effect_id")))
    for frame in record.get("frames", []):
        path = root / Path(str(frame["path"]))
        _require(path.is_file() and sha256_file(path) == frame.get("sha256"), "VFX_FRAME_HASH_INVALID", str(path))


def validate_effect_record(record: Mapping[str, Any], root: Path) -> None:
    _require(record.get("family_id") == FAMILY_ID and record.get("schema_version") == VERSION and record.get("registry_mode") == REGISTRY_MODE and record.get("test_only") is True, "VFX_RECORD_IDENTITY_INVALID", str(record.get("effect_id")))
    effect_class = str(record.get("effect_class"))
    _require(effect_class in CLASS_SPECS and record.get("stable_class_id") == CLASS_SPECS[effect_class]["stable_id"], "VFX_CLASS_IDENTITY_INVALID", str(record.get("effect_id")))
    validate_semantic_input(record)
    _require(record.get("semantic_input_hash") == sha256_bytes(canonical_json(record.get("semantic_input"))), "VFX_SEMANTIC_HASH_INVALID", str(record.get("effect_id")))
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


def generate_fixture_pack(output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    records = [build_effect_fixture(effect_class, output_root, index) for index, effect_class in enumerate(EFFECT_CLASSES)]
    manifest = {"schema_version": VERSION, "family_id": FAMILY_ID, "registry_mode": REGISTRY_MODE, "effect_classes": list(EFFECT_CLASSES), "effects": records, "production_routing": PRODUCTION_ROUTING, "production_approved": False, "new_generation": 0, "real_vfx_asset_coverage": "NONE", "synthetic_vfx_fixture": REGISTRY_MODE}
    validate_vfx_manifest(manifest, output_root)
    return {"manifest": manifest, "records": records}


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
    required = ("profile_id", "max_particles_per_instance", "max_layers", "max_spawn_events_per_second", "max_visual_area_ratio", "supported_steps")
    _require(all(key in constraint_profile for key in required), "VFX_FALLBACK_PROFILE_INVALID", str(record.get("effect_id")))
    _require(all(isinstance(constraint_profile[key], (int, float)) and not isinstance(constraint_profile[key], bool) and float(constraint_profile[key]) > 0 for key in required[1:5]), "VFX_FALLBACK_PROFILE_INVALID", str(record.get("effect_id")))
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


def _alpha_bounds(image: Image.Image) -> list[int] | None:
    box = image.getchannel("A").getbbox()
    return list(box) if box else None


def _render_frame(source: Image.Image, state: Mapping[str, Any], index: int, before: Mapping[str, Any]) -> Image.Image:
    image = source.convert("RGBA")
    scale = min(float(state.get("radius", 1.0)), math.sqrt(max(0.01, float(state.get("visual_area_ratio", 1.0)) / max(0.01, float(before.get("visual_area_ratio", 1.0))))))
    if scale < 0.999:
        width = max(1, int(round(image.width * scale))); height = max(1, int(round(image.height * scale)))
        resized = image.resize((width, height), Image.Resampling.NEAREST)
        canvas = Image.new("RGBA", image.size, (0, 0, 0, 0)); canvas.alpha_composite(resized, ((image.width - width) // 2, (image.height - height) // 2)); image = canvas
    opacity = float(state.get("opacity", 1.0))
    particle_factor = min(1.0, float(state.get("particles", before["particles"])) / max(1.0, float(before["particles"])))
    layer_factor = min(1.0, float(state.get("layers", before["layers"])) / max(1.0, float(before["layers"])))
    spawn_factor = min(1.0, float(state.get("spawn_rate", before["spawn_rate"])) / max(1.0, float(before["spawn_rate"])))
    attenuation = opacity * min(particle_factor, layer_factor, spawn_factor)
    if attenuation < 0.999:
        alpha = image.getchannel("A").point(lambda value: max(0, min(255, int(round(value * attenuation)))))
        image.putalpha(alpha)
    if particle_factor < 0.999 and image.getbbox() is not None:
        pixels = image.load()
        stride = max(2, int(round(1.0 / max(0.1, particle_factor))))
        for y in range(image.height):
            for x in range(image.width):
                if (x + y + index) % stride == 0:
                    red, green, blue, alpha_value = pixels[x, y]
                    pixels[x, y] = (red, green, blue, max(0, alpha_value // 2))
    return image


def render_fallback_output(record: Mapping[str, Any], result: Mapping[str, Any], source_root: Path, output_root: Path, *, force_skip: bool = False) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    skip = force_skip or result["after"].get("visible") is False
    semantic_identity = {"effect_id": record["effect_id"], "effect_class": record["effect_class"], "stable_class_id": record["stable_class_id"], "semantic_input_hash": record["semantic_input_hash"], "semantic_contract_hash": record["semantic_contract_hash"], "visual_only": True, "gameplay_authority": "NONE"}
    if skip:
        return {"status": "SKIPPED", "terminal_step": "SKIP_VISUAL", "skipped_output": {"status": "SKIPPED_VISUAL", "reason": "terminal fallback step emitted no visual bytes"}, "effect_id": record["effect_id"], "semantic_identity": semantic_identity, "output_hash": sha256_bytes(canonical_json({"effect_id": record["effect_id"], "status": "SKIPPED", "frames": []})), "frames": [], "semantic_preserved": True, "changes_gameplay": False, "degradation_mechanisms": [*result["applied_steps"], "SKIP_VISUAL"]}
    frames: list[dict[str, Any]] = []
    source_frames = record["frames"]
    count = int(result["after"]["frame_count"])
    indexes = [min(len(source_frames) - 1, round(i * (len(source_frames) - 1) / max(1, count - 1))) for i in range(count)]
    frame_dir = output_root / "frames" / record["effect_class"]
    frame_dir.mkdir(parents=True, exist_ok=True)
    for output_index, source_index in enumerate(indexes):
        source_path = source_root / Path(source_frames[source_index]["path"])
        with Image.open(source_path) as source:
            image = _render_frame(source, result["after"], output_index, result["before"])
        path = frame_dir / f"{output_index:02d}.png"; image.save(path, format="PNG", optimize=False, compress_level=9)
        with Image.open(path) as check:
            rgba = check.convert("RGBA")
            frames.append({"index": output_index, "source_index": source_index, "path": path.relative_to(output_root).as_posix(), "sha256": sha256_file(path), "width": rgba.width, "height": rgba.height, "alpha_bounds": _alpha_bounds(rgba), "alpha_range": list(rgba.getchannel("A").getextrema())})
    output_hash = sha256_bytes(canonical_json({"effect_id": record["effect_id"], "profile_id": result["profile_id"], "frames": frames}))
    return {"status": "DEGRADED", "effect_id": record["effect_id"], "profile_id": result["profile_id"], "semantic_identity": semantic_identity, "frames": frames, "frame_count": len(frames), "output_hash": output_hash, "full_content_hash": record["content_hash"], "semantic_preserved": True, "changes_gameplay": False, "degradation_mechanisms": list(result["applied_steps"]), "fallback_result": result}


def validate_degraded_output(record: Mapping[str, Any], output: Mapping[str, Any], root: Path) -> None:
    _require(output.get("effect_id") == record.get("effect_id") and output.get("semantic_preserved") is True and output.get("changes_gameplay") is False, "VFX_DEGRADED_OUTPUT_SEMANTIC_INVALID", str(record.get("effect_id")))
    _require(output.get("semantic_identity", {}).get("semantic_contract_hash") == record.get("semantic_contract_hash") and output.get("semantic_identity", {}).get("gameplay_authority") == "NONE", "VFX_DEGRADED_OUTPUT_SEMANTIC_INVALID", str(record.get("effect_id")))
    if output.get("status") == "SKIPPED":
        _require(output.get("terminal_step") == "SKIP_VISUAL" and output.get("skipped_output", {}).get("status") == "SKIPPED_VISUAL", "VFX_FALLBACK_SKIP_RECORD_INVALID", str(record.get("effect_id")))
        return
    _require(output.get("status") == "DEGRADED" and output.get("frames"), "VFX_DEGRADED_OUTPUT_INVALID", str(record.get("effect_id")))
    actual = []
    for frame in output["frames"]:
        path = root / Path(frame["path"]); _require(path.is_file() and sha256_file(path) == frame.get("sha256"), "VFX_DEGRADED_FRAME_HASH_INVALID", str(path)); actual.append(frame)
    _require(output.get("output_hash") == sha256_bytes(canonical_json({"effect_id": record["effect_id"], "profile_id": output["profile_id"], "frames": actual})), "VFX_DEGRADED_OUTPUT_HASH_INVALID", str(record.get("effect_id")))
    _require(output.get("output_hash") != record.get("content_hash"), "VFX_DEGRADED_OUTPUT_UNCHANGED", str(record.get("effect_id")))


def build_contact_sheets(records: list[Mapping[str, Any]], root: Path, output_root: Path) -> tuple[Path, Path]:
    contact = Image.new("RGBA", (5 * 128, 2 * 128), (18, 22, 34, 255)); timing = Image.new("RGBA", (5 * 180, 2 * 108), (18, 22, 34, 255)); cdraw, tdraw = ImageDraw.Draw(contact), ImageDraw.Draw(timing); font = ImageFont.load_default()
    for index, record in enumerate(records):
        x, y = index % 5, index // 5; frames = record["frames"]
        for target_index in (0, len(frames) // 2, len(frames) - 1):
            with Image.open(root / Path(frames[target_index]["path"])) as source: contact.alpha_composite(source.convert("RGBA").resize((96, 96), Image.Resampling.NEAREST), (x * 128 + 16, y * 128 + 16))
        cdraw.text((x * 128 + 4, y * 128 + 4), record["effect_class"], fill=(235, 235, 235, 255), font=font)
        y0 = y * 108 + 20
        for frame in frames:
            fx = x * 180 + 8 + int((frame["index"] / max(1, len(frames) - 1)) * 160); tdraw.ellipse((fx - 3, y0 - 3, fx + 3, y0 + 3), fill=(230, 230, 230, 230))
        tdraw.text((x * 180 + 5, y * 108 + 4), f"{record['effect_class']} {record['lifecycle']['duration_ms']}ms", fill=(235, 235, 235, 255), font=font)
    contact_path = output_root / "vfx-effect-contact-sheet-v0232.png"; timing_path = output_root / "vfx-timing-qa-sheet-v0232.png"; contact.save(contact_path, format="PNG", optimize=False, compress_level=9); timing.save(timing_path, format="PNG", optimize=False, compress_level=9); return contact_path, timing_path


def build_budget_fallback_sheet(full_root: Path, degraded_root: Path, full: Mapping[str, Any], degraded: Mapping[str, Any], output_path: Path) -> Path:
    image = Image.new("RGBA", (640, 160), (18, 22, 34, 255)); draw = ImageDraw.Draw(image); font = ImageFont.load_default()
    with Image.open(full_root / Path(full["frames"][0]["path"])) as source: image.alpha_composite(source.convert("RGBA").resize((128, 128), Image.Resampling.NEAREST), (16, 24))
    if degraded.get("frames"):
        with Image.open(degraded_root / Path(degraded["frames"][0]["path"])) as source: image.alpha_composite(source.convert("RGBA").resize((128, 128), Image.Resampling.NEAREST), (336, 24))
    else:
        draw.rectangle((336, 24, 464, 152), outline=(220, 80, 80, 255), width=2)
    draw.text((16, 6), f"FULL {full['effect_class']} actual frame", fill=(235, 235, 235, 255), font=font); draw.text((336, 6), f"DEGRADED {degraded.get('status')} actual output", fill=(235, 235, 235, 255), font=font); draw.text((480, 42), f"steps={','.join(degraded.get('degradation_mechanisms', []))}", fill=(235, 235, 235, 255), font=font); draw.text((480, 78), "semantic_preserved=True", fill=(235, 235, 235, 255), font=font); draw.text((480, 104), "gameplay_authority=NONE", fill=(235, 235, 235, 255), font=font)
    output_path.parent.mkdir(parents=True, exist_ok=True); image.save(output_path, format="PNG", optimize=False, compress_level=9); return output_path
