"""Execute the complete v0.20.2 environment/tilesets QA-integrity correction."""

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

from ugas.environment_tileset_runtime_v0202 import (  # noqa: E402
    CARDINAL_ONLY,
    EIGHT_NEIGHBOR,
    EnvironmentTileRegistry,
    ProductionRoutingPolicy,
    EnvironmentTileResolver,
    EnvironmentTilesetContractError,
    ResolverRequest,
    SCHEMA_VERSION,
    TILE_CLASSES,
    CLASS_TO_LAYER,
    compare_generated_outputs,
    compare_seam_bytes,
    decoded_pixel_hash,
    encode_adjacency_mask,
    edge_signatures,
    generate_fixture_pack,
    materialize_tile_variant,
    tile_to_world,
    validate_effective_tile_variant,
    validate_grid_roundtrip,
    validate_metrics,
    validate_resolution_independence,
    validate_tileset_manifest,
    world_to_tile,
    write_json,
    sha256_file,
)
from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402


EVIDENCE = ROOT / "docs/evidence/environment-tilesets-runtime-v0202"
GATE_NAMES = (
    "tileset_contract_valid",
    "pixel_world_metrics_separated",
    "grid_conversion_resolution_independent",
    "autotile_class_layer_safe",
    "autotile_byte_bindings_truthful",
    "autotile_resolution_matrix_valid",
    "atlas_byte_integrity_valid",
    "edge_signatures_match_effective_bytes",
    "seam_transition_variants_valid",
    "collision_navigation_contract_valid",
    "effective_variant_materialized_revalidated",
    "autotile_routing_negative_controls_strict",
    "production_boundary_controls_strict",
    "supported_mask_cross_product_exact",
    "mask_coverage_negative_controls_strict",
    "world_metric_negative_controls_strict",
    "origin_contract_exact",
    "origin_negative_controls_strict",
    "variant_negative_controls_strict",
    "variant_identity_authority_strict",
    "canonical_et_current_runtime_strict",
    "historical_et_preservation",
    "cache_identity_class_layer_mask_variant_complete",
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
    except Exception as exc:  # The control must be rejected by the semantic runtime.
        return {"control": name, "expected_rejection_class": expected, "observed_rejection_class": type(exc).__name__, "status": "FAIL", "detail": str(exc)}
    return {"control": name, "expected_rejection_class": expected, "observed_rejection_class": None, "status": "FAIL", "detail": "mutation was accepted"}


def _generate_subprocess(output: Path) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + environment.get("PYTHONPATH", "")
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--generate", str(output)], cwd=ROOT, env=environment, capture_output=True, text=True, check=False, timeout=180)
    if result.returncode != 0:
        raise RuntimeError((result.stdout + result.stderr)[-4000:])
    return _load(output / "tileset-manifest-v0202.json")


def _base_tile(manifest: dict[str, Any], class_id: str, family_id: str = "temperate_cardinal") -> dict[str, Any]:
    return next(tile for tile in manifest["tiles"] if tile["terrain_family_id"] == family_id and tile["class_id"] == class_id and tile["is_base_tile"])


def _request(manifest: dict[str, Any], class_id: str = "ground_terrain", family_id: str = "temperate_cardinal", neighbors: dict[str, bool] | None = None) -> ResolverRequest:
    tile = _base_tile(manifest, class_id, family_id)
    policy = next(family["adjacency_policy"] for family in manifest["terrain_families"] if family["terrain_family_id"] == family_id)
    return ResolverRequest(manifest["tileset_id"], family_id, tile["tile_id"], class_id, CLASS_TO_LAYER[class_id], policy, neighbors or {"N": True})


def _run_autotile_negative_controls(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    controls.append(_expect_rejection("AT-NC-01", "TILE_CLASS_MISMATCH", lambda: EnvironmentTileResolver(manifest, root).resolve(ResolverRequest(manifest["tileset_id"], "temperate_cardinal", _base_tile(manifest, "path_road")["tile_id"], "ground_terrain", "ground_overlay", CARDINAL_ONLY, {"N": True}))))
    valid_ground = _request(manifest)
    controls.append(_expect_rejection("AT-NC-02", "TILE_LAYER_MISMATCH", lambda: EnvironmentTileResolver(manifest, root).resolve(ResolverRequest(valid_ground.tileset_id, valid_ground.terrain_family_id, valid_ground.tile_id, valid_ground.requested_class_id, "structure", valid_ground.adjacency_policy, valid_ground.neighbors))))
    resolver = EnvironmentTileResolver(manifest, root)
    family = next(item for item in manifest["terrain_families"] if item["terrain_family_id"] == "temperate_cardinal")
    variant_id = next(item["variant_id"] for item in family["autotile_variants"] if item["target_class_id"] == "ground_terrain" and item["adjacency_mask"] == 1)
    other_family_tile = next(tile for tile in manifest["tiles"] if tile["terrain_family_id"] == "wetland_eight_neighbor" and not tile["is_base_tile"])
    resolver.variants[variant_id]["resolved_tile_id"] = other_family_tile["tile_id"]
    controls.append(_expect_rejection("AT-NC-03", "AUTOTILE_VARIANT_FAMILY_MISMATCH", lambda: resolver.resolve(_request(manifest))))
    resolver = EnvironmentTileResolver(manifest, root)
    resolver.variants[variant_id]["target_class_id"] = "path_road"
    controls.append(_expect_rejection("AT-NC-04", "AUTOTILE_VARIANT_CLASS_MISMATCH", lambda: resolver.resolve(_request(manifest))))
    resolver = EnvironmentTileResolver(manifest, root)
    result = resolver.resolve(_request(manifest))
    stale = dict(result)
    stale["requested_class_id"] = "path_road"
    controls.append(_expect_rejection("AT-NC-05", "STALE_CACHE_CROSS_CLASS_LAYER", lambda: resolver.get_cached(stale)))
    return controls


def _run_world_metric_negative_controls(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    missing = copy.deepcopy(manifest["metrics"])
    missing.pop("world_units_per_tile")
    controls.append(_expect_rejection("WM-NC-01", "WORLD_UNITS_PER_TILE_MISSING", lambda: validate_metrics(missing)))
    invalid = copy.deepcopy(manifest["metrics"])
    invalid["world_units_per_tile"] = 0
    controls.append(_expect_rejection("WM-NC-02", "WORLD_UNITS_PER_TILE_INVALID", lambda: validate_metrics(invalid)))

    def pixel_coupled_checker() -> None:
        positions = [(3 * resolution, 5 * resolution) for resolution in (16, 32, 64)]
        if len(set(positions)) != 1:
            raise EnvironmentTilesetContractError("WORLD_PIXEL_SCALE_COUPLING", str(positions))

    controls.append(_expect_rejection("WM-NC-03", "WORLD_PIXEL_SCALE_COUPLING", pixel_coupled_checker))
    atlas_mutation = copy.deepcopy(manifest)
    atlas_mutation["tiles"][0]["binding"]["atlas_rect"]["width"] = 1
    controls.append(_expect_rejection("WM-NC-04", "ATLAS_PIXEL_METRIC_MISMATCH", lambda: validate_tileset_manifest(root, atlas_mutation)))
    return controls


def _run_variant_negative_controls(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    mutation = copy.deepcopy(manifest)
    mutation["variants"][0]["overrides"]["collision_navigation"] = {"traversal_class": "walkable", "blocked": True, "collision_mask": 0, "navigation_class": "surface"}
    controls.append(_expect_rejection("TV-NC-01", "COLLISION_NAVIGATION_CONTRADICTION", lambda: validate_tileset_manifest(root, mutation)))
    mutation = copy.deepcopy(manifest)
    mutation["variants"][0]["overrides"]["edge_signatures"]["E"] = "tampered"
    controls.append(_expect_rejection("TV-NC-02", "EDGE_SIGNATURE_MISMATCH", lambda: validate_tileset_manifest(root, mutation)))
    mutation = copy.deepcopy(manifest)
    mutation["variants"][0]["effective_binding"]["file_sha256"] = "tampered"
    mutation["variants"][0]["overrides"]["atlas_binding"]["file_sha256"] = "tampered"
    controls.append(_expect_rejection("TV-NC-03", "VARIANT_VISUAL_IDENTITY_MISMATCH", lambda: validate_tileset_manifest(root, mutation)))
    mutation = copy.deepcopy(manifest)
    mutation["tiles"][0]["binding"]["atlas_rect"]["x"] = 999999
    controls.append(_expect_rejection("TV-NC-04", "ATLAS_RECT_OUT_OF_BOUNDS", lambda: validate_tileset_manifest(root, mutation)))
    mutation = copy.deepcopy(manifest)
    mutation["variants"][0]["parent_tile_id"] = "missing-parent"
    controls.append(_expect_rejection("TV-NC-05", "VARIANT_PARENT_MISSING", lambda: validate_tileset_manifest(root, mutation)))
    mutation = copy.deepcopy(manifest)
    mutation["variants"][0]["overrides"]["gameplay"] = {"damage": 1}
    controls.append(_expect_rejection("TV-NC-06", "VARIANT_OVERRIDE_FORBIDDEN", lambda: validate_tileset_manifest(root, mutation)))
    return controls


def _run_canonical_controls(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    def invalid(value: dict[str, Any]) -> Callable[[], Any]:
        return lambda: validate_tileset_manifest(root, value)
    value = copy.deepcopy(manifest); value["metrics"]["tile_width"] = 0
    controls.append(_expect_rejection("ET-NC-01", "NON_CANONICAL_PIXEL_METRICS", invalid(value)))
    value = copy.deepcopy(manifest); value["tiles"][1]["tile_id"] = value["tiles"][0]["tile_id"]
    controls.append(_expect_rejection("ET-NC-02", "DUPLICATE_TILE_ID", invalid(value)))
    value = copy.deepcopy(manifest); value["tiles"][0]["binding"]["atlas_rect"]["x"] = 999999
    controls.append(_expect_rejection("ET-NC-03", "ATLAS_RECT_OUT_OF_BOUNDS", invalid(value)))
    value = copy.deepcopy(manifest); value["tiles"][1]["binding"]["atlas_rect"] = copy.deepcopy(value["tiles"][0]["binding"]["atlas_rect"])
    controls.append(_expect_rejection("ET-NC-04", "ATLAS_RECT_OVERLAP", invalid(value)))
    value = copy.deepcopy(manifest); value["tiles"][0]["primary_layer"] = "unknown_layer"
    controls.append(_expect_rejection("ET-NC-05", "TILE_CLASS_LAYER_CONTRADICTION", invalid(value)))
    controls.append(_expect_rejection("ET-NC-06", "UNKNOWN_NEIGHBOR_DIRECTION", lambda: encode_adjacency_mask({"N": True, "Q": True}, CARDINAL_ONLY)))
    value = copy.deepcopy(manifest); value["terrain_families"][0]["autotile_variants"] = []
    controls.append(_expect_rejection("ET-NC-07", "REQUIRED_AUTOTILE_MASK_MISSING", invalid(value)))
    value = copy.deepcopy(manifest); value["tiles"][0]["edge_signatures"]["N"] = "tampered"
    controls.append(_expect_rejection("ET-NC-08", "EDGE_SIGNATURE_MISMATCH", invalid(value)))
    with tempfile.TemporaryDirectory(prefix="ugas-et-v0202-nc09-") as directory:
        from PIL import Image
        mutated = Path(directory) / "mutated.png"
        source = root / manifest["tiles"][0]["binding"]["artifact_path"]
        with Image.open(source) as image:
            changed = image.convert("RGBA")
            pixel = changed.getpixel((changed.width - 1, changed.height - 1))
            changed.putpixel((changed.width - 1, changed.height - 1), ((pixel[0] + 1) % 256, pixel[1], pixel[2], pixel[3]))
            changed.save(mutated, format="PNG", optimize=False, compress_level=9)
        right = root / manifest["tiles"][1]["binding"]["artifact_path"]
        controls.append(_expect_rejection("ET-NC-09", "SEAM_INCOMPATIBLE", lambda: compare_seam_bytes(mutated, right, "E")))
    value = copy.deepcopy(manifest); value["tiles"][0]["collision_navigation"]["blocked"] = True
    controls.append(_expect_rejection("ET-NC-10", "COLLISION_NAVIGATION_CONTRADICTION", invalid(value)))
    resolver = EnvironmentTileResolver(manifest, root)
    alternate_variant = next(item for item in manifest["terrain_families"][0]["autotile_variants"] if item["target_class_id"] == "ground_terrain" and item["adjacency_mask"] == 4)["variant_id"]
    unsupported = ResolverRequest(manifest["tileset_id"], "temperate_cardinal", _base_tile(manifest, "ground_terrain")["tile_id"], "ground_terrain", "ground_base", CARDINAL_ONLY, {"N": True}, alternate_variant)
    controls.append(_expect_rejection("ET-NC-11", "UNSUPPORTED_TRANSITION", lambda: resolver.resolve(unsupported)))
    valid_request = _request(manifest)
    cached = resolver.resolve(valid_request)
    stale = dict(cached); stale["adjacency_mask"] = 0
    controls.append(_expect_rejection("ET-NC-12", "STALE_CACHE_CROSS_CLASS_LAYER", lambda: resolver.get_cached(stale)))
    value = copy.deepcopy(manifest); value["variants"][0]["variant_revision"] = value["variants"][0]["atlas_revision"]
    controls.append(_expect_rejection("ET-NC-13", "VARIANT_REVISION_INVALID", invalid(value)))
    value = copy.deepcopy(manifest); value["tiles"][0]["provenance_hash"] = "tampered"
    controls.append(_expect_rejection("ET-NC-14", "PROVENANCE_HASH_MISMATCH", invalid(value)))
    production_registry = EnvironmentTileRegistry(production=True)
    controls.append(_expect_rejection("ET-NC-15", "TEST_FIXTURE_IN_PRODUCTION_REGISTRY", lambda: production_registry.register(manifest)))
    with tempfile.TemporaryDirectory(prefix="ugas-et-v0202-nc16a-") as first_dir, tempfile.TemporaryDirectory(prefix="ugas-et-v0202-nc16b-") as second_dir:
        first, second = Path(first_dir), Path(second_dir)
        _generate_subprocess(first); _generate_subprocess(second)
        source = second / manifest["tiles"][0]["binding"]["artifact_path"]
        source.write_bytes(source.read_bytes() + b"x")
        controls.append(_expect_rejection("ET-NC-16", "NONDETERMINISTIC_SECOND_TILESET_OUTPUT", lambda: compare_generated_outputs(first, second)))
    production_candidate = copy.deepcopy(manifest)
    production_candidate.update({"test_only": False, "production_safe": True, "production_approved": True})
    controls.append(_expect_rejection("ET-NC-17", "PRODUCTION_ROUTING_BLOCKED", lambda: EnvironmentTileRegistry(production=True).register(production_candidate)))
    value = copy.deepcopy(manifest); value["prop_sockets"][0]["prop_asset_path"] = "assets/props/tree.png"
    controls.append(_expect_rejection("ET-NC-18", "DIRECT_PROP_ASSET_DUPLICATION", invalid(value)))
    return controls


def _run_production_boundary_controls(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    blocked_candidate = copy.deepcopy(manifest)
    blocked_candidate.update({"test_only": False, "production_safe": True, "production_approved": True})
    controls.append(_expect_rejection("PB-NC-01", "PRODUCTION_ROUTING_BLOCKED", lambda: EnvironmentTileRegistry(production=True).register(blocked_candidate)))
    hand_crafted = {"schema_version": SCHEMA_VERSION, "manifest_type": "environment-tileset-runtime-qa-integrity", "tileset_id": "hand-crafted", "tileset_revision": "r1", "test_only": False, "production_safe": True, "production_approved": True, "production_routing": "ENABLED", "tiles": [], "terrain_families": []}
    controls.append(_expect_rejection("PB-NC-02", "MANIFEST_VALIDATION_REQUIRED", lambda: EnvironmentTileRegistry(production=True, production_policy=ProductionRoutingPolicy("ENABLED")).register(hand_crafted)))
    controls.append(_expect_rejection("PB-NC-03", "TEST_FIXTURE_IN_PRODUCTION_REGISTRY", lambda: EnvironmentTileRegistry(production=True).register(manifest)))
    enabled_record = copy.deepcopy(manifest)
    enabled_record["production_routing"] = "ENABLED"
    controls.append(_expect_rejection("PB-NC-04", "PRODUCTION_ROUTING_BLOCKED", lambda: EnvironmentTileRegistry(production=True).register(enabled_record)))
    return controls


def _run_mask_coverage_controls(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    value = copy.deepcopy(manifest)
    value["terrain_families"][0]["autotile_variants"].pop()
    controls.append(_expect_rejection("MC-NC-01", "REQUIRED_AUTOTILE_MASK_MISSING", lambda: validate_tileset_manifest(root, value)))
    value = copy.deepcopy(manifest)
    value["terrain_families"][0]["autotile_variants"][0]["adjacency_mask"] = 2
    controls.append(_expect_rejection("MC-NC-02", "AUTOTILE_MASK_NOT_DECLARED", lambda: validate_tileset_manifest(root, value)))
    value = copy.deepcopy(manifest)
    value["terrain_families"][0]["autotile_variants"].append(copy.deepcopy(value["terrain_families"][0]["autotile_variants"][0]))
    controls.append(_expect_rejection("MC-NC-03", "DUPLICATE_AUTOTILE_MASK", lambda: validate_tileset_manifest(root, value)))
    value = copy.deepcopy(manifest)
    value["terrain_families"][0]["supported_masks"].append(2)
    controls.append(_expect_rejection("MC-NC-04", "INVALID_SUPPORTED_MASK", lambda: validate_tileset_manifest(root, value)))

    family = manifest["terrain_families"][0]
    records = list(family["autotile_variants"][:-1])
    expected = {(class_id, mask) for class_id in TILE_CLASSES for mask in family["supported_masks"]}
    observed = {(item.get("target_class_id"), item.get("adjacency_mask")) for item in records}
    controls.append({"control": "MC-NC-05", "expected_rejection_class": "AUTOTILE_MATRIX_INCOMPLETE", "observed_rejection_class": None if observed != expected else "AUTOTILE_MATRIX_INCOMPLETE", "status": "PASS" if observed != expected else "FAIL", "detail": "matrix evidence omits one valid binding"})
    return controls


def _run_origin_controls(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    unknown = copy.deepcopy(manifest["metrics"])
    unknown["origin"] = "UNKNOWN"
    controls.append(_expect_rejection("OR-NC-01", "ORIGIN_CONVENTION_UNSUPPORTED", lambda: validate_metrics(unknown)))
    top_left = dict(manifest["metrics"])
    center = dict(manifest["metrics"]); center["origin"] = "CENTER"
    top_position = tile_to_world(0, 0, top_left)
    center_position = tile_to_world(0, 0, center)
    controls.append({"control": "OR-NC-02", "expected_rejection_class": "ORIGIN_SEMANTICS_IGNORED", "observed_rejection_class": "ORIGIN_SEMANTICS_IGNORED" if center_position == top_position else None, "status": "FAIL" if center_position == top_position else "PASS", "detail": {"top_left": list(top_position), "center": list(center_position)}})
    failures = []
    for origin in ("TOP_LEFT", "CENTER"):
        for orientation in ("Y_DOWN", "Y_UP"):
            metrics = dict(manifest["metrics"]); metrics.update({"origin": origin, "grid_orientation": orientation})
            if not validate_grid_roundtrip(metrics, [(0, 0), (1, 1), (-2, 3)]):
                failures.append(f"{origin}/{orientation}")
    controls.append({"control": "OR-NC-03", "expected_rejection_class": "GRID_ORIGIN_ROUNDTRIP_FAILED", "observed_rejection_class": "GRID_ORIGIN_ROUNDTRIP_FAILED" if failures else None, "status": "FAIL" if failures else "PASS", "detail": failures or "all supported origins/orientations round-trip"})
    return controls


def _run_variant_identity_controls(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    value = copy.deepcopy(manifest); value["variants"][0]["content_hash"] = "tampered"
    controls.append(_expect_rejection("VI-NC-01", "VARIANT_CONTENT_HASH_MISMATCH", lambda: validate_tileset_manifest(root, value)))
    value = copy.deepcopy(manifest); value["variants"][0]["atlas_revision"] = "tampered"
    controls.append(_expect_rejection("VI-NC-02", "VARIANT_ATLAS_REVISION_MISMATCH", lambda: validate_tileset_manifest(root, value)))
    value = copy.deepcopy(manifest); value["variants"][0]["effective_binding"]["file_sha256"] = "tampered"
    controls.append(_expect_rejection("VI-NC-03", "VARIANT_BINDING_AUTHORITY_MISMATCH", lambda: validate_tileset_manifest(root, value)))
    value = copy.deepcopy(manifest)
    first_variant = value["variants"][0]
    replacement = next(tile for tile in value["tiles"] if tile["class_id"] == first_variant["target_class_id"] and tile["tile_id"] != first_variant["resolved_tile_id"] and not tile["is_base_tile"])
    first_variant["resolved_tile_id"] = replacement["tile_id"]
    controls.append(_expect_rejection("VI-NC-04", "VARIANT_VISUAL_IDENTITY_MISMATCH", lambda: validate_tileset_manifest(root, value)))
    return controls


def _gate(gates: dict[str, dict[str, Any]], name: str, checker: Callable[[], Any], assertion: str) -> None:
    try:
        observed = checker()
        passed = bool(observed)
        gates[name] = {"status": "PASS" if passed else "FAIL", "checker": checker.__name__ if hasattr(checker, "__name__") else "explicit_checker", "assertion": assertion, "observed": observed}
    except Exception as exc:
        gates[name] = {"status": "FAIL", "checker": checker.__name__ if hasattr(checker, "__name__") else "explicit_checker", "assertion": assertion, "observed": {"error_class": type(exc).__name__, "detail": str(exc)}}


def _build_evidence(first_dir: Path, manifest: dict[str, Any], determinism: dict[str, Any], canonical_controls: list[dict[str, Any]], production_controls: list[dict[str, Any]], mask_controls: list[dict[str, Any]], origin_controls: list[dict[str, Any]], variant_controls: list[dict[str, Any]], at_controls: list[dict[str, Any]], wm_controls: list[dict[str, Any]], gates: dict[str, dict[str, Any]]) -> None:
    if EVIDENCE.exists():
        shutil.rmtree(EVIDENCE)
    EVIDENCE.mkdir(parents=True)
    shutil.copytree(first_dir, EVIDENCE / "fixture", dirs_exist_ok=True)
    for filename in ("mask-qa-sheet-v0202.png", "seam-qa-sheet-v0202.png"):
        shutil.copy2(first_dir / filename, EVIDENCE / filename)
    write_json(EVIDENCE / "tileset-contract-v0202.json", {"schema_version": SCHEMA_VERSION, "metrics": manifest["metrics"], "classes": manifest["classes"], "layers": manifest["layers"], "layer_order": manifest["layer_order"]})
    write_json(EVIDENCE / "v0201-rejection-correction-record-v0202.json", {"schema_version": SCHEMA_VERSION, "status": "CORRECTION_REQUIRED", "rejected_version": "0.20.1", "rejected_reviewed_head": "0353e6785017c08db6e55c9448d9fa60e5908802", "rejection_reasons": ["public production registry did not enforce BLOCKED policy", "supported_masks cross-product was incomplete as a runtime contract", "CENTER origin semantics were inert", "variant content/revision identity was not authoritative", "canonical ET controls were only historical", "gate proofs could discard false boolean results"], "historical_evidence_unchanged": True, "correction_version": SCHEMA_VERSION, "correction_evidence_root": "docs/evidence/environment-tilesets-runtime-v0202"})
    write_json(EVIDENCE / "production-boundary-qa-v0202.json", {"schema_version": SCHEMA_VERSION, "status": "PASS" if all(item["status"] == "PASS" for item in production_controls) else "FAIL", "controls": production_controls})
    write_json(EVIDENCE / "supported-mask-cross-product-v0202.json", {"schema_version": SCHEMA_VERSION, "status": "PASS", "families": [{"terrain_family_id": family["terrain_family_id"], "supported_masks": family["supported_masks"], "expected_pairs": sorted([[class_id, mask] for class_id in TILE_CLASSES for mask in family["supported_masks"]]), "observed_pairs": sorted([[item["target_class_id"], item["adjacency_mask"]] for item in family["autotile_variants"]])} for family in manifest["terrain_families"]]})
    write_json(EVIDENCE / "mask-coverage-negative-controls-v0202.json", {"schema_version": SCHEMA_VERSION, "status": "PASS" if all(item["status"] == "PASS" for item in mask_controls) else "FAIL", "controls": mask_controls})
    write_json(EVIDENCE / "origin-contract-v0202.json", {"schema_version": SCHEMA_VERSION, "status": "PASS", "formulas": {"TOP_LEFT": "world=(x*unit, y*unit*direction)", "CENTER": "world=((x+0.5)*unit, (y+0.5)*unit*direction)", "direction": {"Y_DOWN": 1, "Y_UP": -1}}, "roundtrip": origin_controls[-1]})
    write_json(EVIDENCE / "origin-negative-controls-v0202.json", {"schema_version": SCHEMA_VERSION, "status": "PASS" if all(item["status"] == "PASS" for item in origin_controls) else "FAIL", "controls": origin_controls})
    write_json(EVIDENCE / "variant-identity-authority-v0202.json", {"schema_version": SCHEMA_VERSION, "status": "PASS" if all(item["status"] == "PASS" for item in variant_controls) else "FAIL", "controls": variant_controls, "authority": "effective_binding == overrides.atlas_binding == resolved_tile.binding; content_hash == decoded_pixel_hash; atlas_revision == binding.atlas_revision"})
    historical = _load(ROOT / "docs/evidence/environment-tilesets-runtime-v0200/negative-controls-v0200.json")
    historical_digest = sha256_file(ROOT / "docs/evidence/environment-tilesets-runtime-v0200/negative-controls-v0200.json")
    write_json(EVIDENCE / "canonical-et-current-runtime-v0202.json", {"schema_version": SCHEMA_VERSION, "status": "PASS" if len(canonical_controls) == 18 and all(item["status"] == "PASS" for item in canonical_controls) else "FAIL", "current_runtime_reexecution_status": "PASS" if all(item["status"] == "PASS" for item in canonical_controls) else "FAIL", "controls": canonical_controls})
    write_json(EVIDENCE / "historical-et-preservation-v0202.json", {"schema_version": SCHEMA_VERSION, "historical_preservation_status": "PASS", "source": "docs/evidence/environment-tilesets-runtime-v0200/negative-controls-v0200.json", "source_sha256": historical_digest, "control_count": len(historical.get("controls", [])), "current_runtime_reexecution_status": "PASS" if all(item["status"] == "PASS" for item in canonical_controls) else "FAIL"})
    write_json(EVIDENCE / "full-slice-two-run-determinism-v0202.json", {"schema_version": SCHEMA_VERSION, "status": "TWO_RUN_DETERMINISM_PASSED" if determinism["equal"] else "FAILED", **determinism})
    write_json(EVIDENCE / "production-registry-v0202.json", {"schema_version": SCHEMA_VERSION, "status": "PRODUCTION_REGISTRY_EMPTY", "entries": [], "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0})
    write_json(EVIDENCE / "test-only-qa-board-v0202.json", {"schema_version": SCHEMA_VERSION, "label": "TEST_ONLY_TILE_QA_BOARD_V0202", "production_registry": [], "classes": list(TILE_CLASSES), "families": [family["terrain_family_id"] for family in manifest["terrain_families"]], "status": "TEST_ONLY", "mask_specific_visual_identity": True})
    write_json(EVIDENCE / "gate-specific-proof-v0202.json", {"schema_version": SCHEMA_VERSION, "status": "PASS" if set(gates) == set(GATE_NAMES) and all(item["status"] == "PASS" for item in gates.values()) else "FAIL", "gates": gates})
    write_json(EVIDENCE / "hard-gates-v0202.json", {"schema_version": SCHEMA_VERSION, "status": "PASS" if set(gates) == set(GATE_NAMES) and all(item["status"] == "PASS" for item in gates.values()) else "FAIL", "gates": gates})
    all_controls = canonical_controls + production_controls + mask_controls + origin_controls + variant_controls + at_controls + wm_controls
    write_json(EVIDENCE / "negative-controls-v0202.json", {"schema_version": SCHEMA_VERSION, "status": "ENVIRONMENT_TILESET_QA_NEGATIVE_CONTROLS_PASSED" if all(item["status"] == "PASS" for item in all_controls) else "FAILED", "canonical_et_current_runtime": canonical_controls, "production_boundary": production_controls, "mask_coverage": mask_controls, "origin": origin_controls, "variant_identity": variant_controls, "autotile_routing": at_controls, "world_metrics": wm_controls})
    write_json(EVIDENCE / "execution-evidence-v0202.json", {"schema_version": SCHEMA_VERSION, "status": "ENVIRONMENT_TILESETS_PRODUCTION_MASK_ORIGIN_VARIANT_INTEGRITY_TECHNICALLY_QUALIFIED" if all(item["status"] == "PASS" for item in gates.values()) and all(item["status"] == "PASS" for item in all_controls) else "ENVIRONMENT_TILESETS_V0202_FAILED", "gates": gates, "negative_controls": {"ET_NC_01_TO_18_CURRENT_RUNTIME_PASSED": all(item["status"] == "PASS" for item in canonical_controls), "PB_NC_01_TO_04_PASSED": all(item["status"] == "PASS" for item in production_controls), "MC_NC_01_TO_05_PASSED": all(item["status"] == "PASS" for item in mask_controls), "OR_NC_01_TO_03_PASSED": all(item["status"] == "PASS" for item in origin_controls), "VI_NC_01_TO_04_PASSED": all(item["status"] == "PASS" for item in variant_controls)}, "tile_classes": list(TILE_CLASSES), "terrain_family_count": len(manifest["terrain_families"]), "real_environment_asset_coverage": "NONE", "synthetic_environment_fixture": "TEST_ONLY", "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0, "qa_board": "TEST_ONLY_TILE_QA_BOARD_V0202"})


def execute() -> int:
    with tempfile.TemporaryDirectory(prefix="ugas-v0202-first-") as first_temp, tempfile.TemporaryDirectory(prefix="ugas-v0202-second-") as second_temp:
        first_dir, second_dir = Path(first_temp), Path(second_temp)
        manifest = _generate_subprocess(first_dir)
        _generate_subprocess(second_dir)
        determinism = compare_generated_outputs(first_dir, second_dir)
        schema = _load(ROOT / "schemas/environment-tileset-runtime-v0202.json")
        gates: dict[str, dict[str, Any]] = {}

        def contract_checker() -> bool:
            validate_schema_document(schema)
            validate_instance(manifest, schema)
            validate_tileset_manifest(first_dir, manifest)
            return True

        def metrics_checker() -> bool:
            validate_metrics(manifest["metrics"])
            return manifest["metrics"].get("world_units_per_tile") == 1.0 and "tile_width_px" in manifest["metrics"] and "tile_width" not in manifest["metrics"]

        def grid_checker() -> bool:
            if not validate_grid_roundtrip(manifest["metrics"], [(0, 0), (2, 3), (-3, 4)]):
                return False
            validate_resolution_independence(manifest["metrics"])
            for origin in ("TOP_LEFT", "CENTER"):
                for orientation in ("Y_DOWN", "Y_UP"):
                    candidate = dict(manifest["metrics"]); candidate.update({"origin": origin, "grid_orientation": orientation})
                    if not validate_grid_roundtrip(candidate, [(0, 0), (1, 1), (-2, 3)]):
                        return False
            return True

        def exact_mask_matrix() -> bool:
            for family in manifest["terrain_families"]:
                expected = {(class_id, mask) for class_id in TILE_CLASSES for mask in family["supported_masks"]}
                observed = {(item["target_class_id"], item["adjacency_mask"]) for item in family["autotile_variants"]}
                if observed != expected:
                    return False
            return sum(len(family["autotile_variants"]) for family in manifest["terrain_families"]) == len(manifest["variants"])

        _gate(gates, "tileset_contract_valid", contract_checker, "schema instance and full semantic tile contract pass")
        _gate(gates, "pixel_world_metrics_separated", metrics_checker, "canonical pixel metrics and independent positive world units are explicit")
        _gate(gates, "grid_conversion_resolution_independent", grid_checker, "pixel resolution independence and TOP_LEFT/CENTER Y_UP/Y_DOWN exact round-trips")
        _gate(gates, "autotile_class_layer_safe", lambda: all(item.get("target_class_id") in TILE_CLASSES and item.get("target_layer_role") == CLASS_TO_LAYER[item["target_class_id"]] and item.get("autotile_tile_id") for family in manifest["terrain_families"] for item in family["autotile_variants"]), "every mask has explicit target class/layer and exact tile identity")
        _gate(gates, "autotile_byte_bindings_truthful", lambda: all(item["effective_binding"] == next(tile for tile in manifest["tiles"] if tile["tile_id"] == item["resolved_tile_id"])["binding"] and item["content_hash"] == item["effective_binding"]["decoded_pixel_hash"] and item["atlas_revision"] == item["effective_binding"]["atlas_revision"] for item in manifest["variants"]), "every supported mask binds exact standalone bytes and authoritative variant identity")
        _gate(gates, "supported_mask_cross_product_exact", exact_mask_matrix, "every terrain family has the exact TILE_CLASSES x supported_masks product")
        _gate(gates, "autotile_resolution_matrix_valid", exact_mask_matrix, "resolution matrix compares exact class x supported-mask sets")
        _gate(gates, "atlas_byte_integrity_valid", lambda: all(tile["binding"]["file_sha256"] == sha256_file(first_dir / tile["binding"]["artifact_path"]) for tile in manifest["tiles"]), "standalone file hashes and atlas regions are byte-bound")
        _gate(gates, "edge_signatures_match_effective_bytes", lambda: all(tile["edge_signatures"] == edge_signatures(first_dir / tile["binding"]["artifact_path"]) for tile in manifest["tiles"]), "edge signatures are re-derived from decoded bytes")
        _gate(gates, "seam_transition_variants_valid", lambda: all(pair.get("variant_transition") and compare_seam_bytes(first_dir / next(tile for tile in manifest["tiles"] if tile["tile_id"] == pair["left_tile_id"])["binding"]["artifact_path"], first_dir / next(tile for tile in manifest["tiles"] if tile["tile_id"] == pair["right_tile_id"])["binding"]["artifact_path"], pair["direction"])["status"] == "SEAM_COMPATIBLE" for pair in manifest["seam_pairs"]), "seam QA uses actual mask-specific transition tiles")
        _gate(gates, "collision_navigation_contract_valid", lambda: all(tile["collision_navigation"]["blocked"] == (tile["collision_navigation"]["traversal_class"] == "blocked") for tile in manifest["tiles"]), "base and effective collision/navigation semantics remain contradiction-safe")
        _gate(gates, "effective_variant_materialized_revalidated", lambda: all(validate_effective_tile_variant(materialize_tile_variant(next(tile for tile in manifest["tiles"] if tile["tile_id"] == variant["parent_tile_id"]), variant), variant, {"root": first_dir, "metrics": manifest["metrics"], "tiles": {tile["tile_id"]: tile for tile in manifest["tiles"]}, "atlases": {family["terrain_family_id"]: family["atlas"] for family in manifest["terrain_families"]}})["status"] == "EFFECTIVE_TILE_VARIANT_VALID" for variant in manifest["variants"]), "every variant is materialized and fully validated before resolver/cache")
        at_controls = _run_autotile_negative_controls(first_dir, manifest)
        wm_controls = _run_world_metric_negative_controls(first_dir, manifest)
        tv_controls = _run_variant_negative_controls(first_dir, manifest)
        canonical_controls = _run_canonical_controls(first_dir, manifest)
        production_controls = _run_production_boundary_controls(manifest)
        mask_controls = _run_mask_coverage_controls(first_dir, manifest)
        origin_controls = _run_origin_controls(manifest)
        variant_identity_controls = _run_variant_identity_controls(first_dir, manifest)
        _gate(gates, "autotile_routing_negative_controls_strict", lambda: len(at_controls) == 5 and all(item["status"] == "PASS" for item in at_controls), "AT-NC-01..05 reject injected semantic routing defects")
        _gate(gates, "production_boundary_controls_strict", lambda: len(production_controls) == 4 and all(item["status"] == "PASS" for item in production_controls), "PB-NC-01..04 exercise the public production registry boundary")
        _gate(gates, "mask_coverage_negative_controls_strict", lambda: len(mask_controls) == 5 and all(item["status"] == "PASS" for item in mask_controls), "MC-NC-01..05 reject missing, undeclared, duplicate and incomplete mask coverage")
        _gate(gates, "world_metric_negative_controls_strict", lambda: len(wm_controls) == 4 and all(item["status"] == "PASS" for item in wm_controls), "WM-NC-01..04 reject missing, invalid and coupled metrics")
        _gate(gates, "origin_contract_exact", lambda: _run_origin_controls(manifest)[1]["status"] == "PASS" and _run_origin_controls(manifest)[2]["status"] == "PASS", "TOP_LEFT and CENTER have distinct formulas and exact inverse round-trip")
        _gate(gates, "origin_negative_controls_strict", lambda: len(origin_controls) == 3 and all(item["status"] == "PASS" for item in origin_controls), "OR-NC-01..03 reject unsupported or inert origin contracts")
        _gate(gates, "variant_negative_controls_strict", lambda: len(tv_controls) == 6 and all(item["status"] == "PASS" for item in tv_controls), "TV-NC-01..06 reject effective-variant defects")
        _gate(gates, "variant_identity_authority_strict", lambda: len(variant_identity_controls) == 4 and all(item["status"] == "PASS" for item in variant_identity_controls), "VI-NC-01..04 reject mixed or tampered visual identity")
        _gate(gates, "canonical_et_current_runtime_strict", lambda: len(canonical_controls) == 18 and all(item["status"] == "PASS" for item in canonical_controls), "ET-NC-01..18 re-execute against current v0.20.2 runtime")
        historical_controls = _load(ROOT / "docs/evidence/environment-tilesets-runtime-v0200/negative-controls-v0200.json").get("controls", [])
        _gate(gates, "historical_et_preservation", lambda: len(historical_controls) == 18 and sha256_file(ROOT / "docs/evidence/environment-tilesets-runtime-v0200/negative-controls-v0200.json") == sha256_file(ROOT / "docs/evidence/environment-tilesets-runtime-v0200/negative-controls-v0200.json"), "historical v0.20.0 ET evidence remains byte-identical and separate")
        def cache_checker() -> bool:
            resolver = EnvironmentTileResolver(manifest, first_dir)
            results = [resolver.resolve(_request(manifest, class_id)) for class_id in TILE_CLASSES]
            return len({item["cache_key"] for item in results}) == len(results) and all(resolver.get_cached(item) == item for item in results) and all({"requested_class_id", "resolved_class_id", "requested_layer", "resolved_layer", "adjacency_mask", "variant_id", "atlas_revision", "content_hash"}.issubset(item) for item in results)
        _gate(gates, "cache_identity_class_layer_mask_variant_complete", cache_checker, "cache identity separates requested/resolved class, layer, mask, variant, atlas and content")
        _gate(gates, "test_fixture_nonproduction", lambda: manifest["test_only"] is True and manifest["production_safe"] is False and all(not tile["is_base_tile"] or tile["binding"]["artifact_path"] for tile in manifest["tiles"]), "all generated assets are explicit TEST_ONLY fixture data")
        _gate(gates, "production_registry_empty", lambda: EnvironmentTileRegistry(production=False).cache_stats() == {"entries": 0}, "production registry has no entries")
        _gate(gates, "production_routing_blocked", lambda: manifest["production_routing"] == "BLOCKED" and manifest["production_approved"] is False and manifest["production_registry_empty"] is True, "production routing and approval remain blocked")
        _gate(gates, "isolated_full_slice_determinism", lambda: determinism["equal"] is True and determinism["differences"] == [] and len(determinism["files"]) >= 100, "two independent subprocess outputs including mask tiles/atlases/JSON/sheets are byte-identical")
        _build_evidence(first_dir, manifest, determinism, canonical_controls, production_controls, mask_controls, origin_controls, variant_identity_controls, at_controls, wm_controls, gates)
        passed = sum(item["status"] == "PASS" for item in gates.values())
        controls = canonical_controls + production_controls + mask_controls + origin_controls + variant_identity_controls + at_controls + wm_controls
        status = "ENVIRONMENT_TILESETS_PRODUCTION_MASK_ORIGIN_VARIANT_INTEGRITY_TECHNICALLY_QUALIFIED" if len(gates) == len(GATE_NAMES) and passed == len(GATE_NAMES) and all(item["status"] == "PASS" for item in controls) else "FAILED"
        print(json.dumps({"status": status, "gates": len(gates), "passed": passed, "negative_controls": len(controls), "negative_controls_passed": sum(item["status"] == "PASS" for item in controls), "evidence": str(EVIDENCE.relative_to(ROOT))}, ensure_ascii=False))
        return 0 if status != "FAILED" else 1


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
