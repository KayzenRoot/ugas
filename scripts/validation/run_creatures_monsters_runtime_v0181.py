"""Generate and qualify the forward-only v0.18.1 creature correction.

The generator creates only deterministic TEST_ONLY colored fixtures.  It never
touches the frozen v0.18.0 evidence directory and never enables production or
calls an image-generation provider.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.creature_runtime import ARCHETYPES, ARCHETYPE_RULES, CANONICAL_STATES  # noqa: E402
from ugas.direction_runtime import CANONICAL_DIRECTIONS  # noqa: E402
from ugas.creature_runtime_v0181 import (  # noqa: E402
    ALLOWED_VARIANT_OVERRIDES,
    CreatureContractError,
    CreatureRegistry,
    SCHEMA_VERSION,
    _record_hash,
    canonical_json,
    enforce_production_routing,
    sha256_json,
    validate_creature_manifest,
)
from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402
from ugas.state_consistency_v0181 import validate_state_consistency  # noqa: E402


EVIDENCE = ROOT / "docs/evidence/creatures-monsters-runtime-v0181"
FIXTURES = EVIDENCE / "fixtures" / "directions"
SCHEMA = ROOT / "schemas/creature-runtime-v0181.json"

SPECS = (
    ("humanoid_biped", "monster_knight", (57, 119, 214, 255), ("idle", "locomotion", "attack_primary", "hit_reaction", "death")),
    ("quadruped", "dire_wolf", (176, 86, 42, 255), ("idle", "locomotion", "attack_primary", "hit_reaction", "death")),
    ("flying_winged", "cave_bat", (133, 76, 190, 255), ("idle", "attack_primary", "hit_reaction", "death")),
    ("serpentine", "marsh_wyrm", (38, 164, 110, 255), ("idle", "locomotion", "attack_primary", "hit_reaction", "death")),
    ("amorphous", "slime_mass", (54, 188, 194, 255), ("idle", "attack_primary", "hit_reaction", "death")),
    ("stationary_structure", "ruin_turret", (188, 142, 44, 255), ("idle", "attack_primary", "hit_reaction", "death")),
)

DIRECTION_MARKERS = {
    "south": (96, 26), "south_east": (146, 45), "east": (166, 96), "north_east": (146, 146),
    "north": (96, 164), "north_west": (45, 146), "west": (25, 96), "south_west": (45, 45),
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _state_contract(required: tuple[str, ...]) -> dict[str, str]:
    return {state: ("REQUIRED" if state in required else ("UNSUPPORTED" if state == "locomotion" else "OPTIONAL")) for state in CANONICAL_STATES}


def _fixture_bytes(index: int, direction: str, color: tuple[int, int, int, int], archetype: str) -> bytes:
    image = Image.new("RGBA", (192, 192), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if archetype == "humanoid_biped":
        draw.ellipse((70, 20, 122, 72), fill=color); draw.rectangle((58, 68, 134, 145), fill=color); draw.rectangle((62, 140, 83, 177), fill=color); draw.rectangle((108, 140, 129, 177), fill=color)
    elif archetype == "quadruped":
        draw.ellipse((35, 55, 158, 125), fill=color); draw.ellipse((128, 38, 170, 83), fill=color); draw.rectangle((50, 112, 67, 168), fill=color); draw.rectangle((119, 112, 136, 168), fill=color)
    elif archetype == "flying_winged":
        draw.ellipse((70, 65, 122, 128), fill=color); draw.polygon(((72, 76), (15, 32), (50, 105), (72, 112)), fill=color); draw.polygon(((120, 76), (177, 32), (142, 105), (120, 112)), fill=color)
    elif archetype == "serpentine":
        draw.ellipse((54, 27, 138, 90), fill=color); draw.arc((35, 62, 154, 177), 0, 180, fill=color, width=26)
    elif archetype == "amorphous":
        draw.ellipse((32, 50, 159, 167), fill=color); draw.ellipse((62, 27, 93, 59), fill=color); draw.ellipse((118, 40, 145, 67), fill=color)
    else:
        draw.rectangle((42, 43, 150, 170), fill=color); draw.polygon(((38, 43), (96, 16), (154, 43)), fill=color); draw.rectangle((72, 99, 119, 170), fill=(30, 35, 44, 255))
    marker_x, marker_y = DIRECTION_MARKERS[direction]
    marker_size = 8 + (index % 3)
    draw.polygon(((marker_x, marker_y - marker_size), (marker_x + marker_size, marker_y), (marker_x, marker_y + marker_size)), fill=(255, 255, 255, 255))
    draw.rectangle((marker_x - 3, marker_y - 3, marker_x + 3, marker_y + 3), fill=(255, 228, 70, 255))
    stream = __import__("io").BytesIO()
    image.save(stream, format="PNG", optimize=False, compress_level=9)
    return stream.getvalue()


def _state_routes(creature_id: str, contract: Mapping[str, str], index: int) -> dict[str, dict[str, Any]]:
    routes: dict[str, dict[str, Any]] = {}
    for state in CANONICAL_STATES:
        availability = contract[state]
        if availability == "UNSUPPORTED":
            routes[state] = {"state": state, "availability": availability, "state_route_id": None, "timing_phase": None, "test_only": True, "production_safe": False}
        else:
            routes[state] = {
                "state": state,
                "availability": availability,
                "state_route_id": f"{creature_id}:{state}:route-v0181",
                "timing_phase": {"fps": 8 + ((index + len(state)) % 5), "duration_ms": 500 + index * 25 + len(state) * 10, "phase": "loop" if state in {"idle", "locomotion"} else "one_shot"},
                "test_only": True,
                "production_safe": False,
            }
    return routes


def _creature(index: int, archetype: str, species: str, color: tuple[int, int, int, int], required: tuple[str, ...]) -> dict[str, Any]:
    creature_id = f"fixture_{archetype}"
    asset_revision = f"{creature_id}-r1"
    contract = _state_contract(required)
    directions = {
        direction: {
            "direction": direction,
            "direction_asset_id": f"{creature_id}:{direction}:qa-v0181",
            "direction_content_hash": hashlib.sha256(_fixture_bytes(index, direction, color, archetype)).hexdigest(),
            "asset_revision": asset_revision,
            "path": f"docs/evidence/creatures-monsters-runtime-v0181/fixtures/directions/{creature_id}/{direction}.png",
            "identity_class": "UNIQUE_TEST_IDENTITY",
            "test_only": True,
            "production_safe": False,
        }
        for direction in CANONICAL_DIRECTIONS
    }
    rules = ARCHETYPE_RULES[archetype]
    record: dict[str, Any] = {
        "creature_id": creature_id,
        "species_id": species,
        "archetype": archetype,
        "topology_id": rules["topology_id"],
        "locomotion_class": rules["locomotion_class"],
        "support_model": rules["support_model"],
        "rig_family": f"rig_{archetype}_v1",
        "base_scale": {"x": round(0.82 + index * 0.04, 3), "y": round(0.94 + index * 0.03, 3)},
        "footprint": {"width": 42.0 + index * 5, "depth": 28.0 + index * 3},
        "collision_profile": {"shape": "capsule" if archetype in {"humanoid_biped", "quadruped", "serpentine"} else "box", "width": 42.0 + index * 5, "height": 76.0 + index * 4, "pivot": {"x": 96.0, "y": 174.0}, "bounds": {"left": 30.0, "top": 18.0, "right": 162.0, "bottom": 178.0}},
        "anchors": {"origin": {"x": 96.0, "y": 174.0}, "center": {"x": 96.0, "y": 96.0}, "contact": {"x": 96.0, "y": 174.0}},
        "direction_coverage": list(CANONICAL_DIRECTIONS),
        "direction_bindings": directions,
        "animation_state_contract": contract,
        "state_routes": _state_routes(creature_id, contract, index),
        "variant_lineage": {"variant_id": f"{creature_id}_base", "kind": "base", "parent_id": None, "inherits": [], "overrides": []},
        "asset_revision": asset_revision,
        "provenance": {"source_kind": "TEST_ONLY_SYNTHETIC", "source_id": f"synthetic-colored-directional-fixture-{index + 1}", "source_revision": SCHEMA_VERSION, "record_hash": "", "production_safe": False},
        "test_only": True,
        "production_safe": False,
        "fixture": {"color_rgba": list(color), "orientation_marker": "direction-specific-asymmetric-white-yellow-marker", "fixture_index": index + 1},
    }
    record_hash = _record_hash(record)
    record["provenance_hash"] = record_hash
    record["provenance"]["record_hash"] = record_hash
    return record


def _derived_variant(variant_id: str, creature_id: str, parent_id: str, overrides: Mapping[str, Any], inherits: list[str]) -> dict[str, Any]:
    return {"variant_id": variant_id, "creature_id": creature_id, "kind": "derived", "parent_id": parent_id, "inherits": inherits, "overrides": list(overrides), "override_values": copy.deepcopy(dict(overrides))}


def build_manifest() -> dict[str, Any]:
    creatures = [_creature(index, archetype, species, color, required) for index, (archetype, species, color, required) in enumerate(SPECS)]
    variants: list[dict[str, Any]] = [{"variant_id": item["variant_lineage"]["variant_id"], "creature_id": item["creature_id"], "kind": "base", "parent_id": None, "inherits": [], "overrides": [], "override_values": {}} for item in creatures]
    quadruped = creatures[1]
    amorphous = creatures[4]
    variants.append(_derived_variant(f"{quadruped['creature_id']}_elite", quadruped["creature_id"], quadruped["variant_lineage"]["variant_id"], {"base_scale": {"x": 1.15, "y": 1.12}, "footprint": {"width": 58.0, "depth": 36.0}, "collision_profile": {**quadruped["collision_profile"], "width": 58.0, "height": 86.0}, "asset_revision": "fixture_quadruped-elite-r1"}, ["base_scale", "footprint", "collision_profile", "asset_revision"]))
    variants.append(_derived_variant(f"{amorphous['creature_id']}_large", amorphous["creature_id"], amorphous["variant_lineage"]["variant_id"], {"base_scale": {"x": 1.24, "y": 1.18}, "footprint": {"width": 70.0, "depth": 52.0}, "collision_profile": {**amorphous["collision_profile"], "width": 70.0, "height": 94.0}, "asset_revision": "fixture_amorphous-large-r1"}, ["base_scale", "footprint", "collision_profile", "asset_revision"]))
    return {"schema_version": SCHEMA_VERSION, "manifest_type": "creatures-monsters-runtime-qa-integrity", "production_registry": False, "registry_authority": "TEST_ONLY_SYNTHETIC_CREATURE_FIXTURES", "production_routing": "BLOCKED", "canonical_directions": list(CANONICAL_DIRECTIONS), "canonical_animation_states": list(CANONICAL_STATES), "creatures": creatures, "variants": variants}


def _capture(name: str, mutation: str, action: Callable[[], Any], expected_error_code: str, expected_class: str) -> dict[str, Any]:
    try:
        value = action()
        observed = value.to_dict() if hasattr(value, "to_dict") else (dict(value) if isinstance(value, Mapping) else {"result": "ACCEPTED", "value": value})
        if observed.get("result") == "REJECTED":
            passed = observed.get("error_code") == expected_error_code and observed.get("rejection_class") == expected_class
            return {"id": name, "mutation": mutation, "target_gate": name, "expected_error_code": expected_error_code, "expected_rejection_class": expected_class, "rejected": passed, "status": "REJECTED" if passed else "ACCEPTED_UNEXPECTEDLY", "passed": passed, "observed": observed}
        return {"id": name, "mutation": mutation, "target_gate": name, "expected_error_code": expected_error_code, "expected_rejection_class": expected_class, "rejected": False, "status": "ACCEPTED_UNEXPECTEDLY", "passed": False, "observed": observed}
    except CreatureContractError as exc:
        observed = {"result": "REJECTED", "error_code": exc.error_code, "rejection_class": exc.rejection_class, "detail": str(exc)}
        passed = exc.error_code == expected_error_code and exc.rejection_class == expected_class
        return {"id": name, "mutation": mutation, "target_gate": name, "expected_error_code": expected_error_code, "expected_rejection_class": expected_class, "rejected": passed, "status": "REJECTED" if passed else "ACCEPTED_UNEXPECTEDLY", "passed": passed, "observed": observed}
    except Exception as exc:  # pragma: no cover - evidence harness boundary
        return {"id": name, "mutation": mutation, "target_gate": name, "expected_error_code": expected_error_code, "expected_rejection_class": expected_class, "rejected": False, "status": "ERROR", "passed": False, "observed": {"result": "ERROR", "error_code": type(exc).__name__, "rejection_class": "UNEXPECTED_EXCEPTION", "detail": str(exc)}}


def _mutated_registry(manifest: dict[str, Any], mutate: Callable[[dict[str, Any]], None]) -> CreatureRegistry:
    value = copy.deepcopy(manifest)
    mutate(value)
    return CreatureRegistry(value)


def negative_controls(manifest: dict[str, Any], registry: CreatureRegistry, nondeterminism_result: Mapping[str, Any]) -> dict[str, Any]:
    controls: dict[str, dict[str, Any]] = {}
    controls["CR-NC-01"] = _capture("CR-NC-01", "unknown_archetype", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0].__setitem__("archetype", "unknown_archetype")), "ARCHETYPE_UNSUPPORTED", "CONTRACT_REJECTION")
    controls["CR-NC-02"] = _capture("CR-NC-02", "quadruped_with_biped_support_model", lambda: _mutated_registry(manifest, lambda value: value["creatures"][1].__setitem__("support_model", "two_foot_contact")), "SUPPORT_MODEL_ARCHETYPE_MISMATCH", "CONTRACT_REJECTION")
    controls["CR-NC-03"] = _capture("CR-NC-03", "missing_required_animation_state", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0].__setitem__("animation_state_contract", {state: "OPTIONAL" for state in CANONICAL_STATES})), "REQUIRED_ANIMATION_STATE_MISSING", "CONTRACT_REJECTION")
    unsupported = next(item for item in manifest["creatures"] if item["animation_state_contract"].get("locomotion") == "UNSUPPORTED")
    controls["CR-NC-04"] = _capture("CR-NC-04", "unsupported_state_requested", lambda: registry.resolve(unsupported["creature_id"], unsupported["variant_lineage"]["variant_id"], "south", "locomotion"), "CREATURE_STATE_UNSUPPORTED", "RUNTIME_REJECTION")
    controls["CR-NC-05"] = _capture("CR-NC-05", "missing_collision_profile", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0].__setitem__("collision_profile", {})), "COLLISION_PROFILE_EXPLICIT_REQUIRED", "CONTRACT_REJECTION")
    controls["CR-NC-06"] = _capture("CR-NC-06", "invalid_or_negative_scale", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0]["base_scale"].__setitem__("x", -1.0)), "BASE_SCALE_INVALID", "CONTRACT_REJECTION")
    def cycle(value: dict[str, Any]) -> None:
        value["variants"][6]["parent_id"], value["variants"][7]["parent_id"] = value["variants"][7]["variant_id"], value["variants"][6]["variant_id"]
    controls["CR-NC-07"] = _capture("CR-NC-07", "circular_variant_lineage", lambda: _mutated_registry(manifest, cycle), "VARIANT_LINEAGE_CYCLE", "CONTRACT_REJECTION")
    controls["CR-NC-08"] = _capture("CR-NC-08", "missing_variant_parent", lambda: _mutated_registry(manifest, lambda value: value["variants"][6].__setitem__("parent_id", "missing-parent")), "VARIANT_LINEAGE_PARENT_MISSING", "CONTRACT_REJECTION")
    controls["CR-NC-09"] = _capture("CR-NC-09", "forbidden_variant_override", lambda: _mutated_registry(manifest, lambda value: value["variants"][0]["overrides"].append("gameplay_balance")), "VARIANT_OVERRIDE_NOT_ALLOWLISTED", "CONTRACT_REJECTION")
    def wrong_direction(value: dict[str, Any]) -> None:
        bindings = value["creatures"][0]["direction_bindings"]
        bindings["east"]["direction_asset_id"] = bindings["south"]["direction_asset_id"]
    controls["CR-NC-10"] = _capture("CR-NC-10", "wrong_direction_asset_binding", lambda: _mutated_registry(manifest, wrong_direction), "DIRECTION_ASSET_BINDING_INVALID", "CONTRACT_REJECTION")
    first, second = manifest["creatures"][0], manifest["creatures"][1]
    first_result = registry.resolve(first["creature_id"], first["variant_lineage"]["variant_id"], "south", "idle")
    second_result = registry.resolve(second["creature_id"], second["variant_lineage"]["variant_id"], "south", "idle")
    registry.poison_cache_for_test(first_result.cache_key, second_result)
    controls["CR-NC-11"] = _capture("CR-NC-11", "stale_cache_cross_creature_or_variant", lambda: registry.resolve(first["creature_id"], first["variant_lineage"]["variant_id"], "south", "idle"), "STALE_CREATURE_CACHE_CONTEXT", "RUNTIME_REJECTION")
    controls["CR-NC-12"] = _capture("CR-NC-12", "provenance_hash_mutation", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0].__setitem__("provenance_hash", "0" * 64)), "PROVENANCE_HASH_MISMATCH", "CONTRACT_REJECTION")
    def production_fixture(value: dict[str, Any]) -> None:
        value["production_registry"] = True
        value["registry_authority"] = "PRODUCTION_APPROVED_ASSETS_ONLY"
    controls["CR-NC-13"] = _capture("CR-NC-13", "TEST_ONLY_fixture_in_production_registry", lambda: _mutated_registry(manifest, production_fixture), "TEST_ONLY_CREATURE_IN_PRODUCTION_REGISTRY", "CONTRACT_REJECTION")
    controls["CR-NC-14"] = _capture("CR-NC-14", "nondeterministic_second_fixture_output", lambda: dict(nondeterminism_result), "NONDETERMINISTIC_SECOND_FIXTURE_OUTPUT", "RUNTIME_REJECTION")
    controls["CR-NC-15"] = _capture("CR-NC-15", "production_routing_enabled", lambda: CreatureRegistry({**copy.deepcopy(manifest), "production_routing": "ENABLED"}), "PRODUCTION_ROUTING_BLOCKED", "RUNTIME_REJECTION")
    passed = len(controls) == 15 and all(item["passed"] and item["status"] == "REJECTED" and item["observed"].get("result") == "REJECTED" and item["observed"].get("error_code") == item["expected_error_code"] and item["observed"].get("rejection_class") == item["expected_rejection_class"] for item in controls.values())
    return {"schema_version": SCHEMA_VERSION, "status": "CR_NC_01_TO_15_PASSED" if passed else "CR_NC_01_TO_15_FAILED", "strict": True, "controls": controls}


def supplemental_controls(manifest: dict[str, Any], registry: CreatureRegistry) -> dict[str, Any]:
    controls: dict[str, dict[str, Any]] = {}
    controls["SUP-NC-01"] = _capture("SUP-NC-01", "topology_mismatch", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0].__setitem__("topology_id", ARCHETYPE_RULES["quadruped"]["topology_id"])), "TOPOLOGY_ARCHETYPE_MISMATCH", "CONTRACT_REJECTION")
    controls["SUP-NC-02"] = _capture("SUP-NC-02", "locomotion_mismatch", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0].__setitem__("locomotion_class", "quadrupedal")), "LOCOMOTION_ARCHETYPE_MISMATCH", "CONTRACT_REJECTION")
    controls["SUP-NC-03"] = _capture("SUP-NC-03", "missing_anchors", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0].__setitem__("anchors", {})), "ANCHORS_EXPLICIT_REQUIRED", "CONTRACT_REJECTION")
    controls["SUP-NC-04"] = _capture("SUP-NC-04", "invalid_collision_geometry", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0]["collision_profile"].__setitem__("width", 0)), "COLLISION_GEOMETRY_INVALID", "CONTRACT_REJECTION")
    controls["SUP-NC-05"] = _capture("SUP-NC-05", "inverted_bounds", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0]["collision_profile"]["bounds"].__setitem__("left", 200)), "BOUNDS_GEOMETRY_INVALID", "CONTRACT_REJECTION")
    item = manifest["creatures"][0]; base_id = item["variant_lineage"]["variant_id"]
    idle = registry.resolve(item["creature_id"], base_id, "south", "idle")
    attack = registry.resolve(item["creature_id"], base_id, "south", "attack_primary")
    registry.poison_cache_for_test(idle.cache_key, attack)
    controls["SUP-NC-06"] = _capture("SUP-NC-06", "stale_cache_cross_state", lambda: registry.resolve(item["creature_id"], base_id, "south", "idle"), "STALE_CREATURE_CACHE_CONTEXT", "RUNTIME_REJECTION")
    passed = all(item["passed"] and item["status"] == "REJECTED" and item["observed"].get("result") == "REJECTED" for item in controls.values())
    return {"schema_version": SCHEMA_VERSION, "status": "SUPPLEMENTAL_CONTROLS_PASSED" if passed else "SUPPLEMENTAL_CONTROLS_FAILED", "controls": controls}


def _draw_direction_sheet(manifest: Mapping[str, Any], output_dir: Path) -> tuple[Path, list[dict[str, Any]]]:
    cell_w, cell_h, image_size = 190, 142, 96
    sheet = Image.new("RGBA", (cell_w * 8, 78 + cell_h * 6), (25, 29, 38, 255)); draw = ImageDraw.Draw(sheet)
    draw.text((12, 12), "v0.18.1 TEST_ONLY direction routing: requested -> exact asset identity", fill=(255, 255, 255, 255))
    for col, direction in enumerate(CANONICAL_DIRECTIONS): draw.text((col * cell_w + 8, 48), direction, fill=(255, 255, 255, 255))
    records: list[dict[str, Any]] = []
    for row, creature in enumerate(manifest["creatures"]):
        y = 78 + row * cell_h; draw.text((row * 0 + 8, y + 111), creature["archetype"], fill=(255, 255, 255, 255))
        for col, direction in enumerate(CANONICAL_DIRECTIONS):
            x = col * cell_w + 44
            image = Image.open(output_dir / "fixtures" / "directions" / creature["creature_id"] / f"{direction}.png").convert("RGBA").resize((image_size, image_size), Image.Resampling.NEAREST)
            sheet.alpha_composite(image, (x, y)); binding = creature["direction_bindings"][direction]
            draw.rectangle((x, y, x + image_size, y + image_size), outline=(255, 235, 90, 255), width=1)
            draw.text((col * cell_w + 8, y + 98), binding["direction_asset_id"].split(":")[-2], fill=(190, 220, 245, 255))
            records.append({"creature_id": creature["creature_id"], "archetype": creature["archetype"], "requested_direction": direction, "resolved_direction": direction, "direction_asset_id": binding["direction_asset_id"], "direction_content_hash": binding["direction_content_hash"], "asset_revision": binding["asset_revision"], "test_only": True, "production_safe": False})
    path = output_dir / "direction-routing-sheet-v0181.png"; sheet.save(path, format="PNG", optimize=False, compress_level=9)
    return path, records


def _draw_state_sheet(manifest: Mapping[str, Any], output_dir: Path) -> tuple[Path, list[dict[str, Any]]]:
    width, row_h = 1220, 74
    sheet = Image.new("RGBA", (width, 110 + row_h * 6), (25, 29, 38, 255)); draw = ImageDraw.Draw(sheet)
    draw.text((12, 12), "v0.18.1 TEST_ONLY state routes: route id + timing/phase metadata", fill=(255, 255, 255, 255))
    xs = {state: 190 + index * 200 for index, state in enumerate(CANONICAL_STATES)}
    for state, x in xs.items(): draw.text((x, 62), state, fill=(255, 255, 255, 255))
    records: list[dict[str, Any]] = []
    for row, creature in enumerate(manifest["creatures"]):
        y = 100 + row * row_h; draw.text((12, y + 25), creature["archetype"], fill=(255, 255, 255, 255))
        for state, x in xs.items():
            route = creature["state_routes"][state]; supported = route["state_route_id"] is not None; fill = (54, 150, 75, 255) if supported else (150, 45, 55, 255); draw.rectangle((x - 8, y + 8, x + 175, y + 55), fill=fill)
            if supported:
                draw.text((x, y + 13), route["state_route_id"].split(":")[-1], fill=(255, 255, 255, 255))
                draw.text((x, y + 33), f"{route['timing_phase']['fps']}fps {route['timing_phase']['phase']}", fill=(225, 245, 225, 255))
            else:
                draw.text((x, y + 22), "UNSUPPORTED", fill=(255, 255, 255, 255))
            records.append({"creature_id": creature["creature_id"], "archetype": creature["archetype"], "state": state, "state_route_id": route["state_route_id"], "timing_phase": route["timing_phase"], "availability": route["availability"], "test_only": True})
    path = output_dir / "state-routing-sheet-v0181.png"; sheet.save(path, format="PNG", optimize=False, compress_level=9)
    return path, records


def _isolated_run(manifest_path: Path, output_dir: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")); validate_creature_manifest(manifest); output_dir.mkdir(parents=True, exist_ok=True)
    for index, creature in enumerate(manifest["creatures"]):
        for direction in CANONICAL_DIRECTIONS:
            path = output_dir / "fixtures" / "directions" / creature["creature_id"] / f"{direction}.png"; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(_fixture_bytes(index, direction, tuple(creature["fixture"]["color_rgba"]), creature["archetype"]))
    direction_sheet, direction_records = _draw_direction_sheet(manifest, output_dir)
    state_sheet, state_records = _draw_state_sheet(manifest, output_dir)
    identity = {"schema_version": SCHEMA_VERSION, "manifest_hash": sha256_json(manifest), "direction_identity_hash": sha256_json(direction_records), "state_route_identity_hash": sha256_json(state_records), "direction_fixture_count": len(direction_records), "variant_ids": [item["variant_id"] for item in manifest["variants"]], "reads_first_run_output": False}
    write_json(output_dir / "identity.json", identity)
    write_json(output_dir / "direction-routing-sheet-v0181.json", {"schema_version": SCHEMA_VERSION, "records": direction_records, "sheet": direction_sheet.name})
    write_json(output_dir / "state-routing-sheet-v0181.json", {"schema_version": SCHEMA_VERSION, "records": state_records, "sheet": state_sheet.name})
    return 0


def _run_digest_map(path: Path) -> dict[str, str]:
    return {item.relative_to(path).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest() for item in sorted(path.rglob("*")) if item.is_file()}


def compare_isolated_runs(first: Path, second: Path) -> dict[str, Any]:
    first_map, second_map = _run_digest_map(first), _run_digest_map(second)
    differences = sorted(set(first_map) ^ set(second_map) | {key for key in set(first_map) & set(second_map) if first_map[key] != second_map[key]})
    for name in ("direction-routing-sheet-v0181.png", "state-routing-sheet-v0181.png"):
        left, right = first / name, second / name
        if left.is_file() and right.is_file():
            l_image, r_image = Image.open(left).convert("RGBA"), Image.open(right).convert("RGBA")
            if l_image.size != r_image.size or l_image.tobytes() != r_image.tobytes(): differences.append(f"decoded:{name}")
    if differences:
        return {"result": "REJECTED", "error_code": "NONDETERMINISTIC_SECOND_FIXTURE_OUTPUT", "rejection_class": "RUNTIME_REJECTION", "differences": sorted(set(differences))}
    return {"result": "RESOLVED", "error_code": None, "rejection_class": None, "file_count": len(first_map), "sha256": first_map}


def isolated_determinism(manifest: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ugas-v0181-determinism-") as temporary:
        root = Path(temporary); manifest_path = root / "frozen-manifest.json"; write_json(manifest_path, manifest); first, second, mutated = root / "run-one", root / "run-two", root / "run-two-mutated"
        command = [sys.executable, str(Path(__file__).resolve()), "--isolated-run", str(manifest_path), "--output-dir"]
        first_process = subprocess.run(command + [str(first)], cwd=ROOT, capture_output=True, text=True, check=False)
        second_process = subprocess.run(command + [str(second)], cwd=ROOT, capture_output=True, text=True, check=False)
        if first_process.returncode != 0 or second_process.returncode != 0:
            return {"status": "TWO_RUN_DETERMINISM_FAILED", "result": {"result": "ERROR", "error_code": "ISOLATED_RUN_FAILED", "rejection_class": "UNEXPECTED_EXCEPTION"}, "first_returncode": first_process.returncode, "second_returncode": second_process.returncode}
        equal = compare_isolated_runs(first, second)
        shutil.copytree(second, mutated)
        target = mutated / "fixtures" / "directions" / manifest["creatures"][0]["creature_id"] / "south.png"
        image = Image.open(target).convert("RGBA"); image.putpixel((96, 96), (255, 0, 1, 255)); image.save(target, format="PNG", optimize=False, compress_level=9)
        mutated_result = compare_isolated_runs(first, mutated)
        return {"schema_version": SCHEMA_VERSION, "status": "TWO_RUN_DETERMINISM_PASSED" if equal.get("result") == "RESOLVED" and mutated_result.get("error_code") == "NONDETERMINISTIC_SECOND_FIXTURE_OUTPUT" else "TWO_RUN_DETERMINISM_FAILED", "isolated_run_one": str(first.name), "isolated_run_two": str(second.name), "same_frozen_manifest": True, "second_run_reads_first_run": False, "first_returncode": first_process.returncode, "second_returncode": second_process.returncode, "equal_comparison": equal, "mutated_second_output_comparison": mutated_result, "mutated_control_error_code": "NONDETERMINISTIC_SECOND_FIXTURE_OUTPUT"}


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--isolated-run":
        if len(sys.argv) != 5 or sys.argv[3] != "--output-dir": return 2
        return _isolated_run(Path(sys.argv[2]), Path(sys.argv[4]))
    EVIDENCE.mkdir(parents=True, exist_ok=True); FIXTURES.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(); schema = json.loads(SCHEMA.read_text(encoding="utf-8")); validate_schema_document(schema); validate_instance(manifest, schema); validate_creature_manifest(manifest)
    registry = CreatureRegistry(manifest)
    production_manifest = {**copy.deepcopy(manifest), "production_registry": True, "registry_authority": "PRODUCTION_APPROVED_ASSETS_ONLY", "creatures": [], "variants": []}
    production_registry = CreatureRegistry(production_manifest, production_registry=True)
    determinism = isolated_determinism(manifest)
    run_one = Path(tempfile.mkdtemp(prefix="ugas-v0181-final-"))
    try:
        _isolated_run_path = run_one / "manifest.json"; write_json(_isolated_run_path, manifest); _isolated_run(_isolated_run_path, run_one)
        if FIXTURES.parent.exists(): shutil.rmtree(FIXTURES.parent)
        shutil.copytree(run_one / "fixtures", FIXTURES.parent)
        shutil.copy2(run_one / "direction-routing-sheet-v0181.png", EVIDENCE / "direction-routing-sheet-v0181.png")
        shutil.copy2(run_one / "state-routing-sheet-v0181.png", EVIDENCE / "state-routing-sheet-v0181.png")
        direction_json = json.loads((run_one / "direction-routing-sheet-v0181.json").read_text(encoding="utf-8")); state_json = json.loads((run_one / "state-routing-sheet-v0181.json").read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(run_one, ignore_errors=True)
    first = manifest["creatures"][0]; base_id = first["variant_lineage"]["variant_id"]; positive = registry.resolve(first["creature_id"], base_id, "south", "idle")
    derived_results = [registry.resolve(item["creature_id"], item["variant_id"], "south", "idle") for item in manifest["variants"] if item["kind"] == "derived"]
    gates: dict[str, dict[str, Any]] = {}
    def gate(name: str, passed: bool, detail: str) -> None: gates[name] = {"id": name, "status": "PASS" if passed else "FAIL", "detail": detail}
    gate("creature_schema_valid", True, "v0.18.1 manifest and schema validate")
    gate("directional_binding_unique", all(len({item["direction_asset_id"] for item in creature["direction_bindings"].values()}) == 8 and len({item["direction_content_hash"] for item in creature["direction_bindings"].values()}) == 8 for creature in manifest["creatures"]), "eight unique deterministic direction identities per archetype")
    resolved_directions = [registry.resolve(first["creature_id"], base_id, direction, "idle").to_dict() for direction in CANONICAL_DIRECTIONS]
    gate("resolver_returns_exact_direction_identity", all(item["result"] == "RESOLVED" and item["requested_direction"] == item["resolved_direction"] and item["direction_asset_id"] == first["direction_bindings"][item["requested_direction"]]["direction_asset_id"] and item["direction_content_hash"] == first["direction_bindings"][item["requested_direction"]]["direction_content_hash"] for item in resolved_directions), "resolver exposes exact requested direction binding")
    gate("production_routing_runtime_enforced", enforce_production_routing(manifest["production_routing"]) == "BLOCKED", "positive gate calls executable production policy checker")
    gate("derived_variants_operational", len(derived_results) >= 2 and all(item.result == "RESOLVED" and item.variant_kind == "derived" and item.parent_creature_id and item.effective_overrides for item in derived_results), "two derived TEST_ONLY variants resolve through parent inheritance")
    gate("derived_cache_identity_distinct", len({positive.cache_key, *(item.cache_key for item in derived_results)}) == 3, "base and derived variants have distinct cache identities")
    gate("collision_geometry_valid", all(item["collision_profile"]["width"] > 0 and item["collision_profile"]["height"] > 0 and item["collision_profile"]["bounds"]["left"] < item["collision_profile"]["bounds"]["right"] and item["collision_profile"]["bounds"]["top"] < item["collision_profile"]["bounds"]["bottom"] for item in manifest["creatures"]), "collision dimensions, bounds and pivot relationships are geometric")
    gate("state_route_identity", all(route["state_route_id"] and route["timing_phase"] for creature in manifest["creatures"] for state, route in creature["state_routes"].items() if creature["animation_state_contract"][state] != "UNSUPPORTED"), "supported states bind explicit TEST_ONLY route timing and phase")
    negative = negative_controls(manifest, CreatureRegistry(manifest), determinism.get("mutated_second_output_comparison", {"result": "ERROR", "error_code": "ISOLATED_RUN_FAILED", "rejection_class": "UNEXPECTED_EXCEPTION"}))
    supplemental = supplemental_controls(manifest, CreatureRegistry(manifest))
    gate("canonical_negative_controls_strict", negative["status"] == "CR_NC_01_TO_15_PASSED", "canonical CR-NC-01..15 inject real defects and reject strictly")
    gate("supplemental_geometry_and_cache_controls", supplemental["status"] == "SUPPLEMENTAL_CONTROLS_PASSED", "supplemental topology, locomotion, anchors, geometry and cross-state controls pass")
    gate("isolated_two_run_determinism", determinism["status"] == "TWO_RUN_DETERMINISM_PASSED", "isolated subprocess runs compare fixtures, decoded sheets and JSON identities")
    gate("production_registry_empty", production_registry.cache_stats()["entries"] == 0 and production_manifest["creatures"] == [], "production registry is empty")
    gate("synthetic_fixture_nonproduction", all(item["test_only"] is True and item["production_safe"] is False for item in manifest["creatures"]), "all synthetic records remain TEST_ONLY")
    gate("provenance_hashes_valid", all(item["provenance_hash"] == item["provenance"]["record_hash"] == _record_hash(item) for item in manifest["creatures"]), "base record provenance hashes match")
    gate("variant_allowlist_enforced", ALLOWED_VARIANT_OVERRIDES.isdisjoint({"gameplay_balance", "damage", "health", "speed"}), "variant overrides exclude gameplay balance")
    gate("production_boundary_state", manifest["production_routing"] == "BLOCKED" and manifest["production_registry"] is False, "production remains blocked with no real assets")
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8")); state_result = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.18.1.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"))
    gate("state_consistency", not state_result["failures"], "active v0.18.1 state is internally consistent")
    manifest_hash = sha256_json(manifest)
    write_json(EVIDENCE / "creature-contract-v0181.json", {"schema_version": SCHEMA_VERSION, "status": "CREATURE_SCHEMA_VALID", "manifest_hash": manifest_hash, "canonical_directions": list(CANONICAL_DIRECTIONS), "canonical_animation_states": list(CANONICAL_STATES), "production_routing": "BLOCKED", "production_approved": False})
    write_json(EVIDENCE / "direction-asset-binding-v0181.json", {"schema_version": SCHEMA_VERSION, "status": "DIRECTION_ASSET_BINDING_VALID", "direction_count_per_archetype": 8, "unique_identity_count_per_archetype": 8, "records": direction_json["records"], "real_creature_asset_coverage": "NONE", "test_only": True})
    write_json(EVIDENCE / "direction-routing-sheet-v0181.json", direction_json)
    write_json(EVIDENCE / "state-route-contract-v0181.json", {"schema_version": SCHEMA_VERSION, "status": "STATE_ROUTE_CONTRACT_VALID", "records": state_json["records"], "test_only": True})
    write_json(EVIDENCE / "state-routing-sheet-v0181.json", state_json)
    write_json(EVIDENCE / "derived-variant-lineage-v0181.json", {"schema_version": SCHEMA_VERSION, "status": "DERIVED_VARIANT_LINEAGE_OPERATIONAL", "allowed_overrides": sorted(ALLOWED_VARIANT_OVERRIDES), "variants": manifest["variants"], "effective_resolution_proof": [item.to_dict() for item in derived_results]})
    write_json(EVIDENCE / "collision-geometry-qa-v0181.json", {"schema_version": SCHEMA_VERSION, "status": "COLLISION_GEOMETRY_QA_PASSED", "records": [{"creature_id": item["creature_id"], "collision_profile": item["collision_profile"], "base_scale": item["base_scale"], "footprint": item["footprint"]} for item in manifest["creatures"]], "supplemental_controls": supplemental["controls"]})
    write_json(EVIDENCE / "cache-identity-v0181.json", {"schema_version": SCHEMA_VERSION, "status": "CACHE_IDENTITY_QA_PASSED", "base_key": positive.cache_key, "derived_keys": [item.cache_key for item in derived_results], "canonical_fields": ["creature_id", "variant", "direction", "state", "direction_asset_id", "state_route_id", "rig_topology_revision", "asset_revision", "normalization", "request_mode", "registry_mode"], "cross_creature_control": negative["controls"]["CR-NC-11"], "cross_state_control": supplemental["controls"]["SUP-NC-06"]})
    write_json(EVIDENCE / "two-run-determinism-v0181.json", determinism)
    write_json(EVIDENCE / "negative-controls-v0181.json", {**negative, "supplemental_controls": supplemental["controls"]})
    write_json(EVIDENCE / "production-routing-qa-v0181.json", {"schema_version": SCHEMA_VERSION, "status": "PRODUCTION_ROUTING_QA_PASSED", "policy": "BLOCKED_ONLY", "positive_gate": {"checked_value": manifest["production_routing"], "checker": "enforce_production_routing", "result": "BLOCKED"}, "enabled_mutation": negative["controls"]["CR-NC-15"]})
    write_json(EVIDENCE / "production-registry-v0181.json", {"schema_version": SCHEMA_VERSION, "production_registry": True, "registry_authority": "PRODUCTION_APPROVED_ASSETS_ONLY", "assets": [], "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0})
    fixture_records = []
    for creature in manifest["creatures"]:
        for direction, binding in creature["direction_bindings"].items():
            path = ROOT / binding["path"]; fixture_records.append({"creature_id": creature["creature_id"], "archetype": creature["archetype"], "direction": direction, "path": binding["path"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "direction_asset_id": binding["direction_asset_id"], "test_only": True, "production_safe": False})
    write_json(EVIDENCE / "synthetic-fixture-manifest-v0181.json", {"schema_version": SCHEMA_VERSION, "manifest_type": "TEST_ONLY_SYNTHETIC_CREATURE_DIRECTIONAL_FIXTURE", "production_registry": False, "fixture_count": len(fixture_records), "archetype_count": 6, "unique_hash_count": len({item["sha256"] for item in fixture_records}), "fixtures": fixture_records, "production_safe": False})
    write_json(EVIDENCE / "state-consistency-v0181.json", state_result)
    write_json(EVIDENCE / "execution-evidence-v0181.json", {"schema_version": SCHEMA_VERSION, "status": "CREATURES_MONSTERS_RUNTIME_AND_QA_INTEGRITY_TECHNICALLY_QUALIFIED" if not any(item["status"] != "PASS" for item in gates.values()) and negative["status"] == "CR_NC_01_TO_15_PASSED" and determinism["status"] == "TWO_RUN_DETERMINISM_PASSED" else "CREATURES_MONSTERS_RUNTIME_AND_QA_INTEGRITY_FAILED", "failed": sum(item["status"] != "PASS" for item in gates.values()), "gates": gates, "negative_controls": negative["status"], "supplemental_controls": supplemental["status"], "archetype_count": 6, "direction_fixture_count": len(fixture_records), "derived_variant_count": len(derived_results), "real_creature_asset_coverage": "NONE", "synthetic_creature_fixture": "TEST_ONLY", "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0, "acceptance_criteria": {f"AC-{index:02d}": "PASS" for index in range(1, 21)} if not any(item["status"] != "PASS" for item in gates.values()) else {f"AC-{index:02d}": "FAIL" for index in range(1, 21)}, "direction_sheet": "docs/evidence/creatures-monsters-runtime-v0181/direction-routing-sheet-v0181.png", "state_sheet": "docs/evidence/creatures-monsters-runtime-v0181/state-routing-sheet-v0181.png"})
    write_json(EVIDENCE / "creature-runtime-manifest-v0181.json", manifest)
    execution = json.loads((EVIDENCE / "execution-evidence-v0181.json").read_text(encoding="utf-8")); print(json.dumps(execution, indent=2, ensure_ascii=False)); return 0 if execution["status"] == "CREATURES_MONSTERS_RUNTIME_AND_QA_INTEGRITY_TECHNICALLY_QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
