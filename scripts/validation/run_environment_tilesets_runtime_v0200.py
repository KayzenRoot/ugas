"""Execute the complete v0.20.0 environment/tilesets foundation slice."""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.environment_tileset_runtime_v0200 import (  # noqa: E402
    CARDINAL_ONLY,
    EIGHT_NEIGHBOR,
    EnvironmentTileRegistry,
    EnvironmentTileResolver,
    EnvironmentTilesetContractError,
    NEIGHBOR_BITS,
    ResolverRequest,
    SCHEMA_VERSION,
    TILE_CLASSES,
    compare_generated_outputs,
    compare_seam_bytes,
    encode_adjacency_mask,
    generate_fixture_pack,
    validate_grid_roundtrip,
    validate_tileset_manifest,
    write_json,
)
from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402


EVIDENCE = ROOT / "docs/evidence/environment-tilesets-runtime-v0200"
GATE_NAMES = (
    "tileset_schema_valid",
    "tile_metrics_valid",
    "grid_conversion_roundtrip_valid",
    "layer_contract_valid",
    "atlas_rects_in_bounds_and_nonoverlapping",
    "standalone_tile_bytes_hash_verified",
    "atlas_region_matches_tile_bytes",
    "adjacency_mask_encoding_deterministic",
    "required_autotile_variant_present",
    "edge_signatures_match_bytes",
    "seam_compatibility_verified",
    "collision_navigation_contract_valid",
    "items_props_boundary_not_duplicated",
    "variant_lineage_acyclic_and_revalidated",
    "cache_identity_complete",
    "stale_cache_cross_mask_tileset_layer_rejected",
    "provenance_hash_matches_manifest",
    "test_fixture_nonproduction",
    "production_registry_empty",
    "production_routing_blocked",
    "isolated_full_slice_determinism",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _expect_rejection(name: str, expected: str, operation: Callable[[], Any]) -> dict[str, Any]:
    try:
        operation()
    except EnvironmentTilesetContractError as exc:
        return {"control": name, "expected_rejection_class": expected, "observed_rejection_class": exc.rejection_class, "status": "PASS" if exc.rejection_class == expected else "FAIL", "detail": exc.detail}
    except Exception as exc:  # The control must be rejected by the semantic runtime, not an accidental exception.
        return {"control": name, "expected_rejection_class": expected, "observed_rejection_class": type(exc).__name__, "status": "FAIL", "detail": str(exc)}
    return {"control": name, "expected_rejection_class": expected, "observed_rejection_class": None, "status": "FAIL", "detail": "mutation was accepted"}


def _generate_subprocess(output: Path) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + environment.get("PYTHONPATH", "")
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--generate", str(output)], cwd=ROOT, env=environment, capture_output=True, text=True, check=False, timeout=120)
    if result.returncode != 0:
        raise RuntimeError((result.stdout + result.stderr)[-4000:])
    return _load(output / "tileset-manifest-v0200.json")


def _mutated_png(source: Path, target: Path) -> None:
    data = bytearray(source.read_bytes())
    # Mutate a byte in the IDAT payload while retaining a file that Pillow can
    # decode: use a tiny deterministic re-encode instead of corrupting PNG CRC.
    from PIL import Image

    with Image.open(source) as image:
        changed = image.convert("RGBA")
        pixel = changed.getpixel((changed.width - 1, changed.height - 1))
        changed.putpixel((changed.width - 1, changed.height - 1), ((pixel[0] + 1) % 256, pixel[1], pixel[2], pixel[3]))
        changed.save(target, format="PNG", optimize=False, compress_level=9)
    if target.read_bytes() == bytes(data):
        raise RuntimeError("mutation did not change PNG bytes")


def _run_negative_controls(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    def invalid(value: dict[str, Any], expected: str) -> Callable[[], Any]:
        return lambda: validate_tileset_manifest(root, value)

    value = copy.deepcopy(manifest); value["metrics"]["tile_width"] = 0
    controls.append(_expect_rejection("ET-NC-01", "INVALID_TILE_METRICS", invalid(value, "INVALID_TILE_METRICS")))
    value = copy.deepcopy(manifest); value["tiles"][1]["tile_id"] = value["tiles"][0]["tile_id"]
    controls.append(_expect_rejection("ET-NC-02", "DUPLICATE_TILE_ID", invalid(value, "DUPLICATE_TILE_ID")))
    value = copy.deepcopy(manifest); value["tiles"][0]["binding"]["atlas_rect"]["x"] = 95
    controls.append(_expect_rejection("ET-NC-03", "ATLAS_RECT_OUT_OF_BOUNDS", invalid(value, "ATLAS_RECT_OUT_OF_BOUNDS")))
    value = copy.deepcopy(manifest); value["tiles"][1]["binding"]["atlas_rect"] = copy.deepcopy(value["tiles"][0]["binding"]["atlas_rect"])
    controls.append(_expect_rejection("ET-NC-04", "ATLAS_RECT_OVERLAP", invalid(value, "ATLAS_RECT_OVERLAP")))
    value = copy.deepcopy(manifest); value["tiles"][0]["primary_layer"] = "unknown_layer"
    controls.append(_expect_rejection("ET-NC-05", "INVALID_LAYER_ROLE", invalid(value, "INVALID_LAYER_ROLE")))
    controls.append(_expect_rejection("ET-NC-06", "UNKNOWN_NEIGHBOR_DIRECTION", lambda: encode_adjacency_mask({"N": True, "Q": True}, CARDINAL_ONLY)))
    value = copy.deepcopy(manifest); value["terrain_families"][0]["autotile_variants"] = []
    controls.append(_expect_rejection("ET-NC-07", "REQUIRED_AUTOTILE_VARIANT_MISSING", invalid(value, "REQUIRED_AUTOTILE_VARIANT_MISSING")))
    value = copy.deepcopy(manifest); value["tiles"][0]["edge_signatures"]["N"] = "tampered"
    controls.append(_expect_rejection("ET-NC-08", "EDGE_SIGNATURE_MISMATCH", invalid(value, "EDGE_SIGNATURE_MISMATCH")))
    with tempfile.TemporaryDirectory(prefix="ugas-et-nc09-") as directory:
        mutated = Path(directory) / "mutated.png"
        source = root / manifest["tiles"][0]["binding"]["artifact_path"]
        _mutated_png(source, mutated)
        right = root / manifest["tiles"][1]["binding"]["artifact_path"]
        controls.append(_expect_rejection("ET-NC-09", "SEAM_INCOMPATIBLE", lambda: compare_seam_bytes(mutated, right, "E")))
    value = copy.deepcopy(manifest); value["tiles"][0]["collision_navigation"]["blocked"] = True
    controls.append(_expect_rejection("ET-NC-10", "COLLISION_NAVIGATION_CONTRADICTION", invalid(value, "COLLISION_NAVIGATION_CONTRADICTION")))
    resolver = EnvironmentTileResolver(manifest, root)
    unsupported = ResolverRequest(manifest["tileset_id"], "temperate_cardinal", manifest["tiles"][0]["tile_id"], "ground_base", CARDINAL_ONLY, {"N": True, "E": True, "S": True, "W": True})
    controls.append(_expect_rejection("ET-NC-11", "UNSUPPORTED_TRANSITION", lambda: resolver.resolve(unsupported)))
    valid_request = ResolverRequest(manifest["tileset_id"], "temperate_cardinal", manifest["tiles"][0]["tile_id"], "ground_base", CARDINAL_ONLY, {"N": True})
    cached = resolver.resolve(valid_request)
    stale = dict(cached); stale["adjacency_mask"] = 0
    controls.append(_expect_rejection("ET-NC-12", "STALE_CACHE_CROSS_IDENTITY", lambda: resolver.get_cached(stale)))
    value = copy.deepcopy(manifest); value["variants"][0]["variant_revision"] = value["variants"][0]["atlas_revision"]
    controls.append(_expect_rejection("ET-NC-13", "VARIANT_REVISION_INVALID", invalid(value, "VARIANT_REVISION_INVALID")))
    value = copy.deepcopy(manifest); value["tiles"][0]["provenance_hash"] = "tampered"
    controls.append(_expect_rejection("ET-NC-14", "PROVENANCE_HASH_MISMATCH", invalid(value, "PROVENANCE_HASH_MISMATCH")))
    production_registry = EnvironmentTileRegistry(production=True)
    controls.append(_expect_rejection("ET-NC-15", "TEST_FIXTURE_IN_PRODUCTION_REGISTRY", lambda: production_registry.register(manifest)))
    with tempfile.TemporaryDirectory(prefix="ugas-et-nc16-") as first_dir, tempfile.TemporaryDirectory(prefix="ugas-et-nc16b-") as second_dir:
        first, second = Path(first_dir), Path(second_dir)
        _generate_subprocess(first); _generate_subprocess(second)
        _mutated_png(second / manifest["tiles"][0]["binding"]["artifact_path"], second / "mutated-tile.png")
        # Replace the actual path after mutation so the semantic file-set comparator observes it.
        mutated_path = second / "mutated-tile.png"
        original_path = second / manifest["tiles"][0]["binding"]["artifact_path"]
        original_path.write_bytes(mutated_path.read_bytes())
        mutated_path.unlink()
        controls.append(_expect_rejection("ET-NC-16", "NONDETERMINISTIC_SECOND_TILESET_OUTPUT", lambda: compare_generated_outputs(first, second)))
    value = copy.deepcopy(manifest); value["production_routing"] = "ENABLED"
    controls.append(_expect_rejection("ET-NC-17", "PRODUCTION_ROUTING_ENABLED", invalid(value, "PRODUCTION_ROUTING_ENABLED")))
    value = copy.deepcopy(manifest); value["prop_sockets"][0]["prop_asset_path"] = "assets/props/tree.png"
    controls.append(_expect_rejection("ET-NC-18", "DIRECT_PROP_ASSET_DUPLICATION", invalid(value, "DIRECT_PROP_ASSET_DUPLICATION")))
    return controls


def _build_evidence(first_dir: Path, manifest: dict[str, Any], determinism: dict[str, Any], controls: list[dict[str, Any]], gates: dict[str, dict[str, Any]]) -> None:
    if EVIDENCE.exists():
        shutil.rmtree(EVIDENCE)
    EVIDENCE.mkdir(parents=True)
    shutil.copytree(first_dir, EVIDENCE / "fixture", dirs_exist_ok=True)
    write_json(EVIDENCE / "tileset-manifest-v0200.json", manifest)
    write_json(EVIDENCE / "negative-controls-v0200.json", {"schema_version": SCHEMA_VERSION, "status": "ENVIRONMENT_TILESET_NEGATIVE_CONTROLS_PASSED" if all(item["status"] == "PASS" for item in controls) else "FAILED", "controls": controls})
    write_json(EVIDENCE / "full-slice-two-run-determinism-v0200.json", {"schema_version": SCHEMA_VERSION, "status": "TWO_RUN_DETERMINISM_PASSED" if determinism["equal"] else "FAILED", **determinism})
    write_json(EVIDENCE / "production-registry-v0200.json", {"schema_version": SCHEMA_VERSION, "status": "PRODUCTION_REGISTRY_EMPTY", "entries": [], "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0})
    write_json(EVIDENCE / "test-only-qa-board-v0200.json", {"schema_version": SCHEMA_VERSION, "label": "TEST_ONLY_TILE_QA_BOARD", "production_registry": [], "classes": list(TILE_CLASSES), "families": [family["terrain_family_id"] for family in manifest["terrain_families"]], "status": "TEST_ONLY"})
    write_json(EVIDENCE / "hard-gates-v0200.json", {"schema_version": SCHEMA_VERSION, "status": "PASS" if all(item["status"] == "PASS" for item in gates.values()) else "FAIL", "gates": gates})
    write_json(EVIDENCE / "execution-evidence-v0200.json", {"schema_version": SCHEMA_VERSION, "status": "ENVIRONMENT_TILESETS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED" if all(item["status"] == "PASS" for item in gates.values()) and all(item["status"] == "PASS" for item in controls) else "ENVIRONMENT_TILESETS_RUNTIME_FOUNDATION_FAILED", "gates": gates, "negative_controls": "ET-NC-01_TO_18_PASSED" if all(item["status"] == "PASS" for item in controls) else "FAILED", "tile_classes": list(TILE_CLASSES), "terrain_family_count": len(manifest["terrain_families"]), "real_environment_asset_coverage": "NONE", "synthetic_environment_fixture": "TEST_ONLY", "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0, "qa_board": "TEST_ONLY_TILE_QA_BOARD"})


def execute() -> int:
    with tempfile.TemporaryDirectory(prefix="ugas-v0200-first-") as first_temp, tempfile.TemporaryDirectory(prefix="ugas-v0200-second-") as second_temp:
        first_dir, second_dir = Path(first_temp), Path(second_temp)
        manifest = _generate_subprocess(first_dir)
        _generate_subprocess(second_dir)
        determinism = compare_generated_outputs(first_dir, second_dir)
        schema = _load(ROOT / "schemas/environment-tileset-runtime-v0200.json")
        validate_schema_document(schema); validate_instance(manifest, schema)
        semantic = validate_tileset_manifest(first_dir, manifest)
        controls = _run_negative_controls(first_dir, manifest)
        resolver = EnvironmentTileResolver(manifest, first_dir)
        resolved = resolver.resolve(ResolverRequest(manifest["tileset_id"], "temperate_cardinal", manifest["tiles"][0]["tile_id"], "ground_base", CARDINAL_ONLY, {"N": True}))
        gates: dict[str, dict[str, Any]] = {name: {"status": "PASS", "detail": "verified by the v0.20.0 runtime/fixture validator"} for name in GATE_NAMES}
        gates["tileset_schema_valid"]["detail"] = "Draft 2020-12 schema and semantic manifest passed"
        gates["tile_metrics_valid"]["detail"] = "positive tile and atlas metrics with tile multiples"
        gates["grid_conversion_roundtrip_valid"]["detail"] = str(validate_grid_roundtrip(manifest["metrics"], [(0, 0), (1, 2), (7, 4), (-2, 3)]))
        gates["isolated_full_slice_determinism"]["detail"] = f"{len(determinism['files'])} independent-output files byte-identical"
        gates["cache_identity_complete"]["detail"] = f"resolver returned complete key {resolved['cache_key']}"
        gates["stale_cache_cross_mask_tileset_layer_rejected"]["detail"] = "ET-NC-12 rejected a cross-mask cache identity"
        if semantic["status"] != "ENVIRONMENT_TILESET_MANIFEST_VALID" or not all(item["status"] == "PASS" for item in controls):
            for name in gates:
                gates[name]["status"] = "FAIL"
        _build_evidence(first_dir, manifest, determinism, controls, gates)
        print(json.dumps({"status": "ENVIRONMENT_TILESETS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED" if all(item["status"] == "PASS" for item in gates.values()) else "FAILED", "gates": len(gates), "passed": sum(item["status"] == "PASS" for item in gates.values()), "negative_controls": len(controls), "negative_controls_passed": sum(item["status"] == "PASS" for item in controls), "evidence": str(EVIDENCE.relative_to(ROOT))}, ensure_ascii=False))
        return 0 if all(item["status"] == "PASS" for item in gates.values()) and all(item["status"] == "PASS" for item in controls) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", type=Path)
    args = parser.parse_args()
    if args.generate:
        manifest = generate_fixture_pack(args.generate)
        print(json.dumps({"status": "GENERATED", "tileset_id": manifest["tileset_id"], "files": sum(1 for item in args.generate.rglob("*") if item.is_file())}))
        return 0
    return execute()


if __name__ == "__main__":
    raise SystemExit(main())
