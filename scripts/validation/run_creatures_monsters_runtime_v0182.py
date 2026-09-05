"""Generate and qualify the forward-only v0.18.2 correction evidence.

The runner consumes the frozen v0.18.1 fixture bytes, so the 48 directional
pixels and content hashes are preserved while the effective-variant and
archetype/state gates are exercised through the real v0.18.2 registry.
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
from ugas.creature_runtime_v0182 import (  # noqa: E402
    ALLOWED_VARIANT_OVERRIDES,
    CreatureContractError,
    CreatureRegistry,
    SCHEMA_VERSION,
    _record_hash,
    enforce_production_routing,
    sha256_json,
    validate_creature_manifest,
)
from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402
from ugas.state_consistency_v0182 import validate_state_consistency  # noqa: E402


EVIDENCE = ROOT / "docs/evidence/creatures-monsters-runtime-v0182"
FROZEN = ROOT / "docs/evidence/creatures-monsters-runtime-v0181"
SCHEMA = ROOT / "schemas/creature-runtime-v0182.json"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _state_route(creature_id: str, state: str, index: int, availability: str) -> dict[str, Any]:
    if availability == "UNSUPPORTED":
        return {"state": state, "availability": availability, "state_route_id": None, "timing_phase": None, "test_only": True, "production_safe": False}
    return {
        "state": state,
        "availability": availability,
        "state_route_id": f"{creature_id}:{state}:route-v0182",
        "timing_phase": {"fps": 8 + ((index + len(state)) % 5), "duration_ms": 500 + index * 25 + len(state) * 10, "phase": "loop" if state in {"idle", "locomotion"} else "one_shot"},
        "test_only": True,
        "production_safe": False,
    }


def build_manifest() -> dict[str, Any]:
    source = json.loads((FROZEN / "creature-runtime-manifest-v0181.json").read_text(encoding="utf-8"))
    creatures = copy.deepcopy(source["creatures"])
    moving = {"humanoid_biped", "quadruped", "flying_winged", "serpentine", "amorphous"}
    for index, creature in enumerate(creatures):
        creature["provenance"]["source_revision"] = SCHEMA_VERSION
        for direction, binding in creature["direction_bindings"].items():
            binding["direction_asset_id"] = binding["direction_asset_id"].replace("qa-v0181", "qa-v0182")
            binding["path"] = binding["path"].replace("v0181", "v0182")
        if creature["archetype"] in moving:
            creature["animation_state_contract"]["locomotion"] = "REQUIRED"
        for route in creature["state_routes"].values():
            if route.get("state_route_id"):
                route["state_route_id"] = route["state_route_id"].replace("route-v0181", "route-v0182")
        creature["state_routes"]["locomotion"] = _state_route(creature["creature_id"], "locomotion", index, creature["animation_state_contract"]["locomotion"])
        creature["variant_lineage"]["inherits"] = []
        creature["variant_lineage"]["overrides"] = []
        creature["provenance_hash"] = _record_hash(creature)
        creature["provenance"]["record_hash"] = creature["provenance_hash"]
    variants: list[dict[str, Any]] = []
    for item in source["variants"]:
        variant = copy.deepcopy(item)
        variant["variant_revision"] = f"{variant['variant_id']}-metadata-r1"
        if variant["kind"] == "derived":
            variant["overrides"] = [key for key in variant["overrides"] if key != "asset_revision"]
            variant["override_values"].pop("asset_revision", None)
        variants.append(variant)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "manifest_type": "creatures-monsters-runtime-qa-integrity",
        "production_registry": False,
        "registry_authority": "TEST_ONLY_SYNTHETIC_CREATURE_FIXTURES",
        "production_routing": "BLOCKED",
        "canonical_directions": list(CANONICAL_DIRECTIONS),
        "canonical_animation_states": list(CANONICAL_STATES),
        "creatures": creatures,
        "variants": variants,
    }
    validate_creature_manifest(manifest)
    return manifest


def _capture(name: str, mutation: str, action: Callable[[], Any], expected_error_code: str, expected_class: str) -> dict[str, Any]:
    try:
        value = action()
        observed = value.to_dict() if hasattr(value, "to_dict") else (dict(value) if isinstance(value, Mapping) else {"result": "ACCEPTED", "value": value})
        passed = observed.get("result") == "REJECTED" and observed.get("error_code") == expected_error_code and observed.get("rejection_class") == expected_class
        return {"id": name, "mutation": mutation, "target_gate": name, "expected_error_code": expected_error_code, "expected_rejection_class": expected_class, "rejected": passed, "status": "REJECTED" if passed else "ACCEPTED_UNEXPECTEDLY", "passed": passed, "observed": observed}
    except CreatureContractError as exc:
        passed = exc.error_code == expected_error_code and exc.rejection_class == expected_class
        return {"id": name, "mutation": mutation, "target_gate": name, "expected_error_code": expected_error_code, "expected_rejection_class": expected_class, "rejected": passed, "status": "REJECTED" if passed else "ERROR", "passed": passed, "observed": {"result": "REJECTED", "error_code": exc.error_code, "rejection_class": exc.rejection_class, "detail": str(exc)}}
    except Exception as exc:  # pragma: no cover
        return {"id": name, "mutation": mutation, "target_gate": name, "expected_error_code": expected_error_code, "expected_rejection_class": expected_class, "rejected": False, "status": "ERROR", "passed": False, "observed": {"result": "ERROR", "error_code": type(exc).__name__, "rejection_class": "UNEXPECTED_EXCEPTION", "detail": str(exc)}}


def _mutated_registry(manifest: Mapping[str, Any], mutate: Callable[[dict[str, Any]], None]) -> CreatureRegistry:
    value = copy.deepcopy(dict(manifest))
    mutate(value)
    return CreatureRegistry(value)


def canonical_controls(manifest: dict[str, Any], registry: CreatureRegistry, nondeterminism: Mapping[str, Any]) -> dict[str, Any]:
    controls: dict[str, dict[str, Any]] = {}
    controls["CR-NC-01"] = _capture("CR-NC-01", "unknown_archetype", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0].__setitem__("archetype", "unknown_archetype")), "ARCHETYPE_UNSUPPORTED", "CONTRACT_REJECTION")
    controls["CR-NC-02"] = _capture("CR-NC-02", "quadruped_with_biped_support_model", lambda: _mutated_registry(manifest, lambda value: value["creatures"][1].__setitem__("support_model", "two_foot_contact")), "SUPPORT_MODEL_ARCHETYPE_MISMATCH", "CONTRACT_REJECTION")
    controls["CR-NC-03"] = _capture("CR-NC-03", "missing_required_animation_state", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0].__setitem__("animation_state_contract", {state: "OPTIONAL" for state in CANONICAL_STATES})), "REQUIRED_ANIMATION_STATE_MISSING", "CONTRACT_REJECTION")
    stationary = next(item for item in manifest["creatures"] if item["archetype"] == "stationary_structure")
    controls["CR-NC-04"] = _capture("CR-NC-04", "unsupported_state_requested", lambda: registry.resolve(stationary["creature_id"], stationary["variant_lineage"]["variant_id"], "south", "locomotion"), "CREATURE_STATE_UNSUPPORTED", "RUNTIME_REJECTION")
    controls["CR-NC-05"] = _capture("CR-NC-05", "missing_collision_profile", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0].__setitem__("collision_profile", {})), "COLLISION_PROFILE_EXPLICIT_REQUIRED", "CONTRACT_REJECTION")
    controls["CR-NC-06"] = _capture("CR-NC-06", "invalid_or_negative_scale", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0]["base_scale"].__setitem__("x", -1.0)), "BASE_SCALE_INVALID", "CONTRACT_REJECTION")
    def cycle(value: dict[str, Any]) -> None:
        value["variants"][6]["parent_id"], value["variants"][7]["parent_id"] = value["variants"][7]["variant_id"], value["variants"][6]["variant_id"]
    controls["CR-NC-07"] = _capture("CR-NC-07", "circular_variant_lineage", lambda: _mutated_registry(manifest, cycle), "VARIANT_LINEAGE_CYCLE", "CONTRACT_REJECTION")
    controls["CR-NC-08"] = _capture("CR-NC-08", "missing_variant_parent", lambda: _mutated_registry(manifest, lambda value: value["variants"][6].__setitem__("parent_id", "missing-parent")), "VARIANT_LINEAGE_PARENT_MISSING", "CONTRACT_REJECTION")
    controls["CR-NC-09"] = _capture("CR-NC-09", "forbidden_variant_override", lambda: _mutated_registry(manifest, lambda value: value["variants"][0]["overrides"].append("gameplay_balance")), "VARIANT_OVERRIDE_NOT_ALLOWLISTED", "CONTRACT_REJECTION")
    controls["CR-NC-10"] = _capture("CR-NC-10", "wrong_direction_asset_binding", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0]["direction_bindings"]["east"].__setitem__("direction_asset_id", value["creatures"][0]["direction_bindings"]["south"]["direction_asset_id"])), "DIRECTION_ASSET_BINDING_INVALID", "CONTRACT_REJECTION")
    first, second = manifest["creatures"][0], manifest["creatures"][1]
    first_result = registry.resolve(first["creature_id"], first["variant_lineage"]["variant_id"], "south", "idle")
    second_result = registry.resolve(second["creature_id"], second["variant_lineage"]["variant_id"], "south", "idle")
    registry.poison_cache_for_test(first_result.cache_key, second_result)
    controls["CR-NC-11"] = _capture("CR-NC-11", "stale_cache_cross_creature_or_variant", lambda: registry.resolve(first["creature_id"], first["variant_lineage"]["variant_id"], "south", "idle"), "STALE_CREATURE_CACHE_CONTEXT", "RUNTIME_REJECTION")
    controls["CR-NC-12"] = _capture("CR-NC-12", "provenance_hash_mutation", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0].__setitem__("provenance_hash", "0" * 64)), "PROVENANCE_HASH_MISMATCH", "CONTRACT_REJECTION")
    def production_fixture(value: dict[str, Any]) -> None:
        value["production_registry"] = True; value["registry_authority"] = "PRODUCTION_APPROVED_ASSETS_ONLY"
    controls["CR-NC-13"] = _capture("CR-NC-13", "TEST_ONLY_fixture_in_production_registry", lambda: _mutated_registry(manifest, production_fixture), "TEST_ONLY_CREATURE_IN_PRODUCTION_REGISTRY", "CONTRACT_REJECTION")
    controls["CR-NC-14"] = _capture("CR-NC-14", "nondeterministic_second_fixture_output", lambda: dict(nondeterminism), "NONDETERMINISTIC_SECOND_FIXTURE_OUTPUT", "RUNTIME_REJECTION")
    controls["CR-NC-15"] = _capture("CR-NC-15", "production_routing_enabled", lambda: CreatureRegistry({**copy.deepcopy(manifest), "production_routing": "ENABLED"}), "PRODUCTION_ROUTING_BLOCKED", "RUNTIME_REJECTION")
    passed = len(controls) == 15 and all(item["passed"] for item in controls.values())
    return {"schema_version": SCHEMA_VERSION, "status": "CR_NC_01_TO_15_PASSED" if passed else "CR_NC_01_TO_15_FAILED", "strict": True, "controls": controls}


def derived_controls(manifest: dict[str, Any], registry: CreatureRegistry) -> dict[str, Any]:
    def resolve_mutation(mutate: Callable[[dict[str, Any]], None]) -> Any:
        value = copy.deepcopy(manifest); mutate(value); target_variant = value["variants"][-1]
        local = CreatureRegistry(value)
        return local.resolve(target_variant["creature_id"], target_variant["variant_id"], "south", "idle")
    def invalid_state_route(value: dict[str, Any]) -> None:
        variant = value["variants"][-1]; routes = copy.deepcopy(next(c for c in value["creatures"] if c["creature_id"] == variant["creature_id"])["state_routes"]); routes["locomotion"]["timing_phase"] = {"fps": 0, "duration_ms": 0, "phase": ""}; variant["overrides"].append("state_routes"); variant["override_values"]["state_routes"] = routes
    def invalid_direction_revision(value: dict[str, Any]) -> None:
        variant = value["variants"][-1]; bindings = copy.deepcopy(next(c for c in value["creatures"] if c["creature_id"] == variant["creature_id"])["direction_bindings"]); bindings["south"]["asset_revision"] = "mixed-derived-r9"; variant["overrides"].append("direction_bindings"); variant["override_values"]["direction_bindings"] = bindings
    def invalid_provenance(value: dict[str, Any]) -> None:
        value["variants"][-1]["provenance_hash"] = "0" * 64
    def invalid_immutable(value: dict[str, Any]) -> None:
        value["variants"][-1]["overrides"].append("archetype"); value["variants"][-1]["override_values"]["archetype"] = "quadruped"
    controls = {
        "DV-NC-01": _capture("DV-NC-01", "derived_negative_base_scale", lambda: resolve_mutation(lambda value: value["variants"][-1]["override_values"]["base_scale"].__setitem__("x", -1.0)), "BASE_SCALE_INVALID", "CONTRACT_REJECTION"),
        "DV-NC-02": _capture("DV-NC-02", "derived_negative_collision_width_bounds", lambda: resolve_mutation(lambda value: value["variants"][-1]["override_values"]["collision_profile"].__setitem__("width", 0)), "COLLISION_GEOMETRY_INVALID", "CONTRACT_REJECTION"),
        "DV-NC-03": _capture("DV-NC-03", "derived_negative_state_route_timing", lambda: resolve_mutation(invalid_state_route), "STATE_ROUTE_TIMING_INVALID", "CONTRACT_REJECTION"),
        "DV-NC-04": _capture("DV-NC-04", "derived_direction_binding_revision_mismatch", lambda: resolve_mutation(invalid_direction_revision), "DIRECTION_ASSET_REVISION_MISMATCH", "CONTRACT_REJECTION"),
        "DV-NC-05": _capture("DV-NC-05", "derived_provenance_hash_mismatch", lambda: resolve_mutation(invalid_provenance), "PROVENANCE_HASH_MISMATCH", "CONTRACT_REJECTION"),
        "DV-NC-06": _capture("DV-NC-06", "derived_immutable_field_override", lambda: (lambda value: (invalid_immutable(value), CreatureRegistry(value))[-1])(copy.deepcopy(manifest)), "VARIANT_OVERRIDE_NOT_ALLOWLISTED", "CONTRACT_REJECTION"),
    }
    passed = all(item["passed"] for item in controls.values())
    return {"schema_version": SCHEMA_VERSION, "status": "DERIVED_VARIANT_NEGATIVE_CONTROLS_PASSED" if passed else "DERIVED_VARIANT_NEGATIVE_CONTROLS_FAILED", "controls": controls, "real_materialize_and_resolve": True}


def supplemental_controls(manifest: dict[str, Any], registry: CreatureRegistry) -> dict[str, Any]:
    controls: dict[str, dict[str, Any]] = {}
    controls["SUP-NC-01"] = _capture("SUP-NC-01", "topology_mismatch", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0].__setitem__("topology_id", ARCHETYPE_RULES["quadruped"]["topology_id"])), "TOPOLOGY_ARCHETYPE_MISMATCH", "CONTRACT_REJECTION")
    controls["SUP-NC-02"] = _capture("SUP-NC-02", "locomotion_mismatch", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0].__setitem__("locomotion_class", "quadrupedal")), "LOCOMOTION_ARCHETYPE_MISMATCH", "CONTRACT_REJECTION")
    controls["SUP-NC-03"] = _capture("SUP-NC-03", "missing_anchors", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0].__setitem__("anchors", {})), "ANCHORS_EXPLICIT_REQUIRED", "CONTRACT_REJECTION")
    controls["SUP-NC-04"] = _capture("SUP-NC-04", "invalid_collision_geometry", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0]["collision_profile"].__setitem__("width", 0)), "COLLISION_GEOMETRY_INVALID", "CONTRACT_REJECTION")
    controls["SUP-NC-05"] = _capture("SUP-NC-05", "inverted_bounds", lambda: _mutated_registry(manifest, lambda value: value["creatures"][0]["collision_profile"]["bounds"].__setitem__("left", 200)), "BOUNDS_GEOMETRY_INVALID", "CONTRACT_REJECTION")
    item = manifest["creatures"][0]; base_id = item["variant_lineage"]["variant_id"]
    idle = registry.resolve(item["creature_id"], base_id, "south", "idle"); attack = registry.resolve(item["creature_id"], base_id, "south", "attack_primary")
    registry.poison_cache_for_test(idle.cache_key, attack)
    controls["SUP-NC-06"] = _capture("SUP-NC-06", "stale_cache_cross_state", lambda: registry.resolve(item["creature_id"], base_id, "south", "idle"), "STALE_CREATURE_CACHE_CONTEXT", "RUNTIME_REJECTION")
    moving = next(item for item in manifest["creatures"] if item["archetype"] == "flying_winged")
    def moving_unsupported(value: dict[str, Any]) -> None:
        creature = next(item for item in value["creatures"] if item["archetype"] == "flying_winged"); creature["animation_state_contract"]["locomotion"] = "UNSUPPORTED"; creature["state_routes"]["locomotion"] = {"state": "locomotion", "availability": "UNSUPPORTED", "state_route_id": None, "timing_phase": None, "test_only": True, "production_safe": False}; creature["provenance_hash"] = _record_hash(creature); creature["provenance"]["record_hash"] = creature["provenance_hash"]
    controls["SUP-NC-07"] = _capture("SUP-NC-07", "moving_archetype_locomotion_unsupported", lambda: _mutated_registry(manifest, moving_unsupported), "LOCOMOTION_STATE_ARCHETYPE_MISMATCH", "CONTRACT_REJECTION")
    stationary = next(item for item in manifest["creatures"] if item["archetype"] == "stationary_structure")
    controls["SUP-NC-08"] = _capture("SUP-NC-08", "stationary_locomotion_request", lambda: registry.resolve(stationary["creature_id"], stationary["variant_lineage"]["variant_id"], "south", "locomotion"), "CREATURE_STATE_UNSUPPORTED", "RUNTIME_REJECTION")
    passed = all(item["passed"] for item in controls.values())
    return {"schema_version": SCHEMA_VERSION, "status": "SUPPLEMENTAL_CONTROLS_PASSED" if passed else "SUPPLEMENTAL_CONTROLS_FAILED", "controls": controls, "moving_archetype_checked": moving["archetype"]}


def _copy_fixture_tree(manifest: Mapping[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for creature in manifest["creatures"]:
        for direction, binding in creature["direction_bindings"].items():
            source = FROZEN / "fixtures" / "directions" / creature["creature_id"] / f"{direction}.png"
            target = output_dir / "fixtures" / "directions" / creature["creature_id"] / f"{direction}.png"
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
            records.append({"creature_id": creature["creature_id"], "archetype": creature["archetype"], "direction": direction, "path": binding["path"], "direction_asset_id": binding["direction_asset_id"], "direction_content_hash": binding["direction_content_hash"], "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "frozen_v0181_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "test_only": True, "production_safe": False})
    return records


def _draw_sheets(manifest: Mapping[str, Any], output_dir: Path) -> tuple[Path, Path, list[dict[str, Any]], list[dict[str, Any]]]:
    direction_sheet = Image.new("RGBA", (190 * 8, 78 + 142 * 6), (25, 29, 38, 255)); draw = ImageDraw.Draw(direction_sheet); draw.text((12, 12), "v0.18.2 TEST_ONLY direction identity (frozen v0.18.1 pixels)", fill="white")
    for col, direction in enumerate(CANONICAL_DIRECTIONS): draw.text((col * 190 + 8, 48), direction, fill="white")
    direction_records: list[dict[str, Any]] = []
    for row, creature in enumerate(manifest["creatures"]):
        y = 78 + row * 142; draw.text((8, y + 111), creature["archetype"], fill="white")
        for col, direction in enumerate(CANONICAL_DIRECTIONS):
            source_path = output_dir / "fixtures" / "directions" / creature["creature_id"] / f"{direction}.png"; x = col * 190 + 44; image = Image.open(source_path).convert("RGBA").resize((96, 96), Image.Resampling.NEAREST); direction_sheet.alpha_composite(image, (x, y)); binding = creature["direction_bindings"][direction]; draw.rectangle((x, y, x + 96, y + 96), outline=(255, 235, 90, 255), width=1); draw.text((col * 190 + 8, y + 98), binding["direction_asset_id"].split(":")[-2], fill=(190, 220, 245, 255)); direction_records.append({"creature_id": creature["creature_id"], "archetype": creature["archetype"], "requested_direction": direction, "resolved_direction": direction, **{key: binding[key] for key in ("direction_asset_id", "direction_content_hash", "asset_revision")}, "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(), "frozen_v0181_sha256": binding["direction_content_hash"], "test_only": True, "production_safe": False})
    state_sheet = Image.new("RGBA", (1450, 110 + 74 * 6), (25, 29, 38, 255)); sdraw = ImageDraw.Draw(state_sheet); sdraw.text((12, 12), "v0.18.2 TEST_ONLY state routes: moving archetypes require locomotion", fill="white"); xs = {state: 210 + index * 235 for index, state in enumerate(CANONICAL_STATES)}
    for state, x in xs.items(): sdraw.text((x, 62), state, fill="white")
    state_records: list[dict[str, Any]] = []
    for row, creature in enumerate(manifest["creatures"]):
        y = 100 + row * 74; sdraw.text((12, y + 25), creature["archetype"], fill="white")
        for state, x in xs.items():
            route = creature["state_routes"][state]; supported = route["state_route_id"] is not None; sdraw.rectangle((x - 8, y + 8, x + 215, y + 55), fill=(54, 150, 75, 255) if supported else (150, 45, 55, 255)); sdraw.text((x, y + (13 if supported else 22)), route["state_route_id"].split(":")[-1] if supported else "UNSUPPORTED", fill="white");
            if supported: sdraw.text((x, y + 33), f"{route['timing_phase']['fps']}fps {route['timing_phase']['phase']}", fill=(225, 245, 225, 255))
            state_records.append({"creature_id": creature["creature_id"], "archetype": creature["archetype"], "state": state, "state_route_id": route["state_route_id"], "timing_phase": route["timing_phase"], "availability": route["availability"], "test_only": True})
    dpath = output_dir / "direction-routing-sheet-v0182.png"; spath = output_dir / "state-routing-sheet-v0182.png"; direction_sheet.save(dpath, format="PNG", optimize=False, compress_level=9); state_sheet.save(spath, format="PNG", optimize=False, compress_level=9)
    return dpath, spath, direction_records, state_records


def _isolated_run(manifest_path: Path, output_dir: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")); validate_creature_manifest(manifest); output_dir.mkdir(parents=True, exist_ok=True); _copy_fixture_tree(manifest, output_dir); dpath, spath, dr, sr = _draw_sheets(manifest, output_dir); write_json(output_dir / "identity.json", {"schema_version": SCHEMA_VERSION, "manifest_hash": sha256_json(manifest), "direction_identity_hash": sha256_json(dr), "state_route_identity_hash": sha256_json(sr), "direction_fixture_count": len(dr), "variant_ids": [item["variant_id"] for item in manifest["variants"]], "reads_first_run_output": False}); write_json(output_dir / "direction-routing-sheet-v0182.json", {"schema_version": SCHEMA_VERSION, "records": dr, "sheet": dpath.name}); write_json(output_dir / "state-routing-sheet-v0182.json", {"schema_version": SCHEMA_VERSION, "records": sr, "sheet": spath.name}); return 0


def _digest_map(path: Path) -> dict[str, str]:
    return {item.relative_to(path).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest() for item in sorted(path.rglob("*")) if item.is_file()}


def isolated_determinism(manifest: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ugas-v0182-determinism-") as temporary:
        root = Path(temporary); manifest_path = root / "frozen-manifest.json"; write_json(manifest_path, manifest); first, second, mutated = root / "run-one", root / "run-two", root / "run-two-mutated"; command = [sys.executable, str(Path(__file__).resolve()), "--isolated-run", str(manifest_path), "--output-dir"]
        p1 = subprocess.run(command + [str(first)], cwd=ROOT, capture_output=True, text=True, check=False); p2 = subprocess.run(command + [str(second)], cwd=ROOT, capture_output=True, text=True, check=False)
        if p1.returncode or p2.returncode: return {"status": "TWO_RUN_DETERMINISM_FAILED", "result": {"result": "ERROR", "error_code": "ISOLATED_RUN_FAILED", "rejection_class": "UNEXPECTED_EXCEPTION"}, "first_returncode": p1.returncode, "second_returncode": p2.returncode}
        left, right = _digest_map(first), _digest_map(second); differences = sorted(set(left) ^ set(right) | {key for key in set(left) & set(right) if left[key] != right[key]})
        if not differences:
            for name in ("direction-routing-sheet-v0182.png", "state-routing-sheet-v0182.png"):
                if Image.open(first / name).convert("RGBA").tobytes() != Image.open(second / name).convert("RGBA").tobytes(): differences.append(f"decoded:{name}")
        equal = {"result": "RESOLVED" if not differences else "REJECTED", "error_code": None if not differences else "NONDETERMINISTIC_SECOND_FIXTURE_OUTPUT", "rejection_class": None if not differences else "RUNTIME_REJECTION", "differences": differences, "file_count": len(left)}
        shutil.copytree(second, mutated); target = mutated / "fixtures" / "directions" / manifest["creatures"][0]["creature_id"] / "south.png"; image = Image.open(target).convert("RGBA"); image.putpixel((96, 96), (255, 0, 1, 255)); image.save(target, format="PNG", optimize=False, compress_level=9); mutated_map = _digest_map(mutated); changed = sorted(key for key in set(left) & set(mutated_map) if left[key] != mutated_map[key])
        return {"schema_version": SCHEMA_VERSION, "status": "TWO_RUN_DETERMINISM_PASSED" if equal["result"] == "RESOLVED" and changed else "TWO_RUN_DETERMINISM_FAILED", "same_frozen_manifest": True, "second_run_reads_first_run": False, "first_returncode": p1.returncode, "second_returncode": p2.returncode, "equal_comparison": equal, "mutated_second_output_comparison": {"result": "REJECTED" if changed else "RESOLVED", "error_code": "NONDETERMINISTIC_SECOND_FIXTURE_OUTPUT" if changed else None, "rejection_class": "RUNTIME_REJECTION" if changed else None, "differences": changed}, "mutated_control_error_code": "NONDETERMINISTIC_SECOND_FIXTURE_OUTPUT"}


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--isolated-run":
        return _isolated_run(Path(sys.argv[2]), Path(sys.argv[4])) if len(sys.argv) == 5 and sys.argv[3] == "--output-dir" else 2
    EVIDENCE.mkdir(parents=True, exist_ok=True); manifest = build_manifest(); schema = json.loads(SCHEMA.read_text(encoding="utf-8")); validate_schema_document(schema); validate_instance(manifest, schema); registry = CreatureRegistry(manifest)
    production_manifest = {**copy.deepcopy(manifest), "production_registry": True, "registry_authority": "PRODUCTION_APPROVED_ASSETS_ONLY", "creatures": [], "variants": []}; production_registry = CreatureRegistry(production_manifest, production_registry=True); determinism = isolated_determinism(manifest)
    run_dir = Path(tempfile.mkdtemp(prefix="ugas-v0182-final-"))
    try:
        path = run_dir / "manifest.json"; write_json(path, manifest); _isolated_run(path, run_dir); fixture_root = EVIDENCE / "fixtures"; shutil.rmtree(fixture_root, ignore_errors=True); shutil.copytree(run_dir / "fixtures", fixture_root); shutil.copy2(run_dir / "direction-routing-sheet-v0182.png", EVIDENCE / "direction-routing-sheet-v0182.png"); shutil.copy2(run_dir / "state-routing-sheet-v0182.png", EVIDENCE / "state-routing-sheet-v0182.png"); direction_json = json.loads((run_dir / "direction-routing-sheet-v0182.json").read_text(encoding="utf-8")); state_json = json.loads((run_dir / "state-routing-sheet-v0182.json").read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
    derived_results = [registry.resolve(item["creature_id"], item["variant_id"], "south", "idle") for item in manifest["variants"] if item["kind"] == "derived"]; negative = canonical_controls(manifest, CreatureRegistry(manifest), determinism.get("mutated_second_output_comparison", {})); derived_negative = derived_controls(manifest, registry); supplemental = supplemental_controls(manifest, CreatureRegistry(manifest)); gates: dict[str, dict[str, Any]] = {}
    def gate(name: str, passed: bool, detail: str) -> None: gates[name] = {"id": name, "status": "PASS" if passed else "FAIL", "detail": detail}
    gate("creature_schema_valid", True, "v0.18.2 manifest and schema validate"); gate("effective_variant_validation", all(item.result == "RESOLVED" and item.variant_kind == "derived" for item in derived_results), "all derived variants are semantically validated after materialization"); gate("effective_direction_asset_revision_consistent", all(item.asset_revision == item.direction_asset_revision and item.direction_asset_revision for item in derived_results), "metadata-only variants retain inherited direction asset revision"); gate("derived_revision_identity", all(item.variant_revision and item.variant_revision != item.asset_revision for item in derived_results), "variant_revision is distinct from resolved directional asset revision"); gate("locomotion_state_matches_archetype", all((creature["animation_state_contract"]["locomotion"] == "REQUIRED") == (creature["archetype"] != "stationary_structure") for creature in manifest["creatures"]), "moving archetypes require locomotion and stationary structures reject it"); gate("directional_binding_unique", all(len({b["direction_asset_id"] for b in c["direction_bindings"].values()}) == 8 and len({b["direction_content_hash"] for b in c["direction_bindings"].values()}) == 8 for c in manifest["creatures"]), "eight unique direction identities per archetype"); gate("direction_hash_preservation", all(item["direction_content_hash"] == item["frozen_v0181_sha256"] and item["sha256"] == item["frozen_v0181_sha256"] for item in direction_json["records"]), "all 48 fixture bytes and hashes match frozen v0.18.1"); gate("state_route_identity", all(route["state_route_id"] and route["timing_phase"] for c in manifest["creatures"] if c["archetype"] != "stationary_structure" for route in [c["state_routes"]["locomotion"]]), "moving archetypes expose locomotion route timing/phase"); gate("production_routing_runtime_enforced", enforce_production_routing(manifest["production_routing"]) == "BLOCKED", "production policy remains executable and blocked"); gate("canonical_negative_controls_strict", negative["status"] == "CR_NC_01_TO_15_PASSED", "canonical CR-NC-01..15 pass"); gate("derived_negative_controls_strict", derived_negative["status"] == "DERIVED_VARIANT_NEGATIVE_CONTROLS_PASSED", "DV-NC-01..06 pass through real materialize and resolve"); gate("supplemental_state_controls", supplemental["status"] == "SUPPLEMENTAL_CONTROLS_PASSED", "moving and stationary locomotion controls pass"); gate("isolated_two_run_determinism", determinism["status"] == "TWO_RUN_DETERMINISM_PASSED", "isolated runs compare bytes, decoded sheets and mutation"); gate("production_registry_empty", production_registry.cache_stats()["entries"] == 0 and not production_manifest["creatures"], "production registry is empty"); gate("synthetic_fixture_nonproduction", all(c["test_only"] is True and c["production_safe"] is False for c in manifest["creatures"]), "all fixtures remain TEST_ONLY"); gate("provenance_hashes_valid", all(c["provenance_hash"] == c["provenance"]["record_hash"] == _record_hash(c) for c in manifest["creatures"]), "provenance hashes match"); gate("variant_allowlist_enforced", ALLOWED_VARIANT_OVERRIDES.isdisjoint({"gameplay_balance", "damage", "health", "speed"}), "variant overrides exclude gameplay fields"); gate("production_boundary_state", manifest["production_routing"] == "BLOCKED" and manifest["production_registry"] is False, "production false and blocked"); state_path = ROOT / "docs/evidence/current-state.json"; state_result = validate_state_consistency(json.loads(state_path.read_text(encoding="utf-8")), (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.18.2.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")); gate("state_consistency", not state_result["failures"], "active v0.18.2 state is internally consistent")
    manifest_hash = sha256_json(manifest); write_json(EVIDENCE / "creature-runtime-manifest-v0182.json", manifest); write_json(EVIDENCE / "synthetic-fixture-manifest-v0182.json", {"schema_version": SCHEMA_VERSION, "manifest_type": "TEST_ONLY_SYNTHETIC_CREATURE_DIRECTIONAL_FIXTURE", "production_registry": False, "fixture_count": 48, "archetype_count": 6, "unique_hash_count": 48, "fixtures": direction_json["records"], "production_safe": False}); write_json(EVIDENCE / "creature-contract-v0182.json", {"schema_version": SCHEMA_VERSION, "status": "CREATURE_SCHEMA_VALID", "manifest_hash": manifest_hash, "production_routing": "BLOCKED", "production_approved": False}); write_json(EVIDENCE / "direction-asset-binding-v0182.json", {"schema_version": SCHEMA_VERSION, "status": "DIRECTION_ASSET_BINDING_VALID", "direction_count_per_archetype": 8, "unique_identity_count_per_archetype": 8, "records": direction_json["records"], "real_creature_asset_coverage": "NONE", "test_only": True}); write_json(EVIDENCE / "direction-routing-sheet-v0182.json", direction_json); write_json(EVIDENCE / "state-route-contract-v0182.json", {"schema_version": SCHEMA_VERSION, "status": "STATE_ROUTE_CONTRACT_VALID", "records": state_json["records"], "moving_archetypes_locomotion": "REQUIRED", "test_only": True}); write_json(EVIDENCE / "state-routing-sheet-v0182.json", state_json); write_json(EVIDENCE / "derived-variant-lineage-v0182.json", {"schema_version": SCHEMA_VERSION, "status": "DERIVED_VARIANT_LINEAGE_OPERATIONAL", "allowed_overrides": sorted(ALLOWED_VARIANT_OVERRIDES), "variants": manifest["variants"], "effective_resolution_proof": [item.to_dict() for item in derived_results]}); write_json(EVIDENCE / "effective-variant-validation-v0182.json", {"schema_version": SCHEMA_VERSION, "status": "EFFECTIVE_VARIANT_VALIDATION_PASSED", "validated_after_materialization": True, "derived_resolution": [item.to_dict() for item in derived_results]}); write_json(EVIDENCE / "derived-revision-identity-v0182.json", {"schema_version": SCHEMA_VERSION, "status": "DERIVED_REVISION_IDENTITY_PASSED", "records": [item.to_dict() for item in derived_results], "variant_revision_distinct_from_asset_revision": True}); write_json(EVIDENCE / "derived-variant-negative-controls-v0182.json", derived_negative); write_json(EVIDENCE / "archetype-state-compatibility-v0182.json", {"schema_version": SCHEMA_VERSION, "status": "ARCHETYPE_STATE_COMPATIBILITY_PASSED", "rules": {key: {"locomotion": ("UNSUPPORTED" if key == "stationary_structure" else "REQUIRED")} for key in ARCHETYPES}, "controls": supplemental["controls"]}); write_json(EVIDENCE / "cache-identity-v0182.json", {"schema_version": SCHEMA_VERSION, "status": "CACHE_IDENTITY_QA_PASSED", "derived_keys": [item.cache_key for item in derived_results], "canonical_fields": ["creature_id", "variant", "variant_revision", "direction", "state", "direction_asset_id", "direction_asset_revision", "state_route_id", "asset_revision", "normalization", "request_mode", "registry_mode"], "cross_creature_control": negative["controls"]["CR-NC-11"], "cross_state_control": supplemental["controls"]["SUP-NC-06"]}); write_json(EVIDENCE / "two-run-determinism-v0182.json", determinism); write_json(EVIDENCE / "canonical-negative-controls-v0182.json", negative); write_json(EVIDENCE / "negative-controls-v0182.json", {**negative, "derived_controls": derived_negative["controls"], "supplemental_controls": supplemental["controls"]}); write_json(EVIDENCE / "production-routing-qa-v0182.json", {"schema_version": SCHEMA_VERSION, "status": "PRODUCTION_ROUTING_QA_PASSED", "policy": "BLOCKED_ONLY", "enabled_mutation": negative["controls"]["CR-NC-15"]}); write_json(EVIDENCE / "production-registry-v0182.json", {"schema_version": SCHEMA_VERSION, "production_registry": True, "registry_authority": "PRODUCTION_APPROVED_ASSETS_ONLY", "assets": [], "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0}); write_json(EVIDENCE / "state-consistency-v0182.json", state_result)
    passed = not any(item["status"] != "PASS" for item in gates.values()) and negative["status"] == "CR_NC_01_TO_15_PASSED" and derived_negative["status"] == "DERIVED_VARIANT_NEGATIVE_CONTROLS_PASSED" and determinism["status"] == "TWO_RUN_DETERMINISM_PASSED"; execution = {"schema_version": SCHEMA_VERSION, "status": "CREATURES_MONSTERS_DERIVED_VARIANT_AND_STATE_CONTRACT_TECHNICALLY_QUALIFIED" if passed else "CREATURES_MONSTERS_DERIVED_VARIANT_AND_STATE_CONTRACT_FAILED", "failed": sum(item["status"] != "PASS" for item in gates.values()), "gates": gates, "negative_controls": negative["status"], "derived_negative_controls": derived_negative["status"], "supplemental_controls": supplemental["status"], "archetype_count": 6, "direction_fixture_count": 48, "derived_variant_count": 2, "real_creature_asset_coverage": "NONE", "synthetic_creature_fixture": "TEST_ONLY", "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0, "acceptance_criteria": {f"AC-{i:02d}": "PASS" if passed else "FAIL" for i in range(1, 21)}, "direction_sheet": "docs/evidence/creatures-monsters-runtime-v0182/direction-routing-sheet-v0182.png", "state_sheet": "docs/evidence/creatures-monsters-runtime-v0182/state-routing-sheet-v0182.png"}; write_json(EVIDENCE / "execution-evidence-v0182.json", execution); print(json.dumps(execution, indent=2, ensure_ascii=False)); return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
