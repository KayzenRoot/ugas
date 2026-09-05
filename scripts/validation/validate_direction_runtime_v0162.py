"""Run the real, fail-closed v0.16.2 direction cache/state correction gates."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evidence/multi-direction-runtime-v0162"
sys.path.insert(0, str(ROOT / "src"))

from ugas.direction_runtime import (  # noqa: E402
    CANONICAL_DIRECTIONS,
    DirectionManifestError,
    DirectionResolver,
    canonicalize_direction,
    direction_contract,
    normalize_direction,
    normalize_direction_result,
    quantize_vector,
    validate_coverage_manifest,
)
from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402
from ugas.state_consistency_v0162 import validate_state_consistency  # noqa: E402


def _digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt", ".py", ".toml", ".js", ".html", ".css"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def _write(name: str, value: Any) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _asset(*, direction: str = "east", safe: bool = False, test_only: bool = False) -> dict[str, Any]:
    return {
        "capability_id": "qa_fixture",
        "direction": direction,
        "variant": "default",
        "asset_revision_id": "qa-r1",
        "asset_id": f"qa-{direction}",
        "path": "tests/fixtures/qa.png",
        "provenance_hash": "0" * 64,
        "metadata": {"capability_id": "qa_fixture", "direction": direction, "variant": "default", "asset_revision_id": "qa-r1"},
        "test_only": test_only,
        "mirror_safe": safe,
        "mirror_pair": "west",
    }


def _observed(*, result: Any = None, error_code: str | None = None, **details: Any) -> dict[str, Any]:
    value = {"result": result, "error_code": error_code}
    value.update(details)
    return value


def _control(mutation: str, target_gate: str, observed: dict[str, Any], rejected: bool) -> dict[str, Any]:
    return {"mutation": mutation, "target_gate": target_gate, "observed": observed, "rejected": rejected, "status": "REJECTED" if rejected else "NOT_REJECTED"}


def _carry_forward(source: Path) -> dict[str, str]:
    return {"path": source.relative_to(ROOT).as_posix(), "sha256": _digest(source)}


def _prepare_forward_evidence() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_dir = ROOT / "docs/evidence/multi-direction-runtime-v0161"
    source_coverage_path = source_dir / "coverage-manifest-v0161.json"
    source_contract_path = source_dir / "direction-contract-v0161.json"
    source_fixture_path = source_dir / "synthetic-fixture-manifest-v0161.json"

    coverage = copy.deepcopy(json.loads(source_coverage_path.read_text(encoding="utf-8")))
    coverage["schema_version"] = "0.16.2"
    coverage["carried_forward_from"] = _carry_forward(source_coverage_path)
    _write("coverage-manifest-v0162.json", coverage)

    contract = copy.deepcopy(json.loads(source_contract_path.read_text(encoding="utf-8")))
    contract["schema_version"] = "0.16.2"
    contract["status"] = "CACHE_AND_STATE_CORRECTION_TECHNICALLY_QUALIFIED"
    contract["cache_identity"] = {
        "unresolved_class_in_key": True,
        "classes": ["UNKNOWN_DIRECTION_UNRESOLVED", "ZERO_VECTOR_UNRESOLVED", "INVALID_VECTOR_UNRESOLVED"],
        "unresolved_results_cached": True,
    }
    contract["cache_mode"] = {"request_mode": ["direct", "preview:0:1", "preview:1:0", "preview:1:1"], "registry_mode": ["production", "test"]}
    contract["carried_forward_from"] = _carry_forward(source_contract_path)
    _write("direction-contract-v0162.json", contract)

    fixture = copy.deepcopy(json.loads(source_fixture_path.read_text(encoding="utf-8")))
    fixture["schema_version"] = "0.16.2"
    fixture["carried_forward_from"] = _carry_forward(source_fixture_path)
    _write("synthetic-fixture-manifest-v0162.json", fixture)
    return coverage, contract, fixture


def _cache_sequence(resolver: DirectionResolver, first_label: str, first_input: Any, second_label: str, second_input: Any) -> dict[str, Any]:
    resolver.clear_cache()
    first = resolver.resolve("death_animation_front", first_input)
    after_first = resolver.cache_stats()
    second = resolver.resolve("death_animation_front", second_input)
    after_second = resolver.cache_stats()
    return {
        "request_order": [first_label, second_label],
        "results": [first.to_dict(), second.to_dict()],
        "cache_keys": list(resolver.cache_keys()),
        "cache_stats_after_first": after_first,
        "cache_stats_after_second": after_second,
        "observed_second_outcome": second.fallback_mode,
        "observed_second_error_code": second.error_code,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    coverage, contract, fixture = _prepare_forward_evidence()
    coverage_path = OUT / "coverage-manifest-v0162.json"
    schema = json.loads((ROOT / "schemas/direction-runtime-v0162.json").read_text(encoding="utf-8"))
    gates: dict[str, bool] = {}
    details: dict[str, str] = {}

    def gate(name: str, passed: bool, detail: str) -> None:
        gates[name] = bool(passed)
        details[name] = detail

    try:
        validate_schema_document(schema)
        validate_instance(coverage, schema)
        gate("direction_schema_valid", contract.get("canonical_directions") and tuple(coverage["canonical_directions"]) == CANONICAL_DIRECTIONS, "forward manifest and frozen contract use canonical eight")
    except Exception as exc:  # noqa: BLE001
        gate("direction_schema_valid", False, f"{type(exc).__name__}:{exc}")

    vectors = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    first = [quantize_vector(*vector) for vector in vectors]
    gate("vector_quantization_deterministic", first == ["east", "south_east", "south", "south_west", "west", "north_west", "north", "north_east"] and first == [quantize_vector(*vector) for vector in vectors], "screen-space cardinal and diagonal vectors repeat identically")
    aliases = {"front": "south", "front_right": "south_east", "right": "east", "back_right": "north_east", "back": "north", "back_left": "north_west", "left": "west", "front_left": "south_west"}
    gate("alias_mapping_unambiguous", all(canonicalize_direction(alias) == direction for alias, direction in aliases.items()), "front and named aliases map one-to-one")
    retained = normalize_direction_result((0, 0), retained_facing="west")
    gate("zero_vector_does_not_guess", normalize_direction((0, 0)) is None and retained.direction == "west" and retained.outcome == "ZERO_VECTOR_RETAINED_FACING", "only finite numeric zero may use explicit retained facing")
    invalid_cases = [(math.nan, 0), (math.inf, 0), (-math.inf, 0), ("1", 0), {"dx": 1}, (1, 0, 2)]
    gate("invalid_vectors_never_retain", all(normalize_direction_result(value, retained_facing="west").outcome == "INVALID_VECTOR_UNRESOLVED" for value in invalid_cases), "non-finite, nonnumeric, missing and malformed vectors stay invalid even with retained facing")

    coverage_result = validate_coverage_manifest(coverage_path, ROOT)
    gate("coverage_manifest_truthful", coverage_result["status"] == "DIRECTION_COVERAGE_MANIFEST_PASSED" and coverage_result["asset_count"] == 6 and coverage_result["production_direction_coverage"] == ["south"], "six approved front profiles are carried forward as south-only and hash-valid")
    resolver = DirectionResolver.from_manifest(coverage_path)
    missing = resolver.resolve("death_animation_front", "north")
    gate("missing_direction_fails_closed", missing.error_code == "DIRECTION_ASSET_UNAVAILABLE" and missing.fallback_mode == "FAIL_CLOSED", "missing real direction returns no asset")
    preview = resolver.resolve("death_animation_front", "north", allow_preview_fallback=True)
    gate("fallback_is_explicit_and_nonproduction", preview.fallback_mode == "EXPLICIT_PREVIEW_FALLBACK" and preview.resolved_direction == "south" and preview.production_safe is False, "preview fallback is explicit and non-production")
    implicit_mirror = resolver.resolve("death_animation_front", "west")
    gate("mirror_requires_explicit_permission", implicit_mirror.mirror_mode == "NONE" and implicit_mirror.error_code == "DIRECTION_ASSET_UNAVAILABLE", "no mirror is selected by default")
    unsafe_resolver = DirectionResolver([_asset(safe=False)], mirror_pairs={"west": "east"})
    safe_resolver = DirectionResolver([_asset(safe=True)], mirror_pairs={"west": "east"})
    unsafe_mirror = unsafe_resolver.resolve("qa_fixture", "west", allow_mirror=True)
    safe_mirror = safe_resolver.resolve("qa_fixture", "west", allow_mirror=True)
    gate("mirror_unsafe_asymmetry_rejected", unsafe_mirror.error_code == "DIRECTION_ASSET_UNAVAILABLE" and safe_mirror.mirror_mode == "HORIZONTAL_EXPLICIT", "only manifest-declared mirror-safe pairs may preview mirror")
    south = resolver.resolve("death_animation_front", "south", asset_revision_id="r4-cutout-rig-v071")
    north = resolver.resolve("death_animation_front", "north", asset_revision_id="r4-cutout-rig-v071")
    gate("direction_in_cache_key", all(token in south.cache_key for token in ("death_animation_front", "south", "default", "r4-cutout-rig-v071")) and south.cache_key != north.cache_key, "cache key contains capability, canonical direction, variant and revision")
    gate("asset_hash_matches_manifest", coverage_result["failures"] == [], "all carried-forward manifest hashes match repository bytes")
    gate("capability_and_direction_match_asset_metadata", all(item["metadata"] == {"capability_id": item["capability_id"], "direction": item["direction"], "variant": item["variant"], "asset_revision_id": item["asset_revision_id"]} for item in coverage["assets"]), "metadata repeats the complete resolver identity")
    front = resolver.resolve("death_animation_front", "front", asset_revision_id="r4-cutout-rig-v071")
    gate("front_to_south_backward_compatibility", front.to_dict() == south.to_dict(), "front alias and canonical south resolve the same approved record")
    expected_profile_hashes = {item["path"]: item["provenance_hash"] for item in coverage["assets"]}
    gate("existing_front_assets_byte_unchanged", all(_digest(ROOT / path) == digest for path, digest in expected_profile_hashes.items()), "approved front profile bytes remain bound to v0.15.1 hashes")

    order_controls = {
        "CACHE-NC-01": _cache_sequence(resolver, "unknown_direction:sideways", "sideways", "invalid_vector:(NaN,0)", {"dx": math.nan, "dy": 0}),
        "CACHE-NC-02": _cache_sequence(resolver, "invalid_vector:(NaN,0)", {"dx": math.nan, "dy": 0}, "unknown_direction:sideways", "sideways"),
        "CACHE-NC-03": _cache_sequence(resolver, "zero_vector:(0,0)", (0, 0), "invalid_vector:(NaN,0)", {"dx": math.nan, "dy": 0}),
        "CACHE-NC-04": _cache_sequence(resolver, "invalid_vector:(NaN,0)", {"dx": math.nan, "dy": 0}, "zero_vector:(0,0)", (0, 0)),
    }
    resolver.clear_cache()
    repeated_first = resolver.resolve("death_animation_front", {"dx": math.nan, "dy": 0})
    stats_after_first = resolver.cache_stats()
    repeated_second = resolver.resolve("death_animation_front", {"dx": math.nan, "dy": 0})
    stats_after_second = resolver.cache_stats()
    order_controls["CACHE-NC-05"] = {
        "request_order": ["invalid_vector:(NaN,0)", "invalid_vector:(NaN,0)"],
        "results": [repeated_first.to_dict(), repeated_second.to_dict()],
        "cache_keys": list(resolver.cache_keys()),
        "cache_stats_after_first": stats_after_first,
        "cache_stats_after_second": stats_after_second,
        "observed_byte_or_field_identical": repeated_first.to_dict() == repeated_second.to_dict(),
    }
    order_pass = {
        "CACHE-NC-01": order_controls["CACHE-NC-01"]["results"][1]["error_code"] == "INVALID_VECTOR_UNRESOLVED",
        "CACHE-NC-02": order_controls["CACHE-NC-02"]["results"][1]["error_code"] == "DIRECTION_UNRESOLVED" and order_controls["CACHE-NC-02"]["results"][1]["fallback_mode"] == "UNRESOLVED",
        "CACHE-NC-03": order_controls["CACHE-NC-03"]["results"][1]["error_code"] == "INVALID_VECTOR_UNRESOLVED",
        "CACHE-NC-04": order_controls["CACHE-NC-04"]["results"][1]["error_code"] == "DIRECTION_UNRESOLVED" and order_controls["CACHE-NC-04"]["results"][1]["fallback_mode"] == "UNRESOLVED",
        "CACHE-NC-05": order_controls["CACHE-NC-05"]["observed_byte_or_field_identical"] and order_controls["CACHE-NC-05"]["cache_stats_after_second"]["hits"] == 1,
    }
    gate("unresolved_cache_class_isolation", all(order_pass.values()) and len({item["results"][1]["cache_key"] for item in order_controls.values() if item["request_order"][0] != "invalid_vector:(NaN,0)" or item["request_order"][1] != "invalid_vector:(NaN,0)"}) >= 2, "order-sensitive unresolved classes retain their semantic outcomes and distinct keys")
    cache_class_keys = {
        "unknown": resolver.resolve("death_animation_front", "sideways").cache_key,
        "zero": resolver.resolve("death_animation_front", (0, 0)).cache_key,
        "invalid": resolver.resolve("death_animation_front", {"dx": math.nan, "dy": 0}).cache_key,
    }
    gate("unresolved_cache_key_is_explicit", all(label.upper() + "_DIRECTION_UNRESOLVED" in key or label.upper() + "_VECTOR_UNRESOLVED" in key for label, key in (("unknown", cache_class_keys["unknown"]), ("zero", cache_class_keys["zero"]), ("invalid", cache_class_keys["invalid"]))), "each unresolved normalization class is visible in its cache identity")

    test_only_asset = _asset(direction="south", test_only=True)
    test_only_resolver = DirectionResolver([test_only_asset], production_registry=False)
    test_only_result = test_only_resolver.resolve("qa_fixture", "south")
    production_resolver = DirectionResolver.from_manifest(coverage_path)
    production_result = production_resolver.resolve("death_animation_front", "south")
    test_mode_pass = (
        test_only_result.production_safe is False
        and "request_mode=direct" in test_only_result.cache_key
        and "registry_mode=test" in test_only_result.cache_key
        and "registry_mode=production" not in test_only_result.cache_key
        and "registry_mode=production" in production_result.cache_key
    )
    gate("test_only_cache_mode_truthful", test_mode_pass, "test-only exact resolution reports direct/test cache context and never production registry mode")
    _write("cache-unresolved-class-qa-v0162.json", {"status": "CACHE_UNRESOLVED_CLASS_QA_PASSED" if gates["unresolved_cache_key_is_explicit"] else "CACHE_UNRESOLVED_CLASS_QA_FAILED", "policy": contract["cache_identity"], "keys": cache_class_keys, "cache_stats": resolver.cache_stats()})
    _write("cache-order-negative-controls-v0162.json", {"status": "CACHE_NC_01_TO_05_PASSED" if all(order_pass.values()) else "CACHE_NC_FAILED", "control_count": 5, "controls": {name: {**record, "rejected": passed, "status": "REJECTED" if passed else "NOT_REJECTED"} for (name, record), passed in zip(order_controls.items(), order_pass.values())}, "method": "each request order is executed against a cleared real resolver and records keys, cache counters and observed second result"})
    _write("test-only-cache-mode-qa-v0162.json", {"status": "TEST_ONLY_CACHE_MODE_QA_PASSED" if test_mode_pass else "TEST_ONLY_CACHE_MODE_QA_FAILED", "non_production_exact": test_only_result.to_dict(), "production_exact": production_result.to_dict(), "policy": {"request_mode": "direct", "test_registry_mode": "test", "production_registry_mode": "production"}, "carried_forward_from": _carry_forward(ROOT / "docs/evidence/multi-direction-runtime-v0161/test-only-production-safety-qa-v0161.json")})

    _write("direction-quantization-v0162.json", {"status": "DIRECTION_QUANTIZATION_PASSED" if gates["vector_quantization_deterministic"] else "DIRECTION_QUANTIZATION_FAILED", "contract": direction_contract(), "vectors": [{"dx": vector[0], "dy": vector[1], "direction": result} for vector, result in zip(vectors, first)], "carried_forward_from": _carry_forward(ROOT / "docs/evidence/multi-direction-runtime-v0161/direction-quantization-v0161.json")})
    _write("alias-mapping-v0162.json", {"status": "DIRECTION_ALIAS_MAPPING_PASSED" if gates["alias_mapping_unambiguous"] else "DIRECTION_ALIAS_MAPPING_FAILED", "aliases": aliases, "carried_forward_from": _carry_forward(ROOT / "docs/evidence/multi-direction-runtime-v0161/alias-mapping-v0161.json")})
    _write("fallback-qa-v0162.json", {"status": "DIRECTION_FALLBACK_QA_PASSED" if gates["fallback_is_explicit_and_nonproduction"] and gates["missing_direction_fails_closed"] else "DIRECTION_FALLBACK_QA_FAILED", "missing": missing.to_dict(), "preview": preview.to_dict(), "carried_forward_from": _carry_forward(ROOT / "docs/evidence/multi-direction-runtime-v0161/fallback-qa-v0161.json")})
    _write("mirror-qa-v0162.json", {"status": "DIRECTION_MIRROR_QA_PASSED" if gates["mirror_requires_explicit_permission"] and gates["mirror_unsafe_asymmetry_rejected"] else "DIRECTION_MIRROR_QA_FAILED", "implicit": implicit_mirror.to_dict(), "unsafe_explicit": unsafe_mirror.to_dict(), "safe_explicit": safe_mirror.to_dict(), "carried_forward_from": _carry_forward(ROOT / "docs/evidence/multi-direction-runtime-v0161/mirror-qa-v0161.json")})
    _write("provenance-qa-v0162.json", {"status": "DIRECTION_PROVENANCE_QA_PASSED" if gates["asset_hash_matches_manifest"] and gates["capability_and_direction_match_asset_metadata"] else "DIRECTION_PROVENANCE_QA_FAILED", "coverage": coverage_result, "carried_forward_from": _carry_forward(ROOT / "docs/evidence/multi-direction-runtime-v0161/provenance-qa-v0161.json")})
    _write("fixture-qa-v0162.json", {"status": "TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE_QA_PASSED" if fixture.get("production_registry") is False else "TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE_QA_FAILED", "manifest": fixture})
    _write("invalid-vector-qa-v0162.json", {"status": "INVALID_VECTOR_QA_PASSED" if gates["invalid_vectors_never_retain"] else "INVALID_VECTOR_QA_FAILED", "retained_facing": "west", "cases": [{"input": label, "result": normalize_direction_result(value, retained_facing="west").to_dict()} for label, value in (("nan", (math.nan, 0)), ("infinity", (math.inf, 0)), ("negative_infinity", (-math.inf, 0)), ("string_component", ("1", 0)), ("missing_component", {"dx": 1}), ("malformed_tuple", (1, 0, 2)))], "zero_vector": retained.to_dict(), "policy": "ZERO_VECTOR_RETAINED_FACING is reserved for finite numeric zero; all invalid vectors use INVALID_VECTOR_UNRESOLVED", "carried_forward_from": _carry_forward(ROOT / "docs/evidence/multi-direction-runtime-v0161/invalid-vector-qa-v0161.json")})
    _write("test-only-production-safety-qa-v0162.json", {"status": "TEST_ONLY_PRODUCTION_SAFETY_QA_PASSED" if test_only_result.production_safe is False else "TEST_ONLY_PRODUCTION_SAFETY_QA_FAILED", "non_production_exact": test_only_result.to_dict(), "production_registry_error": "test_only_fixture_cannot_enter_production_registry"})

    negative: dict[str, dict[str, Any]] = {}
    unknown = resolver.resolve("death_animation_front", "sideways")
    zero_without_retained = resolver.resolve("death_animation_front", (0, 0))
    boundary_actual = quantize_vector(1, math.tan(math.radians(22.5)))
    wrong_direction_assets = copy.deepcopy(coverage["assets"])
    wrong_direction_assets[0]["metadata"]["direction"] = "north"
    wrong_direction_error: str | None = None
    try:
        DirectionResolver(wrong_direction_assets)
    except DirectionManifestError as exc:
        wrong_direction_error = str(exc)
    stale_cache_north = resolver.resolve("death_animation_front", "north", asset_revision_id="r4-cutout-rig-v071")
    invalid_asset_hash = copy.deepcopy(coverage)
    invalid_hash_error: list[str] = []
    with tempfile.TemporaryDirectory(prefix="ugas-v0162-nc-") as directory:
        mutated_manifest = Path(directory) / "coverage-manifest-v0162.json"
        invalid_asset_hash["assets"][0]["provenance_hash"] = "0" * 64
        mutated_manifest.write_text(json.dumps(invalid_asset_hash), encoding="utf-8")
        invalid_hash_error = validate_coverage_manifest(mutated_manifest, ROOT)["failures"]
    capability_assets = copy.deepcopy(coverage["assets"])
    capability_assets[0]["capability_id"] = "wrong_capability"
    capability_error: str | None = None
    try:
        DirectionResolver(capability_assets)
    except DirectionManifestError as exc:
        capability_error = str(exc)
    production_fixture_error: str | None = None
    try:
        DirectionResolver([test_only_asset], production_registry=True)
    except DirectionManifestError as exc:
        production_fixture_error = str(exc)
    state = json.loads((ROOT / "docs/evidence/current-state-v0.16.2.json").read_text(encoding="utf-8"))
    mutated_state = copy.deepcopy(state)
    mutated_state["production_approved"] = True
    mutated_state["production_routing"] = "ENABLED"
    blocked_result = validate_state_consistency(mutated_state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.16.2.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"))
    negative["DIR-NC-01"] = _control("unknown_direction_id=sideways", "normalize_direction/resolve", _observed(result=unknown.to_dict(), error_code=unknown.error_code), unknown.error_code == "DIRECTION_UNRESOLVED" and unknown.fallback_mode == "UNRESOLVED")
    negative["DIR-NC-02"] = _control("zero_vector_without_retained_facing=(0,0)", "zero_vector_policy", _observed(result=zero_without_retained.to_dict(), error_code=zero_without_retained.error_code), zero_without_retained.error_code == "DIRECTION_UNRESOLVED" and zero_without_retained.asset_id is None)
    negative["DIR-NC-03"] = _control("boundary_quantization_wrong_sector=expected east at +22.5 degrees", "deterministic_sector_quantization", _observed(result=boundary_actual, error_code=None, expected_sector="east"), boundary_actual != "east")
    negative["DIR-NC-04"] = _control("silent_front_fallback=request north in production/default resolver", "production_missing_direction", _observed(result=north.to_dict(), error_code=north.error_code), north.error_code == "DIRECTION_ASSET_UNAVAILABLE" and north.resolved_direction is None)
    negative["DIR-NC-05"] = _control("wrong_direction_manifest_binding=metadata direction north for south asset", "manifest_identity", _observed(result=None, error_code=wrong_direction_error), wrong_direction_error == "capability_and_direction_match_asset_metadata")
    negative["DIR-NC-06"] = _control("stale_cache_wrong_direction=resolve south then north", "direction_aware_cache", _observed(result=stale_cache_north.to_dict(), error_code=stale_cache_north.error_code, south_cache_key=south.cache_key, north_cache_key=stale_cache_north.cache_key), stale_cache_north.error_code == "DIRECTION_ASSET_UNAVAILABLE" and south.cache_key != stale_cache_north.cache_key and stale_cache_north.asset_id is None)
    negative["DIR-NC-07"] = _control("mirror_without_permission=request west with allow_mirror=false", "explicit_mirror_policy", _observed(result=implicit_mirror.to_dict(), error_code=implicit_mirror.error_code), implicit_mirror.error_code == "DIRECTION_ASSET_UNAVAILABLE" and implicit_mirror.mirror_mode == "NONE")
    negative["DIR-NC-08"] = _control("asymmetric_fixture_with_mirror_safe=false=request west with mirror", "mirror_safety", _observed(result=unsafe_mirror.to_dict(), error_code=unsafe_mirror.error_code), unsafe_mirror.error_code == "DIRECTION_ASSET_UNAVAILABLE" and unsafe_mirror.mirror_mode == "NONE")
    negative["DIR-NC-09"] = _control("asset_hash_mutation=replace declared hash with zeros", "provenance_hash_validation", _observed(result=invalid_hash_error, error_code="PROVENANCE_HASH_MISMATCH"), bool(invalid_hash_error) and any(item.startswith("hash:") for item in invalid_hash_error))
    negative["DIR-NC-10"] = _control("capability_mismatch=manifest capability wrong_capability with old metadata", "capability_identity", _observed(result=None, error_code=capability_error), capability_error == "capability_and_direction_match_asset_metadata")
    negative["DIR-NC-11"] = _control("test_only_fixture_in_production_registry=test_only=true", "production_registry_boundary", _observed(result=None, error_code=production_fixture_error), production_fixture_error == "test_only_fixture_cannot_enter_production_registry")
    negative["DIR-NC-12"] = _control("production_routing_enabled=production_approved=true,routing=ENABLED", "active_state_production_gate", _observed(result=blocked_result, error_code="production_must_remain_blocked"), blocked_result["status"] == "STATE_CONSISTENCY_FAILED" and "production_must_remain_blocked" in blocked_result["failures"])
    negative_status = "DIR_NC_01_TO_12_PASSED" if all(item["rejected"] for item in negative.values()) else "DIR_NC_FAILED"
    _write("negative-controls-v0162.json", {"status": negative_status, "control_count": len(negative), "controls": negative, "method": "each control constructs or mutates runtime input and records the observed rejection", "carried_forward_from": _carry_forward(ROOT / "docs/evidence/multi-direction-runtime-v0161/negative-controls-v0161.json")})
    gates["negative_controls_reject"] = negative_status == "DIR_NC_01_TO_12_PASSED"
    gate("state_previous_release_truthful", state.get("previous_release", {}).get("version") == "0.15.1" and state.get("correction_history", {}).get("v0.16.0", {}).get("status") == "CORRECTION_REQUIRED" and state.get("correction_history", {}).get("v0.16.1", {}).get("status") == "CORRECTION_REQUIRED", "active state names v0.15.1 as approved previous release and keeps v0.16.0/v0.16.1 separate rejected history")
    gate("production_routing_blocked", state.get("production_approved") is False and state.get("production_routing") == "BLOCKED" and state.get("new_generation") == 0, "active state remains pilot-only, production-blocked and generation-free")
    _write("resolution-evidence-v0162.json", {"status": "DIRECTION_RESOLUTION_EVIDENCE_PASSED" if gates["front_to_south_backward_compatibility"] else "DIRECTION_RESOLUTION_EVIDENCE_FAILED", "all_canonical_directions": {direction: resolver.resolve("death_animation_front", direction).to_dict() for direction in CANONICAL_DIRECTIONS}, "front_alias": front.to_dict(), "carried_forward_from": _carry_forward(ROOT / "docs/evidence/multi-direction-runtime-v0161/resolution-evidence-v0161.json")})
    result = {"schema_version": "0.16.2", "status": "MULTI_DIRECTION_ANIMATION_RUNTIME_CACHE_AND_STATE_INTEGRITY_TECHNICALLY_QUALIFIED" if all(gates.values()) else "MULTI_DIRECTION_ANIMATION_RUNTIME_CACHE_AND_STATE_INTEGRITY_FAILED", "gates": {name: {"passed": passed, "detail": details.get(name, "")} for name, passed in gates.items()}, "passed": sum(gates.values()), "failed": sum(not value for value in gates.values()), "production_coverage": ["south"], "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0, "negative_controls": {"status": negative_status, "count": len(negative)}, "cache_negative_controls": {"status": "CACHE_NC_01_TO_05_PASSED" if all(order_pass.values()) else "CACHE_NC_FAILED", "count": 5}}
    _write("validation-evidence-v0162.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
