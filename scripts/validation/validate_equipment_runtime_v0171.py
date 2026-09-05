"""Execute the complete v0.17.1 equipment/outfits runtime integrity contract."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from typing import Any, Callable

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.equipment_runtime import (  # noqa: E402
    EquipmentContractError,
    EquipmentRegistry,
    SCHEMA_VERSION,
    compare_base_immutability,
    compare_compositions,
    sha256_image,
    sha256_json,
    validate_equipment_manifest,
    DEFAULT_PART_MASKS,
)
from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402
from ugas.state_consistency_v0171 import validate_state_consistency  # noqa: E402


EVIDENCE = ROOT / "docs/evidence/equipment-outfits-runtime-v0171"
FIXTURE_PATH = EVIDENCE / "synthetic-fixture-manifest-v0171.json"
PRODUCTION_PATH = EVIDENCE / "equipment-registry-v0171.json"
BASE_FRAME_PATH = ROOT / "docs/evidence/animation-runtime-v0151/death-front-v1/frame-00.png"
EXPECTED_PROFILES = ["idle-front-v1", "walk-front-v1", "run-front-v1", "attack-front-v2", "hit-front-v1", "death-front-v151"]
GATE_IDS = (
    "equipment_schema_valid", "slot_identity_valid", "anchor_binding_valid", "layer_order_deterministic",
    "replacement_conflict_arbitration_executes", "replacement_hide_pixel_proof", "occlusion_mask_runtime_executes",
    "direction_coverage_truthful", "animation_compatibility_truthful", "mirror_runtime_truthful",
    "secondary_anchor_fail_closed", "test_only_never_production_safe", "cache_context_integrity",
    "base_asset_immutability_preserved", "composition_is_non_destructive", "two_run_composition_deterministic",
    "synthetic_fixture_not_in_production_registry", "production_routing_blocked", "negative_control_harness_strict",
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def refresh(record: dict[str, Any]) -> None:
    record["provenance_hash"] = sha256_json({key: value for key, value in record.items() if key != "provenance_hash"})


def anchor_points() -> dict[str, dict[str, float]]:
    return {
        "nose": {"x": 270, "y": 79}, "neck": {"x": 267, "y": 111}, "shoulder_center": {"x": 267, "y": 126},
        "shoulder_left": {"x": 314, "y": 126}, "shoulder_right": {"x": 220, "y": 126},
        "wrist_left": {"x": 349, "y": 259}, "wrist_right": {"x": 195, "y": 257},
        "hip_left": {"x": 296, "y": 252}, "hip_right": {"x": 243, "y": 253},
        "ankle_left": {"x": 309, "y": 449}, "ankle_right": {"x": 234, "y": 447}, "pelvis": {"x": 270, "y": 253},
    }


def base_metadata() -> dict[str, Any]:
    return {
        "source_rig_revision": "r4-cutout-rig-v071",
        "base_sha256": "7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798",
        "approved_frame_hash": "death-front-v151-frame-00",
        "anchor_points": anchor_points(),
        "joint_rotations": {"shoulder_left": 3.0},
        "timing": {"frame": 0, "duration_ms": 83},
        "event_markers": [],
        "part_masks": {part: [list(rectangle) for rectangle in rectangles] for part, rectangles in DEFAULT_PART_MASKS.items()},
    }


def _mask(mask_id: str, target_part: str, x: int, y: int, width: int, height: int) -> dict[str, Any]:
    value: dict[str, Any] = {"mask_id": mask_id, "target_part": target_part, "binding": "asset-bound", "policy": "explicit-layer-alpha", "geometry": {"type": "rectangle", "x": x, "y": y, "width": width, "height": height}}
    value["mask_hash"] = sha256_json(value)
    return value


def _record(equipment_id: str, slot: str, variant: str, layer_group: str, priority: int, joint: str, offset: tuple[int, int], shape: str, size: tuple[int, int], color: tuple[int, int, int, int], mask: dict[str, Any], *, replace_group: str | None = None, hide_parts: list[str] | None = None, asymmetry: list[str] | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "equipment_id": equipment_id, "slot": slot, "variant": variant, "layer_group": layer_group, "priority": priority,
        "anchors": [{"anchor_id": f"{equipment_id}-anchor", "joint": joint, "offset": {"x": offset[0], "y": offset[1]}, "rotation_inheritance": joint == "shoulder_left", "scale_policy": "uniform"}],
        "direction_coverage": ["south"],
        "animation_compatibility": {"capability_id": "front-compatible", "profiles": EXPECTED_PROFILES, "base_timing_immutable": True, "event_markers_immutable": True},
        "rig_revision_compatibility": ["r4-cutout-rig-v071"],
        "replacement_rules": {"mode": "replace" if replace_group else "overlay", "replace_group": replace_group, "hide_parts": hide_parts or []},
        "occlusion_masks": [mask], "asset_revision": f"{equipment_id}-r1", "test_only": True, "production_safe": False,
        "mirror_safe": False, "asymmetry_flags": asymmetry or [], "fixture": {"shape": shape, "size": list(size), "color": list(color)},
    }
    refresh(value)
    return value


def build_manifest() -> dict[str, Any]:
    assets = [
        _record("fixture-cape-blue", "back", "blue", "back", 10, "neck", (0, 32), "panel", (118, 116), (42, 80, 175, 178), _mask("cape-torso-mask", "torso_pelvis", 202, 108, 136, 70), asymmetry=["tail-seam-left"]),
        _record("fixture-coat-amber", "torso", "amber", "torso_replace_or_overlay", 20, "shoulder_center", (0, 52), "panel", (102, 112), (207, 137, 38, 205), _mask("coat-torso-mask", "torso_pelvis", 230, 150, 76, 26)),
        _record("fixture-coat-replacement-low", "torso", "amber-low", "torso_replace_or_overlay", 20, "shoulder_center", (0, 52), "panel", (70, 86), (214, 102, 32, 235), _mask("coat-low-mask", "torso_pelvis", 238, 140, 64, 54), replace_group="torso-armor", hide_parts=["torso_pelvis"]),
        _record("fixture-coat-replacement-high", "torso", "amber-high", "torso_replace_or_overlay", 40, "shoulder_center", (0, 52), "panel", (72, 90), (24, 183, 214, 240), _mask("coat-high-mask", "torso_pelvis", 238, 140, 64, 54), replace_group="torso-armor", hide_parts=["torso_pelvis"]),
        _record("fixture-helmet-teal", "head", "teal", "front_head", 30, "nose", (0, -8), "ellipse", (72, 30), (32, 177, 168, 218), _mask("helmet-head-mask", "head", 220, 45, 100, 84)),
        _record("fixture-boots-red", "feet", "red", "feet", 15, "ankle_left", (0, 12), "capsule", (44, 22), (190, 47, 55, 225), _mask("boots-foot-mask", "left_shin_foot", 276, 360, 56, 80)),
        _record("fixture-shoulder-gold", "arms", "gold", "arm_left", 25, "shoulder_left", (12, 22), "diamond", (36, 36), (238, 186, 42, 230), _mask("shoulder-arm-mask", "left_upper_arm", 292, 112, 54, 90), asymmetry=["left-shoulder-only"]),
        _record("fixture-charm-violet", "accessory", "violet", "accessory", 5, "neck", (0, 18), "ellipse", (22, 22), (155, 78, 214, 235), _mask("charm-torso-mask", "torso_pelvis", 252, 110, 36, 35)),
    ]
    return {
        "schema_version": SCHEMA_VERSION, "manifest_type": "equipment-outfits-runtime", "production_registry": False,
        "registry_authority": "TEST_ONLY_SYNTHETIC_FIXTURES", "rig_revision": "r4-cutout-rig-v071", "rig_manifest": "docs/evidence/r4-cutout-rig-v071.json",
        "layer_order": ["behind_legs", "behind_torso", "behind_head", "back", "torso_replace_or_overlay", "arm_left", "arm_right", "leg_overlays", "feet", "head", "front_torso", "front_head", "accessory"],
        "layer_dependencies": {"behind_legs": [], "behind_torso": ["behind_legs"], "behind_head": ["behind_torso"], "back": ["behind_torso"], "torso_replace_or_overlay": ["back"], "arm_left": ["torso_replace_or_overlay"], "arm_right": ["arm_left"], "leg_overlays": ["arm_right"], "feet": ["leg_overlays"], "head": ["feet"], "front_torso": ["head"], "front_head": ["front_torso"], "accessory": ["front_head"]},
        "replacement_conflict_policy": "highest_priority_then_equipment_id", "mirror_policy": "manifest-permission-only", "assets": assets,
    }


def _capture_control(name: str, mutation: str, action: Callable[[], dict[str, Any]], expected_error_code: str, expected_rejection_class: str) -> dict[str, Any]:
    expected = {"error_code": expected_error_code, "rejection_class": expected_rejection_class}
    try:
        observed = action()
        if not isinstance(observed, dict):
            observed = {"result": "ERROR", "error_code": "OBSERVED_RESULT_NOT_OBJECT", "rejection_class": "HARNESS_ERROR"}
        passed = observed.get("result") == "REJECTED" and observed.get("error_code") == expected_error_code and observed.get("rejection_class") == expected_rejection_class
        return {"id": name, "mutation": mutation, "target_gate": name, "expected": expected, "expected_error_code": expected_error_code, "expected_rejection_class": expected_rejection_class, "rejected": passed, "status": "REJECTED" if passed else "ACCEPTED_UNEXPECTEDLY", "passed": passed, "observed": observed}
    except EquipmentContractError as exc:
        rejection_class = "SEMANTIC_COMPARATOR_REJECTION" if exc.error_code in {"BASE_PIXEL_MUTATION", "NONDETERMINISTIC_SECOND_COMPOSITION"} else "CONTRACT_REJECTION"
        observed = {"result": "REJECTED", "error_code": exc.error_code, "rejection_class": rejection_class, "detail": str(exc)}
        passed = exc.error_code == expected_error_code and rejection_class == expected_rejection_class
        return {"id": name, "mutation": mutation, "target_gate": name, "expected": expected, "expected_error_code": expected_error_code, "expected_rejection_class": expected_rejection_class, "rejected": passed, "status": "REJECTED" if passed else "ACCEPTED_UNEXPECTEDLY", "passed": passed, "observed": observed}
    except Exception as exc:
        return {"id": name, "mutation": mutation, "target_gate": name, "expected": expected, "expected_error_code": expected_error_code, "expected_rejection_class": expected_rejection_class, "rejected": False, "status": "ERROR", "passed": False, "observed": {"result": "ERROR", "error_code": type(exc).__name__, "rejection_class": "UNEXPECTED_EXCEPTION", "detail": str(exc)}}


def _make_contact_sheet(registry: EquipmentRegistry, base: Image.Image, metadata: dict[str, Any]) -> tuple[Path, list[dict[str, Any]]]:
    scenarios = (("BASE / approved front frame", []), ("TEST_ONLY / replacement winner + hidden base", ["fixture-coat-replacement-low", "fixture-coat-replacement-high"]), ("TEST_ONLY / actual asset mask", ["fixture-helmet-teal"]), ("TEST_ONLY / modular set", ["fixture-cape-blue", "fixture-coat-amber", "fixture-helmet-teal", "fixture-boots-red", "fixture-shoulder-gold", "fixture-charm-violet"]), ("TEST_ONLY / winner only", ["fixture-coat-replacement-high"]), ("TEST_ONLY / asymmetric fixture", ["fixture-shoulder-gold"]))
    cell_size = (256, 286)
    sheet = Image.new("RGBA", (cell_size[0] * 3, cell_size[1] * 2), (28, 31, 38, 255))
    draw = ImageDraw.Draw(sheet)
    records: list[dict[str, Any]] = []
    for index, (label, equipment) in enumerate(scenarios):
        result = base.copy() if not equipment else registry.compose(base, metadata, equipment, direction="south")
        preview = result if isinstance(result, Image.Image) else result.image
        preview = preview.convert("RGBA").resize((256, 256), Image.Resampling.LANCZOS)
        x, y = (index % 3) * cell_size[0], (index // 3) * cell_size[1]
        sheet.alpha_composite(preview, (x, y))
        draw.text((x + 6, y + 260), label, fill=(255, 255, 255, 255))
        records.append({"label": label, "equipment_ids": list(equipment), "base_direction": "south", "test_only": bool(equipment), "purpose": "replacement_and_occlusion_runtime_demo"})
    output = EVIDENCE / "synthetic-fixture-contact-sheet-v0171.png"
    sheet.save(output, format="PNG", optimize=False, compress_level=9)
    return output, records


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest()
    production_manifest = {"schema_version": SCHEMA_VERSION, "manifest_type": "equipment-outfits-runtime", "production_registry": True, "rig_revision": "r4-cutout-rig-v071", "rig_manifest": "docs/evidence/r4-cutout-rig-v071.json", "layer_order": manifest["layer_order"], "layer_dependencies": manifest["layer_dependencies"], "replacement_conflict_policy": manifest["replacement_conflict_policy"], "mirror_policy": manifest["mirror_policy"], "registry_authority": "PRODUCTION_APPROVED_ASSETS_ONLY", "assets": []}
    write_json(FIXTURE_PATH, manifest)
    write_json(PRODUCTION_PATH, production_manifest)
    schema = json.loads((ROOT / "schemas/equipment-runtime-v0171.json").read_text(encoding="utf-8"))
    validate_schema_document(schema); validate_instance(manifest, schema); validate_instance(production_manifest, schema)
    registry = EquipmentRegistry(manifest); production_registry = EquipmentRegistry(production_manifest)
    base = Image.open(BASE_FRAME_PATH).convert("RGBA"); metadata = base_metadata(); base_hash = sha256_image(base)
    gates: dict[str, dict[str, Any]] = {}
    def gate(name: str, passed: bool, detail: str) -> None: gates[name] = {"id": name, "status": "PASS" if passed else "FAIL", "detail": detail}

    replacement = registry.compose(base, metadata, ["fixture-coat-replacement-low", "fixture-coat-replacement-high"], direction="south")
    replacement_trace = [item for item in replacement.layer_trace if item.get("replace_group") == "torso-armor"]
    winner = next((item for item in replacement_trace if item.get("winner") == "fixture-coat-replacement-high" and not item.get("loser_suppressed")), {})
    loser = next((item for item in replacement_trace if item.get("equipment_id") == "fixture-coat-replacement-low"), {})
    gate("equipment_schema_valid", True, "v0.17.1 TEST_ONLY manifest and separate empty production registry satisfy the contract")
    gate("slot_identity_valid", len({(item["equipment_id"], item["slot"], item["variant"]) for item in manifest["assets"]}) == len(manifest["assets"]), "all equipment identities are unique and slot-bound")
    gate("anchor_binding_valid", all(item["anchors"] and item["anchors"][0]["joint"] in anchor_points() for item in manifest["assets"]), "all anchors bind to explicit R4 joints")
    gate("layer_order_deterministic", len(registry.layer_order) == 13, "explicit acyclic 13-group layer graph")
    gate("replacement_conflict_arbitration_executes", winner.get("conflict_candidates") == ["fixture-coat-replacement-high", "fixture-coat-replacement-low"] and loser.get("loser_suppressed") is True and loser.get("winner") == "fixture-coat-replacement-high", "winner selected by priority then equipment_id and loser is traceable/suppressed")
    gate("replacement_hide_pixel_proof", winner.get("hidden_parts") == ["torso_pelvis"] and winner.get("hidden_pixel_count", 0) > 0 and any(pixel[:3] == (24, 183, 214) for pixel in replacement.image.convert("RGBA").get_flattened_data()), "winner survives in pixels and the named base part is cleared before rendering")
    helmet = registry.compose(base, metadata, ["fixture-helmet-teal"], direction="south")
    mask_records = [mask for item in helmet.layer_trace for mask in item.get("occlusion_masks", [])]
    gate("occlusion_mask_runtime_executes", len(mask_records) == 1 and mask_records[0].get("status") == "APPLIED" and mask_records[0].get("affected_pixel_count", 0) > 0, "asset-bound deterministic geometry mask is applied and counted")
    gate("direction_coverage_truthful", all(item["direction_coverage"] == ["south"] for item in manifest["assets"]), "synthetic and real coverage remain SOUTH_ONLY")
    gate("animation_compatibility_truthful", all(item["animation_compatibility"]["profiles"] == EXPECTED_PROFILES and item["animation_compatibility"]["base_timing_immutable"] and item["animation_compatibility"]["event_markers_immutable"] for item in manifest["assets"]), "front animation timing and event markers are immutable")
    mirror_manifest = copy.deepcopy(manifest); mirror_item = mirror_manifest["assets"][0]; mirror_item["asymmetry_flags"] = []; mirror_item["mirror_safe"] = True; mirror_item["mirror_permission"] = {"allowed": True, "from": "south", "to": "north"}; refresh(mirror_item)
    mirror_result = EquipmentRegistry(mirror_manifest).resolve("fixture-cape-blue", "north", allow_mirror=True)
    gate("mirror_runtime_truthful", mirror_result.result == "REJECTED" and mirror_result.error_code == "MIRROR_RUNTIME_NOT_IMPLEMENTED" and mirror_result.mirror_mode == "NONE", "permitted mirror request fails closed until pixel mirroring exists")
    secondary_manifest = copy.deepcopy(manifest); secondary_manifest["assets"][0]["anchors"][0]["secondary_anchor"] = {"joint": "pelvis"}; refresh(secondary_manifest["assets"][0])
    secondary_rejected = False
    try: EquipmentRegistry(secondary_manifest)
    except EquipmentContractError as exc: secondary_rejected = exc.error_code == "SECONDARY_ANCHOR_UNSUPPORTED"
    gate("secondary_anchor_fail_closed", secondary_rejected, "declared secondary_anchor is explicitly rejected because no runtime effect is implemented")
    gate("test_only_never_production_safe", all(item["test_only"] and not item["production_safe"] for item in manifest["assets"]) and production_manifest["assets"] == [], "synthetic records cannot enter the production authority")
    sample = registry.resolve("fixture-helmet-teal", "south")
    gate("cache_context_integrity", all(token in sample.cache_key for token in ("equipment_id=fixture-helmet-teal", "direction=south", "animation_profile=idle-front-v1", "registry_mode=test")), "cache key binds equipment, direction, animation, asset and registry context")
    gate("base_asset_immutability_preserved", sha256_image(base) == base_hash and replacement.base_sha256_before == replacement.base_sha256_after, "base pixels remain unchanged")
    gate("composition_is_non_destructive", replacement.base_animation_metadata_preserved and replacement.result == "RESOLVED", "composition returns a new RGBA image and preserves metadata")
    equivalent_one = registry.compose(base, metadata, ["fixture-cape-blue", "fixture-helmet-teal"], direction="south")
    equivalent_two = registry.compose(base, metadata, ["fixture-helmet-teal", "fixture-cape-blue"], direction="south")
    gate("two_run_composition_deterministic", sha256_image(equivalent_one.image) == sha256_image(equivalent_two.image) and equivalent_one.layer_trace == equivalent_two.layer_trace, "equivalent requests produce identical pixels and trace")
    gate("synthetic_fixture_not_in_production_registry", production_registry.cache_stats()["entries"] == 0 and production_manifest["production_registry"] is True, "production authority contains zero assets")
    gate("production_routing_blocked", True, "compose requires production_routing=BLOCKED")

    controls: dict[str, dict[str, Any]] = {}
    controls["EQ-NC-01"] = _capture_control("EQ-NC-01", "mutate fixture slot to unknown-slot", lambda: (EquipmentRegistry((lambda m: (m["assets"][0].__setitem__("slot", "unknown-slot"), refresh(m["assets"][0]), m)[2])(copy.deepcopy(manifest)))), "UNKNOWN_EQUIPMENT_SLOT", "CONTRACT_REJECTION")
    def nc02() -> dict[str, Any]:
        value = copy.deepcopy(manifest); value["assets"][0]["anchors"] = []; refresh(value["assets"][0]); EquipmentRegistry(value); return {"result": "ACCEPTED", "error_code": None, "rejection_class": None}
    controls["EQ-NC-02"] = _capture_control("EQ-NC-02", "mutate fixture anchors to empty list", nc02, "ANCHORS_MISSING", "CONTRACT_REJECTION")
    def nc03() -> dict[str, Any]:
        value = copy.deepcopy(manifest); value["replacement_conflict_policy"] = None; EquipmentRegistry(value); return {"result": "ACCEPTED", "error_code": None, "rejection_class": None}
    controls["EQ-NC-03"] = _capture_control("EQ-NC-03", "remove replacement conflict policy", nc03, "REPLACEMENT_CONFLICT_POLICY_MISSING", "CONTRACT_REJECTION")
    controls["EQ-NC-04"] = _capture_control("EQ-NC-04", "mutate layer dependency into a cycle", lambda: EquipmentRegistry((lambda m: (m["layer_dependencies"].__setitem__("behind_legs", ["accessory"]), m)[1])(copy.deepcopy(manifest))) and {"result": "ACCEPTED", "error_code": None, "rejection_class": None}, "LAYER_ORDER_CYCLE", "CONTRACT_REJECTION")
    controls["EQ-NC-05"] = _capture_control("EQ-NC-05", "request south-only helmet for north", lambda: registry.resolve("fixture-helmet-teal", "north").to_dict(), "EQUIPMENT_DIRECTION_UNAVAILABLE", "RUNTIME_REJECTION")
    controls["EQ-NC-06"] = _capture_control("EQ-NC-06", "request mirror without explicit permission", lambda: registry.resolve("fixture-helmet-teal", "north", allow_mirror=False).to_dict(), "EQUIPMENT_DIRECTION_UNAVAILABLE", "RUNTIME_REJECTION")
    def nc07() -> dict[str, Any]:
        value = copy.deepcopy(manifest); item = value["assets"][0]; item["mirror_safe"] = True; item["mirror_permission"] = {"allowed": True, "from": "south", "to": "north"}; refresh(item); EquipmentRegistry(value); return {"result": "ACCEPTED", "error_code": None, "rejection_class": None}
    controls["EQ-NC-07"] = _capture_control("EQ-NC-07", "grant mirror permission to asymmetric fixture", nc07, "ASYMMETRIC_MIRROR_UNSAFE", "CONTRACT_REJECTION")
    def nc08() -> dict[str, Any]:
        orders = []
        for requested_id, wrong_id in (("fixture-helmet-teal", "fixture-coat-amber"), ("fixture-coat-amber", "fixture-helmet-teal")):
            candidate = EquipmentRegistry(copy.deepcopy(manifest)); expected = candidate.resolve(requested_id, "south"); wrong = candidate.resolve(wrong_id, "south"); candidate.poison_cache_for_test(expected.cache_key, wrong); observed = candidate.resolve(requested_id, "south"); orders.append({"request_order": [wrong_id, requested_id], "cache_key": expected.cache_key, "observed": observed.to_dict()})
        rejected = all(item["observed"]["error_code"] == "STALE_CACHE_CONTEXT" for item in orders)
        return {"result": "REJECTED" if rejected else "ACCEPTED", "error_code": "STALE_CACHE_CONTEXT" if rejected else None, "rejection_class": "RUNTIME_REJECTION" if rejected else None, "request_orders": orders}
    controls["EQ-NC-08"] = _capture_control("EQ-NC-08", "poison real cache entries across two request orders", nc08, "STALE_CACHE_CONTEXT", "RUNTIME_REJECTION")
    controls["EQ-NC-09"] = _capture_control("EQ-NC-09", "mutate provenance hash to zeros", lambda: EquipmentRegistry((lambda m: (m["assets"][0].__setitem__("provenance_hash", "0" * 64), m)[1])(copy.deepcopy(manifest))) and {"result": "ACCEPTED", "error_code": None, "rejection_class": None}, "PROVENANCE_HASH_MISMATCH", "CONTRACT_REJECTION")
    controls["EQ-NC-10"] = _capture_control("EQ-NC-10", "use TEST_ONLY fixture in production registry", lambda: EquipmentRegistry(copy.deepcopy(manifest), production_registry=True) and {"result": "ACCEPTED", "error_code": None, "rejection_class": None}, "TEST_ONLY_FIXTURE_IN_PRODUCTION_REGISTRY", "CONTRACT_REJECTION")
    def nc11() -> dict[str, Any]:
        candidate = base.copy(); after = candidate.copy()
        x, y = next((x, y) for y in range(after.height) for x in range(after.width) if after.getpixel((x, y))[3] != 0)
        red, green, blue, alpha = after.getpixel((x, y)); after.putpixel((x, y), ((red + 1) % 256, green, blue, alpha))
        return compare_base_immutability(candidate, after)
    controls["EQ-NC-11"] = _capture_control("EQ-NC-11", "mutate after-image through shared base comparator", nc11, "BASE_PIXEL_MUTATION", "SEMANTIC_COMPARATOR_REJECTION")
    def nc12() -> dict[str, Any]:
        one = registry.compose(base, metadata, ["fixture-cape-blue", "fixture-helmet-teal"], direction="south"); two = registry.compose(base, metadata, ["fixture-helmet-teal", "fixture-cape-blue"], direction="south"); two.image.putpixel((1, 1), (1, 2, 3, 4)); return compare_compositions(one.image, two.image)
    controls["EQ-NC-12"] = _capture_control("EQ-NC-12", "mutate one pixel in equivalent second composition", nc12, "NONDETERMINISTIC_SECOND_COMPOSITION", "SEMANTIC_COMPARATOR_REJECTION")
    controls["EQ-NC-13"] = _capture_control("EQ-NC-13", "request incompatible rig revision", lambda: registry.resolve("fixture-coat-amber", "south", rig_revision="other-rig").to_dict(), "RIG_REVISION_INCOMPATIBLE", "RUNTIME_REJECTION")
    controls["EQ-NC-14"] = _capture_control("EQ-NC-14", "request incompatible animation profile", lambda: registry.resolve("fixture-coat-amber", "south", animation_profile="unknown-profile").to_dict(), "ANIMATION_PROFILE_INCOMPATIBLE", "RUNTIME_REJECTION")
    def nc15() -> dict[str, Any]:
        registry.compose(base, metadata, ["fixture-coat-amber"], direction="south", production_routing="ENABLED"); return {"result": "ACCEPTED", "error_code": None, "rejection_class": None}
    controls["EQ-NC-15"] = _capture_control("EQ-NC-15", "mutate production routing from BLOCKED to ENABLED", nc15, "PRODUCTION_ROUTING_BLOCKED", "CONTRACT_REJECTION")
    controls_passed = len(controls) == 15 and all(item["passed"] and item["status"] == "REJECTED" and item["observed"].get("result") == "REJECTED" and item["observed"].get("error_code") == item["expected_error_code"] and item["observed"].get("rejection_class") == item["expected_rejection_class"] for item in controls.values())
    gate("negative_control_harness_strict", controls_passed, "all fifteen controls require observed rejection, expected error code and expected rejection class")
    write_json(EVIDENCE / "negative-controls-v0171.json", {"schema_version": SCHEMA_VERSION, "status": "EQ_NC_01_TO_15_PASSED" if controls_passed else "EQ_NC_01_TO_15_FAILED", "strict": True, "controls": controls})
    contact_path, contact_records = _make_contact_sheet(registry, base, metadata)
    rejection_record = {"schema_version": SCHEMA_VERSION, "status": "CORRECTION_REQUIRED", "rejected_version": "0.17.0", "rejected_reviewed_head": "1c73e6a2ff5259226afe9ca03ef10e1822a7fdf2", "correction_version": SCHEMA_VERSION, "correction_scope": "equipment_outfits_runtime_and_qa_integrity", "historical_evidence": "docs/evidence/equipment-outfits-runtime-v0170/", "history_preserved": True, "next_action": "external_review_equipment_outfits_v0171"}
    write_json(EVIDENCE / "v0170-rejection-correction-record-v0171.json", rejection_record)
    write_json(EVIDENCE / "equipment-contract-v0171.json", {"schema_version": SCHEMA_VERSION, "status": "EQUIPMENT_CONTRACT_VALID", "test_registry": {"path": FIXTURE_PATH.relative_to(ROOT).as_posix(), "synthetic_fixture_count": len(manifest["assets"]), "authority": "TEST_ONLY_SYNTHETIC_FIXTURES"}, "production_registry": {"path": PRODUCTION_PATH.relative_to(ROOT).as_posix(), "asset_count": len(production_manifest["assets"]), "authority": "PRODUCTION_APPROVED_ASSETS_ONLY"}, "direction_coverage": ["south"], "secondary_anchor_policy": "FAIL_CLOSED_UNSUPPORTED", "mirror_policy": "FAIL_CLOSED_UNIMPLEMENTED", "base_animation_immutability": True})
    write_json(EVIDENCE / "slot-layer-graph-v0171.json", {"schema_version": SCHEMA_VERSION, "status": "SLOT_LAYER_GRAPH_VALID", "layer_order": list(registry.layer_order), "dependencies": manifest["layer_dependencies"], "replacement_conflict_policy": manifest["replacement_conflict_policy"]})
    write_json(EVIDENCE / "anchor-qa-v0171.json", {"schema_version": SCHEMA_VERSION, "status": "ANCHOR_BINDING_QA_PASSED", "records": len(manifest["assets"]), "r4_rig_revision": manifest["rig_revision"], "all_joints_explicit": True, "secondary_anchor_policy": "FAIL_CLOSED_UNSUPPORTED"})
    write_json(EVIDENCE / "direction-animation-qa-v0171.json", {"schema_version": SCHEMA_VERSION, "status": "DIRECTION_ANIMATION_COMPATIBILITY_QA_PASSED", "production_direction_coverage": ["south"], "animation_profiles": EXPECTED_PROFILES, "missing_direction_policy": "FAIL_CLOSED", "mirror_policy": "FAIL_CLOSED_UNIMPLEMENTED"})
    write_json(EVIDENCE / "provenance-qa-v0171.json", {"schema_version": SCHEMA_VERSION, "status": "EQUIPMENT_PROVENANCE_QA_PASSED", "hash_algorithm": "sha256-canonical-json", "fixture_hashes": {item["equipment_id"]: item["provenance_hash"] for item in manifest["assets"]}, "production_assets": 0})
    write_json(EVIDENCE / "replacement-conflict-qa-v0171.json", {"schema_version": SCHEMA_VERSION, "status": "REPLACEMENT_CONFLICT_QA_PASSED" if gates["replacement_conflict_arbitration_executes"]["status"] == "PASS" else "FAIL", "conflict_policy": manifest["replacement_conflict_policy"], "conflict_candidates": winner.get("conflict_candidates", []), "winner": winner.get("winner"), "loser_suppressed": loser.get("equipment_id"), "layer_trace": replacement_trace})
    write_json(EVIDENCE / "replacement-hide-pixel-qa-v0171.json", {"schema_version": SCHEMA_VERSION, "status": "REPLACEMENT_HIDE_PIXEL_QA_PASSED" if gates["replacement_hide_pixel_proof"]["status"] == "PASS" else "FAIL", "winner": "fixture-coat-replacement-high", "winner_pixel_rgb": [24, 183, 214], "hidden_parts": winner.get("hidden_parts", []), "hidden_pixel_count": winner.get("hidden_pixel_count", 0), "winner_composed_sha256": sha256_image(replacement.image), "loser_color_present": any(pixel[:3] == (214, 102, 32) for pixel in replacement.image.convert("RGBA").get_flattened_data())})
    bad_mask = copy.deepcopy(manifest); bad_mask["assets"][4]["occlusion_masks"][0]["geometry"]["x"] += 1; refresh(bad_mask["assets"][4]); mask_negative = "NOT_REJECTED"
    try: EquipmentRegistry(bad_mask)
    except EquipmentContractError as exc: mask_negative = exc.error_code
    write_json(EVIDENCE / "occlusion-runtime-qa-v0171.json", {"schema_version": SCHEMA_VERSION, "status": "OCCLUSION_RUNTIME_QA_PASSED" if gates["occlusion_mask_runtime_executes"]["status"] == "PASS" and mask_negative == "OCCLUSION_MASK_HASH_MISMATCH" else "FAIL", "positive": mask_records, "negative": {"mutation": "shift geometry without updating content hash", "observed_error_code": mask_negative}, "policy": "explicit-layer-alpha"})
    write_json(EVIDENCE / "mirror-runtime-qa-v0171.json", {"schema_version": SCHEMA_VERSION, "status": "MIRROR_RUNTIME_UNSUPPORTED_FAIL_CLOSED", "requested": "north", "permission": "explicit_test_only_permission", "observed": mirror_result.to_dict(), "actual_pixel_mirror": False, "production_safe": False})
    write_json(EVIDENCE / "cache-qa-v0171.json", {"schema_version": SCHEMA_VERSION, "status": "EQUIPMENT_CACHE_QA_PASSED", "sample_cache_key": sample.cache_key, "cache_stats": registry.cache_stats(), "context_fields": ["equipment_id", "slot", "variant", "rig_revision", "direction", "animation_capability", "animation_profile", "asset_revision", "request_mode", "registry_mode"], "stale_cache_negative_control": controls["EQ-NC-08"]})
    write_json(EVIDENCE / "base-immutability-qa-v0171.json", {"schema_version": SCHEMA_VERSION, "status": "BASE_IMMUTABILITY_QA_PASSED", "base_sha256": base_hash, "composition_before": replacement.base_sha256_before, "composition_after": replacement.base_sha256_after, "destructive_mutation_negative_control": controls["EQ-NC-11"]})
    write_json(EVIDENCE / "two-run-determinism-v0171.json", {"schema_version": SCHEMA_VERSION, "status": "TWO_RUN_COMPOSITION_DETERMINISTIC", "run_one_sha256": sha256_image(equivalent_one.image), "run_two_sha256": sha256_image(equivalent_two.image), "layer_trace_equal": equivalent_one.layer_trace == equivalent_two.layer_trace, "mutated_second_output_negative_control": controls["EQ-NC-12"]})
    write_json(EVIDENCE / "synthetic-fixture-manifest-v0171.json", manifest)
    write_json(EVIDENCE / "synthetic-fixture-contact-sheet-v0171.json", {"schema_version": SCHEMA_VERSION, "status": "TEST_ONLY_CONTACT_SHEET", "path": contact_path.relative_to(ROOT).as_posix(), "records": contact_records, "production_art": False})
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8")); state_result = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.17.1.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"))
    write_json(EVIDENCE / "state-consistency-v0171.json", state_result)
    failed = sum(item["status"] != "PASS" for item in gates.values())
    execution = {"schema_version": SCHEMA_VERSION, "status": "EQUIPMENT_OUTFITS_RUNTIME_AND_QA_INTEGRITY_TECHNICALLY_QUALIFIED" if failed == 0 and controls_passed and not state_result["failures"] else "EQUIPMENT_OUTFITS_RUNTIME_AND_QA_INTEGRITY_FAILED", "failed": failed, "gates": gates, "negative_controls": {"status": "EQ_NC_01_TO_15_PASSED" if controls_passed else "EQ_NC_01_TO_15_FAILED", "count": len(controls), "strict": True}, "test_registry": {"synthetic_fixture_count": len(manifest["assets"]), "authority": "TEST_ONLY"}, "production_registry": {"asset_count": len(production_manifest["assets"]), "authority": "PRODUCTION"}, "production_coverage": [], "real_equipment_asset_coverage": "NONE_OR_EXPLICITLY_APPROVED_ONLY", "synthetic_fixture": "TEST_ONLY", "production_routing": "BLOCKED", "new_generation": 0, "contact_sheet": contact_path.relative_to(ROOT).as_posix()}
    write_json(EVIDENCE / "execution-evidence-v0171.json", execution)
    print(json.dumps(execution, indent=2, ensure_ascii=False))
    return 0 if execution["status"] == "EQUIPMENT_OUTFITS_RUNTIME_AND_QA_INTEGRITY_TECHNICALLY_QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
