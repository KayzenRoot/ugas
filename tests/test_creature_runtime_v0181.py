from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from ugas.creature_runtime_v0181 import CreatureContractError, CreatureRegistry, _record_hash


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/evidence/creatures-monsters-runtime-v0181/creature-runtime-manifest-v0181.json"


class CreatureRuntimeV0181Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not MANIFEST.is_file():
            raise unittest.SkipTest("v0.18.1 fixture manifest not generated yet")
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def registry(self, manifest: dict | None = None) -> CreatureRegistry:
        return CreatureRegistry(copy.deepcopy(manifest or self.manifest))

    def test_all_archetypes_have_eight_unique_direction_identities(self) -> None:
        self.assertEqual(len(self.manifest["creatures"]), 6)
        for creature in self.manifest["creatures"]:
            bindings = creature["direction_bindings"]
            self.assertEqual(len(bindings), 8)
            self.assertEqual(len({item["direction_asset_id"] for item in bindings.values()}), 8)
            self.assertEqual(len({item["direction_content_hash"] for item in bindings.values()}), 8)
            self.assertTrue(all(item["test_only"] and not item["production_safe"] for item in bindings.values()))

    def test_resolver_returns_exact_requested_direction_identity(self) -> None:
        creature = self.manifest["creatures"][0]
        registry = self.registry()
        for direction, binding in creature["direction_bindings"].items():
            result = registry.resolve(creature["creature_id"], creature["variant_lineage"]["variant_id"], direction, "idle")
            self.assertEqual(result.result, "RESOLVED")
            self.assertEqual(result.requested_direction, direction)
            self.assertEqual(result.resolved_direction, direction)
            self.assertEqual(result.direction_asset_id, binding["direction_asset_id"])
            self.assertEqual(result.direction_content_hash, binding["direction_content_hash"])

    def test_production_routing_is_executable_and_fail_closed(self) -> None:
        with self.assertRaisesRegex(CreatureContractError, "PRODUCTION_ROUTING_BLOCKED"):
            self.registry({**copy.deepcopy(self.manifest), "production_routing": "ENABLED"})
        creature = self.manifest["creatures"][0]
        result = self.registry().resolve(creature["creature_id"], creature["variant_lineage"]["variant_id"], "south", production_routing="ENABLED")
        self.assertEqual((result.result, result.error_code, result.rejection_class), ("REJECTED", "PRODUCTION_ROUTING_BLOCKED", "RUNTIME_REJECTION"))

    def test_two_derived_variants_materialize_with_parent_and_distinct_cache(self) -> None:
        registry = self.registry()
        derived = [item for item in self.manifest["variants"] if item["kind"] == "derived"]
        self.assertGreaterEqual(len(derived), 2)
        results = []
        for variant in derived:
            result = registry.resolve(variant["creature_id"], variant["variant_id"], "south", "idle")
            self.assertEqual(result.result, "RESOLVED")
            self.assertEqual(result.variant_kind, "derived")
            self.assertEqual(result.parent_creature_id, variant["creature_id"])
            self.assertTrue(result.parent_variant_id)
            self.assertEqual(set(result.effective_overrides), set(variant["overrides"]))
            results.append(result)
        self.assertEqual(len({item.cache_key for item in results}), len(results))

    def test_collision_geometry_rejects_nonpositive_and_inverted_bounds(self) -> None:
        negative = copy.deepcopy(self.manifest)
        negative["creatures"][0]["collision_profile"]["width"] = 0
        with self.assertRaisesRegex(CreatureContractError, "COLLISION_GEOMETRY_INVALID"):
            self.registry(negative)
        negative = copy.deepcopy(self.manifest)
        negative["creatures"][0]["collision_profile"]["bounds"]["left"] = 200
        with self.assertRaisesRegex(CreatureContractError, "BOUNDS_GEOMETRY_INVALID"):
            self.registry(negative)

    def test_state_route_identity_and_unsupported_state_fail_closed(self) -> None:
        creature = next(item for item in self.manifest["creatures"] if item["animation_state_contract"]["locomotion"] == "UNSUPPORTED")
        base = creature["variant_lineage"]["variant_id"]
        registry = self.registry()
        idle = registry.resolve(creature["creature_id"], base, "south", "idle")
        self.assertEqual(idle.state_route_id, creature["state_routes"]["idle"]["state_route_id"])
        self.assertEqual(idle.timing_phase, creature["state_routes"]["idle"]["timing_phase"])
        unsupported = registry.resolve(creature["creature_id"], base, "south", "locomotion")
        self.assertEqual((unsupported.result, unsupported.error_code), ("REJECTED", "CREATURE_STATE_UNSUPPORTED"))

    def test_cross_creature_variant_and_state_cache_contexts_are_rejected(self) -> None:
        registry = self.registry()
        first, second = self.manifest["creatures"][0], self.manifest["creatures"][1]
        first_base = first["variant_lineage"]["variant_id"]
        second_base = second["variant_lineage"]["variant_id"]
        expected = registry.resolve(first["creature_id"], first_base, "south", "idle")
        wrong_creature = registry.resolve(second["creature_id"], second_base, "south", "idle")
        registry.poison_cache_for_test(expected.cache_key, wrong_creature)
        self.assertEqual(registry.resolve(first["creature_id"], first_base, "south", "idle").error_code, "STALE_CREATURE_CACHE_CONTEXT")

        registry = self.registry()
        derived = next(item for item in self.manifest["variants"] if item["kind"] == "derived")
        expected = registry.resolve(derived["creature_id"], derived["variant_id"], "south", "idle")
        base = next(item for item in self.manifest["creatures"] if item["creature_id"] == derived["creature_id"])["variant_lineage"]["variant_id"]
        wrong_variant = registry.resolve(derived["creature_id"], base, "south", "idle")
        registry.poison_cache_for_test(expected.cache_key, wrong_variant)
        self.assertEqual(registry.resolve(derived["creature_id"], derived["variant_id"], "south", "idle").error_code, "STALE_CREATURE_CACHE_CONTEXT")

    def test_negative_control_evidence_is_strict(self) -> None:
        evidence = json.loads((ROOT / "docs/evidence/creatures-monsters-runtime-v0181/negative-controls-v0181.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["status"], "CR_NC_01_TO_15_PASSED")
        self.assertEqual(len(evidence["controls"]), 15)
        for item in evidence["controls"].values():
            self.assertTrue(item["rejected"] and item["passed"] and item["status"] == "REJECTED")
            self.assertEqual(item["observed"]["result"], "REJECTED")
            self.assertEqual(item["observed"]["error_code"], item["expected_error_code"])
            self.assertEqual(item["observed"]["rejection_class"], item["expected_rejection_class"])

    def test_base_provenance_hashes_remain_bound(self) -> None:
        self.assertTrue(all(item["provenance_hash"] == item["provenance"]["record_hash"] == _record_hash(item) for item in self.manifest["creatures"]))


if __name__ == "__main__":
    unittest.main()
