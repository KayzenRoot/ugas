from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from ugas.creature_runtime import CreatureContractError, CreatureRegistry, _record_hash


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/evidence/creatures-monsters-runtime-v0180/creature-runtime-manifest-v0180.json"


class CreatureRuntimeV0180Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not MANIFEST.is_file():
            raise unittest.SkipTest("v0.18.0 fixture manifest not generated yet")
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def registry(self, manifest: dict | None = None) -> CreatureRegistry:
        return CreatureRegistry(copy.deepcopy(manifest or self.manifest))

    def test_six_archetypes_are_explicit_and_hash_bound(self) -> None:
        self.assertEqual(len(self.manifest["creatures"]), 6)
        self.assertEqual(len({item["archetype"] for item in self.manifest["creatures"]}), 6)
        self.assertTrue(all(item["provenance_hash"] == item["provenance"]["record_hash"] == _record_hash(item) for item in self.manifest["creatures"]))

    def test_resolution_binds_direction_state_and_topology(self) -> None:
        item = self.manifest["creatures"][0]
        result = self.registry().resolve(item["creature_id"], item["variant_lineage"]["variant_id"], "south", "idle")
        self.assertEqual(result.result, "RESOLVED")
        self.assertTrue(all(token in result.cache_key for token in ("creature_id=", "variant=", "direction=south", "state=idle", "rig_topology_revision=", "asset_revision=")))
        self.assertEqual(result.production_safe, False)

    def test_unsupported_state_and_direction_fail_closed(self) -> None:
        item = next(item for item in self.manifest["creatures"] if "UNSUPPORTED" in item["animation_state_contract"].values())
        state = next(key for key, value in item["animation_state_contract"].items() if value == "UNSUPPORTED")
        registry = self.registry()
        self.assertEqual(registry.resolve(item["creature_id"], item["variant_lineage"]["variant_id"], "south", state).error_code, "CREATURE_STATE_UNSUPPORTED")
        self.assertEqual(registry.resolve(item["creature_id"], item["variant_lineage"]["variant_id"], "east").error_code, None)
        changed = copy.deepcopy(self.manifest); changed["creatures"][0]["direction_coverage"] = ["south"]; changed["creatures"][0]["provenance_hash"] = _record_hash(changed["creatures"][0]); changed["creatures"][0]["provenance"]["record_hash"] = changed["creatures"][0]["provenance_hash"]; self.assertEqual(self.registry(changed).resolve(changed["creatures"][0]["creature_id"], changed["creatures"][0]["variant_lineage"]["variant_id"], "east").error_code, "CREATURE_DIRECTION_UNAVAILABLE")

    def test_cross_creature_cache_poisoning_is_rejected(self) -> None:
        registry = self.registry(); first, second = self.manifest["creatures"][0], self.manifest["creatures"][1]
        expected = registry.resolve(first["creature_id"], first["variant_lineage"]["variant_id"], "south")
        wrong = registry.resolve(second["creature_id"], second["variant_lineage"]["variant_id"], "south")
        registry.poison_cache_for_test(expected.cache_key, wrong)
        observed = registry.resolve(first["creature_id"], first["variant_lineage"]["variant_id"], "south")
        self.assertEqual(observed.error_code, "STALE_CREATURE_CACHE_CONTEXT")

    def test_production_registry_rejects_test_only_records(self) -> None:
        with self.assertRaisesRegex(CreatureContractError, "TEST_ONLY_CREATURE_IN_PRODUCTION_REGISTRY"):
            CreatureRegistry(copy.deepcopy(self.manifest), production_registry=True)
        production = {**copy.deepcopy(self.manifest), "production_registry": True, "registry_authority": "PRODUCTION_APPROVED_ASSETS_ONLY", "creatures": [], "variants": []}
        self.assertEqual(self.registry(production).cache_stats()["entries"], 0)


if __name__ == "__main__":
    unittest.main()
