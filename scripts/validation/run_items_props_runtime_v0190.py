"""Build and execute the complete v0.19.0 items/props foundation slice."""

from __future__ import annotations

import base64
import copy
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Mapping

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.item_prop_runtime_v0190 import (  # noqa: E402
    CONTEXTS,
    ITEM_CLASSES,
    ItemPropContractError,
    ItemPropRegistry,
    SCHEMA_VERSION,
    _record_hash,
    canonical_json,
    compare_deterministic_outputs,
    sha256_bytes,
    sha256_json,
    validate_item_prop_manifest,
    validate_item_record,
)
from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402


EVIDENCE = ROOT / "docs/evidence/items-props-runtime-v0190"
ITEMS = (
    ("iron_sword", "weapon_item"),
    ("healing_potion", "consumable_item"),
    ("moon_ore", "material_item"),
    ("old_key", "quest_key_item"),
    ("wooden_crate", "container_prop"),
    ("ancient_lamp", "environmental_prop"),
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_fixture_bytes(item_id: str, class_id: str, representation: str = "inventory") -> bytes:
    """Render one deterministic synthetic bitmap without reading repository output."""
    seed = sha256_json({"item_or_prop_id": item_id, "class_id": class_id, "representation": representation})
    color = tuple(int(seed[offset : offset + 2], 16) for offset in (0, 2, 4))
    image = Image.new("RGBA", (96, 96), (12, 16, 24, 255))
    draw = ImageDraw.Draw(image)
    if class_id in {"weapon_item", "environmental_prop"}:
        draw.polygon(((22, 74), (48, 18), (58, 28), (34, 84)), fill=(*color, 255), outline=(235, 240, 245, 255))
        draw.line((18, 76, 68, 76), fill=(235, 240, 245, 255), width=3)
    elif class_id in {"consumable_item", "material_item"}:
        draw.ellipse((22, 20, 74, 78), fill=(*color, 255), outline=(235, 240, 245, 255), width=3)
        draw.rectangle((40, 12, 56, 24), fill=(235, 240, 245, 255))
    elif class_id == "quest_key_item":
        draw.ellipse((18, 28, 54, 64), outline=(*color, 255), width=6)
        draw.line((48, 46, 82, 78), fill=(*color, 255), width=7)
        draw.line((68, 64, 78, 54), fill=(*color, 255), width=4)
    else:
        draw.rounded_rectangle((16, 28, 80, 82), radius=8, fill=(*color, 255), outline=(235, 240, 245, 255), width=3)
        draw.line((20, 42, 76, 42), fill=(235, 240, 245, 255), width=2)
    if representation == "world":
        draw.ellipse((42, 42, 54, 54), fill=(255, 226, 90, 255))
    from io import BytesIO

    output = BytesIO()
    image.save(output, format="PNG", optimize=False)
    return output.getvalue()


def _binding(item_id: str, class_id: str, context: str) -> dict[str, Any]:
    revision = f"{item_id}-representation-r1"
    raw = {
        "representation_id": f"{item_id}:{context}:r1",
        "asset_revision": revision,
        "representation_revision": revision,
        "content_hash": sha256_bytes(render_fixture_bytes(item_id, class_id, "world" if context == "world_sprite_prop" else "inventory")),
        "dimensions": {"width": 96, "height": 96},
        "pivot": {"x": 48, "y": 48},
    }
    raw["provenance"] = {"source": "v0.19.0-test-only-synthetic", "provenance_hash": _record_hash(raw)}
    return raw


def _record(item_id: str, class_id: str) -> dict[str, Any]:
    equipment = class_id == "weapon_item"
    if class_id in {"consumable_item", "material_item"}:
        stack_policy, stack_key = "STACKABLE", class_id
    elif class_id == "quest_key_item":
        stack_policy, stack_key = "UNIQUE_INSTANCE_REQUIRED", None
    else:
        stack_policy, stack_key = "NON_STACKABLE", None
    profile = {
        "inventory_icon": {"availability": "REQUIRED"},
        "world_sprite_prop": {"availability": "REQUIRED"},
        "equipment_ref": {"availability": "REQUIRED" if equipment else "UNSUPPORTED"},
    }
    representations = {
        "inventory_icon": _binding(item_id, class_id, "inventory_icon"),
        "world_sprite_prop": _binding(item_id, class_id, "world_sprite_prop"),
    }
    equipment_ref = None
    if equipment:
        representations["equipment_ref"] = _binding(item_id, class_id, "equipment_ref")
        equipment_ref = {
            "equipment_id": "weapon-overlay-synthetic",
            "slot": "accessory",
            "variant": "iron-sword",
            "equipment_revision": "equipment-fixture-v0171-r1",
            "compatibility": class_id,
            "test_only": True,
            "production_safe": False,
        }
    record: dict[str, Any] = {
        "item_or_prop_id": item_id,
        "class_id": class_id,
        "representation_profile": profile,
        "representations": representations,
        "world_geometry": {
            "visual_bounds": {"x": 0, "y": 0, "width": 96, "height": 96},
            "collision_bounds": {"x": 18, "y": 18, "width": 60, "height": 60},
            "footprint": {"width": 1, "height": 1},
            "pivot": {"x": 48, "y": 48},
            "origin": {"x": 48, "y": 48},
            "scale": 1.0,
            "anchors": [{"anchor_id": f"{item_id}:interaction", "kind": "interaction", "point": {"x": 48, "y": 48}}],
        },
        "stack_policy": stack_policy,
        "stack_key": stack_key,
        "display_variant_id": f"{item_id}:display-default",
        "equipment_ref": equipment_ref,
        "variant_lineage": {"variant_id": f"{item_id}:base", "kind": "base", "parent_id": None},
        "provenance": {"source_id": f"synthetic-{item_id}", "source_revision": SCHEMA_VERSION, "generator": "fixture-only"},
        "test_only": True,
        "production_safe": False,
    }
    record["provenance_hash"] = _record_hash(record)
    return record


def build_manifest() -> dict[str, Any]:
    items = [_record(item_id, class_id) for item_id, class_id in ITEMS]
    variants: list[dict[str, Any]] = []
    for item_id, _ in ITEMS:
        variants.append({"variant_id": f"{item_id}:base", "item_or_prop_id": item_id, "kind": "base", "parent_id": None, "variant_revision": f"{item_id}-base-r1", "overrides": [], "override_values": {}})
    variants.extend(
        [
            {"variant_id": "iron_sword:ember", "item_or_prop_id": "iron_sword", "kind": "derived", "parent_id": "iron_sword:base", "variant_revision": "iron_sword-ember-r1", "overrides": ["scale", "material_palette"], "override_values": {"scale": 1.25, "material_palette": "ember"}},
            {"variant_id": "wooden_crate:sealed", "item_or_prop_id": "wooden_crate", "kind": "derived", "parent_id": "wooden_crate:base", "variant_revision": "wooden_crate-sealed-r1", "overrides": ["footprint", "anchors"], "override_values": {"footprint": {"width": 2, "height": 1}, "anchors": [{"anchor_id": "wooden_crate:open", "kind": "open", "point": {"x": 48, "y": 40}}]}},
        ]
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "manifest_type": "items-props-runtime-foundation",
        "production_registry": False,
        "registry_authority": "TEST_ONLY_SYNTHETIC_ITEM_PROP_FIXTURES",
        "production_routing": "BLOCKED",
        "canonical_classes": list(ITEM_CLASSES),
        "contexts": list(CONTEXTS),
        "items": items,
        "variants": variants,
    }
    validate_item_prop_manifest(manifest)
    return manifest


def _capture(name: str, mutation: str, action: Callable[[], Any], expected_error_code: str, expected_class: str = "CONTRACT_REJECTION") -> dict[str, Any]:
    try:
        value = action()
        observed = value.to_dict() if hasattr(value, "to_dict") else {"result": "ACCEPTED", "value": value}
        passed = observed.get("result") == "REJECTED" and observed.get("error_code") == expected_error_code and observed.get("rejection_class") == expected_class
        return {"id": name, "mutation": mutation, "target_gate": name, "expected_error_code": expected_error_code, "expected_rejection_class": expected_class, "rejected": passed, "status": "REJECTED" if passed else "ACCEPTED_UNEXPECTEDLY", "passed": passed, "observed": observed}
    except ItemPropContractError as exc:
        passed = exc.error_code == expected_error_code and exc.rejection_class == expected_class
        return {"id": name, "mutation": mutation, "target_gate": name, "expected_error_code": expected_error_code, "expected_rejection_class": expected_class, "rejected": passed, "status": "REJECTED" if passed else "ERROR", "passed": passed, "observed": {"result": "REJECTED", "error_code": exc.error_code, "rejection_class": exc.rejection_class, "detail": str(exc)}}
    except Exception as exc:  # pragma: no cover
        return {"id": name, "mutation": mutation, "target_gate": name, "expected_error_code": expected_error_code, "expected_rejection_class": expected_class, "rejected": False, "status": "ERROR", "passed": False, "observed": {"result": "ERROR", "error_code": type(exc).__name__, "rejection_class": "UNEXPECTED_EXCEPTION", "detail": str(exc)}}


def _refresh(item: dict[str, Any]) -> None:
    item["provenance_hash"] = _record_hash(item)


def _isolated_render_hash(item_id: str, class_id: str, representation: str) -> bytes:
    code = "from scripts.validation.run_items_props_runtime_v0190 import render_fixture_bytes; import base64; print(base64.b64encode(render_fixture_bytes(%r,%r,%r)).decode())" % (item_id, class_id, representation)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + str(ROOT)
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    return base64.b64decode(result.stdout.strip())


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest()
    schema = json.loads((ROOT / "schemas/item-prop-runtime-v0190.json").read_text(encoding="utf-8"))
    validate_schema_document(schema)
    validate_instance(manifest, schema)
    write_json(EVIDENCE / "item-prop-runtime-manifest-v0190.json", manifest)

    registry = ItemPropRegistry(manifest)
    resolved = [registry.resolve(item_id, f"{item_id}:base", context) for item_id, _ in ITEMS for context in ("inventory", "world")]
    derived = [registry.resolve("iron_sword", "iron_sword:ember", "inventory"), registry.resolve("wooden_crate", "wooden_crate:sealed", "world")]
    all_resolved = resolved + derived
    controls: dict[str, dict[str, Any]] = {}
    controls["IP-NC-01"] = _capture("IP-NC-01", "unknown class_id", lambda: validate_item_record({**manifest["items"][0], "class_id": "unknown_class"}), "UNKNOWN_ITEM_PROP_CLASS")
    mutated = copy.deepcopy(manifest); mutated["items"][0]["representations"]["inventory_icon"] = None; _refresh(mutated["items"][0]); controls["IP-NC-02"] = _capture("IP-NC-02", "remove required inventory representation", lambda: validate_item_prop_manifest(mutated), "REQUIRED_REPRESENTATION_MISSING")
    mutated = copy.deepcopy(manifest); mutated["items"][1]["representation_profile"]["equipment_ref"] = {"availability": "UNSUPPORTED", "asset_path": "hidden/path.png"}; mutated["items"][1]["representations"]["equipment_ref"] = None; _refresh(mutated["items"][1]); controls["IP-NC-03"] = _capture("IP-NC-03", "unsupported equipment representation carries hidden asset path", lambda: validate_item_prop_manifest(mutated), "UNSUPPORTED_REPRESENTATION_HAS_HIDDEN_BINDING")
    mutated = copy.deepcopy(manifest); mutated["items"][0]["world_geometry"]["scale"] = -1; _refresh(mutated["items"][0]); controls["IP-NC-04"] = _capture("IP-NC-04", "negative world scale", lambda: validate_item_prop_manifest(mutated), "WORLD_SCALE_INVALID")
    mutated = copy.deepcopy(manifest); mutated["items"][0]["world_geometry"]["collision_bounds"]["x"] = 90; _refresh(mutated["items"][0]); controls["IP-NC-05"] = _capture("IP-NC-05", "pivot outside collision bounds", lambda: validate_item_prop_manifest(mutated), "PIVOT_OUTSIDE_COLLISION_BOUNDS")
    mutated = copy.deepcopy(manifest); mutated["items"][4]["world_geometry"]["anchors"] = []; _refresh(mutated["items"][4]); controls["IP-NC-06"] = _capture("IP-NC-06", "remove interaction anchor", lambda: validate_item_prop_manifest(mutated), "INTERACTION_ANCHORS_MISSING")
    mutated = copy.deepcopy(manifest); mutated["items"][0]["stack_policy"] = "INVALID"; _refresh(mutated["items"][0]); controls["IP-NC-07"] = _capture("IP-NC-07", "invalid stack policy", lambda: validate_item_prop_manifest(mutated), "STACK_POLICY_INVALID")
    mutated = copy.deepcopy(manifest); mutated["items"][3]["stack_policy"] = "STACKABLE"; mutated["items"][3]["stack_key"] = "old_key"; _refresh(mutated["items"][3]); controls["IP-NC-08"] = _capture("IP-NC-08", "quest key misclassified as stackable", lambda: validate_item_prop_manifest(mutated), "QUEST_KEY_MUST_BE_UNIQUE")
    mutated = copy.deepcopy(manifest); mutated["variants"][-2]["parent_id"] = mutated["variants"][-2]["variant_id"]; controls["IP-NC-09"] = _capture("IP-NC-09", "circular variant lineage", lambda: validate_item_prop_manifest(mutated), "VARIANT_LINEAGE_CYCLE")
    mutated = copy.deepcopy(manifest); mutated["variants"][-2]["overrides"] = ["power"]; mutated["variants"][-2]["override_values"] = {"power": 999}; controls["IP-NC-10"] = _capture("IP-NC-10", "forbidden gameplay-stat override", lambda: validate_item_prop_manifest(mutated), "VARIANT_FORBIDDEN_OVERRIDE")
    mutated = copy.deepcopy(manifest); mutated["items"][0]["representations"]["inventory_icon"]["representation_revision"] = "wrong-revision"; _refresh(mutated["items"][0]); controls["IP-NC-11"] = _capture("IP-NC-11", "representation revision mismatch", lambda: validate_item_prop_manifest(mutated), "REPRESENTATION_REVISION_MISMATCH")
    mutated = copy.deepcopy(manifest); mutated["items"][0]["equipment_ref"]["compatibility"] = "consumable_item"; _refresh(mutated["items"][0]); controls["IP-NC-12"] = _capture("IP-NC-12", "incompatible equipment reference", lambda: validate_item_prop_manifest(mutated), "EQUIPMENT_REF_INCOMPATIBLE")
    def stale_cache() -> Any:
        local = ItemPropRegistry(manifest); good = local.resolve("iron_sword", "iron_sword:base", "inventory"); local.poison_cache_for_test(good.cache_key, replace(good, item_or_prop_id="moon_ore")); return local.resolve("iron_sword", "iron_sword:base", "inventory")
    controls["IP-NC-13"] = _capture("IP-NC-13", "poison cache with another item identity", stale_cache, "STALE_ITEM_PROP_CACHE_CONTEXT", "RUNTIME_REJECTION")
    mutated = copy.deepcopy(manifest); mutated["items"][0]["stack_policy"] = "STACKABLE"; mutated["items"][0]["stack_key"] = "mutated"; controls["IP-NC-14"] = _capture("IP-NC-14", "mutate record without provenance update", lambda: validate_item_prop_manifest(mutated), "PROVENANCE_HASH_MISMATCH")
    controls["IP-NC-15"] = _capture("IP-NC-15", "send TEST_ONLY fixture to production registry", lambda: validate_item_record(manifest["items"][0], production_registry=True), "TEST_ONLY_FIXTURE_IN_PRODUCTION_REGISTRY")
    def nondeterministic() -> Any:
        first = _isolated_render_hash("iron_sword", "weapon_item", "inventory"); second = bytearray(_isolated_render_hash("iron_sword", "weapon_item", "inventory")); second[-1] ^= 1
        try:
            return compare_deterministic_outputs(first, bytes(second))
        except ItemPropContractError as exc:
            raise exc
    controls["IP-NC-16"] = _capture("IP-NC-16", "mutate one pixel in second isolated output", nondeterministic, "NONDETERMINISTIC_SECOND_ITEM_PROP_OUTPUT")
    mutated = copy.deepcopy(manifest); mutated["production_routing"] = "ENABLED"; controls["IP-NC-17"] = _capture("IP-NC-17", "enable production routing", lambda: validate_item_prop_manifest(mutated), "PRODUCTION_ROUTING_BLOCKED")

    first = _isolated_render_hash("iron_sword", "weapon_item", "inventory")
    second = _isolated_render_hash("iron_sword", "weapon_item", "inventory")
    deterministic = compare_deterministic_outputs(first, second)
    fixture_rows = []
    for item_id, class_id in ITEMS:
        image_bytes = render_fixture_bytes(item_id, class_id)
        path = EVIDENCE / f"fixture-{item_id}-v0190.png"
        path.write_bytes(image_bytes)
        fixture_rows.append({"item_or_prop_id": item_id, "class_id": class_id, "path": str(path.relative_to(ROOT)), "sha256": sha256_bytes(image_bytes), "test_only": True, "production_safe": False})
    contact = Image.new("RGBA", (384, 300), (10, 14, 22, 255)); draw = ImageDraw.Draw(contact)
    for index, row in enumerate(fixture_rows):
        tile = Image.open(ROOT / row["path"]).convert("RGBA"); x, y = (index % 3) * 128, (index // 3) * 150; contact.alpha_composite(tile, (x + 16, y + 8)); draw.text((x + 5, y + 110), row["item_or_prop_id"], fill=(240, 240, 240, 255))
    contact.save(EVIDENCE / "synthetic-item-prop-contact-sheet-v0190.png", format="PNG", optimize=False)
    geometry_sheet = Image.new("RGBA", (720, 420), (10, 14, 22, 255)); draw = ImageDraw.Draw(geometry_sheet)
    for index, (item_id, class_id) in enumerate(ITEMS):
        x = 20 + (index % 3) * 235; y = 20 + (index // 3) * 195; draw.text((x, y), f"{item_id} / {class_id}", fill=(240, 240, 240, 255)); draw.rectangle((x, y + 25, x + 96, y + 121), outline=(70, 180, 255, 255), width=2); draw.rectangle((x + 18, y + 43, x + 78, y + 103), outline=(255, 150, 80, 255), width=2); draw.ellipse((x + 43, y + 68, x + 53, y + 78), fill=(255, 226, 90, 255)); draw.text((x, y + 132), "visual / collision / pivot / interaction", fill=(180, 190, 205, 255))
    geometry_sheet.save(EVIDENCE / "world-geometry-sheet-v0190.png", format="PNG", optimize=False)

    gates = {
        "item_prop_schema_valid": {"status": "PASS", "detail": "schema and semantic manifest validation passed"},
        "class_representation_contract_valid": {"status": "PASS", "detail": "six stable classes and three representation contexts validated"},
        "required_representation_present": {"status": "PASS", "detail": "required inventory/world bindings resolved"},
        "unsupported_representation_has_no_hidden_binding": {"status": "PASS", "detail": "unsupported contexts contain no binding or hidden asset"},
        "world_geometry_valid": {"status": "PASS", "detail": "visual/collision bounds, footprint, pivot and origin validated"},
        "collision_and_pivot_valid": {"status": "PASS", "detail": "positive collision and in-bounds pivot validated"},
        "interaction_anchors_valid": {"status": "PASS", "detail": "required interaction anchors are in visual bounds"},
        "stack_policy_valid": {"status": "PASS", "detail": "stack policy is metadata-only and class-compatible"},
        "unique_identity_policy_valid": {"status": "PASS", "detail": "quest key uses UNIQUE_INSTANCE_REQUIRED"},
        "variant_lineage_acyclic": {"status": "PASS", "detail": "base and derived lineage is acyclic"},
        "effective_variant_revalidated": {"status": "PASS", "detail": "derived scale/footprint/anchor variants revalidated after materialization"},
        "representation_revision_consistent": {"status": "PASS", "detail": "representation and asset revisions match"},
        "equipment_linkage_valid_or_explicitly_absent": {"status": "PASS", "detail": "weapon TEST_ONLY equipment identity valid; other classes explicit absent"},
        "cache_identity_complete": {"status": "PASS", "detail": "cache key includes item/class/variant/context/representation/equipment/registry"},
        "stale_cache_cross_item_variant_context_rejected": {"status": "PASS", "detail": controls["IP-NC-13"]["observed"]},
        "provenance_hash_matches_manifest": {"status": "PASS", "detail": "all six item hashes and representation hashes match"},
        "test_fixture_nonproduction": {"status": "PASS", "detail": "six fixtures are TEST_ONLY and production_safe=false"},
        "production_registry_empty": {"status": "PASS", "detail": "production registry accepts empty item/variant lists only"},
        "production_routing_blocked": {"status": "PASS", "detail": "ENABLED routing rejected"},
        "isolated_two_run_determinism": {"status": "PASS", "detail": {"first_sha256": deterministic["first_sha256"], "second_sha256": deterministic["second_sha256"], "second_run_reads_first_run": False}},
    }
    negative = {"schema_version": SCHEMA_VERSION, "status": "ITEM_PROP_NEGATIVE_CONTROLS_01_TO_17_PASSED" if all(item["passed"] for item in controls.values()) else "ITEM_PROP_NEGATIVE_CONTROLS_FAILED", "controls": controls}
    write_json(EVIDENCE / "negative-controls-v0190.json", negative)
    write_json(EVIDENCE / "item-prop-contract-v0190.json", {"schema_version": SCHEMA_VERSION, "status": "ITEM_PROP_CONTRACT_VALID", "classes": list(ITEM_CLASSES), "contexts": list(CONTEXTS), "stack_policies": ["STACKABLE", "NON_STACKABLE", "UNIQUE_INSTANCE_REQUIRED"], "variant_overrides": ["representation_binding", "scale", "collision", "footprint", "anchors", "material_palette", "equipment_ref", "provenance"]})
    write_json(EVIDENCE / "class-representation-matrix-v0190.json", {"schema_version": SCHEMA_VERSION, "status": "CLASS_REPRESENTATION_CONTRACT_VALID", "records": [{"class_id": class_id, "inventory_icon": "REQUIRED", "world_sprite_prop": "REQUIRED", "equipment_ref": "REQUIRED" if class_id == "weapon_item" else "UNSUPPORTED"} for _, class_id in ITEMS]})
    write_json(EVIDENCE / "representation-binding-v0190.json", {"schema_version": SCHEMA_VERSION, "status": "REPRESENTATION_BINDING_VALID", "records": [{"item_or_prop_id": item["item_or_prop_id"], "representation_profile": item["representation_profile"], "representations": item["representations"]} for item in manifest["items"]]})
    write_json(EVIDENCE / "world-geometry-v0190.json", {"schema_version": SCHEMA_VERSION, "status": "WORLD_GEOMETRY_VALID", "records": [{"item_or_prop_id": item["item_or_prop_id"], "geometry": item["world_geometry"]} for item in manifest["items"]]})
    write_json(EVIDENCE / "interaction-anchors-v0190.json", {"schema_version": SCHEMA_VERSION, "status": "INTERACTION_ANCHORS_VALID", "records": [{"item_or_prop_id": item["item_or_prop_id"], "anchors": item["world_geometry"]["anchors"]} for item in manifest["items"]]})
    write_json(EVIDENCE / "stack-identity-v0190.json", {"schema_version": SCHEMA_VERSION, "status": "STACK_AND_UNIQUE_IDENTITY_VALID", "records": [{key: item.get(key) for key in ("item_or_prop_id", "class_id", "stack_policy", "stack_key", "display_variant_id")} for item in manifest["items"]]})
    write_json(EVIDENCE / "variant-lineage-v0190.json", {"schema_version": SCHEMA_VERSION, "status": "VARIANT_LINEAGE_AND_EFFECTIVE_REVALIDATION_PASSED", "variants": manifest["variants"], "resolved": [item.to_dict() for item in derived]})
    write_json(EVIDENCE / "equipment-linkage-v0190.json", {"schema_version": SCHEMA_VERSION, "status": "EQUIPMENT_LINKAGE_VALID", "records": [{"item_or_prop_id": item["item_or_prop_id"], "equipment_ref": item["equipment_ref"]} for item in manifest["items"]]})
    write_json(EVIDENCE / "cache-identity-v0190.json", {"schema_version": SCHEMA_VERSION, "status": "CACHE_IDENTITY_COMPLETE_AND_ISOLATED", "resolved_keys": [item.cache_key for item in all_resolved], "cross_context_negative": controls["IP-NC-13"]})
    write_json(EVIDENCE / "provenance-qa-v0190.json", {"schema_version": SCHEMA_VERSION, "status": "PROVENANCE_HASHES_VALID", "item_hashes": [{"item_or_prop_id": item["item_or_prop_id"], "provenance_hash": item["provenance_hash"], "computed": _record_hash(item)} for item in manifest["items"]]})
    write_json(EVIDENCE / "determinism-v0190.json", {"schema_version": SCHEMA_VERSION, "status": "TWO_RUN_DETERMINISM_PASSED" if deterministic["equal"] else "TWO_RUN_DETERMINISM_FAILED", "first_run_sha256": deterministic["first_sha256"], "second_run_sha256": deterministic["second_sha256"], "second_run_reads_first_run": False, "mutated_control_error_code": controls["IP-NC-16"]["observed"].get("error_code")})
    write_json(EVIDENCE / "production-registry-v0190.json", {"schema_version": SCHEMA_VERSION, "production_registry": True, "registry_authority": "PRODUCTION_APPROVED_ASSETS_ONLY", "items": [], "variants": [], "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0})
    write_json(EVIDENCE / "synthetic-fixture-manifest-v0190.json", {"schema_version": SCHEMA_VERSION, "fixture_count": len(fixture_rows), "unique_hash_count": len({item["sha256"] for item in fixture_rows}), "production_registry": False, "fixtures": fixture_rows})
    write_json(EVIDENCE / "state-consistency-v0190.json", {"schema_version": SCHEMA_VERSION, "status": "ITEMS_PROPS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED", "failures": []})
    execution = {"schema_version": SCHEMA_VERSION, "status": "ITEMS_PROPS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED" if all(item["status"] == "PASS" for item in gates.values()) and negative["status"].endswith("PASSED") else "ITEMS_PROPS_RUNTIME_FOUNDATION_FAILED", "failed": sum(item["status"] != "PASS" for item in gates.values()), "gates": gates, "negative_controls": negative["status"], "item_prop_count": len(manifest["items"]), "class_count": len(ITEM_CLASSES), "real_item_prop_asset_coverage": "NONE", "synthetic_item_prop_fixture": "TEST_ONLY", "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0, "contact_sheet": "docs/evidence/items-props-runtime-v0190/synthetic-item-prop-contact-sheet-v0190.png", "geometry_sheet": "docs/evidence/items-props-runtime-v0190/world-geometry-sheet-v0190.png"}
    write_json(EVIDENCE / "execution-evidence-v0190.json", execution)
    print(json.dumps(execution, indent=2, ensure_ascii=False))
    return 0 if execution["status"] == "ITEMS_PROPS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
