from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path

from ugas.item_prop_runtime_v0190 import ItemPropContractError, ItemPropRegistry, validate_item_prop_manifest
from scripts.validation.run_items_props_runtime_v0190 import ITEMS, build_manifest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/items-props-runtime-v0190"


class ItemPropRuntimeV0190Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = build_manifest()

    def registry(self, manifest: dict | None = None) -> ItemPropRegistry:
        return ItemPropRegistry(copy.deepcopy(manifest or self.manifest))

    def test_all_six_classes_resolve_inventory_and_world(self) -> None:
        registry = self.registry()
        for item_id, _ in ITEMS:
            for context in ("inventory", "world"):
                result = registry.resolve(item_id, f"{item_id}:base", context)
                self.assertEqual(result.result, "RESOLVED")
                self.assertEqual(result.requested_context, context)
                self.assertEqual(result.item_or_prop_id, item_id)
                self.assertFalse(result.production_safe)

    def test_unsupported_equipment_representation_is_explicit(self) -> None:
        registry = self.registry()
        result = registry.resolve("moon_ore", "moon_ore:base", "equipment-preview")
        self.assertEqual((result.result, result.error_code), ("REJECTED", "REPRESENTATION_CONTEXT_UNSUPPORTED"))
        preview = registry.resolve("moon_ore", "moon_ore:base", "equipment-preview", request_mode="preview", allow_preview_fallback=True)
        self.assertEqual((preview.result, preview.fallback_mode), ("RESOLVED", "EXPLICIT_TEST_PREVIEW"))

    def test_derived_variant_is_materialized_and_revalidated(self) -> None:
        registry = self.registry()
        result = registry.resolve("iron_sword", "iron_sword:ember", "inventory")
        self.assertEqual(result.result, "RESOLVED")
        self.assertEqual(result.variant_revision, "iron_sword-ember-r1")
        self.assertIn("variant_id=iron_sword:ember", result.cache_key)

    def test_gameplay_variant_override_fails_closed(self) -> None:
        negative = copy.deepcopy(self.manifest)
        negative["variants"][-2]["overrides"] = ["power"]
        negative["variants"][-2]["override_values"] = {"power": 100}
        with self.assertRaisesRegex(ItemPropContractError, "VARIANT_FORBIDDEN_OVERRIDE"):
            validate_item_prop_manifest(negative)

    def test_cache_identity_rejects_poisoned_cross_item_result(self) -> None:
        registry = self.registry()
        good = registry.resolve("iron_sword", "iron_sword:base", "inventory")
        registry.poison_cache_for_test(good.cache_key, replace(good, item_or_prop_id="moon_ore"))
        result = registry.resolve("iron_sword", "iron_sword:base", "inventory")
        self.assertEqual((result.result, result.error_code), ("REJECTED", "STALE_ITEM_PROP_CACHE_CONTEXT"))

    def test_equipment_linkage_is_valid_only_for_weapon_fixture(self) -> None:
        result = self.registry().resolve("iron_sword", "iron_sword:base", "equipment-preview")
        self.assertEqual(result.result, "RESOLVED")
        self.assertEqual(result.equipment_ref["compatibility"], "weapon_item")

    def test_production_registry_is_empty_and_routing_is_blocked(self) -> None:
        production = {**copy.deepcopy(self.manifest), "production_registry": True, "registry_authority": "PRODUCTION_APPROVED_ASSETS_ONLY", "items": [], "variants": []}
        registry = ItemPropRegistry(production)
        self.assertEqual(registry.cache_stats()["entries"], 0)
        negative = copy.deepcopy(self.manifest)
        negative["production_routing"] = "ENABLED"
        with self.assertRaisesRegex(ItemPropContractError, "PRODUCTION_ROUTING_BLOCKED"):
            validate_item_prop_manifest(negative)

    def test_evidence_contains_all_strict_negative_controls(self) -> None:
        evidence = json.loads((EVIDENCE / "negative-controls-v0190.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["status"], "ITEM_PROP_NEGATIVE_CONTROLS_01_TO_17_PASSED")
        self.assertEqual(len(evidence["controls"]), 17)
        self.assertTrue(all(item["rejected"] and item["passed"] and item["status"] == "REJECTED" for item in evidence["controls"].values()))

    def test_evidence_keeps_fixture_and_production_boundaries(self) -> None:
        fixture = json.loads((EVIDENCE / "synthetic-fixture-manifest-v0190.json").read_text(encoding="utf-8"))
        production = json.loads((EVIDENCE / "production-registry-v0190.json").read_text(encoding="utf-8"))
        self.assertEqual((fixture["fixture_count"], fixture["unique_hash_count"], fixture["production_registry"]), (6, 6, False))
        self.assertTrue(all(item["test_only"] and not item["production_safe"] for item in fixture["fixtures"]))
        self.assertEqual((production["items"], production["variants"], production["production_routing"]), ([], [], "BLOCKED"))


if __name__ == "__main__":
    unittest.main()
