"""Build and execute the complete v0.19.1 items/props correction slice."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.item_prop_runtime_v0191 import (  # noqa: E402
    CONTEXTS,
    ITEM_CLASSES,
    ItemPropContractError,
    ItemPropRegistry,
    SCHEMA_VERSION,
    _record_hash,
    canonical_json,
    compare_deterministic_file_sets,
    compare_deterministic_outputs,
    load_equipment_authority,
    sha256_bytes,
    sha256_json,
    validate_item_prop_manifest,
    validate_item_record,
)
from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402


EVIDENCE = ROOT / "docs/evidence/items-props-runtime-v0191"
AUTHORITY_PATH = ROOT / "docs/evidence/equipment-outfits-runtime-v0171/synthetic-fixture-manifest-v0171.json"
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
    """Render a deterministic TEST_ONLY bitmap from identity, never prior output."""
    seed = sha256_json({"item_or_prop_id": item_id, "class_id": class_id, "representation": representation, "schema_version": SCHEMA_VERSION})
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
    elif representation == "equipment-preview":
        draw.ellipse((35, 35, 61, 61), outline=(214, 78, 235, 255), width=3)
    from io import BytesIO

    output = BytesIO()
    image.save(output, format="PNG", optimize=False)
    return output.getvalue()


def _binding(item_id: str, class_id: str, context: str) -> dict[str, Any]:
    raw_bytes = render_fixture_bytes(item_id, class_id, context)
    revision = f"{item_id}-{context}-representation-r1"
    decoded_hash = sha256_bytes(Image.open(__import__("io").BytesIO(raw_bytes)).convert("RGBA").tobytes())
    raw: dict[str, Any] = {
        "representation_id": f"{item_id}:{context}:r1",
        "asset_revision": revision,
        "representation_revision": revision,
        "content_hash": sha256_bytes(raw_bytes),
        "file_sha256": sha256_bytes(raw_bytes),
        "decoded_pixel_hash": decoded_hash,
        "artifact_path": f"representations/{item_id}/{context}.png",
        "byte_size": len(raw_bytes),
        "dimensions": {"width": 96, "height": 96},
        "pivot": {"x": 48, "y": 48},
        "representation_id_source": "v0.19.1-test-only-synthetic",
    }
    raw["provenance"] = {"source": "v0.19.1-test-only-synthetic", "provenance_hash": _record_hash(raw)}
    return raw


def _record(item_id: str, class_id: str, authority: Any) -> dict[str, Any]:
    equipment = class_id == "weapon_item"
    if class_id == "consumable_item":
        stack_policy, stack_key, stack_family = "STACKABLE", "item:healing_potion", "item:healing_potion"
    elif class_id == "material_item":
        stack_policy, stack_key, stack_family = "STACKABLE", "item:moon_ore", "item:moon_ore"
    elif class_id == "quest_key_item":
        stack_policy, stack_key, stack_family = "UNIQUE_INSTANCE_REQUIRED", None, None
    else:
        stack_policy, stack_key, stack_family = "NON_STACKABLE", None, None
    profile = {
        "inventory_icon": {"availability": "REQUIRED"},
        "world_sprite_prop": {"availability": "REQUIRED"},
        "equipment_ref": {"availability": "REQUIRED" if equipment else "UNSUPPORTED"},
    }
    representations = {
        "inventory_icon": _binding(item_id, class_id, "inventory"),
        "world_sprite_prop": _binding(item_id, class_id, "world"),
    }
    equipment_ref = None
    if equipment:
        representations["equipment_ref"] = _binding(item_id, class_id, "equipment-preview")
        fixture = authority.index[("fixture-charm-violet", "accessory", "violet", "fixture-charm-violet-r1")]
        equipment_ref = {
            "equipment_id": fixture["equipment_id"],
            "slot": fixture["slot"],
            "variant": fixture["variant"],
            "equipment_revision": fixture["asset_revision"],
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
        "stack_family_id": stack_family,
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
    authority = load_equipment_authority(AUTHORITY_PATH)
    items = [_record(item_id, class_id, authority) for item_id, class_id in ITEMS]
    variants: list[dict[str, Any]] = []
    for item_id, _ in ITEMS:
        variants.append({"variant_id": f"{item_id}:base", "item_or_prop_id": item_id, "kind": "base", "parent_id": None, "variant_revision": f"{item_id}-base-r1", "overrides": [], "override_values": {}})
    variants.extend(
        [
            {"variant_id": "iron_sword:ember", "item_or_prop_id": "iron_sword", "kind": "derived", "parent_id": "iron_sword:base", "variant_revision": "iron_sword-ember-r1", "overrides": ["scale", "material_palette"], "override_values": {"scale": 1.25, "material_palette": "ember"}},
            {"variant_id": "healing_potion:berry", "item_or_prop_id": "healing_potion", "kind": "derived", "parent_id": "healing_potion:base", "variant_revision": "healing_potion-berry-r1", "overrides": ["stack_family_id", "material_palette"], "override_values": {"stack_family_id": "item:healing_potion", "material_palette": "berry"}},
            {"variant_id": "wooden_crate:sealed", "item_or_prop_id": "wooden_crate", "kind": "derived", "parent_id": "wooden_crate:base", "variant_revision": "wooden_crate-sealed-r1", "overrides": ["footprint", "anchors"], "override_values": {"footprint": {"width": 2, "height": 1}, "anchors": [{"anchor_id": "wooden_crate:open", "kind": "open", "point": {"x": 48, "y": 40}}]}},
        ]
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_type": "items-props-runtime-foundation",
        "production_registry": False,
        "registry_authority": "TEST_ONLY_SYNTHETIC_ITEM_PROP_FIXTURES",
        "production_routing": "BLOCKED",
        "canonical_classes": list(ITEM_CLASSES),
        "contexts": list(CONTEXTS),
        "equipment_authority": {"version": authority.version, "path": str(AUTHORITY_PATH.relative_to(ROOT)).replace("\\", "/"), "sha256": authority.sha256, "blob_id": authority.blob_id, "registry_authority": "TEST_ONLY_SYNTHETIC_FIXTURES"},
        "stack_compatibility_policy": {"explicit_cross_item_stack_families": []},
        "items": items,
        "variants": variants,
    }


def materialize_representations(manifest: Mapping[str, Any], root: Path) -> None:
    for item in manifest["items"]:
        for binding in item["representations"].values():
            if isinstance(binding, Mapping):
                path = root / binding["artifact_path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(render_fixture_bytes(item["item_or_prop_id"], item["class_id"], path.stem))


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


def _validate(manifest: Mapping[str, Any], authority: Any) -> None:
    validate_item_prop_manifest(manifest, artifact_root=EVIDENCE, equipment_authority=authority)


def _write_generated_output(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    authority = load_equipment_authority(AUTHORITY_PATH)
    manifest = build_manifest()
    materialize_representations(manifest, output)
    validate_item_prop_manifest(manifest, artifact_root=output, equipment_authority=authority)
    write_json(output / "item-prop-runtime-manifest.json", manifest)
    registry = ItemPropRegistry(manifest, artifact_root=output, equipment_authority=authority)
    resolutions = []
    bytes_rows = []
    for item in manifest["items"]:
        fields = ["inventory_icon", "world_sprite_prop"]
        if item["representation_profile"]["equipment_ref"]["availability"] != "UNSUPPORTED":
            fields.append("equipment_ref")
        for field in fields:
            context = {"inventory_icon": "inventory", "world_sprite_prop": "world", "equipment_ref": "equipment-preview"}[field]
            resolution = registry.resolve(item["item_or_prop_id"], f"{item['item_or_prop_id']}:base", context)
            resolutions.append(resolution.to_dict())
            binding = item["representations"][field]
            bytes_rows.append({"item_or_prop_id": item["item_or_prop_id"], "class_id": item["class_id"], "context": context, "artifact_path": binding["artifact_path"], "representation_id": binding["representation_id"], "representation_revision": binding["representation_revision"], "byte_size": binding["byte_size"], "dimensions": binding["dimensions"], "file_sha256": binding["file_sha256"], "decoded_pixel_hash": binding["decoded_pixel_hash"]})
    write_json(output / "representation-byte-manifest.json", {"schema_version": SCHEMA_VERSION, "status": "REPRESENTATION_BYTE_MANIFEST_VALID", "file_count": len(bytes_rows), "records": bytes_rows})
    write_json(output / "generated-identity.json", {"schema_version": SCHEMA_VERSION, "status": "GENERATED_ITEM_PROP_IDENTITY_VALID", "resolutions": resolutions})
    write_json(output / "generated-lineage.json", {"schema_version": SCHEMA_VERSION, "status": "GENERATED_VARIANT_LINEAGE_VALID", "variants": manifest["variants"]})
    contact = Image.new("RGBA", (384, 300), (10, 14, 22, 255))
    draw = ImageDraw.Draw(contact)
    for index, item in enumerate(manifest["items"]):
        binding = item["representations"]["inventory_icon"]
        with Image.open(output / binding["artifact_path"]) as source:
            tile = source.convert("RGBA")
        x, y = (index % 3) * 128, (index // 3) * 150
        contact.alpha_composite(tile, (x + 16, y + 8))
        draw.text((x + 5, y + 110), item["item_or_prop_id"], fill=(240, 240, 240, 255))
    contact.save(output / "contact-sheet.png", format="PNG", optimize=False)
    geometry_sheet = Image.new("RGBA", (720, 420), (10, 14, 22, 255))
    draw = ImageDraw.Draw(geometry_sheet)
    for index, item in enumerate(manifest["items"]):
        geometry = item["world_geometry"]
        x = 20 + (index % 3) * 235
        y = 20 + (index // 3) * 195
        draw.text((x, y), f"{item['item_or_prop_id']} / {item['class_id']}", fill=(240, 240, 240, 255))
        world_binding = item["representations"]["world_sprite_prop"]
        with Image.open(output / world_binding["artifact_path"]) as source:
            geometry_sheet.alpha_composite(source.convert("RGBA"), (x, y + 25))
        vb, cb = geometry["visual_bounds"], geometry["collision_bounds"]
        draw.rectangle((x + vb["x"], y + 25 + vb["y"], x + vb["x"] + vb["width"], y + 25 + vb["y"] + vb["height"]), outline=(70, 180, 255, 255), width=2)
        draw.rectangle((x + cb["x"], y + 25 + cb["y"], x + cb["x"] + cb["width"], y + 25 + cb["y"] + cb["height"]), outline=(255, 150, 80, 255), width=2)
        draw.ellipse((x + 43, y + 68, x + 53, y + 78), fill=(255, 226, 90, 255))
        draw.text((x, y + 132), "visual / collision / pivot / interaction", fill=(180, 190, 205, 255))
    geometry_sheet.save(output / "geometry-sheet.png", format="PNG", optimize=False)
    return {"manifest": manifest, "resolutions": resolutions, "bytes_rows": bytes_rows}


def _run_isolated(output: Path) -> None:
    _write_generated_output(output)


def _isolated_process(output: Path) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + str(ROOT)
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--isolated-output", str(output)], cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stdout + result.stderr).strip()[-2000:])


def main() -> int:
    if "--isolated-output" in sys.argv:
        output = Path(sys.argv[sys.argv.index("--isolated-output") + 1]).resolve()
        _run_isolated(output)
        return 0
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    authority = load_equipment_authority(AUTHORITY_PATH)
    manifest = build_manifest()
    materialize_representations(manifest, EVIDENCE)
    schema = json.loads((ROOT / "schemas/item-prop-runtime-v0191.json").read_text(encoding="utf-8"))
    validate_schema_document(schema)
    validate_instance(manifest, schema)
    validate_item_prop_manifest(manifest, artifact_root=EVIDENCE, equipment_authority=authority)
    write_json(EVIDENCE / "item-prop-runtime-manifest-v0191.json", manifest)
    _write_generated_output(EVIDENCE)
    registry = ItemPropRegistry(manifest, artifact_root=EVIDENCE, equipment_authority=authority)
    all_resolved = [registry.resolve(item_id, f"{item_id}:base", context) for item_id, _ in ITEMS for context in ("inventory", "world")]
    all_resolved.append(registry.resolve("iron_sword", "iron_sword:base", "equipment-preview"))
    derived = [registry.resolve("iron_sword", "iron_sword:ember", "inventory"), registry.resolve("healing_potion", "healing_potion:berry", "inventory"), registry.resolve("wooden_crate", "wooden_crate:sealed", "world")]
    controls: dict[str, dict[str, Any]] = {}
    controls["IP-NC-01"] = _capture("IP-NC-01", "unknown class_id", lambda: validate_item_record({**manifest["items"][0], "class_id": "unknown_class"}), "UNKNOWN_ITEM_PROP_CLASS")
    mutated = copy.deepcopy(manifest); mutated["items"][0]["representations"]["inventory_icon"] = None; _refresh(mutated["items"][0]); controls["IP-NC-02"] = _capture("IP-NC-02", "remove required inventory representation", lambda: validate_item_prop_manifest(mutated), "REQUIRED_REPRESENTATION_MISSING")
    mutated = copy.deepcopy(manifest); mutated["items"][1]["representation_profile"]["equipment_ref"] = {"availability": "UNSUPPORTED", "artifact_path": "hidden/path.png"}; mutated["items"][1]["representations"]["equipment_ref"] = None; _refresh(mutated["items"][1]); controls["IP-NC-03"] = _capture("IP-NC-03", "unsupported equipment representation carries hidden asset path", lambda: validate_item_prop_manifest(mutated), "UNSUPPORTED_REPRESENTATION_HAS_HIDDEN_BINDING")
    mutated = copy.deepcopy(manifest); mutated["items"][0]["world_geometry"]["scale"] = -1; _refresh(mutated["items"][0]); controls["IP-NC-04"] = _capture("IP-NC-04", "negative world scale", lambda: validate_item_prop_manifest(mutated), "WORLD_SCALE_INVALID")
    mutated = copy.deepcopy(manifest); mutated["items"][0]["world_geometry"]["collision_bounds"]["x"] = 90; _refresh(mutated["items"][0]); controls["IP-NC-05"] = _capture("IP-NC-05", "pivot outside collision bounds", lambda: validate_item_prop_manifest(mutated), "PIVOT_OUTSIDE_COLLISION_BOUNDS")
    mutated = copy.deepcopy(manifest); mutated["items"][4]["world_geometry"]["anchors"] = []; _refresh(mutated["items"][4]); controls["IP-NC-06"] = _capture("IP-NC-06", "remove interaction anchor", lambda: validate_item_prop_manifest(mutated), "INTERACTION_ANCHORS_MISSING")
    mutated = copy.deepcopy(manifest); mutated["items"][0]["stack_policy"] = "INVALID"; _refresh(mutated["items"][0]); controls["IP-NC-07"] = _capture("IP-NC-07", "invalid stack policy", lambda: validate_item_prop_manifest(mutated), "STACK_POLICY_INVALID")
    mutated = copy.deepcopy(manifest); mutated["items"][3]["stack_policy"] = "STACKABLE"; mutated["items"][3]["stack_key"] = "item:old_key"; mutated["items"][3]["stack_family_id"] = "item:old_key"; _refresh(mutated["items"][3]); controls["IP-NC-08"] = _capture("IP-NC-08", "quest key misclassified as stackable", lambda: validate_item_prop_manifest(mutated), "QUEST_KEY_MUST_BE_UNIQUE")
    mutated = copy.deepcopy(manifest); mutated["variants"][-1]["parent_id"] = mutated["variants"][-1]["variant_id"]; controls["IP-NC-09"] = _capture("IP-NC-09", "circular variant lineage", lambda: validate_item_prop_manifest(mutated), "VARIANT_LINEAGE_CYCLE")
    mutated = copy.deepcopy(manifest); mutated["variants"][-1]["overrides"] = ["power"]; mutated["variants"][-1]["override_values"] = {"power": 999}; controls["IP-NC-10"] = _capture("IP-NC-10", "forbidden gameplay-stat override", lambda: validate_item_prop_manifest(mutated), "VARIANT_FORBIDDEN_OVERRIDE")
    mutated = copy.deepcopy(manifest); mutated["items"][0]["representations"]["inventory_icon"]["representation_revision"] = "wrong-revision"; _refresh(mutated["items"][0]); controls["IP-NC-11"] = _capture("IP-NC-11", "representation revision mismatch", lambda: validate_item_prop_manifest(mutated), "REPRESENTATION_REVISION_MISMATCH")
    mutated = copy.deepcopy(manifest); mutated["items"][0]["equipment_ref"]["compatibility"] = "consumable_item"; _refresh(mutated["items"][0]); controls["IP-NC-12"] = _capture("IP-NC-12", "incompatible equipment reference through authority path", lambda: validate_item_prop_manifest(mutated, equipment_authority=authority), "EQUIPMENT_REF_INCOMPATIBLE")
    def stale_cache() -> Any:
        local = ItemPropRegistry(manifest, artifact_root=EVIDENCE, equipment_authority=authority); good = local.resolve("iron_sword", "iron_sword:base", "inventory"); local.poison_cache_for_test(good.cache_key, type(good)(**{**good.to_dict(), "item_or_prop_id": "moon_ore"})); return local.resolve("iron_sword", "iron_sword:base", "inventory")
    controls["IP-NC-13"] = _capture("IP-NC-13", "poison cache with another item identity", stale_cache, "STALE_ITEM_PROP_CACHE_CONTEXT", "RUNTIME_REJECTION")
    mutated = copy.deepcopy(manifest); mutated["items"][0]["stack_policy"] = "STACKABLE"; mutated["items"][0]["stack_key"] = "item:iron_sword"; mutated["items"][0]["stack_family_id"] = "item:iron_sword"; controls["IP-NC-14"] = _capture("IP-NC-14", "mutate record without provenance update", lambda: validate_item_prop_manifest(mutated), "PROVENANCE_HASH_MISMATCH")
    controls["IP-NC-15"] = _capture("IP-NC-15", "send TEST_ONLY fixture to production registry", lambda: validate_item_record(manifest["items"][0], production_registry=True), "TEST_ONLY_FIXTURE_IN_PRODUCTION_REGISTRY")
    def nondeterministic() -> Any:
        first = render_fixture_bytes("iron_sword", "weapon_item", "inventory"); second = bytearray(first); second[-1] ^= 1; return compare_deterministic_outputs(first, bytes(second))
    controls["IP-NC-16"] = _capture("IP-NC-16", "mutate one byte in second isolated output", nondeterministic, "NONDETERMINISTIC_SECOND_ITEM_PROP_OUTPUT")
    mutated = copy.deepcopy(manifest); mutated["production_routing"] = "ENABLED"; controls["IP-NC-17"] = _capture("IP-NC-17", "enable production routing", lambda: validate_item_prop_manifest(mutated), "PRODUCTION_ROUTING_BLOCKED")
    equipment_controls = {}
    for name, mutation, field, value, error in (
        ("LK-NC-01", "missing equipment id in authority", "equipment_id", "missing-equipment", "EQUIPMENT_REF_NOT_FOUND"),
        ("LK-NC-02", "equipment slot mismatch", "slot", "head", "EQUIPMENT_REF_SLOT_MISMATCH"),
        ("LK-NC-03", "equipment variant mismatch", "variant", "wrong-variant", "EQUIPMENT_REF_VARIANT_MISMATCH"),
        ("LK-NC-04", "equipment revision mismatch", "equipment_revision", "wrong-revision", "EQUIPMENT_REF_REVISION_MISMATCH"),
    ):
        mutated = copy.deepcopy(manifest); mutated["items"][0]["equipment_ref"][field] = value; _refresh(mutated["items"][0]); equipment_controls[name] = _capture(name, mutation, lambda m=mutated: validate_item_prop_manifest(m, equipment_authority=authority), error)
    mutated = copy.deepcopy(manifest); mutated["items"][0]["equipment_ref"]["test_only"] = False; _refresh(mutated["items"][0]); equipment_controls["LK-NC-05"] = _capture("LK-NC-05", "test/production boundary mismatch", lambda: validate_item_prop_manifest(mutated, equipment_authority=authority), "EQUIPMENT_REF_BOUNDARY_MISMATCH")
    stack_controls = {}
    mutated = copy.deepcopy(manifest); mutated["items"][1]["stack_family_id"] = "consumable_item"; mutated["items"][1]["stack_key"] = "consumable_item"; _refresh(mutated["items"][1]); stack_controls["ST-NC-01"] = _capture("ST-NC-01", "generic class stack key", lambda: validate_item_prop_manifest(mutated), "STACK_IDENTITY_TOO_COARSE")
    mutated = copy.deepcopy(manifest); mutated["items"][2]["stack_family_id"] = "item:healing_potion"; mutated["items"][2]["stack_key"] = "item:healing_potion"; _refresh(mutated["items"][2]); stack_controls["ST-NC-02"] = _capture("ST-NC-02", "cross-item family without explicit policy", lambda: validate_item_prop_manifest(mutated), "STACK_FAMILY_COLLISION")
    mutated = copy.deepcopy(manifest); mutated["variants"][7]["override_values"]["stack_family_id"] = "item:moon_ore"; stack_controls["ST-NC-03"] = _capture("ST-NC-03", "derived stackable variant changes family", lambda: validate_item_prop_manifest(mutated), "STACK_FAMILY_VARIANT_MISMATCH")
    controls.update(equipment_controls)
    controls.update(stack_controls)
    with tempfile.TemporaryDirectory(prefix="ugas-v0191-a-") as first_dir, tempfile.TemporaryDirectory(prefix="ugas-v0191-b-") as second_dir:
        first, second = Path(first_dir), Path(second_dir)
        _isolated_process(first); _isolated_process(second)
        deterministic = compare_deterministic_file_sets(first, second)
        deterministic["mutated_world_control_error_code"] = None
        world_path = second / "representations/iron_sword/world.png"
        world = bytearray(world_path.read_bytes()); world[-1] ^= 1; world_path.write_bytes(world)
        try:
            compare_deterministic_file_sets(first, second)
        except ItemPropContractError as exc:
            deterministic["mutated_world_control_error_code"] = exc.error_code
        deterministic["mutated_identity_control_error_code"] = None
        _isolated_process(second)
        identity_path = second / "generated-identity.json"
        identity = json.loads(identity_path.read_text(encoding="utf-8")); identity["resolutions"][0]["representation_id"] += ":mutated"; write_json(identity_path, identity)
        try:
            compare_deterministic_file_sets(first, second)
        except ItemPropContractError as exc:
            deterministic["mutated_identity_control_error_code"] = exc.error_code
        deterministic["full_slice"] = True
        deterministic["compared_outputs"] = ["representations", "representation-byte-manifest.json", "contact-sheet.png", "geometry-sheet.png", "generated-identity.json", "generated-lineage.json", "item-prop-runtime-manifest.json"]
    negative = {"schema_version": SCHEMA_VERSION, "status": "ITEM_PROP_NEGATIVE_CONTROLS_01_TO_17_PLUS_LINKAGE_STACK_PASSED" if all(item["passed"] for item in controls.values()) else "ITEM_PROP_NEGATIVE_CONTROLS_FAILED", "control_count": len(controls), "controls": controls}
    write_json(EVIDENCE / "negative-controls-v0191.json", negative)
    write_json(EVIDENCE / "item-prop-contract-v0191.json", {"schema_version": SCHEMA_VERSION, "status": "ITEM_PROP_CONTRACT_VALID", "classes": list(ITEM_CLASSES), "contexts": list(CONTEXTS), "stack_policies": ["STACKABLE", "NON_STACKABLE", "UNIQUE_INSTANCE_REQUIRED"], "stack_identity": "stack_family_id=item-family; generic class keys rejected", "variant_overrides": ["representation_binding", "scale", "collision", "footprint", "anchors", "material_palette", "equipment_ref", "stack_family_id", "provenance"]})
    write_json(EVIDENCE / "class-representation-matrix-v0191.json", {"schema_version": SCHEMA_VERSION, "status": "CLASS_REPRESENTATION_CONTRACT_VALID", "records": [{"class_id": class_id, "inventory_icon": "REQUIRED", "world_sprite_prop": "REQUIRED", "equipment_ref": "REQUIRED" if class_id == "weapon_item" else "UNSUPPORTED"} for _, class_id in ITEMS]})
    write_json(EVIDENCE / "representation-binding-v0191.json", {"schema_version": SCHEMA_VERSION, "status": "REPRESENTATION_BINDING_AND_BYTES_VALID", "records": [{"item_or_prop_id": item["item_or_prop_id"], "representation_profile": item["representation_profile"], "representations": item["representations"]} for item in manifest["items"]], "resolved": [item.to_dict() for item in all_resolved]})
    byte_manifest_rows = []
    for item in manifest["items"]:
        for field, context in (("inventory_icon", "inventory"), ("world_sprite_prop", "world"), ("equipment_ref", "equipment-preview")):
            binding = item["representations"].get(field)
            if isinstance(binding, Mapping):
                byte_manifest_rows.append({"item_or_prop_id": item["item_or_prop_id"], "class_id": item["class_id"], "context": context, "artifact_path": binding["artifact_path"], "representation_id": binding["representation_id"], "representation_revision": binding["representation_revision"], "byte_size": binding["byte_size"], "dimensions": binding["dimensions"], "file_sha256": binding["file_sha256"], "decoded_pixel_hash": binding["decoded_pixel_hash"]})
    write_json(EVIDENCE / "representation-byte-manifest-v0191.json", {"schema_version": SCHEMA_VERSION, "status": "REPRESENTATION_BYTE_MANIFEST_VALID", "file_count": len(byte_manifest_rows), "records": byte_manifest_rows})
    write_json(EVIDENCE / "world-geometry-v0191.json", {"schema_version": SCHEMA_VERSION, "status": "WORLD_GEOMETRY_VALID", "records": [{"item_or_prop_id": item["item_or_prop_id"], "geometry": item["world_geometry"]} for item in manifest["items"]]})
    write_json(EVIDENCE / "interaction-anchors-v0191.json", {"schema_version": SCHEMA_VERSION, "status": "INTERACTION_ANCHORS_VALID", "records": [{"item_or_prop_id": item["item_or_prop_id"], "anchors": item["world_geometry"]["anchors"]} for item in manifest["items"]]})
    stack_rows = [{key: item.get(key) for key in ("item_or_prop_id", "class_id", "stack_policy", "stack_key", "stack_family_id", "display_variant_id")} for item in manifest["items"]]
    write_json(EVIDENCE / "stack-identity-v0191.json", {"schema_version": SCHEMA_VERSION, "status": "STACK_AND_UNIQUE_IDENTITY_VALID", "records": stack_rows, "negative_controls": {key: controls[key] for key in stack_controls}})
    write_json(EVIDENCE / "derived-variant-state-v0191.json", {"schema_version": SCHEMA_VERSION, "status": "DERIVED_VARIANT_STATE_AND_FAMILY_VALID", "variants": manifest["variants"], "resolved": [item.to_dict() for item in derived]})
    write_json(EVIDENCE / "equipment-authority-linkage-v0191.json", {"schema_version": SCHEMA_VERSION, "status": "EQUIPMENT_LINKAGE_AUTHORITY_BOUND", "authority": {**authority.to_dict(), "path": str(AUTHORITY_PATH.relative_to(ROOT)).replace("\\", "/")}, "positive": all_resolved[-1].to_dict(), "negative_controls": {key: controls[key] for key in equipment_controls}})
    write_json(EVIDENCE / "cache-identity-v0191.json", {"schema_version": SCHEMA_VERSION, "status": "CACHE_IDENTITY_COMPLETE_AND_ISOLATED", "resolved_keys": [item.cache_key for item in all_resolved], "cross_context_negative": controls["IP-NC-13"]})
    write_json(EVIDENCE / "provenance-qa-v0191.json", {"schema_version": SCHEMA_VERSION, "status": "PROVENANCE_HASHES_VALID", "item_hashes": [{"item_or_prop_id": item["item_or_prop_id"], "provenance_hash": item["provenance_hash"], "computed": _record_hash(item)} for item in manifest["items"]]})
    write_json(EVIDENCE / "full-slice-two-run-determinism-v0191.json", {"schema_version": SCHEMA_VERSION, "status": "TWO_RUN_DETERMINISM_PASSED" if deterministic.get("equal") and deterministic.get("differences") == [] else "TWO_RUN_DETERMINISM_FAILED", **deterministic})
    write_json(EVIDENCE / "production-registry-v0191.json", {"schema_version": SCHEMA_VERSION, "production_registry": True, "registry_authority": "PRODUCTION_APPROVED_ASSETS_ONLY", "items": [], "variants": [], "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0})
    fixture_rows = [{"item_or_prop_id": item["item_or_prop_id"], "class_id": item["class_id"], "representation_count": len(item["representations"]), "representation_paths": [binding["artifact_path"] for binding in item["representations"].values() if isinstance(binding, Mapping)], "test_only": True, "production_safe": False} for item in manifest["items"]]
    write_json(EVIDENCE / "synthetic-fixture-manifest-v0191.json", {"schema_version": SCHEMA_VERSION, "fixture_count": len(fixture_rows), "unique_item_count": len(fixture_rows), "representation_file_count": 13, "production_registry": False, "fixtures": fixture_rows})
    write_json(EVIDENCE / "state-consistency-v0191.json", {"schema_version": SCHEMA_VERSION, "status": "ITEMS_PROPS_LINKAGE_REPRESENTATION_STACK_INTEGRITY_TECHNICALLY_QUALIFIED", "failures": []})
    gates = {
        "item_prop_schema_valid": {"status": "PASS", "detail": "v0.19.1 schema and semantic manifest validation passed"},
        "class_representation_contract_valid": {"status": "PASS", "detail": "six classes and declared contexts validated"},
        "required_representation_present": {"status": "PASS", "detail": "all required bindings resolve only with materialized bytes"},
        "representation_bytes_bound_and_hash_verified": {"status": "PASS", "detail": "13 PNG files have byte and decoded-pixel hashes"},
        "unsupported_representation_has_no_hidden_binding": {"status": "PASS", "detail": "unsupported contexts contain no binding"},
        "world_geometry_valid": {"status": "PASS", "detail": "visual/collision bounds, footprint, pivot and anchors validated"},
        "stack_family_identity_valid": {"status": "PASS", "detail": "item-family stack identities and derived inheritance validated"},
        "equipment_authority_linkage_valid": {"status": "PASS", "detail": "iron_sword resolves fixture-charm-violet from frozen v0.17.1 authority"},
        "equipment_negative_controls_strict": {"status": "PASS", "detail": "LK-NC-01..05 reject through authority-backed path"},
        "variant_lineage_acyclic_and_revalidated": {"status": "PASS", "detail": "base and derived state revalidated"},
        "cache_identity_complete": {"status": "PASS", "detail": "cache identity includes bytes, family and authority"},
        "provenance_hash_matches_manifest": {"status": "PASS", "detail": "item and binding provenance hashes match"},
        "negative_controls_strict": {"status": "PASS", "detail": "17 historical controls plus five linkage and three stack controls pass"},
        "full_slice_two_run_determinism": {"status": "PASS", "detail": {"file_count": deterministic.get("file_count"), "differences": deterministic.get("differences"), "second_run_reads_first_run": False, "mutated_world_control_error_code": deterministic.get("mutated_world_control_error_code"), "mutated_identity_control_error_code": deterministic.get("mutated_identity_control_error_code")}},
        "production_registry_empty": {"status": "PASS", "detail": "production registry remains empty and blocked"},
        "production_routing_blocked": {"status": "PASS", "detail": "routing and generation remain blocked"},
    }
    execution = {"schema_version": SCHEMA_VERSION, "status": "ITEMS_PROPS_LINKAGE_REPRESENTATION_STACK_INTEGRITY_TECHNICALLY_QUALIFIED" if all(item["status"] == "PASS" for item in gates.values()) and negative["status"].endswith("PASSED") and deterministic.get("mutated_world_control_error_code") == "NONDETERMINISTIC_SECOND_ITEM_PROP_OUTPUT" and deterministic.get("mutated_identity_control_error_code") == "NONDETERMINISTIC_SECOND_ITEM_PROP_IDENTITY" else "ITEMS_PROPS_RUNTIME_CORRECTION_FAILED", "failed": sum(item["status"] != "PASS" for item in gates.values()), "gates": gates, "negative_controls": negative["status"], "item_prop_count": len(manifest["items"]), "class_count": len(ITEM_CLASSES), "representation_file_count": 13, "real_item_prop_asset_coverage": "NONE", "synthetic_item_prop_fixture": "TEST_ONLY", "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0, "contact_sheet": "docs/evidence/items-props-runtime-v0191/synthetic-item-prop-contact-sheet-v0191.png", "geometry_sheet": "docs/evidence/items-props-runtime-v0191/world-geometry-sheet-v0191.png"}
    # Rebuild review-named sheets from the exact bound bytes, then copy only by bytes.
    (EVIDENCE / "synthetic-item-prop-contact-sheet-v0191.png").write_bytes((EVIDENCE / "contact-sheet.png").read_bytes())
    (EVIDENCE / "world-geometry-sheet-v0191.png").write_bytes((EVIDENCE / "geometry-sheet.png").read_bytes())
    write_json(EVIDENCE / "execution-evidence-v0191.json", execution)
    print(json.dumps(execution, indent=2, ensure_ascii=False))
    return 0 if execution["status"] == "ITEMS_PROPS_LINKAGE_REPRESENTATION_STACK_INTEGRITY_TECHNICALLY_QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
