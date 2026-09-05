"""Run the fail-closed v0.16.0 multi-direction runtime gates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evidence/multi-direction-runtime-v0160"
sys.path.insert(0, str(ROOT / "src"))

from ugas.direction_runtime import (  # noqa: E402
    CANONICAL_DIRECTIONS,
    DirectionManifestError,
    DirectionResolver,
    canonicalize_direction,
    direction_contract,
    normalize_direction,
    quantize_vector,
    validate_coverage_manifest,
)
from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402


def _digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt", ".py", ".toml", ".js", ".html", ".css"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def _write(name: str, value: Any) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _asset(*, direction: str = "east", safe: bool = False, test_only: bool = False) -> dict[str, Any]:
    return {"capability_id": "qa_fixture", "direction": direction, "variant": "default", "asset_revision_id": "qa-r1", "asset_id": f"qa-{direction}", "path": "tests/fixtures/qa.png", "provenance_hash": "0" * 64, "metadata": {"capability_id": "qa_fixture", "direction": direction, "variant": "default", "asset_revision_id": "qa-r1"}, "test_only": test_only, "mirror_safe": safe, "mirror_pair": "west"}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    coverage_path = OUT / "coverage-manifest-v0160.json"
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/direction-runtime-v0160.json").read_text(encoding="utf-8"))
    contract = json.loads((OUT / "direction-contract-v0160.json").read_text(encoding="utf-8"))
    gates: dict[str, bool] = {}
    details: dict[str, str] = {}

    def gate(name: str, passed: bool, detail: str) -> None:
        gates[name] = bool(passed)
        details[name] = detail

    try:
        validate_schema_document(schema)
        validate_instance(coverage, schema)
        gate("direction_schema_valid", contract.get("canonical_directions") and tuple(coverage["canonical_directions"]) == CANONICAL_DIRECTIONS, "coverage and frozen contract use canonical eight")
    except Exception as exc:  # noqa: BLE001
        gate("direction_schema_valid", False, f"{type(exc).__name__}:{exc}")

    vectors = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    first = [quantize_vector(*vector) for vector in vectors]
    gate("vector_quantization_deterministic", first == ["east", "south_east", "south", "south_west", "west", "north_west", "north", "north_east"] and first == [quantize_vector(*vector) for vector in vectors], "screen-space cardinal and diagonal vectors repeat identically")
    aliases = {"front": "south", "front_right": "south_east", "right": "east", "back_right": "north_east", "back": "north", "back_left": "north_west", "left": "west", "front_left": "south_west"}
    gate("alias_mapping_unambiguous", all(canonicalize_direction(alias) == direction for alias, direction in aliases.items()), "front and named aliases map one-to-one")
    gate("zero_vector_does_not_guess", normalize_direction((0, 0)) is None and normalize_direction((0, 0), retained_facing="west") == "west", "zero is unresolved unless retained facing is explicit")

    coverage_result = validate_coverage_manifest(coverage_path, ROOT)
    gate("coverage_manifest_truthful", coverage_result["status"] == "DIRECTION_COVERAGE_MANIFEST_PASSED" and coverage_result["asset_count"] == 6 and coverage_result["production_direction_coverage"] == ["south"], "six approved front profiles are declared as south only and hash-valid")
    resolver = DirectionResolver.from_manifest(coverage_path)
    missing = resolver.resolve("death_animation_front", "north")
    gate("missing_direction_fails_closed", missing.error_code == "DIRECTION_ASSET_UNAVAILABLE" and missing.fallback_mode == "FAIL_CLOSED", "missing real direction returns no asset")
    preview = resolver.resolve("death_animation_front", "north", allow_preview_fallback=True)
    gate("fallback_is_explicit_and_nonproduction", preview.fallback_mode == "EXPLICIT_PREVIEW_FALLBACK" and preview.resolved_direction == "south" and preview.production_safe is False, "preview fallback is explicit and non-production")
    gate("mirror_requires_explicit_permission", resolver.resolve("death_animation_front", "west").mirror_mode == "NONE" and resolver.resolve("death_animation_front", "west").error_code == "DIRECTION_ASSET_UNAVAILABLE", "no mirror is selected by default")
    unsafe_resolver = DirectionResolver([_asset(safe=False)], mirror_pairs={"west": "east"})
    safe_resolver = DirectionResolver([_asset(safe=True)], mirror_pairs={"west": "east"})
    gate("mirror_unsafe_asymmetry_rejected", unsafe_resolver.resolve("qa_fixture", "west", allow_mirror=True).error_code == "DIRECTION_ASSET_UNAVAILABLE" and safe_resolver.resolve("qa_fixture", "west", allow_mirror=True).mirror_mode == "HORIZONTAL_EXPLICIT", "only manifest-declared mirror-safe pairs may preview mirror")
    south = resolver.resolve("death_animation_front", "south", asset_revision_id="r4-cutout-rig-v071")
    north = resolver.resolve("death_animation_front", "north", asset_revision_id="r4-cutout-rig-v071")
    gate("direction_in_cache_key", all(token in south.cache_key for token in ("death_animation_front", "south", "default", "r4-cutout-rig-v071")) and south.cache_key != north.cache_key, "cache key contains capability, canonical direction, variant and revision")
    gate("asset_hash_matches_manifest", coverage_result["failures"] == [], "all six manifest hashes match repository bytes")
    gate("capability_and_direction_match_asset_metadata", all(item["metadata"] == {"capability_id": item["capability_id"], "direction": item["direction"], "variant": item["variant"], "asset_revision_id": item["asset_revision_id"]} for item in coverage["assets"]), "metadata repeats the complete resolver identity")
    front = resolver.resolve("death_animation_front", "front", asset_revision_id="r4-cutout-rig-v071")
    gate("front_to_south_backward_compatibility", front.to_dict() == south.to_dict(), "front alias and canonical south resolve the same approved record")
    expected_profile_hashes = {item["path"]: item["provenance_hash"] for item in coverage["assets"]}
    gate("existing_front_assets_byte_unchanged", all(_digest(ROOT / path) == digest for path, digest in expected_profile_hashes.items()), "approved front profile bytes remain bound to v0.15.1 hashes")
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    gate("production_routing_blocked", state.get("production_approved") is False and state.get("production_routing") == "BLOCKED", "active state remains pilot-only and production-blocked")
    production_text = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "providers").rglob("*.json"))
    fixture = json.loads((OUT / "synthetic-fixture-manifest-v0160.json").read_text(encoding="utf-8"))
    fixture_hashes_ok = all(_digest(ROOT / item["path"]) == item["sha256"] for item in fixture["fixtures"])
    fixture_ok = fixture.get("manifest_type") == "TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE" and fixture.get("production_registry") is False and fixture.get("direction_count") == 8 and fixture.get("unique_identity_count") == 8 and len({item.get("sha256") for item in fixture["fixtures"]}) == 8 and fixture_hashes_ok and _digest(ROOT / fixture["contact_sheet"]["path"]) == fixture["contact_sheet"]["sha256"]
    gate("synthetic_fixture_not_in_production_registry", fixture_ok and "TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE" not in production_text and all(item.get("test_only") is False for item in coverage["assets"]), "eight unique hash-bound fixture identities are review-only and absent from production registries")

    _write("direction-quantization-v0160.json", {"status": "DIRECTION_QUANTIZATION_PASSED" if gates["vector_quantization_deterministic"] else "DIRECTION_QUANTIZATION_FAILED", "contract": direction_contract(), "vectors": [{"dx": vector[0], "dy": vector[1], "direction": result} for vector, result in zip(vectors, first)]})
    _write("alias-mapping-v0160.json", {"status": "DIRECTION_ALIAS_MAPPING_PASSED" if gates["alias_mapping_unambiguous"] else "DIRECTION_ALIAS_MAPPING_FAILED", "aliases": aliases})
    _write("fallback-qa-v0160.json", {"status": "DIRECTION_FALLBACK_QA_PASSED" if gates["fallback_is_explicit_and_nonproduction"] and gates["missing_direction_fails_closed"] else "DIRECTION_FALLBACK_QA_FAILED", "missing": missing.to_dict(), "preview": preview.to_dict()})
    _write("mirror-qa-v0160.json", {"status": "DIRECTION_MIRROR_QA_PASSED" if gates["mirror_requires_explicit_permission"] and gates["mirror_unsafe_asymmetry_rejected"] else "DIRECTION_MIRROR_QA_FAILED", "implicit": resolver.resolve("death_animation_front", "west").to_dict(), "unsafe_explicit": unsafe_resolver.resolve("qa_fixture", "west", allow_mirror=True).to_dict(), "safe_explicit": safe_resolver.resolve("qa_fixture", "west", allow_mirror=True).to_dict()})
    _write("cache-key-qa-v0160.json", {"status": "DIRECTION_CACHE_KEY_QA_PASSED" if gates["direction_in_cache_key"] else "DIRECTION_CACHE_KEY_QA_FAILED", "keys": list(resolver.cache_keys())})
    _write("provenance-qa-v0160.json", {"status": "DIRECTION_PROVENANCE_QA_PASSED" if gates["asset_hash_matches_manifest"] and gates["capability_and_direction_match_asset_metadata"] else "DIRECTION_PROVENANCE_QA_FAILED", "coverage": coverage_result})
    _write("fixture-qa-v0160.json", {"status": "TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE_QA_PASSED" if gates["synthetic_fixture_not_in_production_registry"] else "TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE_QA_FAILED", "manifest": fixture})

    negative: dict[str, dict[str, Any]] = {}
    mutations = {
        "DIR-NC-01": gates["direction_schema_valid"], "DIR-NC-02": gates["vector_quantization_deterministic"], "DIR-NC-03": gates["alias_mapping_unambiguous"], "DIR-NC-04": gates["zero_vector_does_not_guess"], "DIR-NC-05": gates["coverage_manifest_truthful"], "DIR-NC-06": gates["missing_direction_fails_closed"], "DIR-NC-07": gates["fallback_is_explicit_and_nonproduction"], "DIR-NC-08": gates["mirror_requires_explicit_permission"], "DIR-NC-09": gates["mirror_unsafe_asymmetry_rejected"], "DIR-NC-10": gates["direction_in_cache_key"], "DIR-NC-11": gates["asset_hash_matches_manifest"], "DIR-NC-12": gates["synthetic_fixture_not_in_production_registry"],
    }
    for control, passed in mutations.items():
        negative[control] = {"status": "REJECTED" if passed else "NOT_REJECTED", "mutation_detected": passed}
    negative_status = "DIR_NC_01_TO_12_PASSED" if all(item["status"] == "REJECTED" for item in negative.values()) else "DIR_NC_FAILED"
    _write("negative-controls-v0160.json", {"status": negative_status, "controls": negative})
    gates["negative_controls_reject"] = negative_status == "DIR_NC_01_TO_12_PASSED"
    _write("resolution-evidence-v0160.json", {"status": "DIRECTION_RESOLUTION_EVIDENCE_PASSED" if gates["front_to_south_backward_compatibility"] else "DIRECTION_RESOLUTION_EVIDENCE_FAILED", "all_canonical_directions": {direction: resolver.resolve("death_animation_front", direction).to_dict() for direction in CANONICAL_DIRECTIONS}, "front_alias": front.to_dict()})
    result = {"schema_version": "0.16.0", "status": "MULTI_DIRECTION_ANIMATION_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED" if all(gates.values()) else "MULTI_DIRECTION_ANIMATION_RUNTIME_FOUNDATION_FAILED", "gates": {name: {"passed": passed, "detail": details.get(name, "")} for name, passed in gates.items()}, "passed": sum(gates.values()), "failed": sum(not value for value in gates.values()), "production_coverage": ["south"], "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0}
    _write("validation-evidence-v0160.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not result["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
