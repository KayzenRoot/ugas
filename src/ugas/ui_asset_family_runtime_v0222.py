"""Fail-closed UI semantic runtime correction for UGAS v0.22.2.

This module is a forward-only correction over v0.22.1.  It keeps the fixture
TEST_ONLY, gives generic UI its own local style/Art-DNA authority, validates a
complete progress-bar contract, and independently verifies decoded 9-slice
pixels instead of trusting the renderer as its only oracle.
"""

from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image

from ugas import ui_asset_family_runtime_v0221 as v021


SCHEMA_VERSION = "0.22.2"
RUNTIME_REVISION = "ui-asset-family-runtime-v0222"
FAMILY_ID = "ugas-ui-asset-family-v0222"
STYLE_TOKEN_SET_ID = "TEST_ONLY_UI_STYLE_V0222"
PRODUCTION_ROUTING_BLOCKED = "BLOCKED"
REGISTRY_TEST_ONLY = "TEST_ONLY"
BASE_MAIN_SHA = v021.BASE_MAIN_SHA
UI_COMPONENT_CLASSES = v021.UI_COMPONENT_CLASSES
UI_STATES = v021.UI_STATES
SUPPORTED_SCALES = v021.SUPPORTED_SCALES
CLASS_SPECS = deepcopy(v021.CLASS_SPECS)


class UIAssetFamilyContractError(ValueError):
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


def _rect(value: Mapping[str, Any], *, name: str, allow_zero: bool = False) -> tuple[int, int, int, int]:
    _require(isinstance(value, Mapping), "UI_GEOMETRY_INVALID", name)
    fields = ("x", "y", "width", "height")
    _require(all(type(value.get(field)) is int for field in fields), "UI_GEOMETRY_INVALID", name)
    x, y, width, height = (int(value[field]) for field in fields)
    _require(x >= 0 and y >= 0 and width >= (0 if allow_zero else 1) and height >= (0 if allow_zero else 1), "UI_GEOMETRY_INVALID", name)
    return x, y, width, height


def _inside(inner: tuple[int, int, int, int], outer: tuple[int, int, int, int]) -> bool:
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    return ix >= ox and iy >= oy and ix + iw <= ox + ow and iy + ih <= oy + oh


def build_test_only_style_tokens() -> dict[str, Any]:
    tokens = deepcopy(v021.build_test_only_style_tokens())
    tokens["style_token_set_id"] = STYLE_TOKEN_SET_ID
    tokens["revision"] = RUNTIME_REVISION
    return tokens


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


LOCAL_STYLE_AUTHORITY = {
    "authority_type": "LOCAL_UI_STYLE_ART_DNA",
    "capability_id": "ui_asset_family",
    "authoritative_path": "docs/evidence/ui-asset-family-runtime-v0222/ui-style-authority-v0222.json",
    "semantic_revision": "v0.22.2",
    "identity": "TEST_ONLY_UI_STYLE_ART_DNA_V0222",
    "external_integration": "NONE",
}
LOCAL_STYLE_AUTHORITY_BYTES = canonical_json(LOCAL_STYLE_AUTHORITY)
LOCAL_STYLE_AUTHORITY_SHA = sha256_bytes(LOCAL_STYLE_AUTHORITY_BYTES)


def _integration_name(component_class: str) -> str:
    if component_class == "inventory_slot":
        return "items_props"
    if component_class == "equipment_slot":
        return "equipment_outfits"
    if component_class == "minimap_frame":
        return "maps_minimap_runtime"
    return "ui_asset_family"


def resolve_approved_authority(authority_name: str) -> dict[str, Any]:
    if authority_name == "ui_asset_family":
        return {
            **LOCAL_STYLE_AUTHORITY,
            "blob_sha256": LOCAL_STYLE_AUTHORITY_SHA,
            "raw_bytes_sha256": LOCAL_STYLE_AUTHORITY_SHA,
        }
    source = v021.resolve_approved_authority(authority_name)
    return {
        **source,
        "authority_type": "EXTERNAL_CAPABILITY_CONTRACT",
        "blob_sha256": source["git_blob_sha"],
        "external_integration": authority_name,
    }


def _class_metadata(component_class: str, width: int, height: int, margin: int) -> dict[str, Any]:
    metadata = deepcopy(v021._class_metadata(component_class, width, height, margin))
    if component_class == "progress_bar":
        frame = {"x": 0, "y": 0, "width": width, "height": height}
        track = {"x": margin, "y": margin, "width": width - 2 * margin, "height": height - 2 * margin}
        fill = {"x": margin + 1, "y": margin + 1, "width": track["width"] - 2, "height": track["height"] - 2}
        metadata.update({
            "frame_rect": frame,
            "track_rect": track,
            "fill_rect": fill,
            "fill_axis": "x",
            "normalized_fill": {
                "domain": [0.0, 1.0], "axis": "x", "origin": "left",
                "direction": "positive", "clipping": "track", "clamp": True,
                "mapping": "FLOOR_LINEAR",
            },
        })
    return metadata


def validate_progress_bar_contract(component: Mapping[str, Any], value: float | None = None) -> dict[str, Any]:
    _require(component.get("component_class") == "progress_bar", "UI_PROGRESS_CONTRACT_INVALID", "not a progress bar")
    metadata = component.get("class_metadata", {})
    visual = _rect(component.get("visual_bounds", {}), name="progress_visual")
    frame = _rect(metadata.get("frame_rect", {}), name="progress_frame")
    track = _rect(metadata.get("track_rect", {}), name="progress_track")
    fill = _rect(metadata.get("fill_rect", {}), name="progress_fill")
    _require(_inside(frame, visual) and _inside(track, frame) and _inside(fill, track), "UI_PROGRESS_GEOMETRY_INVALID", "frame/track/fill containment")
    _require(frame[2] == visual[2] and frame[3] == visual[3], "UI_PROGRESS_GEOMETRY_INVALID", "frame must cover visual bounds")
    normalized = metadata.get("normalized_fill")
    _require(isinstance(normalized, Mapping), "UI_PROGRESS_CONTRACT_INVALID", "normalized fill contract missing")
    _require(normalized.get("domain") == [0.0, 1.0], "UI_PROGRESS_NORMALIZED_RANGE_INVALID", "domain")
    _require(normalized.get("axis") == "x", "UI_PROGRESS_AXIS_INVALID", "axis")
    _require(normalized.get("origin") == "left", "UI_PROGRESS_ORIGIN_INVALID", "origin")
    _require(normalized.get("direction") == "positive", "UI_PROGRESS_DIRECTION_INVALID", "direction")
    _require(normalized.get("clipping") == "track" and normalized.get("clamp") is True and normalized.get("mapping") == "FLOOR_LINEAR", "UI_PROGRESS_MAPPING_INVALID", "mapping")
    if value is not None:
        _require(type(value) is float and 0.0 <= value <= 1.0, "UI_PROGRESS_NORMALIZED_RANGE_INVALID", str(value))
    return {"frame_rect": dict(metadata["frame_rect"]), "track_rect": dict(metadata["track_rect"]), "fill_rect": dict(metadata["fill_rect"]), "normalized_fill": dict(normalized)}


def progress_fill_rect(component: Mapping[str, Any], normalized_value: float) -> dict[str, int]:
    validate_progress_bar_contract(component, normalized_value)
    fill = component["class_metadata"]["fill_rect"]
    width = int(fill["width"] * normalized_value)
    return {"x": fill["x"], "y": fill["y"], "width": width, "height": fill["height"]}


def validate_class_spec_table() -> None:
    _require(tuple(CLASS_SPECS) == UI_COMPONENT_CLASSES, "UI_CLASS_SPEC_TABLE_INVALID", "class authority order")
    for name in UI_COMPONENT_CLASSES:
        spec = CLASS_SPECS[name]
        _require(isinstance(spec.get("states"), tuple) and spec["states"] and set(spec["states"]).issubset(UI_STATES), "UI_STATE_MATRIX_INVALID", name)
        _require(spec.get("stretch_policy") in {"NINE_SLICE", "NON_STRETCH"}, "UI_STRETCH_POLICY_INVALID", name)


def validate_state_applicability(component: Mapping[str, Any], requested_state: str | None = None) -> dict[str, Any]:
    validate_class_spec_table()
    name = component.get("component_class")
    _require(name in UI_COMPONENT_CLASSES, "UI_COMPONENT_CLASS_MISSING", str(name))
    expected = list(CLASS_SPECS[name]["states"])
    _require(component.get("supported_states") == expected, "UI_STATE_MATRIX_INVALID", str(name))
    if requested_state is not None:
        _require(requested_state in expected, "UI_STATE_UNSUPPORTED_FOR_COMPONENT", f"{name}:{requested_state}")
    return {"component_class": name, "supported_states": expected}


def _authority_identity(authority: Mapping[str, Any]) -> dict[str, Any]:
    return {key: authority.get(key) for key in ("authority_type", "capability_id", "authoritative_path", "blob_sha256", "raw_bytes_sha256")}


def _semantic_payload(component: Mapping[str, Any]) -> dict[str, Any]:
    fields = ("component_class", "logical_size", "supported_states", "stretch_geometry", "content_safe_rect", "icon_safe_rect", "text_safe_rect", "visual_bounds", "hit_bounds", "class_metadata", "integration_authority_identity", "style_token_hash")
    return {field: component.get(field) for field in fields}


def _content_payload(component: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in component.items() if key != "content_hash"}


def build_component_manifest(component_class: str, style_tokens: Mapping[str, Any] | None = None) -> dict[str, Any]:
    tokens = dict(style_tokens or build_test_only_style_tokens())
    validate_style_tokens(tokens)
    validate_class_spec_table()
    _require(component_class in UI_COMPONENT_CLASSES, "UI_COMPONENT_CLASS_MISSING", component_class)
    width, height = v021._class_size(component_class)
    margin = int(tokens["metrics"]["nine_slice_margin"])
    visual = {"x": 0, "y": 0, "width": width, "height": height}
    hit = {"x": 1, "y": 1, "width": max(1, width - 2), "height": max(1, height - 2)}
    content = {"x": margin, "y": margin, "width": width - margin * 2, "height": height - margin * 2}
    icon = {"x": margin + 2, "y": margin + 2, "width": width - (margin + 2) * 2, "height": height - (margin + 2) * 2}
    authority = resolve_approved_authority(_integration_name(component_class))
    integration = {"authority": authority, "authority_type": authority["authority_type"], "external_integration": authority.get("external_integration", "NONE"), "mode": "READ_ONLY", "mutation_allowed": False}
    record: dict[str, Any] = {
        "component_id": f"{FAMILY_ID}:{component_class}", "component_class": component_class, "family_id": FAMILY_ID, "revision": RUNTIME_REVISION,
        "supported_states": list(CLASS_SPECS[component_class]["states"]), "default_state": "normal", "logical_size": [width, height],
        "scale_policy": {"supported": list(SUPPORTED_SCALES), "pixel_snap": True, "relation": "NEAREST_NEIGHBOR_2X"},
        "stretch_policy": CLASS_SPECS[component_class]["stretch_policy"],
        "stretch_geometry": {"policy": CLASS_SPECS[component_class]["stretch_policy"], "slice_margins": {"left": margin, "top": margin, "right": margin, "bottom": margin}, "center_width": width - margin * 2, "center_height": height - margin * 2},
        "content_safe_rect": content, "icon_safe_rect": icon, "text_safe_rect": content, "visual_bounds": visual, "hit_bounds": hit,
        "class_metadata": _class_metadata(component_class, width, height, margin), "style_token_set_id": tokens["style_token_set_id"], "style_token_hash": style_token_hash(tokens),
        "integration_linkage": integration, "integration_authority_identity": _authority_identity(authority), "registry_mode": REGISTRY_TEST_ONLY, "production_safe": False,
    }
    record["semantic_input_hash"] = sha256_bytes(canonical_json(_semantic_payload(record)))
    record["content_hash"] = sha256_bytes(canonical_json(_content_payload(record)))
    return record


def build_ui_manifest(style_tokens: Mapping[str, Any] | None = None) -> dict[str, Any]:
    tokens = dict(style_tokens or build_test_only_style_tokens())
    validate_style_tokens(tokens)
    components = [build_component_manifest(name, tokens) for name in UI_COMPONENT_CLASSES]
    return {"schema_version": SCHEMA_VERSION, "manifest_type": "ui-asset-family-runtime-v0222", "family_id": FAMILY_ID, "runtime_revision": RUNTIME_REVISION, "component_classes": list(UI_COMPONENT_CLASSES), "components": components, "state_vocabulary": list(UI_STATES), "style_tokens": tokens, "style_token_hash": style_token_hash(tokens), "registry_mode": REGISTRY_TEST_ONLY, "production_registry_empty": True, "production_routing": PRODUCTION_ROUTING_BLOCKED, "production_approved": False, "real_ui_asset_coverage": "NONE", "synthetic_ui_fixture": REGISTRY_TEST_ONLY, "new_generation": 0, "provenance": {"source": "deterministic-semantic-runtime-fixture", "test_only": True}}


def validate_integration_authority(link: Mapping[str, Any], expected_name: str) -> dict[str, Any]:
    expected = resolve_approved_authority(expected_name)
    recorded = link.get("authority")
    _require(isinstance(recorded, Mapping), "UI_INTEGRATION_AUTHORITY_INVALID", expected_name)
    for field in ("authority_type", "capability_id", "authoritative_path", "blob_sha256", "raw_bytes_sha256"):
        _require(recorded.get(field) == expected.get(field), "UI_INTEGRATION_AUTHORITY_STALE", f"{expected_name}:{field}")
    _require(link.get("authority_type") == expected["authority_type"], "UI_INTEGRATION_AUTHORITY_TYPE_INVALID", expected_name)
    _require(link.get("external_integration") == expected.get("external_integration", "NONE"), "UI_INTEGRATION_AUTHORITY_TYPE_INVALID", expected_name)
    return _authority_identity(expected)


def validate_component_record(component: Mapping[str, Any], style_tokens: Mapping[str, Any] | None = None) -> None:
    tokens = dict(style_tokens or build_test_only_style_tokens())
    validate_style_tokens(tokens); validate_class_spec_table()
    name = component.get("component_class")
    _require(name in UI_COMPONENT_CLASSES, "UI_COMPONENT_CLASS_MISSING", str(name))
    _require(component.get("component_id") == f"{FAMILY_ID}:{name}", "UI_COMPONENT_ID_INVALID", str(component.get("component_id")))
    validate_state_applicability(component)
    _require(component.get("style_token_set_id") == STYLE_TOKEN_SET_ID and component.get("style_token_hash") == style_token_hash(tokens), "UI_STYLE_TOKEN_HASH_STALE", str(name))
    logical = component.get("logical_size", [])
    _require(isinstance(logical, list) and len(logical) == 2 and all(type(value) is int and value > 0 for value in logical), "UI_GEOMETRY_INVALID", "logical_size")
    visual = _rect(component.get("visual_bounds", {}), name="visual_bounds")
    hit = _rect(component.get("hit_bounds", {}), name="hit_bounds")
    _require(visual != hit, "UI_VISUAL_HIT_BOUNDS_NOT_SEPARATE", name)
    for field, rejection in (("content_safe_rect", "UI_CONTENT_SAFE_RECT_OUT_OF_BOUNDS"), ("icon_safe_rect", "UI_ICON_TEXT_SAFE_RECT_OUT_OF_BOUNDS"), ("text_safe_rect", "UI_ICON_TEXT_SAFE_RECT_OUT_OF_BOUNDS")):
        _require(_inside(_rect(component.get(field, {}), name=field), visual), rejection, name)
    _require(component.get("scale_policy", {}).get("supported") == list(SUPPORTED_SCALES), "UI_SCALE_VARIANT_INVALID", name)
    _require(component.get("stretch_policy") == CLASS_SPECS[name]["stretch_policy"], "UI_STRETCH_POLICY_INVALID", name)
    margins = component.get("stretch_geometry", {}).get("slice_margins", {})
    _require(set(margins) == {"left", "top", "right", "bottom"} and all(type(item) is int and item > 0 for item in margins.values()), "UI_NINE_SLICE_MARGINS_INVALID", name)
    _require(component.get("class_metadata") == _class_metadata(name, visual[2], visual[3], margins["left"]), "UI_CLASS_METADATA_INVALID", name)
    expected_name = _integration_name(name)
    validate_integration_authority(component.get("integration_linkage", {}), expected_name)
    _require(component.get("integration_authority_identity") == _authority_identity(resolve_approved_authority(expected_name)), "UI_INTEGRATION_AUTHORITY_STALE", name)
    _require(component.get("integration_linkage", {}).get("mode") == "READ_ONLY" and component.get("integration_linkage", {}).get("mutation_allowed") is False, "UI_INTEGRATION_REFERENCE_INVALID", name)
    if name == "progress_bar":
        validate_progress_bar_contract(component)
    _require(component.get("registry_mode") == REGISTRY_TEST_ONLY and component.get("production_safe") is False, "UI_PRODUCTION_REGISTRY_NON_EMPTY", name)
    _require(component.get("semantic_input_hash") == sha256_bytes(canonical_json(_semantic_payload(component))), "UI_SEMANTIC_INPUT_HASH_STALE", name)
    _require(component.get("content_hash") == sha256_bytes(canonical_json(_content_payload(component))), "UI_CONTENT_HASH_STALE", name)


def validate_ui_manifest(manifest: Mapping[str, Any], style_tokens: Mapping[str, Any] | None = None) -> dict[str, Any]:
    tokens = dict(style_tokens or manifest.get("style_tokens") or build_test_only_style_tokens())
    validate_style_tokens(tokens); validate_class_spec_table()
    _require(manifest.get("schema_version") == SCHEMA_VERSION, "UI_SCHEMA_VERSION_INVALID", str(manifest.get("schema_version")))
    _require(tuple(manifest.get("component_classes", [])) == UI_COMPONENT_CLASSES, "UI_COMPONENT_CLASS_MISSING", "14 authoritative classes required")
    components = manifest.get("components", [])
    _require(len(components) == len(UI_COMPONENT_CLASSES), "UI_COMPONENT_CLASS_MISSING", "component records")
    _require(len({item.get("component_id") for item in components}) == len(components), "UI_COMPONENT_ID_DUPLICATE", "component IDs")
    for component in components:
        validate_component_record(component, tokens)
    _require(manifest.get("style_token_hash") == style_token_hash(tokens), "UI_STYLE_TOKEN_HASH_STALE", "manifest authority")
    _require(manifest.get("production_registry_empty") is True and manifest.get("production_routing") == PRODUCTION_ROUTING_BLOCKED and manifest.get("production_approved") is False and manifest.get("new_generation") == 0, "UI_PRODUCTION_REGISTRY_NON_EMPTY", "production boundary")
    return {"status": "UI_ASSET_FAMILY_MANIFEST_VALID", "component_count": len(components), "state_count": len(UI_STATES), "class_semantics": True}


def _cache_authority_hash(component: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(component["integration_authority_identity"]))


def build_cache_key(*, family_id: str, component_id: str, revision: str, state: str, scale_factor: int, style_token_hash_value: str, semantic_input_hash: str, content_hash: str, authority_identity_hash: str) -> str:
    _require(type(state) is str, "UI_STATE_UNSUPPORTED", str(state)); _require(scale_factor in SUPPORTED_SCALES, "UI_SCALE_VARIANT_INVALID", str(scale_factor))
    return sha256_bytes(canonical_json({"family_id": family_id, "component_id": component_id, "revision": revision, "state": state, "scale_factor": scale_factor, "style_token_hash": style_token_hash_value, "semantic_input_hash": semantic_input_hash, "content_hash": content_hash, "authority_identity_hash": authority_identity_hash}))


def cache_key_for(component: Mapping[str, Any], state: str, scale_factor: int, style_tokens: Mapping[str, Any] | None = None) -> str:
    tokens = dict(style_tokens or build_test_only_style_tokens()); validate_component_record(component, tokens); validate_state_applicability(component, state)
    return build_cache_key(family_id=component["family_id"], component_id=component["component_id"], revision=component["revision"], state=state, scale_factor=scale_factor, style_token_hash_value=style_token_hash(tokens), semantic_input_hash=component["semantic_input_hash"], content_hash=component["content_hash"], authority_identity_hash=_cache_authority_hash(component))


def validate_cache_record(record: Mapping[str, Any], component: Mapping[str, Any], style_tokens: Mapping[str, Any] | None = None) -> None:
    tokens = dict(style_tokens or build_test_only_style_tokens()); validate_component_record(component, tokens)
    required = {"family_id", "component_id", "revision", "state", "scale_factor", "style_token_hash", "semantic_input_hash", "content_hash", "authority_identity_hash", "cache_key"}
    _require(required.issubset(record), "UI_CACHE_IDENTITY_OMITTED", component.get("component_id", ""))
    _require(record.get("family_id") == component["family_id"] and record.get("component_id") == component["component_id"] and record.get("revision") == component["revision"], "UI_CACHE_IDENTITY_OMITTED", component["component_id"])
    validate_state_applicability(component, record.get("state"))
    _require(record.get("style_token_hash") == style_token_hash(tokens) and record.get("semantic_input_hash") == component["semantic_input_hash"] and record.get("content_hash") == component["content_hash"] and record.get("authority_identity_hash") == _cache_authority_hash(component), "UI_CACHE_SEMANTIC_IDENTITY_STALE", component["component_id"])
    expected = build_cache_key(family_id=component["family_id"], component_id=component["component_id"], revision=component["revision"], state=record["state"], scale_factor=record["scale_factor"], style_token_hash_value=record["style_token_hash"], semantic_input_hash=record["semantic_input_hash"], content_hash=record["content_hash"], authority_identity_hash=record["authority_identity_hash"])
    _require(record.get("cache_key") == expected, "UI_CACHE_SEMANTIC_IDENTITY_STALE", component["component_id"])


def render_component(component: Mapping[str, Any], state: str, scale_factor: int, style_tokens: Mapping[str, Any] | None = None) -> Image.Image:
    tokens = dict(style_tokens or build_test_only_style_tokens()); validate_component_record(component, tokens); validate_state_applicability(component, state); _require(scale_factor in SUPPORTED_SCALES, "UI_SCALE_VARIANT_INVALID", str(scale_factor))
    native = v021._render_native(component, state, tokens)
    return native if scale_factor == 1 else native.resize((native.width * scale_factor, native.height * scale_factor), Image.Resampling.NEAREST)


def _nine_slice_resize(source: Image.Image, target_size: tuple[int, int], margins: Mapping[str, int]) -> Image.Image:
    return v021._nine_slice_resize(source, target_size, margins)


def render_component_to_size(component: Mapping[str, Any], state: str, scale_factor: int, target_logical_size: Sequence[int], style_tokens: Mapping[str, Any] | None = None) -> Image.Image:
    tokens = dict(style_tokens or build_test_only_style_tokens()); validate_component_record(component, tokens); validate_state_applicability(component, state); _require(scale_factor in SUPPORTED_SCALES, "UI_SCALE_VARIANT_INVALID", str(scale_factor))
    _require(isinstance(target_logical_size, Sequence) and len(target_logical_size) == 2 and all(type(value) is int and value > 0 for value in target_logical_size), "UI_TARGET_SIZE_INVALID", component["component_id"])
    target = (int(target_logical_size[0]), int(target_logical_size[1])); logical = tuple(component["logical_size"])
    if component["stretch_policy"] == "NON_STRETCH":
        _require(target == logical, "UI_NON_STRETCH_TARGET_INVALID", component["component_id"])
    source = render_component(component, state, 1, tokens)
    result = source if target == logical else _nine_slice_resize(source, target, component["stretch_geometry"]["slice_margins"])
    return result if scale_factor == 1 else result.resize((target[0] * scale_factor, target[1] * scale_factor), Image.Resampling.NEAREST)


def _scaled_source_coord(offset: int, source_length: int, target_length: int) -> int:
    return min(source_length - 1, int(offset * source_length / target_length))


def verify_nine_slice_invariants(source: Image.Image, target: Image.Image, margins: Mapping[str, int]) -> dict[str, Any]:
    """Independent decoded-region proof; it never invokes the renderer."""
    _require(source.mode == "RGBA" and target.mode == "RGBA", "UI_NINE_SLICE_INVARIANT_INVALID", "RGBA required")
    sw, sh = source.size; tw, th = target.size
    left, top, right, bottom = (int(margins[key]) for key in ("left", "top", "right", "bottom"))
    _require(tw >= left + right and th >= top + bottom and sw > left + right and sh > top + bottom, "UI_NINE_SLICE_INVARIANT_INVALID", "invalid region geometry")
    source_cw, source_ch = sw - left - right, sh - top - bottom
    target_cw, target_ch = tw - left - right, th - top - bottom
    checked = {"corners": 0, "top_bottom_edges": 0, "left_right_edges": 0, "center": 0}
    for y in range(th):
        for x in range(tw):
            if x < left:
                sx = x
            elif x >= tw - right:
                sx = sw - right + (x - (tw - right))
            else:
                sx = left + _scaled_source_coord(x - left, source_cw, target_cw)
            if y < top:
                sy = y
            elif y >= th - bottom:
                sy = sh - bottom + (y - (th - bottom))
            else:
                sy = top + _scaled_source_coord(y - top, source_ch, target_ch)
            _require(target.getpixel((x, y)) == source.getpixel((sx, sy)), "UI_NINE_SLICE_INVARIANT_INVALID", f"target:{x},{y}:source:{sx},{sy}")
            if (x < left or x >= tw - right) and (y < top or y >= th - bottom):
                checked["corners"] += 1
            elif y < top or y >= th - bottom:
                checked["top_bottom_edges"] += 1
            elif x < left or x >= tw - right:
                checked["left_right_edges"] += 1
            else:
                checked["center"] += 1
    return {"status": "PASS", "source_size": [sw, sh], "target_size": [tw, th], "checked_pixels": checked}


def validate_reconstructed_output(image: Image.Image, component: Mapping[str, Any], state: str, scale_factor: int, target_logical_size: Sequence[int], style_tokens: Mapping[str, Any] | None = None) -> dict[str, Any]:
    expected = render_component_to_size(component, state, scale_factor, target_logical_size, style_tokens)
    _require(image.mode == "RGBA" and image.size == expected.size and image.tobytes() == expected.tobytes(), "UI_STRETCH_OUTPUT_MISMATCH", component["component_id"])
    if scale_factor == 1 and component["stretch_policy"] == "NINE_SLICE":
        source = render_component(component, state, 1, style_tokens)
        independent = verify_nine_slice_invariants(source, image, component["stretch_geometry"]["slice_margins"])
    else:
        independent = {"status": "PASS", "skipped": True}
    return {"component_id": component["component_id"], "target_logical_size": list(target_logical_size), "scale_factor": scale_factor, "decoded_pixel_sha256": sha256_bytes(image.tobytes()), "reconstruction_valid": True, "independent_invariant_verifier": independent}


def validate_rendered_output(image: Image.Image, component: Mapping[str, Any], state: str, scale_factor: int) -> dict[str, Any]:
    _require(image.mode == "RGBA", "UI_ALPHA_BOUNDS_INVALID", "RGBA required")
    _require(image.size == tuple(int(value) * scale_factor for value in component["logical_size"]), "UI_SCALE_OUTPUT_INVALID", component["component_id"])
    _require(image.getbbox() is not None, "UI_ALPHA_BOUNDS_INVALID", component["component_id"])
    validate_state_applicability(component, state)
    return {"mode": image.mode, "size": list(image.size), "decoded_pixel_sha256": sha256_bytes(image.tobytes())}


def validate_scale_pixel_relation(one_x: Image.Image, two_x: Image.Image, component: Mapping[str, Any], state: str) -> dict[str, Any]:
    validate_state_applicability(component, state)
    expected = one_x.resize((one_x.width * 2, one_x.height * 2), Image.Resampling.NEAREST)
    _require(two_x.size == expected.size and two_x.tobytes() == expected.tobytes(), "UI_SCALE_PIXEL_RELATION_INVALID", component["component_id"])
    return {"component_id": component["component_id"], "state": state, "one_x_decoded_sha256": sha256_bytes(one_x.tobytes()), "expected_expanded_sha256": sha256_bytes(expected.tobytes()), "actual_two_x_decoded_sha256": sha256_bytes(two_x.tobytes()), "result": "PASS"}


def validate_state_materiality(outputs: Mapping[str, bytes]) -> None:
    _require(bool(outputs) and set(outputs).issubset(set(UI_STATES)), "UI_STATE_VOCABULARY_INVALID", "state set")
    _require(len(set(outputs.values())) == len(outputs), "UI_STATE_BYTES_NOT_DISTINCT", "state bytes must differ")


def validate_nine_slice(component: Mapping[str, Any]) -> dict[str, Any]:
    visual = _rect(component["visual_bounds"], name="visual_bounds"); margins = component["stretch_geometry"]["slice_margins"]
    left, top, right, bottom = (margins[name] for name in ("left", "top", "right", "bottom"))
    if component["stretch_policy"] == "NON_STRETCH":
        return {"component_id": component["component_id"], "policy": "NON_STRETCH", "slice_margins": dict(margins)}
    _require(left + right < visual[2] and top + bottom < visual[3], "UI_NINE_SLICE_CENTER_INVALID", component["component_id"])
    return {"component_id": component["component_id"], "policy": "NINE_SLICE", "slice_margins": dict(margins), "center_area": [visual[2] - left - right, visual[3] - top - bottom]}


def validate_integration_linkage(component: Mapping[str, Any], *, attempted_mutation: bool = False, expected_revision: str | None = None) -> dict[str, Any]:
    _require(attempted_mutation is False, "UI_INTEGRATION_MUTATION_FORBIDDEN", component.get("component_id", ""))
    name = component.get("component_class"); validate_integration_authority(component.get("integration_linkage", {}), _integration_name(name))
    _require(component["integration_linkage"].get("mode") == "READ_ONLY" and component["integration_linkage"].get("mutation_allowed") is False, "UI_INTEGRATION_REFERENCE_INVALID", component.get("component_id", ""))
    if expected_revision is not None:
        _require(component["integration_linkage"]["authority"].get("semantic_revision") == expected_revision, "UI_SLOT_AUTHORITY_STALE", component.get("component_id", ""))
    return {"component_id": component["component_id"], "authority": dict(component["integration_linkage"]["authority"]), "mode": "READ_ONLY", "mutation_allowed": False}


def validate_production_registry(registry: Sequence[Mapping[str, Any]], *, production_safe: bool = False) -> bool:
    _require(type(production_safe) is bool and len(registry) == 0 and production_safe is False, "UI_PRODUCTION_REGISTRY_NON_EMPTY", "TEST_ONLY production boundary")
    return True


def validate_provenance_output(record: Mapping[str, Any], output_bytes: bytes) -> None:
    _require(record.get("output_sha256") == sha256_bytes(output_bytes), "UI_PROVENANCE_OUTPUT_HASH_MISMATCH", str(record.get("relative_path")))


def validate_historical_authority(authority_bytes: bytes, candidate_bytes: bytes, *, authority_ref: str) -> dict[str, Any]:
    authority_canonical = authority_bytes.replace(b"\r\n", b"\n")
    candidate_canonical = candidate_bytes.replace(b"\r\n", b"\n")
    authority_hash = sha256_bytes(authority_canonical); candidate_hash = sha256_bytes(candidate_canonical)
    _require(candidate_canonical == authority_canonical, "HISTORICAL_EVIDENCE_MUTATION_REJECTED", f"{authority_ref}:{candidate_hash}")
    return {"status": "HISTORICAL_AUTHORITY_VALID", "authority_ref": authority_ref, "authority_sha256": authority_hash, "candidate_sha256": candidate_hash, "candidate_raw_sha256": sha256_bytes(candidate_bytes)}


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
                image = render_component(component, state, scale, tokens); validate_rendered_output(image, component, state, scale)
                buffer = BytesIO(); image.save(buffer, format="PNG", optimize=False, compress_level=9); data = buffer.getvalue(); relative = Path("fixtures") / component["component_class"] / f"{state}-{scale}x.png"; (output_dir / relative).parent.mkdir(parents=True, exist_ok=True); (output_dir / relative).write_bytes(data); outputs[str(relative)] = data
                records.append({"component_id": component["component_id"], "component_class": component["component_class"], "state": state, "scale_factor": scale, "relative_path": str(relative).replace("\\", "/"), "output_sha256": sha256_bytes(data), "cache_key": cache_key_for(component, state, scale, tokens), "authority_identity_hash": _cache_authority_hash(component)})
                if scale == 1: state_outputs[state] = data
        validate_state_materiality(state_outputs)
    manifest = {**manifest, "outputs": records, "local_style_authority_bytes_sha256": LOCAL_STYLE_AUTHORITY_SHA}
    write_json(output_dir / "ui-family-manifest-v0222.json", manifest)
    return {"manifest": manifest, "outputs": outputs}


__all__ = [
    "BASE_MAIN_SHA", "CLASS_SPECS", "FAMILY_ID", "LOCAL_STYLE_AUTHORITY", "LOCAL_STYLE_AUTHORITY_BYTES", "LOCAL_STYLE_AUTHORITY_SHA", "PRODUCTION_ROUTING_BLOCKED", "REGISTRY_TEST_ONLY", "RUNTIME_REVISION", "SCHEMA_VERSION", "SUPPORTED_SCALES", "STYLE_TOKEN_SET_ID", "UIAssetFamilyContractError", "UIAssetFamilyError", "UI_COMPONENT_CLASSES", "UI_STATES", "build_cache_key", "build_component_manifest", "build_test_only_style_tokens", "build_ui_manifest", "cache_key_for", "canonical_json", "compare_generated_outputs", "generate_fixture_pack", "progress_fill_rect", "render_component", "render_component_to_size", "resolve_approved_authority", "sha256_bytes", "sha256_file", "style_token_hash", "validate_cache_record", "validate_class_spec_table", "validate_component_record", "validate_determinism", "validate_historical_authority", "validate_integration_authority", "validate_integration_linkage", "validate_nine_slice", "validate_progress_bar_contract", "validate_production_registry", "validate_provenance_output", "validate_reconstructed_output", "validate_rendered_output", "validate_scale_pixel_relation", "validate_state_applicability", "validate_state_materiality", "validate_style_tokens", "validate_ui_manifest", "verify_nine_slice_invariants", "write_json",
]
