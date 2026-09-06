"""Execute the v0.20.3 environment/tilesets QA-governance correction."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from ugas.environment_tileset_governance_v0203 import (  # noqa: E402
    EnvironmentTileRegistry,
    EnvironmentTilesetContractError,
    ProductionRoutingPolicy,
    recompute_manifest_provenance,
    validate_autotile_matrix,
    validate_origin_roundtrips,
    validate_origin_semantics,
    validate_production_tileset_candidate,
)
from ugas.environment_tileset_runtime_v0202 import (  # noqa: E402
    CARDINAL_ONLY,
    CLASS_TO_LAYER,
    EnvironmentTileResolver,
    EnvironmentTilesetContractError as RuntimeContractError,
    ResolverRequest,
    TILE_CLASSES,
    compare_generated_outputs,
    generate_fixture_pack,
    tile_to_world,
    validate_grid_roundtrip,
    validate_metrics,
    validate_tileset_manifest,
    world_to_tile,
    write_json,
)
from ugas.historical_authority_v0203 import build_historical_authority_manifest, validate_historical_preservation  # noqa: E402
from scripts.validation.run_environment_tilesets_runtime_v0202 import _run_canonical_controls  # noqa: E402


EVIDENCE = ROOT / "docs/evidence/environment-tilesets-runtime-v0203"
GATE_NAMES = (
    "tileset_contract_valid",
    "production_semantic_contract_complete",
    "production_boundary_controls_strict",
    "mask_matrix_validator_strict",
    "origin_positive_proofs_strict",
    "origin_negative_controls_strict",
    "historical_authority_bound",
    "historical_preservation_non_tautological",
    "summary_statuses_fail_closed",
    "canonical_et_current_runtime_strict",
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
    except (EnvironmentTilesetContractError, RuntimeContractError) as exc:
        observed = exc.rejection_class
        return {"control": name, "expected_rejection_class": expected, "observed_rejection_class": observed, "status": "PASS" if observed == expected else "FAIL", "detail": exc.detail}
    except Exception as exc:
        return {"control": name, "expected_rejection_class": expected, "observed_rejection_class": type(exc).__name__, "status": "FAIL", "detail": str(exc)}
    return {"control": name, "expected_rejection_class": expected, "observed_rejection_class": None, "status": "FAIL", "detail": "mutation was accepted"}


def _generate_subprocess(output: Path) -> dict[str, Any]:
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--generate", str(output)], cwd=ROOT, capture_output=True, text=True, check=False, timeout=180)
    if result.returncode != 0:
        raise RuntimeError((result.stdout + result.stderr)[-4000:])
    return _load(output / "tileset-manifest-v0202.json")


def _base_tile(manifest: Mapping[str, Any], class_id: str) -> dict[str, Any]:
    return next(tile for tile in manifest["tiles"] if tile["class_id"] == class_id and tile["is_base_tile"])


def _valid_production_candidate(manifest: Mapping[str, Any]) -> dict[str, Any]:
    candidate = copy.deepcopy(dict(manifest))
    candidate.update({"test_only": False, "production_safe": True, "production_approved": True, "production_routing": "ENABLED", "production_registry_empty": True})
    return recompute_manifest_provenance(candidate)


def _run_production_controls(root: Path, manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    blocked_candidate = _valid_production_candidate(manifest)
    blocked_candidate["production_routing"] = "BLOCKED"
    blocked_candidate = recompute_manifest_provenance(blocked_candidate)
    controls.append(_expect_rejection("PB-NC-01", "PRODUCTION_ROUTING_BLOCKED", lambda: EnvironmentTileRegistry(production=True, production_policy=ProductionRoutingPolicy("BLOCKED"), root=root).register(blocked_candidate)))

    malformed_hash = _valid_production_candidate(manifest)
    malformed_hash["tiles"][0]["binding"]["file_sha256"] = "tampered"
    malformed_hash = recompute_manifest_provenance(malformed_hash)
    controls.append(_expect_rejection("PB-NC-02", "STANDALONE_TILE_BYTES_HASH_MISMATCH", lambda: EnvironmentTileRegistry(production=True, production_policy=ProductionRoutingPolicy("ENABLED"), root=root).register(malformed_hash)))

    controls.append(_expect_rejection("PB-NC-03", "TEST_FIXTURE_IN_PRODUCTION_REGISTRY", lambda: EnvironmentTileRegistry(production=True, production_policy=ProductionRoutingPolicy("BLOCKED"), root=root).register(manifest)))
    enabled_while_blocked = _valid_production_candidate(manifest)
    controls.append(_expect_rejection("PB-NC-04", "PRODUCTION_ROUTING_BLOCKED", lambda: EnvironmentTileRegistry(production=True, production_policy=ProductionRoutingPolicy("BLOCKED"), root=root).register(enabled_while_blocked)))

    malformed_layer = _valid_production_candidate(manifest)
    malformed_layer["terrain_families"][0]["autotile_variants"][0]["target_layer_role"] = "structure"
    malformed_layer = recompute_manifest_provenance(malformed_layer)
    controls.append(_expect_rejection("PB-NC-05", "AUTOTILE_VARIANT_CLASS_MISMATCH", lambda: EnvironmentTileRegistry(production=True, production_policy=ProductionRoutingPolicy("ENABLED"), root=root).register(malformed_layer)))

    positive_candidate = _valid_production_candidate(manifest)
    try:
        validation = validate_production_tileset_candidate(root, positive_candidate, ProductionRoutingPolicy("ENABLED"))
        isolated_registry = EnvironmentTileRegistry(production=True, production_policy=ProductionRoutingPolicy("ENABLED"), root=root)
        isolated_registry.register(positive_candidate)
        positive = {"control": "PB-POS-01", "status": "PASS" if validation.get("status") == "PRODUCTION_CANDIDATE_VALID" and isolated_registry.cache_stats() == {"entries": 1} else "FAIL", "validation": validation, "isolated_registry_entries": isolated_registry.cache_stats()["entries"]}
    except Exception as exc:
        positive = {"control": "PB-POS-01", "status": "FAIL", "observed_rejection_class": getattr(exc, "rejection_class", type(exc).__name__), "detail": str(exc)}
    return controls, positive


def _run_matrix_controls(manifest: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    matrix = validate_autotile_matrix(manifest)
    controls: list[dict[str, Any]] = []
    value = copy.deepcopy(manifest)
    value["terrain_families"][0]["autotile_variants"].pop()
    controls.append(_expect_rejection("MC-NC-05", "AUTOTILE_MATRIX_INCOMPLETE", lambda: validate_autotile_matrix(value)))
    return matrix, controls


def _run_origin_controls(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    metrics = manifest["metrics"]
    positive: list[dict[str, Any]] = []
    negative: list[dict[str, Any]] = []
    try:
        result = validate_origin_semantics(tile_to_world, metrics)
        positive.append({"control": "OR-POS-01", "status": "PASS" if result.get("status") == "ORIGIN_SEMANTICS_DISTINCT" else "FAIL", "result": result})
    except Exception as exc:
        positive.append({"control": "OR-POS-01", "status": "FAIL", "detail": str(exc)})
    try:
        results = []
        for origin in ("TOP_LEFT", "CENTER"):
            for orientation in ("Y_DOWN", "Y_UP"):
                candidate = dict(metrics)
                candidate.update({"origin": origin, "grid_orientation": orientation})
                results.append(validate_origin_roundtrips(candidate, [(0, 0), (1, 1), (-2, 3)]))
        positive.append({"control": "OR-POS-02", "status": "PASS" if len(results) == 4 and all(item.get("status") == "GRID_ORIGIN_ROUNDTRIPS_VALID" for item in results) else "FAIL", "results": results})
    except Exception as exc:
        positive.append({"control": "OR-POS-02", "status": "FAIL", "detail": str(exc)})

    unknown = dict(metrics)
    unknown["origin"] = "UNKNOWN"
    negative.append(_expect_rejection("OR-NC-01", "ORIGIN_CONVENTION_UNSUPPORTED", lambda: validate_metrics(unknown)))

    def broken_origin_transform(x: int, y: int, value: Mapping[str, Any]) -> tuple[float, float]:
        ignored = dict(value)
        ignored["origin"] = "TOP_LEFT"
        return tile_to_world(x, y, ignored)

    negative.append(_expect_rejection("OR-NC-02", "ORIGIN_SEMANTICS_IGNORED", lambda: validate_origin_semantics(broken_origin_transform, metrics)))

    def broken_inverse(world_x: float, world_y: float, value: Mapping[str, Any]) -> tuple[int, int]:
        observed = world_to_tile(world_x, world_y, value)
        return (observed[0] + 1, observed[1])

    negative.append(_expect_rejection("OR-NC-03", "GRID_ORIGIN_ROUNDTRIP_FAILED", lambda: validate_origin_roundtrips(dict(metrics, origin="CENTER"), [(0, 0), (1, 1)], inverse=broken_inverse)))
    return positive, negative


def _gate(gates: dict[str, dict[str, Any]], name: str, checker: Callable[[], Any], assertion: str) -> None:
    try:
        observed = checker()
        passed = bool(observed)
        gates[name] = {"status": "PASS" if passed else "FAIL", "checker": getattr(checker, "__name__", "explicit_checker"), "assertion": assertion, "observed": observed}
    except Exception as exc:
        gates[name] = {"status": "FAIL", "checker": getattr(checker, "__name__", "explicit_checker"), "assertion": assertion, "observed": {"error_class": type(exc).__name__, "detail": str(exc)}}


def _summary(name: str, result: Mapping[str, Any], expected_status: str) -> dict[str, Any]:
    passed = result.get("status") == expected_status
    return {"name": name, "status": "PASS" if passed else "FAIL", "expected_status": expected_status, "observed_status": result.get("status"), "source_result": dict(result)}


def _copy_fixture(first_dir: Path) -> None:
    if EVIDENCE.exists():
        shutil.rmtree(EVIDENCE)
    EVIDENCE.mkdir(parents=True)
    shutil.copytree(first_dir, EVIDENCE / "fixture")
    shutil.copy2(first_dir / "mask-qa-sheet-v0202.png", EVIDENCE / "mask-qa-sheet-v0203.png")
    shutil.copy2(first_dir / "seam-qa-sheet-v0202.png", EVIDENCE / "seam-qa-sheet-v0203.png")


def _mutated_authority_control(authority: Mapping[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ugas-v0203-history-") as directory:
        root = Path(directory)
        for binding in authority["authorities"].values():
            for record in binding["records"]:
                source = ROOT / record["path"]
                target = root / record["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        target_record = authority["authorities"]["v0202_evidence_root"]["records"][0]
        target = root / target_record["path"]
        target.write_bytes(target.read_bytes() + b"mutation")
        result = validate_historical_preservation(root, authority)
        return {"control": "HP-NC-01", "expected": "FAIL_ON_BOUND_HISTORY_MUTATION", "observed_status": result.get("status"), "status": "PASS" if result.get("status") == "FAIL" else "FAIL", "failures": result.get("failures", [])}


def _build_evidence(first_dir: Path, manifest: dict[str, Any], determinism: dict[str, Any], et_controls: list[dict[str, Any]], production_controls: list[dict[str, Any]], production_positive: dict[str, Any], matrix: dict[str, Any], matrix_controls: list[dict[str, Any]], origin_positive: list[dict[str, Any]], origin_negative: list[dict[str, Any]], authority: dict[str, Any], preservation: dict[str, Any], mutation_control: dict[str, Any], gates: dict[str, dict[str, Any]]) -> None:
    _copy_fixture(first_dir)
    write_json(EVIDENCE / "tileset-contract-v0203.json", {"schema_version": "0.20.3", "runtime_schema_version": manifest["schema_version"], "metrics": manifest["metrics"], "classes": manifest["classes"], "layers": manifest["layers"], "layer_order": manifest["layer_order"]})
    write_json(EVIDENCE / "production-semantic-contract-v0203.json", {"schema_version": "0.20.3", "runtime_schema_version": manifest["schema_version"], "status": "PASS" if production_positive.get("status") == "PASS" else "FAIL", "shared_semantic_core": "validate_tileset_manifest", "candidate_validation": production_positive})
    production_summary = _summary("production_boundary", {"status": "PASS" if all(item.get("status") == "PASS" for item in production_controls) and production_positive.get("status") == "PASS" else "FAIL", "controls": production_controls, "positive": production_positive}, "PASS")
    write_json(EVIDENCE / "production-boundary-qa-v0203.json", {"schema_version": "0.20.3", "status": production_summary["status"], "controls": production_controls, "isolated_positive_candidate_validation": production_positive})
    matrix_summary = _summary("mask_matrix", matrix, "AUTOTILE_MATRIX_VALID")
    write_json(EVIDENCE / "mask-matrix-validator-v0203.json", {"schema_version": "0.20.3", "status": "PASS" if matrix_summary["status"] == "PASS" and all(item.get("status") == "PASS" for item in matrix_controls) else "FAIL", "validator_result": matrix, "negative_controls": matrix_controls})
    write_json(EVIDENCE / "origin-positive-proofs-v0203.json", {"schema_version": "0.20.3", "status": "PASS" if all(item.get("status") == "PASS" for item in origin_positive) else "FAIL", "proofs": origin_positive})
    write_json(EVIDENCE / "origin-negative-controls-v0203.json", {"schema_version": "0.20.3", "status": "PASS" if all(item.get("status") == "PASS" and item.get("observed_rejection_class") == item.get("expected_rejection_class") for item in origin_negative) else "FAIL", "controls": origin_negative})
    write_json(EVIDENCE / "historical-authority-manifest-v0203.json", authority)
    write_json(EVIDENCE / "historical-preservation-v0203.json", {"schema_version": "0.20.3", "status": "PASS" if preservation.get("status") == "PASS" and mutation_control.get("status") == "PASS" else "FAIL", "current_vs_immutable_authority": preservation, "mutation_control": mutation_control})
    summary_results = [production_summary, matrix_summary, _summary("origin_positive", {"status": "PASS" if all(item.get("status") == "PASS" for item in origin_positive) else "FAIL"}, "PASS"), _summary("historical_preservation", {"status": preservation.get("status")}, "PASS"), _summary("historical_mutation_control", mutation_control, "PASS")]
    write_json(EVIDENCE / "summary-integrity-v0203.json", {"schema_version": "0.20.3", "status": "PASS" if all(item.get("status") == "PASS" for item in summary_results) else "FAIL", "summaries": summary_results, "rule": "summary status is derived from the underlying result object; missing proof is FAIL"})
    write_json(EVIDENCE / "canonical-et-current-runtime-v0203.json", {"schema_version": "0.20.3", "runtime_schema_version": manifest["schema_version"], "status": "PASS" if len(et_controls) == 18 and all(item.get("status") == "PASS" for item in et_controls) else "FAIL", "controls": et_controls})
    write_json(EVIDENCE / "full-slice-two-run-determinism-v0203.json", {"schema_version": "0.20.3", "status": "PASS" if determinism.get("equal") is True and determinism.get("differences") == [] else "FAIL", **determinism})
    write_json(EVIDENCE / "production-registry-v0203.json", {"schema_version": "0.20.3", "status": "PRODUCTION_REGISTRY_EMPTY", "entries": [], "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0})
    write_json(EVIDENCE / "test-only-qa-board-v0203.json", {"schema_version": "0.20.3", "label": "TEST_ONLY_TILE_QA_BOARD_V0203", "runtime_fixture_schema": manifest["schema_version"], "production_registry": [], "status": "TEST_ONLY"})
    write_json(EVIDENCE / "gate-specific-proof-v0203.json", {"schema_version": "0.20.3", "status": "PASS" if set(gates) == set(GATE_NAMES) and all(item.get("status") == "PASS" for item in gates.values()) else "FAIL", "gates": gates})
    write_json(EVIDENCE / "hard-gates-v0203.json", {"schema_version": "0.20.3", "status": "PASS" if set(gates) == set(GATE_NAMES) and all(item.get("status") == "PASS" for item in gates.values()) else "FAIL", "gates": gates})
    all_controls = et_controls + production_controls + matrix_controls + origin_negative
    write_json(EVIDENCE / "negative-controls-v0203.json", {"schema_version": "0.20.3", "status": "PASS" if all(item.get("status") == "PASS" for item in all_controls) else "FAIL", "canonical_et": et_controls, "production_boundary": production_controls, "mask_matrix": matrix_controls, "origin": origin_negative})
    write_json(EVIDENCE / "v0202-rejection-correction-record-v0203.json", {"schema_version": "0.20.3", "status": "CORRECTION_REQUIRED", "rejected_version": "0.20.2", "correction_version": "0.20.3", "rejected_reviewed_head": "6022cf3c6158ebb762519a04e79ed42378438ccc", "historical_evidence_root": "docs/evidence/environment-tilesets-runtime-v0202/", "historical_evidence_unchanged": True, "correction_evidence_root": "docs/evidence/environment-tilesets-runtime-v0203/", "correction_reasons": ["production semantic validation was shallow and did not share the complete TEST_ONLY semantic core", "manual production, mask-matrix and origin negative controls could report false green", "historical preservation checks were tautological or lacked fixed Git authority", "summary status fields were not fail-closed from underlying checker results"], "forward_only": True, "production_routing": "BLOCKED", "production_approved": False, "new_generation": 0})
    write_json(EVIDENCE / "execution-evidence-v0203.json", {"schema_version": "0.20.3", "status": "ENVIRONMENT_TILESETS_QA_GOVERNANCE_INTEGRITY_TECHNICALLY_QUALIFIED" if all(item.get("status") == "PASS" for item in gates.values()) and all(item.get("status") == "PASS" for item in all_controls) else "ENVIRONMENT_TILESETS_V0203_FAILED", "gates": gates, "negative_controls": {"ET_NC_01_TO_18_CURRENT_RUNTIME_PASSED": all(item.get("status") == "PASS" for item in et_controls), "PB_NC_01_TO_05_PASSED": all(item.get("status") == "PASS" for item in production_controls), "MC_NC_05_PASSED": all(item.get("status") == "PASS" for item in matrix_controls), "OR_NC_01_TO_03_PASSED": all(item.get("status") == "PASS" for item in origin_negative)}, "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0, "maps_minimap_started": False})


def execute() -> int:
    with tempfile.TemporaryDirectory(prefix="ugas-v0203-first-") as first_temp, tempfile.TemporaryDirectory(prefix="ugas-v0203-second-") as second_temp:
        first_dir, second_dir = Path(first_temp), Path(second_temp)
        manifest = _generate_subprocess(first_dir)
        _generate_subprocess(second_dir)
        determinism = compare_generated_outputs(first_dir, second_dir)
        validate_tileset_manifest(first_dir, manifest)
        et_controls = _run_canonical_controls(first_dir, manifest)
        production_controls, production_positive = _run_production_controls(first_dir, manifest)
        matrix, matrix_controls = _run_matrix_controls(manifest)
        origin_positive, origin_negative = _run_origin_controls(manifest)
        authority = build_historical_authority_manifest(ROOT)
        preservation = validate_historical_preservation(ROOT, authority)
        mutation_control = _mutated_authority_control(authority)
        gates: dict[str, dict[str, Any]] = {}
        _gate(gates, "tileset_contract_valid", lambda: validate_tileset_manifest(first_dir, manifest).get("status") == "ENVIRONMENT_TILESET_MANIFEST_VALID", "v0.20.2 semantic tile contract remains valid as the shared runtime core")
        _gate(gates, "production_semantic_contract_complete", lambda: production_positive.get("status") == "PASS", "isolated ENABLED test policy validates a complete production-shaped candidate through shared semantics")
        _gate(gates, "production_boundary_controls_strict", lambda: len(production_controls) == 5 and all(item.get("status") == "PASS" and item.get("observed_rejection_class") == item.get("expected_rejection_class") for item in production_controls), "PB-NC-01..05 traverse real production boundary rejection paths")
        _gate(gates, "mask_matrix_validator_strict", lambda: matrix.get("status") == "AUTOTILE_MATRIX_VALID" and len(matrix_controls) == 1 and matrix_controls[0].get("status") == "PASS" and matrix_controls[0].get("observed_rejection_class") == matrix_controls[0].get("expected_rejection_class"), "the same dedicated matrix validator powers the hard gate and MC-NC-05")
        _gate(gates, "origin_positive_proofs_strict", lambda: len(origin_positive) == 2 and all(item.get("status") == "PASS" for item in origin_positive), "positive origin proofs are separate from negative controls")
        _gate(gates, "origin_negative_controls_strict", lambda: len(origin_negative) == 3 and all(item.get("status") == "PASS" and item.get("observed_rejection_class") == item.get("expected_rejection_class") for item in origin_negative), "OR-NC-01..03 inject broken origin behavior and observe exact rejection classes")
        _gate(gates, "historical_authority_bound", lambda: authority.get("status") == "IMMUTABLE_AUTHORITY_BOUND" and all(binding.get("records") for binding in authority.get("authorities", {}).values()), "historical proof is bound to fixed rejected Git heads and blob/SHA records")
        _gate(gates, "historical_preservation_non_tautological", lambda: preservation.get("status") == "PASS" and mutation_control.get("status") == "PASS", "current historical bytes match external authority and a bound mutation fails the validator")
        summary_probe = {"status": "PASS" if production_positive.get("status") == "PASS" and matrix.get("status") == "AUTOTILE_MATRIX_VALID" and preservation.get("status") == "PASS" and mutation_control.get("status") == "PASS" else "FAIL"}
        _gate(gates, "summary_statuses_fail_closed", lambda: summary_probe.get("status") == "PASS", "summary evidence is derived from explicit underlying result objects")
        _gate(gates, "canonical_et_current_runtime_strict", lambda: len(et_controls) == 18 and all(item.get("status") == "PASS" and item.get("observed_rejection_class") == item.get("expected_rejection_class") for item in et_controls), "ET-NC-01..18 are re-executed against the current v0.20.2 runtime")
        _gate(gates, "test_fixture_nonproduction", lambda: manifest.get("test_only") is True and manifest.get("production_safe") is False and manifest.get("production_routing") == "BLOCKED", "generated fixture remains TEST_ONLY")
        _gate(gates, "production_registry_empty", lambda: EnvironmentTileRegistry(production=False).cache_stats() == {"entries": 0}, "real production registry remains empty")
        _gate(gates, "production_routing_blocked", lambda: manifest.get("production_routing") == "BLOCKED" and manifest.get("production_approved") is False, "real system production routing remains BLOCKED")
        _gate(gates, "isolated_full_slice_determinism", lambda: determinism.get("equal") is True and determinism.get("differences") == [] and len(determinism.get("files", [])) >= 100, "independent fixture outputs are byte-identical")
        _build_evidence(first_dir, manifest, determinism, et_controls, production_controls, production_positive, matrix, matrix_controls, origin_positive, origin_negative, authority, preservation, mutation_control, gates)
        all_controls = et_controls + production_controls + matrix_controls + origin_negative
        passed = sum(item.get("status") == "PASS" for item in gates.values())
        status = "ENVIRONMENT_TILESETS_QA_GOVERNANCE_INTEGRITY_TECHNICALLY_QUALIFIED" if len(gates) == len(GATE_NAMES) and passed == len(GATE_NAMES) and all(item.get("status") == "PASS" for item in all_controls) else "FAILED"
        print(json.dumps({"status": status, "gates": len(gates), "passed": passed, "negative_controls": len(all_controls), "negative_controls_passed": sum(item.get("status") == "PASS" for item in all_controls), "evidence": str(EVIDENCE.relative_to(ROOT))}, ensure_ascii=False))
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
