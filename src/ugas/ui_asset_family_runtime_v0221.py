"""Fail-closed, deterministic TEST_ONLY UI semantic runtime for UGAS v0.22.1.

This correction makes the UI fixture contract semantic rather than nominal.  It
does not register production assets, start a UI, or mutate any downstream
authority.  All rendering is synthetic and remains TEST_ONLY.
"""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw


SCHEMA_VERSION = "0.22.1"
RUNTIME_REVISION = "ui-asset-family-runtime-v0221"
FAMILY_ID = "ugas-ui-asset-family-v0221"
STYLE_TOKEN_SET_ID = "TEST_ONLY_UI_STYLE_V0221"
PRODUCTION_ROUTING_BLOCKED = "BLOCKED"
REGISTRY_TEST_ONLY = "TEST_ONLY"
BASE_MAIN_SHA = "1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3"
UI_COMPONENT_CLASSES = (
    "panel_frame", "window_frame", "button", "tab", "inventory_slot",
    "equipment_slot", "progress_bar", "resource_meter_frame", "tooltip_frame",
    "portrait_frame", "minimap_frame", "badge_or_icon_frame", "cursor",
    "divider_or_separator",
)
UI_STATES = ("normal", "hover", "pressed", "disabled", "selected", "focus")
SUPPORTED_SCALES = (1, 2)


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


# This is the one authoritative class table consumed by manifest construction,
# validation, rendering and the v0.22.1 evidence runner.
CLASS_SPECS: dict[str, dict[str, Any]] = {
    "panel_frame": {"states": ("normal", "disabled", "focus"), "stretch_policy": "NINE_SLICE", "semantic": {"panel_role": "container", "content_region": "content_safe_rect"}},
    "window_frame": {"states": ("normal", "hover", "pressed", "disabled", "focus"), "stretch_policy": "NINE_SLICE", "semantic": {"panel_role": "window", "title_region": "header_rect", "content_region": "content_safe_rect"}},
    "button": {"states": UI_STATES, "stretch_policy": "NINE_SLICE", "semantic": {"activation": "click", "stateful": True}},
    "tab": {"states": ("normal", "hover", "pressed", "disabled", "selected", "focus"), "stretch_policy": "NINE_SLICE", "semantic": {"activation": "select", "selected_state": "selected"}},
    "inventory_slot": {"states": ("normal", "hover", "pressed", "disabled", "selected", "focus"), "stretch_policy": "NINE_SLICE", "semantic": {"accepted_categories": ["item", "prop"], "linkage": "items_props_read_only"}},
    "equipment_slot": {"states": ("normal", "hover", "pressed", "disabled", "selected", "focus"), "stretch_policy": "NINE_SLICE", "semantic": {"slot_type": "weapon", "linkage": "equipment_outfits_read_only"}},
    "progress_bar": {"states": ("normal", "disabled", "focus"), "stretch_policy": "NINE_SLICE", "semantic": {"fill_axis": "x", "gameplay_values": False}},
    "resource_meter_frame": {"states": ("normal", "disabled", "focus"), "stretch_policy": "NINE_SLICE", "semantic": {"frame_only": True, "gameplay_values": False}},
    "tooltip_frame": {"states": ("normal", "hover", "disabled", "focus"), "stretch_policy": "NINE_SLICE", "semantic": {"content_region": "text_safe_rect", "anchor": "pointer"}},
    "portrait_frame": {"states": ("normal", "hover", "disabled", "selected", "focus"), "stretch_policy": "NINE_SLICE", "semantic": {"content_region": "portrait_safe_rect", "aspect": "portrait"}},
    "minimap_frame": {"states": ("normal", "disabled", "focus"), "stretch_policy": "NINE_SLICE", "semantic": {"content_region": "minimap_content_safe_rect", "linkage": "maps_minimap_read_only"}},
    "badge_or_icon_frame": {"states": ("normal", "hover", "disabled", "selected", "focus"), "stretch_policy": "NINE_SLICE", "semantic": {"content_region": "icon_safe_rect", "badge": True}},
    "cursor": {"states": ("normal", "hover", "pressed"), "stretch_policy": "NON_STRETCH", "semantic": {"hotspot_coordinates": "logical", "hit_test": "hotspot"}},
    "divider_or_separator": {"states": ("normal", "disabled", "focus"), "stretch_policy": "NON_STRETCH", "semantic": {"orientation": "horizontal", "thickness": 2, "thickness_axis": "y"}},
}


APPROVED_AUTHORITY_SOURCES: dict[str, dict[str, str]] = {
    "items_props": {"capability_id": "items_props", "approved_commit": BASE_MAIN_SHA, "authoritative_path": "docs/evidence/items-props-runtime-v0191/item-prop-contract-v0191.json", "semantic_revision": "v0.19.1"},
    "equipment_outfits": {"capability_id": "equipment_outfits", "approved_commit": BASE_MAIN_SHA, "authoritative_path": "docs/evidence/equipment-outfits-runtime-v0171/equipment-contract-v0171.json", "semantic_revision": "v0.17.1"},
    "maps_minimap_runtime": {"capability_id": "maps_minimap_runtime", "approved_commit": BASE_MAIN_SHA, "authoritative_path": "docs/evidence/maps-minimap-runtime-v0213/map-contract-v0213.json", "semantic_revision": "v0.21.3"},
    "ui_asset_family": {"capability_id": "ui_asset_family", "approved_commit": BASE_MAIN_SHA, "authoritative_path": "docs/evidence/maps-minimap-runtime-v0213/map-contract-v0213.json", "semantic_revision": "v0.21.3"},
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=None)
def resolve_approved_authority(authority_name: str) -> dict[str, Any]:
    """Resolve immutable bytes/Git identity independently of candidate data."""
    source = APPROVED_AUTHORITY_SOURCES.get(authority_name)
    _require(source is not None, "UI_INTEGRATION_AUTHORITY_UNKNOWN", authority_name)
    root = _repo_root()
    object_ref = f"{source['approved_commit']}:{source['authoritative_path']}"
    blob = subprocess.run(["git", "show", object_ref], cwd=root, capture_output=True, check=False)
    _require(blob.returncode == 0, "UI_INTEGRATION_AUTHORITY_UNRESOLVED", object_ref)
    blob_sha = subprocess.run(["git", "rev-parse", object_ref], cwd=root, capture_output=True, text=True, check=False)
    _require(blob_sha.returncode == 0, "UI_INTEGRATION_AUTHORITY_UNRESOLVED", object_ref)
    raw = bytes(blob.stdout)
    return {**source, "git_blob_sha": blob_sha.stdout.strip(), "raw_bytes_sha256": sha256_bytes(raw)}


def build_test_only_style_tokens() -> dict[str, Any]:
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
    _require(type(style_tokens["metrics"].get("nine_slice_margin")) is int and style_tokens["metrics"]["nine_slice_margin"] > 0, "UI_STYLE_TOKEN_SCHEMA_INVALID", "nine slice margin")


def _class_size(component_class: str) -> tuple[int, int]:
    index = UI_COMPONENT_CLASSES.index(component_class)
    return (32 + (index % 4) * 4, 24 + (index % 3) * 4)


def _integration_name(component_class: str) -> str:
    if component_class == "inventory_slot":
        return "items_props"
    if component_class == "equipment_slot":
        return "equipment_outfits"
    if component_class == "minimap_frame":
        return "maps_minimap_runtime"
    return "ui_asset_family"


def _class_metadata(component_class: str, width: int, height: int, margin: int) -> dict[str, Any]:
    spec = deepcopy(CLASS_SPECS[component_class]["semantic"])
    if component_class == "cursor":
        spec.update({"hotspot": {"x": 3, "y": 3}, "hotspot_bounds": {"x": 0, "y": 0, "width": width, "height": height}})
    elif component_class == "equipment_slot":
        spec.update({"slot_type": "weapon", "authority_capability": "equipment_outfits"})
    elif component_class == "inventory_slot":
        spec.update({"accepted_categories": ["item", "prop"], "authority_capability": "items_props"})
    elif component_class == "window_frame":
        spec.update({"header_rect": {"x": margin, "y": margin, "width": width - 2 * margin, "height": 5}, "content_safe_rect": "content_safe_rect"})
    elif component_class == "progress_bar":
        spec.update({"track_rect": {"x": margin, "y": margin, "width": width - 2 * margin, "height": height - 2 * margin}, "fill_rect": {"x": margin + 1, "y": margin + 1, "width": width - 2 * margin - 2, "height": height - 2 * margin - 2}, "fill_axis": "x"})
    elif component_class == "minimap_frame":
        spec.update({"minimap_content_safe_rect": {"x": margin + 2, "y": margin + 2, "width": width - 2 * margin - 4, "height": height - 2 * margin - 4}, "authority_capability": "maps_minimap_runtime"})
    elif component_class == "portrait_frame":
        spec.update({"portrait_safe_rect": {"x": margin + 1, "y": margin + 1, "width": width - 2 * margin - 2, "height": height - 2 * margin - 2}})
    elif component_class == "divider_or_separator":
        spec.update({"orientation": "horizontal", "thickness": 2, "thickness_axis": "y"})
    return spec


def validate_class_spec_table() -> None:
    _require(tuple(CLASS_SPECS) == UI_COMPONENT_CLASSES, "UI_CLASS_SPEC_TABLE_INVALID", "class authority order")
    for name in UI_COMPONENT_CLASSES:
        spec = CLASS_SPECS.get(name, {})
        states = spec.get("states")
        _require(isinstance(states, tuple) and states and set(states).issubset(UI_STATES), "UI_STATE_MATRIX_INVALID", name)
        _require(spec.get("stretch_policy") in {"NINE_SLICE", "NON_STRETCH"}, "UI_STRETCH_POLICY_INVALID", name)


def validate_state_applicability(component: Mapping[str, Any], requested_state: str | None = None) -> dict[str, Any]:
    name = component.get("component_class")
    validate_class_spec_table()
    _require(name in UI_COMPONENT_CLASSES, "UI_COMPONENT_CLASS_MISSING", str(name))
    expected = list(CLASS_SPECS[name]["states"])
    _require(component.get("supported_states") == expected, "UI_STATE_MATRIX_INVALID", str(name))
    if requested_state is not None:
        _require(requested_state in expected, "UI_STATE_UNSUPPORTED_FOR_COMPONENT", f"{name}:{requested_state}")
    return {"component_class": name, "supported_states": expected}


def _semantic_payload(component: Mapping[str, Any]) -> dict[str, Any]:
    fields = ("component_class", "logical_size", "supported_states", "stretch_geometry", "content_safe_rect", "icon_safe_rect", "text_safe_rect", "visual_bounds", "hit_bounds", "class_metadata", "integration_linkage", "style_token_hash")
    return {field: component.get(field) for field in fields}


def _content_payload(component: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in component.items() if key != "content_hash"}


def build_component_manifest(component_class: str, style_tokens: Mapping[str, Any] | None = None) -> dict[str, Any]:
    tokens = style_tokens or build_test_only_style_tokens()
    validate_style_tokens(tokens); validate_class_spec_table()
    _require(component_class in UI_COMPONENT_CLASSES, "UI_COMPONENT_CLASS_MISSING", component_class)
    width, height = _class_size(component_class); margin = int(tokens["metrics"]["nine_slice_margin"])
    visual = {"x": 0, "y": 0, "width": width, "height": height}
    hit = {"x": 1, "y": 1, "width": max(1, width - 2), "height": max(1, height - 2)}
    content = {"x": margin, "y": margin, "width": width - margin * 2, "height": height - margin * 2}
    icon = {"x": margin + 2, "y": margin + 2, "width": width - (margin + 2) * 2, "height": height - (margin + 2) * 2}
    authority = resolve_approved_authority(_integration_name(component_class))
    integration = {"authority": authority, "mode": "READ_ONLY", "mutation_allowed": False}
    record: dict[str, Any] = {
        "component_id": f"{FAMILY_ID}:{component_class}", "component_class": component_class,
        "family_id": FAMILY_ID, "revision": RUNTIME_REVISION,
        "supported_states": list(CLASS_SPECS[component_class]["states"]), "default_state": "normal",
        "logical_size": [width, height], "scale_policy": {"supported": list(SUPPORTED_SCALES), "pixel_snap": True, "relation": "NEAREST_NEIGHBOR_2X"},
        "stretch_policy": CLASS_SPECS[component_class]["stretch_policy"],
        "stretch_geometry": {"policy": CLASS_SPECS[component_class]["stretch_policy"], "slice_margins": {"left": margin, "top": margin, "right": margin, "bottom": margin}, "center_width": width - margin * 2, "center_height": height - margin * 2},
        "content_safe_rect": content, "icon_safe_rect": icon, "text_safe_rect": content, "visual_bounds": visual, "hit_bounds": hit,
        "class_metadata": _class_metadata(component_class, width, height, margin),
        "style_token_set_id": tokens["style_token_set_id"], "style_token_hash": style_token_hash(tokens),
        "integration_linkage": integration, "registry_mode": REGISTRY_TEST_ONLY, "production_safe": False,
    }
    record["semantic_input_hash"] = sha256_bytes(canonical_json(_semantic_payload(record)))
    record["content_hash"] = sha256_bytes(canonical_json(_content_payload(record)))
    return record


def build_ui_manifest(style_tokens: Mapping[str, Any] | None = None) -> dict[str, Any]:
    tokens = style_tokens or build_test_only_style_tokens(); validate_style_tokens(tokens)
    components = [build_component_manifest(name, tokens) for name in UI_COMPONENT_CLASSES]
    return {"schema_version": SCHEMA_VERSION, "manifest_type": "ui-asset-family-runtime-v0221", "family_id": FAMILY_ID, "runtime_revision": RUNTIME_REVISION, "component_classes": list(UI_COMPONENT_CLASSES), "components": components, "state_vocabulary": list(UI_STATES), "style_tokens": dict(tokens), "style_token_hash": style_token_hash(tokens), "registry_mode": REGISTRY_TEST_ONLY, "production_registry_empty": True, "production_routing": PRODUCTION_ROUTING_BLOCKED, "production_approved": False, "real_ui_asset_coverage": "NONE", "synthetic_ui_fixture": REGISTRY_TEST_ONLY, "new_generation": 0, "provenance": {"source": "deterministic-semantic-runtime-fixture", "test_only": True}}


def validate_integration_authority(link: Mapping[str, Any], expected_name: str) -> dict[str, Any]:
    expected = resolve_approved_authority(expected_name); recorded = link.get("authority")
    _require(isinstance(recorded, Mapping), "UI_INTEGRATION_AUTHORITY_INVALID", expected_name)
    for field in ("capability_id", "approved_commit", "authoritative_path", "semantic_revision", "git_blob_sha", "raw_bytes_sha256"):
        _require(recorded.get(field) == expected.get(field), "UI_INTEGRATION_AUTHORITY_STALE", f"{expected_name}:{field}")
    return {"capability_id": expected["capability_id"], "approved_commit": expected["approved_commit"], "authoritative_path": expected["authoritative_path"], "semantic_revision": expected["semantic_revision"], "git_blob_sha": expected["git_blob_sha"], "raw_bytes_sha256": expected["raw_bytes_sha256"]}


def validate_component_record(component: Mapping[str, Any], style_tokens: Mapping[str, Any] | None = None) -> None:
    tokens = style_tokens or build_test_only_style_tokens(); validate_style_tokens(tokens); validate_class_spec_table()
    name = component.get("component_class"); _require(name in UI_COMPONENT_CLASSES, "UI_COMPONENT_CLASS_MISSING", str(name))
    _require(component.get("component_id") == f"{FAMILY_ID}:{name}", "UI_COMPONENT_ID_INVALID", str(component.get("component_id")))
    validate_state_applicability(component)
    _require(component.get("style_token_set_id") == STYLE_TOKEN_SET_ID and component.get("style_token_hash") == style_token_hash(tokens), "UI_STYLE_TOKEN_HASH_STALE", str(name))
    logical = component.get("logical_size", []); _require(isinstance(logical, list) and len(logical) == 2 and all(type(value) is int and value > 0 for value in logical), "UI_GEOMETRY_INVALID", "logical_size")
    visual = _rect(component.get("visual_bounds", {}), name="visual_bounds"); hit = _rect(component.get("hit_bounds", {}), name="hit_bounds")
    _require(visual != hit, "UI_VISUAL_HIT_BOUNDS_NOT_SEPARATE", name)
    for field, rejection in (("content_safe_rect", "UI_CONTENT_SAFE_RECT_OUT_OF_BOUNDS"), ("icon_safe_rect", "UI_ICON_TEXT_SAFE_RECT_OUT_OF_BOUNDS"), ("text_safe_rect", "UI_ICON_TEXT_SAFE_RECT_OUT_OF_BOUNDS")):
        _require(_inside(_rect(component.get(field, {}), name=field), visual), rejection, name)
    _require(component.get("scale_policy", {}).get("supported") == list(SUPPORTED_SCALES), "UI_SCALE_VARIANT_INVALID", name)
    policy = component.get("stretch_policy"); _require(policy == CLASS_SPECS[name]["stretch_policy"], "UI_STRETCH_POLICY_INVALID", name)
    margins = component.get("stretch_geometry", {}).get("slice_margins", {}); _require(set(margins) == {"left", "top", "right", "bottom"} and all(type(item) is int and item > 0 for item in margins.values()), "UI_NINE_SLICE_MARGINS_INVALID", name)
    _require(component.get("class_metadata") == _class_metadata(name, visual[2], visual[3], margins["left"]), "UI_CLASS_METADATA_INVALID", name)
    validate_integration_authority(component.get("integration_linkage", {}), _integration_name(name))
    _require(component.get("integration_linkage", {}).get("mode") == "READ_ONLY" and component.get("integration_linkage", {}).get("mutation_allowed") is False, "UI_INTEGRATION_REFERENCE_INVALID", name)
    _require(component.get("registry_mode") == REGISTRY_TEST_ONLY and component.get("production_safe") is False, "UI_PRODUCTION_REGISTRY_NON_EMPTY", name)
    _require(component.get("semantic_input_hash") == sha256_bytes(canonical_json(_semantic_payload(component))), "UI_SEMANTIC_INPUT_HASH_STALE", name)
    _require(component.get("content_hash") == sha256_bytes(canonical_json(_content_payload(component))), "UI_CONTENT_HASH_STALE", name)


def validate_ui_manifest(manifest: Mapping[str, Any], style_tokens: Mapping[str, Any] | None = None) -> dict[str, Any]:
    tokens = style_tokens or manifest.get("style_tokens") or build_test_only_style_tokens(); validate_style_tokens(tokens); validate_class_spec_table()
    _require(manifest.get("schema_version") == SCHEMA_VERSION, "UI_SCHEMA_VERSION_INVALID", str(manifest.get("schema_version")))
    _require(tuple(manifest.get("component_classes", [])) == UI_COMPONENT_CLASSES, "UI_COMPONENT_CLASS_MISSING", "14 authoritative classes required")
    components = manifest.get("components", []); _require(len(components) == len(UI_COMPONENT_CLASSES), "UI_COMPONENT_CLASS_MISSING", "component records")
    ids = [item.get("component_id") for item in components]; _require(len(ids) == len(set(ids)), "UI_COMPONENT_ID_DUPLICATE", "component IDs")
    for component in components: validate_component_record(component, tokens)
    _require(manifest.get("style_token_hash") == style_token_hash(tokens), "UI_STYLE_TOKEN_HASH_STALE", "manifest authority")
    _require(manifest.get("production_registry_empty") is True and manifest.get("production_routing") == PRODUCTION_ROUTING_BLOCKED and manifest.get("production_approved") is False and manifest.get("new_generation") == 0, "UI_PRODUCTION_REGISTRY_NON_EMPTY", "production boundary")
    return {"status": "UI_ASSET_FAMILY_MANIFEST_VALID", "component_count": len(components), "state_count": len(UI_STATES), "class_semantics": True}


def build_cache_key(*, family_id: str, component_id: str, revision: str, state: str, scale_factor: int, style_token_hash_value: str, semantic_input_hash: str, content_hash: str) -> str:
    _require(type(state) is str, "UI_STATE_UNSUPPORTED", str(state)); _require(scale_factor in SUPPORTED_SCALES, "UI_SCALE_VARIANT_INVALID", str(scale_factor))
    fields = {"family_id": family_id, "component_id": component_id, "revision": revision, "state": state, "scale_factor": scale_factor, "style_token_hash": style_token_hash_value, "semantic_input_hash": semantic_input_hash, "content_hash": content_hash}
    return sha256_bytes(canonical_json(fields))


def cache_key_for(component: Mapping[str, Any], state: str, scale_factor: int, style_tokens: Mapping[str, Any] | None = None) -> str:
    tokens = style_tokens or build_test_only_style_tokens(); validate_component_record(component, tokens); validate_state_applicability(component, state)
    return build_cache_key(family_id=component["family_id"], component_id=component["component_id"], revision=component["revision"], state=state, scale_factor=scale_factor, style_token_hash_value=style_token_hash(tokens), semantic_input_hash=component["semantic_input_hash"], content_hash=component["content_hash"])


def validate_cache_record(record: Mapping[str, Any], component: Mapping[str, Any], style_tokens: Mapping[str, Any] | None = None) -> None:
    tokens = style_tokens or build_test_only_style_tokens(); validate_component_record(component, tokens)
    required = {"family_id", "component_id", "revision", "state", "scale_factor", "style_token_hash", "semantic_input_hash", "content_hash", "cache_key"}; _require(required.issubset(record), "UI_CACHE_IDENTITY_OMITTED", component.get("component_id", ""))
    _require(record.get("family_id") == component["family_id"] and record.get("component_id") == component["component_id"] and record.get("revision") == component["revision"], "UI_CACHE_IDENTITY_OMITTED", component["component_id"])
    validate_state_applicability(component, record.get("state")); _require(record.get("style_token_hash") == style_token_hash(tokens) and record.get("semantic_input_hash") == component["semantic_input_hash"] and record.get("content_hash") == component["content_hash"], "UI_CACHE_SEMANTIC_IDENTITY_STALE", component["component_id"])
    expected = build_cache_key(family_id=component["family_id"], component_id=component["component_id"], revision=component["revision"], state=record["state"], scale_factor=record["scale_factor"], style_token_hash_value=record["style_token_hash"], semantic_input_hash=record["semantic_input_hash"], content_hash=record["content_hash"])
    _require(record.get("cache_key") == expected, "UI_CACHE_SEMANTIC_IDENTITY_STALE", component["component_id"])


def _render_native(component: Mapping[str, Any], state: str, tokens: Mapping[str, Any]) -> Image.Image:
    width, height = component["logical_size"]; colours = tokens["colors"]
    image = Image.new("RGBA", (width, height), tuple(colours["transparent"])); draw = ImageDraw.Draw(image)
    fill = tuple(colours[state]); border = tuple(colours["disabled_border"] if state == "disabled" else colours["border"])
    draw.rectangle((0, 0, width - 1, height - 1), fill=fill, outline=border, width=int(tokens["metrics"]["border"]))
    if component["component_class"] == "divider_or_separator":
        draw.rectangle((0, height // 2, width - 1, min(height - 1, height // 2 + 1)), fill=border)
    if state == "focus":
        inset = int(tokens["metrics"]["focus_inset"]); draw.rectangle((inset, inset, width - inset - 1, height - inset - 1), outline=tuple(colours["focus"]), width=1)
    if state in {"hover", "pressed", "selected"}:
        marker = int(tokens["metrics"]["state_marker"]); draw.rectangle((width - marker - 1, height - marker - 1, width - 2, height - 2), fill=tuple(colours["border"]))
    if state == "disabled": draw.line((0, 0, width - 1, height - 1), fill=tuple(colours["disabled_border"]), width=1)
    return image


def render_component(component: Mapping[str, Any], state: str, scale_factor: int, style_tokens: Mapping[str, Any] | None = None) -> Image.Image:
    tokens = style_tokens or build_test_only_style_tokens(); validate_component_record(component, tokens); validate_state_applicability(component, state); _require(scale_factor in SUPPORTED_SCALES, "UI_SCALE_VARIANT_INVALID", str(scale_factor))
    native = _render_native(component, state, tokens)
    return native if scale_factor == 1 else native.resize((native.width * scale_factor, native.height * scale_factor), Image.Resampling.NEAREST)


def _nine_slice_resize(source: Image.Image, target_size: tuple[int, int], margins: Mapping[str, int]) -> Image.Image:
    sw, sh = source.size; tw, th = target_size; left, top, right, bottom = (int(margins[key]) for key in ("left", "top", "right", "bottom"))
    _require(tw >= left + right and th >= top + bottom, "UI_NINE_SLICE_TARGET_TOO_SMALL", f"{tw}x{th}")
    result = Image.new("RGBA", (tw, th), (0, 0, 0, 0)); cx, cy = tw - left - right, th - top - bottom; sx, sy = sw - left - right, sh - top - bottom
    boxes = [((0, 0, left, top), (0, 0, left, top)), ((sw - right, 0, sw, top), (tw - right, 0, tw, top)), ((0, sh - bottom, left, sh), (0, th - bottom, left, th)), ((sw - right, sh - bottom, sw, sh), (tw - right, th - bottom, tw, th))]
    for src_box, dst_box in boxes: result.paste(source.crop(src_box), dst_box[:2])
    if cx: result.paste(source.crop((left, 0, sw - right, top)).resize((cx, top), Image.Resampling.NEAREST), (left, 0))
    if cx: result.paste(source.crop((left, sh - bottom, sw - right, sh)).resize((cx, bottom), Image.Resampling.NEAREST), (left, th - bottom))
    if cy: result.paste(source.crop((0, top, left, sh - bottom)).resize((left, cy), Image.Resampling.NEAREST), (0, top))
    if cy: result.paste(source.crop((sw - right, top, sw, sh - bottom)).resize((right, cy), Image.Resampling.NEAREST), (tw - right, top))
    if cx and cy: result.paste(source.crop((left, top, sw - right, sh - bottom)).resize((cx, cy), Image.Resampling.NEAREST), (left, top))
    return result


def render_component_to_size(component: Mapping[str, Any], state: str, scale_factor: int, target_logical_size: Sequence[int], style_tokens: Mapping[str, Any] | None = None) -> Image.Image:
    tokens = style_tokens or build_test_only_style_tokens(); validate_component_record(component, tokens); validate_state_applicability(component, state); _require(scale_factor in SUPPORTED_SCALES, "UI_SCALE_VARIANT_INVALID", str(scale_factor))
    _require(isinstance(target_logical_size, Sequence) and len(target_logical_size) == 2 and all(type(value) is int and value > 0 for value in target_logical_size), "UI_TARGET_SIZE_INVALID", component["component_id"])
    target = (int(target_logical_size[0]), int(target_logical_size[1])); logical = tuple(component["logical_size"]); policy = component["stretch_policy"]
    if policy == "NON_STRETCH": _require(target == logical, "UI_NON_STRETCH_TARGET_INVALID", component["component_id"])
    source = render_component(component, state, 1, tokens)
    result = source if target == logical else _nine_slice_resize(source, (target[0], target[1]), component["stretch_geometry"]["slice_margins"])
    return result if scale_factor == 1 else result.resize((target[0] * scale_factor, target[1] * scale_factor), Image.Resampling.NEAREST)


def validate_reconstructed_output(image: Image.Image, component: Mapping[str, Any], state: str, scale_factor: int, target_logical_size: Sequence[int], style_tokens: Mapping[str, Any] | None = None) -> dict[str, Any]:
    expected = render_component_to_size(component, state, scale_factor, target_logical_size, style_tokens)
    _require(image.mode == "RGBA" and image.size == expected.size, "UI_STRETCH_OUTPUT_INVALID", component["component_id"])
    _require(image.tobytes() == expected.tobytes(), "UI_STRETCH_OUTPUT_MISMATCH", component["component_id"])
    return {"component_id": component["component_id"], "target_logical_size": list(target_logical_size), "scale_factor": scale_factor, "decoded_pixel_sha256": sha256_bytes(image.tobytes()), "reconstruction_valid": True}


def validate_rendered_output(image: Image.Image, component: Mapping[str, Any], state: str, scale_factor: int) -> dict[str, Any]:
    _require(image.mode == "RGBA", "UI_ALPHA_BOUNDS_INVALID", "RGBA required"); _require(image.size == tuple(int(value) * scale_factor for value in component["logical_size"]), "UI_SCALE_OUTPUT_INVALID", component["component_id"]); _require(image.getbbox() is not None, "UI_ALPHA_BOUNDS_INVALID", component["component_id"]); validate_state_applicability(component, state)
    return {"mode": image.mode, "size": list(image.size), "decoded_pixel_sha256": sha256_bytes(image.tobytes())}


def validate_scale_pixel_relation(one_x: Image.Image, two_x: Image.Image, component: Mapping[str, Any], state: str) -> dict[str, Any]:
    validate_state_applicability(component, state); expected = one_x.resize((one_x.width * 2, one_x.height * 2), Image.Resampling.NEAREST)
    _require(two_x.size == expected.size, "UI_SCALE_PIXEL_RELATION_INVALID", component["component_id"]); _require(two_x.tobytes() == expected.tobytes(), "UI_SCALE_PIXEL_RELATION_INVALID", component["component_id"])
    return {"component_id": component["component_id"], "state": state, "one_x_decoded_sha256": sha256_bytes(one_x.tobytes()), "expected_expanded_sha256": sha256_bytes(expected.tobytes()), "actual_two_x_decoded_sha256": sha256_bytes(two_x.tobytes()), "result": "PASS"}


def validate_state_materiality(outputs: Mapping[str, bytes]) -> None:
    _require(bool(outputs) and set(outputs).issubset(set(UI_STATES)), "UI_STATE_VOCABULARY_INVALID", "state set")
    _require(len(set(outputs.values())) == len(outputs), "UI_STATE_BYTES_NOT_DISTINCT", "state bytes must differ")


def validate_nine_slice(component: Mapping[str, Any]) -> dict[str, Any]:
    visual = _rect(component["visual_bounds"], name="visual_bounds"); margins = component["stretch_geometry"]["slice_margins"]; left, top, right, bottom = (margins[name] for name in ("left", "top", "right", "bottom"))
    if component["stretch_policy"] == "NON_STRETCH": return {"component_id": component["component_id"], "policy": "NON_STRETCH", "slice_margins": dict(margins)}
    _require(left + right < visual[2] and top + bottom < visual[3], "UI_NINE_SLICE_CENTER_INVALID", component["component_id"])
    return {"component_id": component["component_id"], "policy": "NINE_SLICE", "slice_margins": dict(margins), "center_area": [visual[2] - left - right, visual[3] - top - bottom]}


def validate_safe_geometry(component: Mapping[str, Any]) -> dict[str, Any]:
    visual = _rect(component["visual_bounds"], name="visual_bounds")
    for name in ("content_safe_rect", "icon_safe_rect", "text_safe_rect"): _require(_inside(_rect(component[name], name=name), visual), "UI_CONTENT_SAFE_RECT_OUT_OF_BOUNDS" if name == "content_safe_rect" else "UI_ICON_TEXT_SAFE_RECT_OUT_OF_BOUNDS", component["component_id"])
    return {"component_id": component["component_id"], "visual_bounds": dict(component["visual_bounds"]), "content_safe_rect": dict(component["content_safe_rect"]), "icon_safe_rect": dict(component["icon_safe_rect"]), "text_safe_rect": dict(component["text_safe_rect"]), "visual_hit_separate": component["visual_bounds"] != component["hit_bounds"]}


def validate_integration_linkage(component: Mapping[str, Any], *, attempted_mutation: bool = False, expected_revision: str | None = None) -> dict[str, Any]:
    _require(attempted_mutation is False, "UI_INTEGRATION_MUTATION_FORBIDDEN", component.get("component_id", "")); name = component.get("component_class"); authority_name = _integration_name(name); validate_integration_authority(component.get("integration_linkage", {}), authority_name)
    _require(component.get("integration_linkage", {}).get("mode") == "READ_ONLY" and component.get("integration_linkage", {}).get("mutation_allowed") is False, "UI_INTEGRATION_REFERENCE_INVALID", component.get("component_id", ""))
    if expected_revision is not None: _require(component["integration_linkage"]["authority"].get("semantic_revision") == expected_revision, "UI_SLOT_AUTHORITY_STALE", component.get("component_id", ""))
    return {"component_id": component["component_id"], "authority": dict(component["integration_linkage"]["authority"]), "mode": "READ_ONLY", "mutation_allowed": False}


def validate_production_registry(registry: Sequence[Mapping[str, Any]], *, production_safe: bool = False) -> bool:
    _require(type(production_safe) is bool, "UI_PRODUCTION_REGISTRY_NON_EMPTY", "typed boundary"); _require(len(registry) == 0, "UI_PRODUCTION_REGISTRY_NON_EMPTY", "production registry must be empty"); _require(production_safe is False, "UI_TEST_ONLY_PRODUCTION_SAFE", "TEST_ONLY fixtures cannot be production safe"); return True


def validate_provenance_output(record: Mapping[str, Any], output_bytes: bytes) -> None:
    _require(record.get("output_sha256") == sha256_bytes(output_bytes), "UI_PROVENANCE_OUTPUT_HASH_MISMATCH", str(record.get("relative_path")))


def validate_historical_authority(authority_bytes: bytes, candidate_bytes: bytes, *, authority_ref: str) -> dict[str, Any]:
    authority_hash = sha256_bytes(authority_bytes); candidate_hash = sha256_bytes(candidate_bytes); _require(candidate_bytes == authority_bytes, "HISTORICAL_EVIDENCE_MUTATION_REJECTED", f"{authority_ref}:{candidate_hash}"); return {"status": "HISTORICAL_AUTHORITY_VALID", "authority_ref": authority_ref, "authority_sha256": authority_hash, "candidate_sha256": candidate_hash}


def compare_generated_outputs(first: Mapping[str, bytes], second: Mapping[str, bytes]) -> bool:
    return type(first) is dict and type(second) is dict and first == second


def validate_determinism(first: Mapping[str, bytes], second: Mapping[str, bytes]) -> None:
    _require(compare_generated_outputs(first, second), "UI_NONDETERMINISTIC_SECOND_RUN", "isolated fixture outputs differ")


def generate_fixture_pack(output_dir: Path) -> dict[str, Any]:
    tokens = build_test_only_style_tokens(); manifest = build_ui_manifest(tokens); validate_ui_manifest(manifest, tokens); output_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, bytes] = {}; records: list[dict[str, Any]] = []
    for component in manifest["components"]:
        state_outputs: dict[str, bytes] = {}
        for state in component["supported_states"]:
            for scale in SUPPORTED_SCALES:
                image = render_component(component, state, scale, tokens); info = validate_rendered_output(image, component, state, scale)
                relative = Path("fixtures") / component["component_class"] / f"{state}-{scale}x.png"; path = output_dir / relative; path.parent.mkdir(parents=True, exist_ok=True); image.save(path, format="PNG", optimize=False, compress_level=9); file_bytes = path.read_bytes(); key = f"{component['component_class']}:{state}:{scale}x"; outputs[key] = file_bytes; state_outputs[state] = file_bytes
                record = {"component_id": component["component_id"], "state": state, "scale_factor": scale, "relative_path": relative.as_posix(), "output_sha256": sha256_bytes(file_bytes), "decoded_pixel_sha256": info["decoded_pixel_sha256"], "cache_key": cache_key_for(component, state, scale, tokens), "content_hash": component["content_hash"], "semantic_input_hash": component["semantic_input_hash"], "raster_size": info["size"]}
                records.append(record)
        validate_state_materiality(state_outputs)
    manifest["outputs"] = records; manifest["manifest_hash"] = sha256_bytes(canonical_json(manifest)); write_json(output_dir / "ui-family-manifest-v0221.json", manifest); return {"manifest": manifest, "outputs": outputs}


__all__ = ["APPROVED_AUTHORITY_SOURCES", "BASE_MAIN_SHA", "CLASS_SPECS", "FAMILY_ID", "PRODUCTION_ROUTING_BLOCKED", "REGISTRY_TEST_ONLY", "RUNTIME_REVISION", "SCHEMA_VERSION", "SUPPORTED_SCALES", "STYLE_TOKEN_SET_ID", "UIAssetFamilyContractError", "UIAssetFamilyError", "UI_COMPONENT_CLASSES", "UI_STATES", "build_cache_key", "build_component_manifest", "build_test_only_style_tokens", "build_ui_manifest", "cache_key_for", "canonical_json", "compare_generated_outputs", "generate_fixture_pack", "render_component", "render_component_to_size", "resolve_approved_authority", "sha256_bytes", "sha256_file", "style_token_hash", "validate_cache_record", "validate_class_spec_table", "validate_component_record", "validate_determinism", "validate_historical_authority", "validate_integration_authority", "validate_integration_linkage", "validate_nine_slice", "validate_production_registry", "validate_provenance_output", "validate_reconstructed_output", "validate_rendered_output", "validate_safe_geometry", "validate_scale_pixel_relation", "validate_state_applicability", "validate_state_materiality", "validate_style_tokens", "validate_ui_manifest", "write_json"]
