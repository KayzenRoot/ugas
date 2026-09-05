from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from ugas.creature_runtime_v0182 import CreatureContractError, CreatureRegistry, _record_hash


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/evidence/creatures-monsters-runtime-v0182/creature-runtime-manifest-v0182.json"


class CreatureRuntimeV0182Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not MANIFEST.is_file():
            raise unittest.SkipTest("v0.18.2 fixture manifest not generated yet")
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def registry(self, manifest: dict | None = None) -> CreatureRegistry:
        return CreatureRegistry(copy.deepcopy(manifest or self.manifest))

    def test_effective_variant_validation_and_revision_identity(self) -> None:
        registry = self.registry()
        for variant in [item for item in self.manifest["variants"] if item["kind"] == "derived"]:
            result = registry.resolve(variant["creature_id"], variant["variant_id"], "south", "idle")
            self.assertEqual(result.result, "RESOLVED")
            self.assertTrue(result.variant_revision)
            self.assertNotEqual(result.variant_revision, result.asset_revision)
            self.assertEqual(result.asset_revision, result.direction_asset_revision)
            self.assertEqual(set(result.effective_overrides), set(variant["overrides"]))

    def test_moving_archetypes_require_locomotion_and_stationary_rejects_it(self) -> None:
        registry = self.registry()
        for creature in self.manifest["creatures"]:
            result = registry.resolve(creature["creature_id"], creature["variant_lineage"]["variant_id"], "south", "locomotion")
            if creature["archetype"] == "stationary_structure":
                self.assertEqual((result.result, result.error_code), ("REJECTED", "CREATURE_STATE_UNSUPPORTED"))
            else:
                self.assertEqual(result.result, "RESOLVED")
                self.assertTrue(result.state_route_id and result.timing_phase)

    def test_each_derived_negative_control_is_strict(self) -> None:
        evidence = json.loads((ROOT / "docs/evidence/creatures-monsters-runtime-v0182/derived-variant-negative-controls-v0182.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["status"], "DERIVED_VARIANT_NEGATIVE_CONTROLS_PASSED")
        self.assertEqual(len(evidence["controls"]), 6)
        for item in evidence["controls"].values():
            self.assertTrue(item["rejected"] and item["passed"] and item["status"] == "REJECTED")
            self.assertEqual(item["observed"]["error_code"], item["expected_error_code"])
            self.assertEqual(item["observed"]["rejection_class"], "CONTRACT_REJECTION")

    def test_effective_variant_mutation_rejects_after_materialization(self) -> None:
        negative = copy.deepcopy(self.manifest)
        variant = next(item for item in negative["variants"] if item["kind"] == "derived")
        variant["override_values"]["base_scale"]["x"] = -1
        result = self.registry(negative).resolve(variant["creature_id"], variant["variant_id"], "south", "idle")
        self.assertEqual((result.result, result.error_code, result.rejection_class), ("REJECTED", "BASE_SCALE_INVALID", "CONTRACT_REJECTION"))

    def test_direction_revision_mismatch_rejects(self) -> None:
        negative = copy.deepcopy(self.manifest)
        variant = next(item for item in negative["variants"] if item["kind"] == "derived")
        creature = next(item for item in negative["creatures"] if item["creature_id"] == variant["creature_id"])
        variant["overrides"].append("direction_bindings")
        variant["override_values"]["direction_bindings"] = copy.deepcopy(creature["direction_bindings"])
        variant["override_values"]["direction_bindings"]["south"]["asset_revision"] = "mixed-r9"
        result = self.registry(negative).resolve(variant["creature_id"], variant["variant_id"], "south", "idle")
        self.assertEqual((result.result, result.error_code), ("REJECTED", "DIRECTION_ASSET_REVISION_MISMATCH"))

    def test_cache_key_contains_variant_and_direction_revision_and_poisoning_fails(self) -> None:
        registry = self.registry()
        derived = next(item for item in self.manifest["variants"] if item["kind"] == "derived")
        result = registry.resolve(derived["creature_id"], derived["variant_id"], "south", "idle")
        self.assertIn("variant_revision=", result.cache_key)
        self.assertIn("direction_asset_revision=", result.cache_key)
        base = next(item for item in self.manifest["creatures"] if item["creature_id"] == derived["creature_id"])["variant_lineage"]["variant_id"]
        wrong = registry.resolve(derived["creature_id"], base, "south", "idle")
        registry.poison_cache_for_test(result.cache_key, wrong)
        self.assertEqual(registry.resolve(derived["creature_id"], derived["variant_id"], "south", "idle").error_code, "STALE_CREATURE_CACHE_CONTEXT")

    def test_frozen_direction_hashes_and_provenance(self) -> None:
        binding = json.loads((ROOT / "docs/evidence/creatures-monsters-runtime-v0182/direction-asset-binding-v0182.json").read_text(encoding="utf-8"))
        self.assertEqual(binding["status"], "DIRECTION_ASSET_BINDING_VALID")
        self.assertEqual(len(binding["records"]), 48)
        self.assertTrue(all(item["sha256"] == item["frozen_v0181_sha256"] == item["direction_content_hash"] for item in binding["records"]))
        self.assertTrue(all(item["provenance_hash"] == item["provenance"]["record_hash"] == _record_hash(item) for item in self.manifest["creatures"]))

    def test_production_boundary_remains_fail_closed(self) -> None:
        with self.assertRaisesRegex(CreatureContractError, "PRODUCTION_ROUTING_BLOCKED"):
            self.registry({**copy.deepcopy(self.manifest), "production_routing": "ENABLED"})


if __name__ == "__main__":
    unittest.main()
