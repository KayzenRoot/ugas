"""Fail-closed VFX runtime correction for F-29R.

This module is deliberately forward-only. The v0.23.3 runtime and evidence
remain historical; this layer preserves the validated runtime behavior while
binding the v0.23.4 correction to the exact historical-tree proof.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

from . import vfx_asset_family_runtime_v0232 as base

VERSION = "0.23.4"
FAMILY_ID = base.FAMILY_ID
BASE_MAIN_SHA = "b08b9c3df74ef6a23046be396289e2fd72dc336b"
REJECTED_REVIEWED_HEAD = "9eda08b25a674a5423a99d35a42711102df91b8b"
HISTORICAL_V0230_REF = "c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72"
HISTORICAL_V0231_REF = "136079540f674c7467d93bd28e9834addbfce5c3"
REGISTRY_MODE = base.REGISTRY_MODE
PRODUCTION_ROUTING = base.PRODUCTION_ROUTING
EFFECT_CLASSES = base.EFFECT_CLASSES
CLASS_SPECS = base.CLASS_SPECS
SEMANTIC_SCHEMAS = base.SEMANTIC_SCHEMAS
READ_ONLY = base.READ_ONLY

VFXAssetFamilyContractError = base.VFXAssetFamilyContractError
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
validate_representation = base.validate_representation
validate_decoded_alpha = base.validate_decoded_alpha
validate_production_registry = base.validate_production_registry


def _require(condition: bool, rejection_class: str, detail: str) -> None:
    if not condition:
        raise VFXAssetFamilyContractError(rejection_class, detail)


def _authority_identity() -> dict[str, str]:
    payload = {
        "authority_type": "VFX_RUNTIME_CONTRACT",
        "path": "src/ugas/vfx_asset_family_runtime_v0234.py",
        "revision": VERSION,
    }
    return {**payload, "sha256": sha256_bytes(canonical_json(payload))}


def _allowed_semantic_keys(effect_class: str) -> set[str]:
    schema = SEMANTIC_SCHEMAS.get(effect_class)
    _require(isinstance(schema, Mapping), "VFX_SEMANTIC_CLASS_INVALID", effect_class)
    return set(schema) | {"fixture_index", "fixture_seed", "visual_only", "gameplay_authority"}


def validate_semantic_input(record: Mapping[str, Any]) -> None:
    # v0.23.2 already owns the exact per-class allowlist.  Calling it here
    # keeps the semantic authority singular while this module owns the new
    # fallback/output contracts.
    base.validate_semantic_input(record)
    effect_class = str(record.get("effect_class"))
    semantic = record.get("semantic_input")
    _require(isinstance(semantic, Mapping), "VFX_SEMANTIC_CLASS_INVALID", effect_class)
    semantics = semantic.get("semantics")
    _require(isinstance(semantics, Mapping), "VFX_SEMANTIC_CLASS_INVALID", effect_class)
    _require(set(semantics) <= _allowed_semantic_keys(effect_class), "VFX_SEMANTIC_UNKNOWN_FIELD", effect_class)


def build_effective_semantic_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "family_id": record.get("family_id"),
        "schema_version": record.get("schema_version"),
        "effect_id": record.get("effect_id"),
        "effect_class": record.get("effect_class"),
        "stable_class_id": record.get("stable_class_id"),
        "intent": record.get("intent"),
        "semantic_input": record.get("semantic_input"),
        "lifecycle": record.get("lifecycle"),
        "blend_alpha": record.get("blend_alpha"),
        "spatial": record.get("spatial"),
        "budget_profile": record.get("budget_profile"),
        "fallback": record.get("fallback"),
        "representation": record.get("representation"),
        "integration": record.get("integration"),
        "authority_identity_hash": record.get("authority_identity_hash"),
        "frame_set_hash": record.get("frame_set_hash"),
        "content_hash": record.get("content_hash"),
        "test_only": record.get("test_only"),
    }


def cache_key_for(record: Mapping[str, Any]) -> str:
    payload = {
        "semantic_contract": build_effective_semantic_payload(record),
        "semantic_input_hash": record.get("semantic_input_hash"),
        "content_hash": record.get("content_hash"),
        "authority_identity_hash": record.get("authority_identity_hash"),
    }
    return sha256_bytes(canonical_json(payload))


def build_effect_fixture(effect_class: str, output_root: Path, index: int = 0) -> dict[str, Any]:
    record = base.build_effect_fixture(effect_class, output_root, index)
    semantic = deepcopy(record["semantic_input"])
    semantic["effect_id"] = semantic["effect_id"].replace("v0232", "v0234")
    semantic["semantic_revision"] = VERSION
    semantic["semantics"]["fixture_seed"] = 23400 + index
    record["effect_id"] = semantic["effect_id"]
    record["schema_version"] = VERSION
    record["semantic_input"] = semantic
    record["semantic_input_hash"] = sha256_bytes(canonical_json(semantic))
    record["integration"]["authority"] = _authority_identity()
    record["authority_identity_hash"] = record["integration"]["authority"]["sha256"]
    record["content_hash"] = sha256_bytes(
        canonical_json(
            {
                "effect_id": record["effect_id"],
                "frame_set_hash": record["frame_set_hash"],
                "frames": record["frames"],
            }
        )
    )
    record["provenance"] = {
        **record["provenance"],
        "generator": "deterministic-test-fixture-renderer-v0234",
        "seed": 23400 + index,
        "input_hash": "",
        "raw_semantic_input_hash": record["semantic_input_hash"],
        "output_hash": record["content_hash"],
        "effective_semantic_hash": "",
    }
    record["semantic_contract"] = build_effective_semantic_payload(record)
    record["semantic_contract_hash"] = sha256_bytes(canonical_json(record["semantic_contract"]))
    record["provenance"]["input_hash"] = record["semantic_contract_hash"]
    record["provenance"]["effective_semantic_hash"] = record["semantic_contract_hash"]
    record["cache_key"] = cache_key_for(record)
    validate_effect_record(record, output_root)
    return record


def validate_integration(record: Mapping[str, Any]) -> None:
    value = record.get("integration")
    authority = value.get("authority") if isinstance(value, Mapping) else None
    event = value.get("event_binding") if isinstance(value, Mapping) else None
    _require(
        isinstance(value, Mapping)
        and value.get("mode") == READ_ONLY
        and value.get("integration_revision") == "read-only-v1",
        "VFX_INTEGRATION_MODE_INVALID",
        str(record.get("effect_id")),
    )
    _require(
        isinstance(authority, Mapping)
        and authority.get("authority_type") == "VFX_RUNTIME_CONTRACT"
        and authority.get("sha256") == _authority_identity()["sha256"],
        "VFX_INTEGRATION_AUTHORITY_STALE",
        str(record.get("effect_id")),
    )
    _require(
        isinstance(event, Mapping)
        and event.get("read_only") is True
        and event.get("gameplay_authoritative") is False
        and event.get("event_id"),
        "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN",
        str(record.get("effect_id")),
    )
    _require(value.get("no_gameplay_mutation") is True, "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN", str(record.get("effect_id")))


def validate_provenance(record: Mapping[str, Any], root: Path) -> None:
    value = record.get("provenance")
    _require(
        isinstance(value, Mapping)
        and value.get("generator") == "deterministic-test-fixture-renderer-v0234"
        and value.get("provider") is None
        and value.get("generation_model") is None
        and value.get("production_claim") is False,
        "VFX_PROVENANCE_INVALID",
        str(record.get("effect_id")),
    )
    _require(
        value.get("input_hash") == record.get("semantic_contract_hash")
        and value.get("raw_semantic_input_hash") == record.get("semantic_input_hash")
        and value.get("output_hash") == record.get("content_hash")
        and value.get("effective_semantic_hash") == record.get("semantic_contract_hash"),
        "VFX_PROVENANCE_HASH_INVALID",
        str(record.get("effect_id")),
    )
    for frame in record.get("frames", []):
        path = root / Path(str(frame["path"]))
        _require(path.is_file() and sha256_file(path) == frame.get("sha256"), "VFX_FRAME_HASH_INVALID", str(path))


def validate_effect_record(record: Mapping[str, Any], root: Path) -> None:
    _require(
        record.get("family_id") == FAMILY_ID
        and record.get("schema_version") == VERSION
        and record.get("registry_mode") == REGISTRY_MODE
        and record.get("test_only") is True,
        "VFX_RECORD_IDENTITY_INVALID",
        str(record.get("effect_id")),
    )
    effect_class = str(record.get("effect_class"))
    _require(
        effect_class in CLASS_SPECS and record.get("stable_class_id") == CLASS_SPECS[effect_class]["stable_id"],
        "VFX_CLASS_IDENTITY_INVALID",
        str(record.get("effect_id")),
    )
    validate_semantic_input(record)
    _require(
        record.get("semantic_input_hash") == sha256_bytes(canonical_json(record.get("semantic_input"))),
        "VFX_SEMANTIC_HASH_INVALID",
        str(record.get("effect_id")),
    )
    validate_lifecycle(record)
    validate_blend_alpha(record)
    base.validate_spatial_anchor(record)
    base.validate_budget(record)
    base.validate_fallback(record)
    base.validate_representation(record)
    validate_integration(record)
    frame_set_hash = sha256_bytes(canonical_json([item.get("sha256") for item in record.get("frames", [])]))
    _require(frame_set_hash == record.get("frame_set_hash"), "VFX_FRAME_SET_HASH_INVALID", str(record.get("effect_id")))
    content_hash = sha256_bytes(
        canonical_json({"effect_id": record.get("effect_id"), "frame_set_hash": frame_set_hash, "frames": record.get("frames")})
    )
    _require(content_hash == record.get("content_hash"), "VFX_CONTENT_HASH_INVALID", str(record.get("effect_id")))
    validate_decoded_alpha(record, root)
    expected_contract = build_effective_semantic_payload(record)
    _require(
        record.get("semantic_contract") == expected_contract
        and record.get("semantic_contract_hash") == sha256_bytes(canonical_json(expected_contract)),
        "VFX_SEMANTIC_CONTRACT_HASH_INVALID",
        str(record.get("effect_id")),
    )
    _require(record.get("cache_key") == cache_key_for(record), "VFX_CACHE_KEY_INVALID", str(record.get("effect_id")))
    validate_provenance(record, root)


def validate_vfx_manifest(manifest: Mapping[str, Any], root: Path | None = None) -> dict[str, Any]:
    validate_class_spec_table()
    _require(
        manifest.get("schema_version") == VERSION
        and manifest.get("family_id") == FAMILY_ID
        and manifest.get("registry_mode") == REGISTRY_MODE,
        "VFX_MANIFEST_IDENTITY_INVALID",
        "manifest",
    )
    records = manifest.get("effects")
    _require(
        isinstance(records, list)
        and len(records) == len(EFFECT_CLASSES)
        and tuple(item.get("effect_class") for item in records) == EFFECT_CLASSES,
        "VFX_MANIFEST_CLASS_SET_INVALID",
        "manifest",
    )
    _require(len({item.get("effect_id") for item in records}) == len(records), "VFX_EFFECT_ID_DUPLICATE", "manifest")
    if root is not None:
        for item in records:
            validate_effect_record(item, root)
    return {"status": "VFX_ASSET_FAMILY_MANIFEST_VALID", "effect_count": len(records), "classes": list(EFFECT_CLASSES)}


def generate_fixture_pack(output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    records = [build_effect_fixture(effect_class, output_root, index) for index, effect_class in enumerate(EFFECT_CLASSES)]
    manifest = {
        "schema_version": VERSION,
        "family_id": FAMILY_ID,
        "registry_mode": REGISTRY_MODE,
        "effect_classes": list(EFFECT_CLASSES),
        "effects": records,
        "production_routing": PRODUCTION_ROUTING,
        "production_approved": False,
        "new_generation": 0,
        "real_vfx_asset_coverage": "NONE",
        "synthetic_vfx_fixture": REGISTRY_MODE,
    }
    validate_vfx_manifest(manifest, output_root)
    return {"manifest": manifest, "records": records}


def _fallback_state(record: Mapping[str, Any]) -> dict[str, Any]:
    budget = record["budget_profile"]
    return {
        "visible": True,
        "particles": budget["max_particles_per_instance"],
        "layers": budget["max_layers"],
        "spawn_rate": budget["max_spawn_events_per_second"],
        "visual_area_ratio": budget["max_visual_area_ratio"],
        "opacity": 1.0,
        "frame_count": record["lifecycle"]["frame_count"],
        "radius": 1.0,
    }


def _apply_step(state: dict[str, Any], step: str, profile: Mapping[str, Any]) -> None:
    base._apply_step(state, step, profile)


def _validate_profile(record: Mapping[str, Any], profile: Mapping[str, Any]) -> None:
    required = (
        "profile_id",
        "max_particles_per_instance",
        "max_layers",
        "max_spawn_events_per_second",
        "max_visual_area_ratio",
        "supported_steps",
    )
    _require(all(key in profile for key in required), "VFX_FALLBACK_PROFILE_INVALID", str(record.get("effect_id")))
    _require(
        all(isinstance(profile[key], (int, float)) and not isinstance(profile[key], bool) and float(profile[key]) > 0 for key in required[1:5]),
        "VFX_FALLBACK_PROFILE_INVALID",
        str(record.get("effect_id")),
    )
    _require(isinstance(profile["supported_steps"], list), "VFX_FALLBACK_PROFILE_INVALID", str(record.get("effect_id")))


def _replay_fallback(record: Mapping[str, Any], profile: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    _validate_profile(record, profile)
    ordered = list(record["fallback"]["ordered_steps"])
    unsupported = [step for step in ordered if step not in profile["supported_steps"]]
    _require(not unsupported, "VFX_FALLBACK_UNSUPPORTED_STEP", ",".join(unsupported))
    before = _fallback_state(record)
    after = deepcopy(before)
    applied: list[str] = []
    for step in ordered:
        if (
            after["particles"] > profile["max_particles_per_instance"]
            or after["layers"] > profile["max_layers"]
            or after["spawn_rate"] > profile["max_spawn_events_per_second"]
            or after["visual_area_ratio"] > profile["max_visual_area_ratio"]
        ):
            _apply_step(after, step, profile)
            applied.append(step)
    _require(
        after["particles"] <= profile["max_particles_per_instance"]
        and after["layers"] <= profile["max_layers"]
        and after["spawn_rate"] <= profile["max_spawn_events_per_second"]
        and after["visual_area_ratio"] <= profile["max_visual_area_ratio"],
        "VFX_FALLBACK_CONSTRAINT_UNSATISFIED",
        str(record.get("effect_id")),
    )
    return before, after, applied


def select_fallback(record: Mapping[str, Any], constraint_profile: Mapping[str, Any]) -> dict[str, Any]:
    before, after, applied = _replay_fallback(record, constraint_profile)
    result = {
        "effect_id": record["effect_id"],
        "profile_id": constraint_profile["profile_id"],
        "deterministic": True,
        "fallback_order": list(record["fallback"]["ordered_steps"]),
        "applied_steps": applied,
        "before": before,
        "after": after,
        "visual_degraded": before != after,
        "semantic_preserved": True,
        "changes_gameplay": False,
        "constraint_profile": deepcopy(dict(constraint_profile)),
    }
    validate_fallback_result(record, result, constraint_profile)
    return result


def validate_fallback_result(record: Mapping[str, Any], result: Mapping[str, Any], constraint_profile: Mapping[str, Any]) -> None:
    _validate_profile(record, constraint_profile)
    _require(
        result.get("effect_id") == record.get("effect_id")
        and result.get("profile_id") == constraint_profile.get("profile_id")
        and result.get("deterministic") is True
        and result.get("semantic_preserved") is True
        and result.get("changes_gameplay") is False,
        "VFX_FALLBACK_RESULT_INVALID",
        str(record.get("effect_id")),
    )
    expected_before, expected_after, expected_applied = _replay_fallback(record, constraint_profile)
    _require(result.get("fallback_order") == list(record["fallback"]["ordered_steps"]), "VFX_FALLBACK_ORDER_INVALID", str(record.get("effect_id")))
    _require(result.get("applied_steps") == expected_applied, "VFX_FALLBACK_ORDER_INVALID", str(record.get("effect_id")))
    _require(result.get("before") == expected_before and result.get("after") == expected_after, "VFX_FALLBACK_STATE_INVALID", str(record.get("effect_id")))
    _require(result.get("visual_degraded") is (expected_before != expected_after), "VFX_FALLBACK_RESULT_INVALID", str(record.get("effect_id")))


def _alpha_bounds(image: Image.Image) -> list[int] | None:
    box = image.getchannel("A").getbbox()
    return list(box) if box else None


def _alpha_sum(image: Image.Image) -> int:
    return sum(image.getchannel("A").getdata())


def _bbox_area(bounds: list[int] | None) -> int:
    if not bounds:
        return 0
    return max(0, bounds[2] - bounds[0]) * max(0, bounds[3] - bounds[1])


def _frame_indexes(record: Mapping[str, Any], count: int) -> list[int]:
    source_frames = record["frames"]
    return [min(len(source_frames) - 1, round(i * (len(source_frames) - 1) / max(1, count - 1))) for i in range(count)]


def render_fallback_output(
    record: Mapping[str, Any],
    result: Mapping[str, Any],
    source_root: Path,
    output_root: Path,
    *,
    force_skip: bool = False,
) -> dict[str, Any]:
    _validate_profile(record, result.get("constraint_profile", {}))
    validate_fallback_result(record, result, result["constraint_profile"])
    output_root.mkdir(parents=True, exist_ok=True)
    semantic_identity = {
        "effect_id": record["effect_id"],
        "effect_class": record["effect_class"],
        "stable_class_id": record["stable_class_id"],
        "semantic_input_hash": record["semantic_input_hash"],
        "semantic_contract_hash": record["semantic_contract_hash"],
        "visual_only": True,
        "gameplay_authority": "NONE",
    }
    if force_skip:
        return {
            "status": "SKIPPED",
            "terminal_step": "SKIP_VISUAL",
            "skipped_output": {"status": "SKIPPED_VISUAL", "reason": "terminal fallback step emitted no visual bytes"},
            "effect_id": record["effect_id"],
            "profile_id": result["profile_id"],
            "semantic_identity": semantic_identity,
            "fallback_result": deepcopy(dict(result)),
            "fallback_profile": deepcopy(dict(result["constraint_profile"])),
            "output_hash": sha256_bytes(canonical_json({"effect_id": record["effect_id"], "status": "SKIPPED", "frames": []})),
            "frames": [],
            "semantic_preserved": True,
            "changes_gameplay": False,
            "degradation_mechanisms": [*result["applied_steps"], "SKIP_VISUAL"],
        }
    frames: list[dict[str, Any]] = []
    indexes = _frame_indexes(record, int(result["after"]["frame_count"]))
    frame_dir = output_root / "frames" / record["effect_class"]
    frame_dir.mkdir(parents=True, exist_ok=True)
    for output_index, source_index in enumerate(indexes):
        source_path = source_root / Path(record["frames"][source_index]["path"])
        with Image.open(source_path) as source:
            image = base._render_frame(source, result["after"], output_index, result["before"])
        path = frame_dir / f"{output_index:02d}.png"
        image.save(path, format="PNG", optimize=False, compress_level=9)
        with Image.open(path) as check:
            rgba = check.convert("RGBA")
            frames.append(
                {
                    "index": output_index,
                    "source_index": source_index,
                    "path": path.relative_to(output_root).as_posix(),
                    "sha256": sha256_file(path),
                    "width": rgba.width,
                    "height": rgba.height,
                    "alpha_bounds": _alpha_bounds(rgba),
                    "alpha_range": list(rgba.getchannel("A").getextrema()),
                }
            )
    output_hash = sha256_bytes(
        canonical_json(
            {
                "effect_id": record["effect_id"],
                "profile_id": result["profile_id"],
                "fallback_result": result,
                "frames": frames,
            }
        )
    )
    return {
        "status": "DEGRADED",
        "effect_id": record["effect_id"],
        "profile_id": result["profile_id"],
        "semantic_identity": semantic_identity,
        "fallback_result": deepcopy(dict(result)),
        "fallback_profile": deepcopy(dict(result["constraint_profile"])),
        "frames": frames,
        "frame_count": len(frames),
        "output_hash": output_hash,
        "full_content_hash": record["content_hash"],
        "semantic_preserved": True,
        "changes_gameplay": False,
        "degradation_mechanisms": list(result["applied_steps"]),
    }


def _expected_output_hash(record: Mapping[str, Any], output: Mapping[str, Any], frames: list[Mapping[str, Any]]) -> str:
    return sha256_bytes(
        canonical_json(
            {
                "effect_id": record["effect_id"],
                "profile_id": output["profile_id"],
                "fallback_result": output["fallback_result"],
                "frames": frames,
            }
        )
    )


def validate_degraded_output(
    record: Mapping[str, Any],
    output: Mapping[str, Any],
    source_root: Path,
    output_root: Path,
) -> None:
    _require(
        output.get("effect_id") == record.get("effect_id")
        and output.get("semantic_preserved") is True
        and output.get("changes_gameplay") is False,
        "VFX_DEGRADED_OUTPUT_SEMANTIC_INVALID",
        str(record.get("effect_id")),
    )
    identity = output.get("semantic_identity")
    _require(
        isinstance(identity, Mapping)
        and identity.get("semantic_input_hash") == record.get("semantic_input_hash")
        and identity.get("semantic_contract_hash") == record.get("semantic_contract_hash")
        and identity.get("effect_class") == record.get("effect_class")
        and identity.get("stable_class_id") == record.get("stable_class_id")
        and identity.get("visual_only") is True
        and identity.get("gameplay_authority") == "NONE",
        "VFX_DEGRADED_OUTPUT_SEMANTIC_INVALID",
        str(record.get("effect_id")),
    )
    result = output.get("fallback_result")
    profile = output.get("fallback_profile")
    _require(isinstance(result, Mapping) and isinstance(profile, Mapping), "VFX_FALLBACK_RESULT_INVALID", str(record.get("effect_id")))
    validate_fallback_result(record, result, profile)
    expected_mechanisms = list(result["applied_steps"])
    if output.get("status") == "SKIPPED":
        _require(
            output.get("terminal_step") == "SKIP_VISUAL"
            and output.get("skipped_output", {}).get("status") == "SKIPPED_VISUAL"
            and output.get("frames") == []
            and output.get("degradation_mechanisms") == [*expected_mechanisms, "SKIP_VISUAL"],
            "VFX_FALLBACK_SKIP_RECORD_INVALID",
            str(record.get("effect_id")),
        )
        return
    _require(output.get("status") == "DEGRADED", "VFX_DEGRADED_OUTPUT_INVALID", str(record.get("effect_id")))
    _require(output.get("degradation_mechanisms") == expected_mechanisms, "VFX_FALLBACK_MECHANISM_INVALID", str(record.get("effect_id")))
    frames = output.get("frames")
    _require(isinstance(frames, list) and frames, "VFX_DEGRADED_OUTPUT_INVALID", str(record.get("effect_id")))
    expected_indexes = _frame_indexes(record, int(result["after"]["frame_count"]))
    _require(len(frames) == len(expected_indexes) and output.get("frame_count") == len(expected_indexes), "VFX_FRAME_COUNT_INVALID", str(record.get("effect_id")))
    for output_index, (frame, source_index) in enumerate(zip(frames, expected_indexes)):
        _require(frame.get("index") == output_index and frame.get("source_index") == source_index, "VFX_FRAME_SELECTION_INVALID", str(record.get("effect_id")))
        path = output_root / Path(str(frame.get("path")))
        _require(path.is_file() and sha256_file(path) == frame.get("sha256"), "VFX_DEGRADED_FRAME_HASH_INVALID", str(path))
        with Image.open(path) as actual_image:
            actual = actual_image.convert("RGBA")
            _require(frame.get("width") == actual.width and frame.get("height") == actual.height, "VFX_DEGRADED_FRAME_METADATA_INVALID", str(path))
            _require(frame.get("alpha_bounds") == _alpha_bounds(actual) and frame.get("alpha_range") == list(actual.getchannel("A").getextrema()), "VFX_DEGRADED_FRAME_METADATA_INVALID", str(path))
            source_path = source_root / Path(record["frames"][source_index]["path"])
            with Image.open(source_path) as source_image:
                expected = base._render_frame(source_image, result["after"], output_index, result["before"])
                _require(actual.tobytes() == expected.convert("RGBA").tobytes(), "VFX_DEGRADED_PIXELS_INVALID", str(path))
                source_rgba = source_image.convert("RGBA")
                source_alpha_sum = _alpha_sum(source_rgba)
                degraded_alpha_sum = _alpha_sum(actual)
                if "REDUCE_OPACITY" in expected_mechanisms:
                    _require(result["after"]["opacity"] < result["before"]["opacity"] and degraded_alpha_sum < source_alpha_sum, "VFX_DEGRADED_OPACITY_METRIC_INVALID", str(path))
                if "REDUCE_PARTICLE_COUNT" in expected_mechanisms or "REDUCE_LAYER_COUNT" in expected_mechanisms or "REDUCE_SPAWN_RATE" in expected_mechanisms:
                    _require(degraded_alpha_sum < source_alpha_sum, "VFX_DEGRADED_BUDGET_METRIC_INVALID", str(path))
                if "REDUCE_RADIUS" in expected_mechanisms or "REDUCE_VISUAL_AREA" in expected_mechanisms:
                    source_bounds = _alpha_bounds(source_rgba)
                    degraded_bounds = _alpha_bounds(actual)
                    _require(_bbox_area(degraded_bounds) < _bbox_area(source_bounds), "VFX_DEGRADED_AREA_METRIC_INVALID", str(path))
    _require(output.get("output_hash") == _expected_output_hash(record, output, frames), "VFX_DEGRADED_OUTPUT_HASH_INVALID", str(record.get("effect_id")))
    _require(output.get("output_hash") != record.get("content_hash"), "VFX_DEGRADED_OUTPUT_UNCHANGED", str(record.get("effect_id")))


def validate_degraded_determinism(first: Mapping[str, Any], repeat: Mapping[str, Any]) -> None:
    _require(
        first.get("status") == "DEGRADED"
        and repeat.get("status") == "DEGRADED"
        and first.get("effect_id") == repeat.get("effect_id")
        and first.get("profile_id") == repeat.get("profile_id"),
        "VFX_DEGRADED_DETERMINISM_INVALID",
        str(first.get("effect_id")),
    )
    _require(first.get("output_hash") == repeat.get("output_hash"), "VFX_DEGRADED_DETERMINISM_MISMATCH", str(first.get("effect_id")))
    first_frames = [(item.get("source_index"), item.get("sha256"), item.get("alpha_bounds"), item.get("alpha_range")) for item in first.get("frames", [])]
    repeat_frames = [(item.get("source_index"), item.get("sha256"), item.get("alpha_bounds"), item.get("alpha_range")) for item in repeat.get("frames", [])]
    _require(first_frames == repeat_frames and first.get("frame_count") == repeat.get("frame_count"), "VFX_DEGRADED_DETERMINISM_MISMATCH", str(first.get("effect_id")))


def build_budget_fallback_sheet(full_root: Path, degraded_root: Path, full: Mapping[str, Any], degraded: Mapping[str, Any], output_path: Path) -> Path:
    """Persist a real FULL/DEGRADED image comparison for TEST_ONLY QA."""

    from PIL import ImageDraw, ImageFont

    image = Image.new("RGBA", (640, 160), (18, 22, 34, 255))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    with Image.open(full_root / Path(full["frames"][0]["path"])) as source:
        image.alpha_composite(source.convert("RGBA").resize((128, 128), Image.Resampling.NEAREST), (16, 24))
    if degraded.get("frames"):
        with Image.open(degraded_root / Path(degraded["frames"][0]["path"])) as source:
            image.alpha_composite(source.convert("RGBA").resize((128, 128), Image.Resampling.NEAREST), (336, 24))
    else:
        draw.rectangle((336, 24, 464, 152), outline=(220, 80, 80, 255), width=2)
    draw.text((16, 6), f"FULL {full['effect_class']} actual frame", fill=(235, 235, 235, 255), font=font)
    draw.text((336, 6), f"DEGRADED {degraded.get('status')} actual output", fill=(235, 235, 235, 255), font=font)
    draw.text((480, 42), f"steps={','.join(degraded.get('degradation_mechanisms', []))}", fill=(235, 235, 235, 255), font=font)
    draw.text((480, 78), "semantic_preserved=True", fill=(235, 235, 235, 255), font=font)
    draw.text((480, 104), "gameplay_authority=NONE", fill=(235, 235, 235, 255), font=font)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG", optimize=False, compress_level=9)
    return output_path
