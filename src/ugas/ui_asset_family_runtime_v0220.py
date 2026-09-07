"""Fail-closed, deterministic TEST_ONLY UI asset-family runtime for UGAS v0.22.0.

The module deliberately stops at semantic UI contracts and generated fixtures.  It
does not register production assets, start a UI, or mutate inventory, equipment,
map, or minimap authorities.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw


SCHEMA_VERSION = "0.22.0"
RUNTIME_REVISION = "ui-asset-family-runtime-v0220"
FAMILY_ID = "ugas-ui-asset-family-v0220"
STYLE_TOKEN_SET_ID = "TEST_ONLY_UI_STYLE_V0220"
PRODUCTION_ROUTING_BLOCKED = "BLOCKED"
REGISTRY_TEST_ONLY = "TEST_ONLY"
UI_COMPONENT_CLASSES = (
    "panel_frame", "window_frame", "button", "tab", "inventory_slot",
    "equipment_slot", "progress_bar", "resource_meter_frame", "tooltip_frame",
    "portrait_frame", "minimap_frame", "badge_or_icon_frame", "cursor",
    "divider_or_separator",
)
UI_STATES = ("normal", "hover", "pressed", "disabled", "selected", "focus")
SUPPORTED_SCALES = (1, 2)
INTEGRATION_AUTHORITIES = {
    "items_props": "v0.19.1",
    "equipment_outfits": "v0.17.1",
    "maps_minimap_runtime": "v0.21.3",
}


class UIAssetFamilyContractError(ValueError):
    """Machine-readable rejection from a public UI contract entry point."""

    def __init__(self, rejection_class: str, detail: str):
        self.rejection_class = rejection_class
        self.error_code = rejection_class
        self.detail = detail
        super().__init__(f"{rejection_class}: {detail}")


UIAssetFamilyError = UIAssetFamilyContractError


def _require(condition: bool, rejection_class: str, detail: str) -> None:
    if not condition:
        raise UIAssetFamilyContractError(rejection_class, detail)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(value))


def _rect(value: Mapping[str, Any], *, name: str) -> tuple[int, int, int, int]:
    _require(isinstance(value, Mapping), "UI_GEOMETRY_INVALID", name)
    fields = ("x", "y", "width", "height")
    _require(all(type(value.get(field)) is int for field in fields), "UI_GEOMETRY_INVALID", name)
    x, y, width, height = (int(value[field]) for field in fields)
    _require(x >= 0 and y >= 0 and width > 0 and height > 0, "UI_GEOMETRY_INVALID", name)
    return x, y, width, height


def _inside(inner: tuple[int, int, int, int], outer: tuple[int, int, int, int]) -> bool:
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    return ix >= ox and iy >= oy and ix + iw <= ox + ow and iy + ih <= oy + oh


def build_test_only_style_tokens() -> dict[str, Any]:
    """Return semantic data tokens, not duplicated rendering magic numbers."""
    return {
        "style_token_set_id": STYLE_TOKEN_SET_ID,
        "revision": RUNTIME_REVISION,
        "colors": {
            "normal": [48, 64, 88, 255], "hover": [72, 112, 168, 255],
            "pressed": [32, 48, 72, 255], "disabled": [72, 76, 84, 220],
            "selected": [112, 96, 32, 255], "focus": [48, 144, 128, 255],
            "border": [176, 196, 224, 255], "disabled_border": [120, 124, 132, 220],
            "transparent": [0, 0, 0, 0],
        },
        "metrics": {"border": 2, "corner": 3, "nine_slice_margin": 4, "focus_inset": 3, "state_marker": 2},
        "spacing": {"content_inset": 6, "icon_inset": 8, "text_inset": 10},
        "progress": {"fill_axis": "x", "minimum_fill": 2},
        "test_only": True,
    }


def style_token_hash(style_tokens: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(style_tokens))


def validate_style_tokens(style_tokens: Mapping[str, Any]) -> None:
    _require(style_tokens.get("style_token_set_id") == STYLE_TOKEN_SET_ID, "UI_STYLE_TOKEN_SET_INVALID", "style token authority")
    _require(style_tokens.get("test_only") is True, "UI_STYLE_TOKEN_NOT_TEST_ONLY", "production style tokens are not allowed")
    _require(isinstance(style_tokens.get("colors"), Mapping) and isinstance(style_tokens.get("metrics"), Mapping), "UI_STYLE_TOKEN_SCHEMA_INVALID", "semantic token data required")
    for state in UI_STATES:
        colour = style_tokens["colors"].get(state)
        _require(isinstance(colour, list) and len(colour) == 4 and all(type(item) is int and 0 <= item <= 255 for item in colour), "UI_STYLE_TOKEN_SCHEMA_INVALID", state)
    _require(style_tokens["metrics"].get("nine_slice_margin") > 0, "UI_STYLE_TOKEN_SCHEMA_INVALID", "nine slice margin")


def _class_size(component_class: str) -> tuple[int, int]:
    index = UI_COMPONENT_CLASSES.index(component_class)
    return (32 + (index % 4) * 4, 24 + (index % 3) * 4)


def _integration_for(component_class: str) -> dict[str, Any]:
    if component_class in {"inventory_slot", "equipment_slot"}:
        return {"authority": "items_props" if component_class == "inventory_slot" else "equipment_outfits", "revision": INTEGRATION_AUTHORITIES["items_props" if component_class == "inventory_slot" else "equipment_outfits"], "mode": "READ_ONLY", "mutation_allowed": False}
    if component_class == "minimap_frame":
        return {"authority": "maps_minimap_runtime", "revision": INTEGRATION_AUTHORITIES["maps_minimap_runtime"], "mode": "READ_ONLY", "mutation_allowed": False}
    return {"authority": "ui_asset_family", "revision": RUNTIME_REVISION, "mode": "READ_ONLY", "mutation_allowed": False}


def build_component_manifest(component_class: str, style_tokens: Mapping[str, Any] | None = None) -> dict[str, Any]:
    tokens = style_tokens or build_test_only_style_tokens()
    validate_style_tokens(tokens)
    _require(component_class in UI_COMPONENT_CLASSES, "UI_COMPONENT_CLASS_MISSING", component_class)
    width, height = _class_size(component_class)
    visual = {"x": 0, "y": 0, "width": width, "height": height}
    hit = {"x": 1, "y": 1, "width": max(1, width - 2), "height": max(1, height - 2)}
    margin = int(tokens["metrics"]["nine_slice_margin"])
    content = {"x": margin, "y": margin, "width": width - margin * 2, "height": height - margin * 2}
    icon = {"x": margin + 2, "y": margin + 2, "width": width - (margin + 2) * 2, "height": height - (margin + 2) * 2}
    record: dict[str, Any] = {
        "component_id": f"{FAMILY_ID}:{component_class}", "component_class": component_class,
        "family_id": FAMILY_ID, "revision": RUNTIME_REVISION, "supported_states": list(UI_STATES),
        "default_state": "normal", "logical_size": [width, height],
        "scale_policy": {"supported": list(SUPPORTED_SCALES), "pixel_snap": True},
        "stretch_geometry": {"policy": "NINE_SLICE", "slice_margins": {"left": margin, "top": margin, "right": margin, "bottom": margin}, "center_width": width - margin * 2, "center_height": height - margin * 2},
        "content_safe_rect": content, "icon_safe_rect": icon, "text_safe_rect": content,
        "visual_bounds": visual, "hit_bounds": hit,
        "style_token_set_id": tokens["style_token_set_id"], "style_token_hash": style_token_hash(tokens),
        "integration_linkage": _integration_for(component_class),
        "registry_mode": REGISTRY_TEST_ONLY, "production_safe": False,
    }
    record["semantic_input_hash"] = sha256_bytes(canonical_json({"component_class": component_class, "logical_size": record["logical_size"], "integration": record["integration_linkage"]}))
    record["content_hash"] = sha256_bytes(canonical_json(record))
    return record


def build_ui_manifest(style_tokens: Mapping[str, Any] | None = None) -> dict[str, Any]:
    tokens = style_tokens or build_test_only_style_tokens()
    validate_style_tokens(tokens)
    components = [build_component_manifest(name, tokens) for name in UI_COMPONENT_CLASSES]
    return {
        "schema_version": SCHEMA_VERSION, "manifest_type": "ui-asset-family-runtime-v0220",
        "family_id": FAMILY_ID, "runtime_revision": RUNTIME_REVISION,
        "component_classes": list(UI_COMPONENT_CLASSES), "components": components,
        "state_vocabulary": list(UI_STATES), "style_tokens": dict(tokens),
        "style_token_hash": style_token_hash(tokens), "registry_mode": REGISTRY_TEST_ONLY,
        "production_registry_empty": True, "production_routing": PRODUCTION_ROUTING_BLOCKED,
        "production_approved": False, "real_ui_asset_coverage": "NONE",
        "synthetic_ui_fixture": REGISTRY_TEST_ONLY, "new_generation": 0,
        "provenance": {"source": "deterministic-runtime-fixture", "test_only": True},
    }


def validate_component_record(component: Mapping[str, Any], style_tokens: Mapping[str, Any] | None = None) -> None:
    tokens = style_tokens or build_test_only_style_tokens()
    validate_style_tokens(tokens)
    name = component.get("component_class")
    _require(name in UI_COMPONENT_CLASSES, "UI_COMPONENT_CLASS_MISSING", str(name))
    _require(component.get("component_id") == f"{FAMILY_ID}:{name}", "UI_COMPONENT_ID_INVALID", str(component.get("component_id")))
    _require(tuple(component.get("supported_states", [])) == UI_STATES, "UI_STATE_VOCABULARY_INVALID", str(name))
    _require(component.get("style_token_set_id") == STYLE_TOKEN_SET_ID and component.get("style_token_hash") == style_token_hash(tokens), "UI_STYLE_TOKEN_HASH_STALE", str(name))
    logical = component.get("logical_size", [])
    _require(isinstance(logical, list) and len(logical) == 2 and all(type(value) is int and value > 0 for value in logical), "UI_GEOMETRY_INVALID", "logical_size")
    visual = _rect(component.get("visual_bounds", {}), name="visual_bounds")
    hit = _rect(component.get("hit_bounds", {}), name="hit_bounds")
    _require(visual != hit, "UI_VISUAL_HIT_BOUNDS_NOT_SEPARATE", name)
    _require(_inside(_rect(component.get("content_safe_rect", {}), name="content_safe_rect"), visual), "UI_CONTENT_SAFE_RECT_OUT_OF_BOUNDS", name)
    _require(_inside(_rect(component.get("icon_safe_rect", {}), name="icon_safe_rect"), visual), "UI_ICON_TEXT_SAFE_RECT_OUT_OF_BOUNDS", name)
    _require(_inside(_rect(component.get("text_safe_rect", {}), name="text_safe_rect"), visual), "UI_ICON_TEXT_SAFE_RECT_OUT_OF_BOUNDS", name)
    scales = component.get("scale_policy", {}).get("supported")
    _require(scales == list(SUPPORTED_SCALES), "UI_SCALE_VARIANT_INVALID", name)
    margins = component.get("stretch_geometry", {}).get("slice_margins", {})
    _require(set(margins) == {"left", "top", "right", "bottom"} and all(type(item) is int and item > 0 for item in margins.values()), "UI_NINE_SLICE_MARGINS_INVALID", name)
    _require(component.get("integration_linkage", {}).get("mode") == "READ_ONLY" and component.get("integration_linkage", {}).get("mutation_allowed") is False, "UI_INTEGRATION_REFERENCE_INVALID", name)
    _require(component.get("registry_mode") == REGISTRY_TEST_ONLY and component.get("production_safe") is False, "UI_PRODUCTION_REGISTRY_NON_EMPTY", name)


def validate_ui_manifest(manifest: Mapping[str, Any], style_tokens: Mapping[str, Any] | None = None) -> dict[str, Any]:
    tokens = style_tokens or manifest.get("style_tokens") or build_test_only_style_tokens()
    validate_style_tokens(tokens)
    _require(manifest.get("schema_version") == SCHEMA_VERSION, "UI_SCHEMA_VERSION_INVALID", str(manifest.get("schema_version")))
    _require(tuple(manifest.get("component_classes", [])) == UI_COMPONENT_CLASSES, "UI_COMPONENT_CLASS_MISSING", "14 stable classes required")
    components = manifest.get("components", [])
    _require(len(components) == len(UI_COMPONENT_CLASSES), "UI_COMPONENT_CLASS_MISSING", "component records")
    ids = [item.get("component_id") for item in components]
    _require(len(ids) == len(set(ids)), "UI_COMPONENT_ID_DUPLICATE", "component IDs")
    for component in components:
        validate_component_record(component, tokens)
    _require(manifest.get("style_token_hash") == style_token_hash(tokens), "UI_STYLE_TOKEN_HASH_STALE", "manifest authority")
    _require(manifest.get("production_registry_empty") is True and manifest.get("production_routing") == PRODUCTION_ROUTING_BLOCKED and manifest.get("production_approved") is False and manifest.get("new_generation") == 0, "UI_PRODUCTION_REGISTRY_NON_EMPTY", "production boundary")
    return {"status": "UI_ASSET_FAMILY_MANIFEST_VALID", "component_count": len(components), "state_count": len(UI_STATES)}


def build_cache_key(*, family_id: str, component_id: str, revision: str, state: str, scale_factor: int, style_token_hash_value: str, semantic_input_hash: str) -> str:
    _require(state in UI_STATES, "UI_STATE_UNSUPPORTED", state)
    _require(scale_factor in SUPPORTED_SCALES, "UI_SCALE_VARIANT_INVALID", str(scale_factor))
    fields = {"family_id": family_id, "component_id": component_id, "revision": revision, "state": state, "scale_factor": scale_factor, "style_token_hash": style_token_hash_value, "semantic_input_hash": semantic_input_hash}
    return sha256_bytes(canonical_json(fields))


def cache_key_for(component: Mapping[str, Any], state: str, scale_factor: int, style_tokens: Mapping[str, Any] | None = None) -> str:
    tokens = style_tokens or build_test_only_style_tokens()
    validate_component_record(component, tokens)
    return build_cache_key(family_id=component["family_id"], component_id=component["component_id"], revision=component["revision"], state=state, scale_factor=scale_factor, style_token_hash_value=style_token_hash(tokens), semantic_input_hash=component["semantic_input_hash"])


def validate_cache_record(record: Mapping[str, Any], component: Mapping[str, Any], style_tokens: Mapping[str, Any] | None = None) -> None:
    """Validate the complete cache identity instead of accepting arbitrary truthiness."""
    tokens = style_tokens or build_test_only_style_tokens()
    required = {"family_id", "component_id", "revision", "state", "scale_factor", "style_token_hash", "semantic_input_hash", "cache_key"}
    _require(required.issubset(record), "UI_CACHE_STATE_OMITTED", component.get("component_id", ""))
    _require(record.get("family_id") == component["family_id"] and record.get("component_id") == component["component_id"] and record.get("revision") == component["revision"], "UI_CACHE_STATE_OMITTED", component["component_id"])
    _require(record.get("style_token_hash") == style_token_hash(tokens) and record.get("semantic_input_hash") == component["semantic_input_hash"], "UI_CACHE_STYLE_OR_SCALE_OMITTED", component["component_id"])
    expected = build_cache_key(family_id=component["family_id"], component_id=component["component_id"], revision=component["revision"], state=record["state"], scale_factor=record["scale_factor"], style_token_hash_value=record["style_token_hash"], semantic_input_hash=record["semantic_input_hash"])
    _require(record.get("cache_key") == expected, "UI_CACHE_STATE_OMITTED", component["component_id"])


def validate_provenance_output(record: Mapping[str, Any], output_bytes: bytes) -> None:
    _require(record.get("output_sha256") == sha256_bytes(output_bytes), "UI_PROVENANCE_OUTPUT_HASH_MISMATCH", str(record.get("relative_path")))


def render_component(component: Mapping[str, Any], state: str, scale_factor: int, style_tokens: Mapping[str, Any] | None = None) -> Image.Image:
    tokens = style_tokens or build_test_only_style_tokens()
    validate_component_record(component, tokens)
    _require(state in component["supported_states"], "UI_STATE_UNSUPPORTED", state)
    _require(scale_factor in SUPPORTED_SCALES, "UI_SCALE_VARIANT_INVALID", str(scale_factor))
    width, height = (int(item) * scale_factor for item in component["logical_size"])
    image = Image.new("RGBA", (width, height), tuple(tokens["colors"]["transparent"]))
    draw = ImageDraw.Draw(image)
    colours = tokens["colors"]
    fill = tuple(colours[state]); border = tuple(colours["disabled_border"] if state == "disabled" else colours["border"])
    draw.rectangle((0, 0, width - 1, height - 1), fill=fill, outline=border, width=max(1, int(tokens["metrics"]["border"]) * scale_factor))
    inset = int(tokens["metrics"]["focus_inset"]) * scale_factor
    if state == "focus":
        draw.rectangle((inset, inset, width - inset - 1, height - inset - 1), outline=tuple(colours["focus"]), width=max(1, scale_factor))
    marker = int(tokens["metrics"]["state_marker"]) * scale_factor
    if state in {"hover", "pressed", "selected"}:
        draw.rectangle((width - marker - scale_factor, height - marker - scale_factor, width - scale_factor, height - scale_factor), fill=tuple(colours["border"]))
    if state == "disabled":
        draw.line((0, 0, width - 1, height - 1), fill=tuple(colours["disabled_border"]), width=scale_factor)
    return image


def validate_rendered_output(image: Image.Image, component: Mapping[str, Any], state: str, scale_factor: int) -> dict[str, Any]:
    _require(image.mode == "RGBA", "UI_ALPHA_BOUNDS_INVALID", "RGBA required")
    _require(image.size == tuple(int(value) * scale_factor for value in component["logical_size"]), "UI_SCALE_OUTPUT_INVALID", component["component_id"])
    _require(image.getbbox() is not None, "UI_ALPHA_BOUNDS_INVALID", component["component_id"])
    _require(state in UI_STATES, "UI_STATE_UNSUPPORTED", state)
    return {"mode": image.mode, "size": list(image.size), "decoded_pixel_sha256": sha256_bytes(image.tobytes())}


def validate_state_materiality(outputs: Mapping[str, bytes]) -> None:
    _require(set(outputs) == set(UI_STATES), "UI_STATE_VOCABULARY_INVALID", "all states required")
    _require(len(set(outputs.values())) == len(UI_STATES), "UI_STATE_BYTES_NOT_DISTINCT", "state bytes must differ")


def validate_nine_slice(component: Mapping[str, Any]) -> dict[str, Any]:
    visual = _rect(component["visual_bounds"], name="visual_bounds")
    margins = component["stretch_geometry"]["slice_margins"]
    left, top, right, bottom = (margins[name] for name in ("left", "top", "right", "bottom"))
    _require(left + right < visual[2] and top + bottom < visual[3], "UI_NINE_SLICE_CENTER_INVALID", component["component_id"])
    _require(component["stretch_geometry"].get("policy") == "NINE_SLICE", "UI_NINE_SLICE_MARGINS_INVALID", component["component_id"])
    return {"component_id": component["component_id"], "slice_margins": dict(margins), "center_area": [visual[2] - left - right, visual[3] - top - bottom]}


def validate_safe_geometry(component: Mapping[str, Any]) -> dict[str, Any]:
    visual = _rect(component["visual_bounds"], name="visual_bounds")
    for name in ("content_safe_rect", "icon_safe_rect", "text_safe_rect"):
        _require(_inside(_rect(component[name], name=name), visual), "UI_CONTENT_SAFE_RECT_OUT_OF_BOUNDS" if name == "content_safe_rect" else "UI_ICON_TEXT_SAFE_RECT_OUT_OF_BOUNDS", component["component_id"])
    return {"component_id": component["component_id"], "visual_bounds": dict(component["visual_bounds"]), "content_safe_rect": dict(component["content_safe_rect"]), "icon_safe_rect": dict(component["icon_safe_rect"]), "text_safe_rect": dict(component["text_safe_rect"]), "visual_hit_separate": component["visual_bounds"] != component["hit_bounds"]}


def validate_integration_linkage(component: Mapping[str, Any], *, attempted_mutation: bool = False, expected_revision: str | None = None) -> dict[str, Any]:
    link = component.get("integration_linkage", {})
    _require(attempted_mutation is False, "UI_MINIMAP_LINKAGE_MUTATION_FORBIDDEN", component.get("component_id", ""))
    _require(link.get("mode") == "READ_ONLY" and link.get("mutation_allowed") is False, "UI_INTEGRATION_REFERENCE_INVALID", component.get("component_id", ""))
    if expected_revision is not None:
        _require(link.get("revision") == expected_revision, "UI_SLOT_AUTHORITY_STALE", component.get("component_id", ""))
    return {"component_id": component["component_id"], "authority": link.get("authority"), "revision": link.get("revision"), "mode": link.get("mode"), "mutation_allowed": link.get("mutation_allowed")}


def validate_production_registry(registry: Sequence[Mapping[str, Any]], *, production_safe: bool = False) -> bool:
    _require(type(production_safe) is bool, "UI_PRODUCTION_REGISTRY_NON_EMPTY", "typed boundary")
    _require(len(registry) == 0, "UI_PRODUCTION_REGISTRY_NON_EMPTY", "production registry must be empty")
    _require(production_safe is False, "UI_TEST_ONLY_PRODUCTION_SAFE", "TEST_ONLY fixtures cannot be production safe")
    return True


def validate_historical_authority(authority_bytes: bytes, candidate_bytes: bytes, *, authority_ref: str) -> dict[str, Any]:
    authority_hash = sha256_bytes(authority_bytes); candidate_hash = sha256_bytes(candidate_bytes)
    _require(candidate_bytes == authority_bytes, "HISTORICAL_EVIDENCE_MUTATION_REJECTED", f"{authority_ref}:{candidate_hash}")
    return {"status": "HISTORICAL_AUTHORITY_VALID", "authority_ref": authority_ref, "authority_sha256": authority_hash, "candidate_sha256": candidate_hash}


def compare_generated_outputs(first: Mapping[str, bytes], second: Mapping[str, bytes]) -> bool:
    return type(first) is dict and type(second) is dict and first == second


def validate_determinism(first: Mapping[str, bytes], second: Mapping[str, bytes]) -> None:
    _require(compare_generated_outputs(first, second), "UI_NONDETERMINISTIC_SECOND_RUN", "isolated fixture outputs differ")


def generate_fixture_pack(output_dir: Path) -> dict[str, Any]:
    tokens = build_test_only_style_tokens(); manifest = build_ui_manifest(tokens); validate_ui_manifest(manifest, tokens)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, bytes] = {}; records: list[dict[str, Any]] = []
    for component in manifest["components"]:
        states: dict[str, bytes] = {}
        for state in UI_STATES:
            for scale in SUPPORTED_SCALES:
                image = render_component(component, state, scale, tokens); info = validate_rendered_output(image, component, state, scale)
                relative = Path("fixtures") / component["component_class"] / f"{state}-{scale}x.png"; path = output_dir / relative; path.parent.mkdir(parents=True, exist_ok=True); image.save(path, format="PNG", optimize=False, compress_level=9)
                file_bytes = path.read_bytes(); key = f"{component['component_class']}:{state}:{scale}x"; outputs[key] = file_bytes; states[state] = file_bytes
                component_output = {"state": state, "scale_factor": scale, "relative_path": relative.as_posix(), "output_sha256": sha256_bytes(file_bytes), "decoded_pixel_sha256": info["decoded_pixel_sha256"], "cache_key": cache_key_for(component, state, scale, tokens), "raster_size": info["size"]}
                records.append({"component_id": component["component_id"], **component_output})
        validate_state_materiality(states)
    manifest["outputs"] = records; manifest["manifest_hash"] = sha256_bytes(canonical_json(manifest)); write_json(output_dir / "ui-family-manifest-v0220.json", manifest)
    return {"manifest": manifest, "outputs": outputs}


__all__ = ["FAMILY_ID", "INTEGRATION_AUTHORITIES", "PRODUCTION_ROUTING_BLOCKED", "REGISTRY_TEST_ONLY", "RUNTIME_REVISION", "SCHEMA_VERSION", "STYLE_TOKEN_SET_ID", "SUPPORTED_SCALES", "UIAssetFamilyContractError", "UIAssetFamilyError", "UI_COMPONENT_CLASSES", "UI_STATES", "build_cache_key", "build_component_manifest", "build_test_only_style_tokens", "build_ui_manifest", "cache_key_for", "canonical_json", "compare_generated_outputs", "generate_fixture_pack", "render_component", "sha256_bytes", "sha256_file", "style_token_hash", "validate_cache_record", "validate_component_record", "validate_determinism", "validate_historical_authority", "validate_integration_linkage", "validate_nine_slice", "validate_provenance_output", "validate_production_registry", "validate_rendered_output", "validate_safe_geometry", "validate_state_materiality", "validate_style_tokens", "validate_ui_manifest", "write_json"]
