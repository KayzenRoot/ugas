from __future__ import annotations

import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from ugas.item_prop_runtime_v0191 import ItemPropContractError, ItemPropRegistry, _record_hash, load_equipment_authority, validate_item_prop_manifest
from scripts.validation.run_items_props_runtime_v0191 import AUTHORITY_PATH, ITEMS, build_manifest, materialize_representations


class ItemPropRuntimeV0191Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = build_manifest()
        cls._fixture_directory = tempfile.TemporaryDirectory(prefix="ugas-v0191-item-props-")
        cls.fixture_root = Path(cls._fixture_directory.name)
        materialize_representations(cls.manifest, cls.fixture_root)
        cls.authority = load_equipment_authority(AUTHORITY_PATH)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._fixture_directory.cleanup()

    def registry(self, manifest: dict | None = None) -> ItemPropRegistry:
        return ItemPropRegistry(copy.deepcopy(manifest or self.manifest), artifact_root=self.fixture_root, equipment_authority=self.authority)

    def test_all_six_classes_resolve_declared_inventory_and_world_bytes(self) -> None:
        registry = self.registry()
        for item_id, _ in ITEMS:
            for context in ("inventory", "world"):
                result = registry.resolve(item_id, f"{item_id}:base", context)
                self.assertEqual(result.result, "RESOLVED")
                self.assertEqual(result.artifact_path, f"representations/{item_id}/{context}.png")
                self.assertEqual(result.content_hash, result.to_dict()["content_hash"])

    def test_equipment_preview_contains_authority_and_resolved_identity(self) -> None:
        result = self.registry().resolve("iron_sword", "iron_sword:base", "equipment-preview")
        self.assertEqual(result.result, "RESOLVED")
        self.assertEqual(result.equipment_authority_version, "0.17.1")
        self.assertEqual(result.resolved_equipment["equipment_id"], "fixture-charm-violet")
        self.assertEqual(result.resolved_equipment["asset_revision"], "fixture-charm-violet-r1")

    def test_missing_artifact_cannot_resolve(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["items"][0]["representations"]["inventory_icon"]["artifact_path"] = "representations/missing.png"
        binding = manifest["items"][0]["representations"]["inventory_icon"]
        binding["provenance"]["provenance_hash"] = _record_hash({key: value for key, value in binding.items() if key != "provenance"})
        manifest["items"][0]["provenance_hash"] = _record_hash(manifest["items"][0])
        with self.assertRaisesRegex(ItemPropContractError, "REPRESENTATION_ARTIFACT_MISSING"):
            ItemPropRegistry(manifest, artifact_root=self.fixture_root, equipment_authority=self.authority)

    def test_mutated_artifact_hash_cannot_resolve(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["items"][0]["representations"]["inventory_icon"]["file_sha256"] = "0" * 64
        manifest["items"][0]["representations"]["inventory_icon"]["content_hash"] = "0" * 64
        binding = manifest["items"][0]["representations"]["inventory_icon"]
        binding["provenance"]["provenance_hash"] = _record_hash({key: value for key, value in binding.items() if key != "provenance"})
        manifest["items"][0]["provenance_hash"] = _record_hash(manifest["items"][0])
        with self.assertRaisesRegex(ItemPropContractError, "REPRESENTATION_ARTIFACT_HASH_MISMATCH"):
            ItemPropRegistry(manifest, artifact_root=self.fixture_root, equipment_authority=self.authority)

    def test_equipment_reference_is_authority_bound(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["items"][0]["equipment_ref"]["equipment_id"] = "not-in-v0171"
        manifest["items"][0]["provenance_hash"] = __import__("ugas.item_prop_runtime_v0191", fromlist=["_record_hash"])._record_hash(manifest["items"][0])
        with self.assertRaisesRegex(ItemPropContractError, "EQUIPMENT_REF_NOT_FOUND"):
            validate_item_prop_manifest(manifest, equipment_authority=self.authority)

    def test_equipment_slot_mismatch_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["items"][0]["equipment_ref"]["slot"] = "head"
        manifest["items"][0]["provenance_hash"] = __import__("ugas.item_prop_runtime_v0191", fromlist=["_record_hash"])._record_hash(manifest["items"][0])
        with self.assertRaisesRegex(ItemPropContractError, "EQUIPMENT_REF_SLOT_MISMATCH"):
            validate_item_prop_manifest(manifest, equipment_authority=self.authority)

    def test_stack_family_is_item_specific(self) -> None:
        registry = self.registry()
        potion = registry.resolve("healing_potion", "healing_potion:base", "inventory")
        ore = registry.resolve("moon_ore", "moon_ore:base", "inventory")
        self.assertEqual(potion.stack_family_id, "item:healing_potion")
        self.assertEqual(ore.stack_family_id, "item:moon_ore")
        self.assertNotEqual(potion.stack_family_id, ore.stack_family_id)

    def test_generic_stack_family_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["items"][1]["stack_family_id"] = "consumable_item"
        manifest["items"][1]["stack_key"] = "consumable_item"
        manifest["items"][1]["provenance_hash"] = _record_hash(manifest["items"][1])
        with self.assertRaisesRegex(ItemPropContractError, "STACK_IDENTITY_TOO_COARSE"):
            validate_item_prop_manifest(manifest)

    def test_cross_item_stack_family_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["items"][2]["stack_family_id"] = "item:healing_potion"
        manifest["items"][2]["stack_key"] = "item:healing_potion"
        manifest["items"][2]["provenance_hash"] = _record_hash(manifest["items"][2])
        with self.assertRaisesRegex(ItemPropContractError, "STACK_FAMILY_COLLISION"):
            validate_item_prop_manifest(manifest)

    def test_derived_variant_inherits_family(self) -> None:
        result = self.registry().resolve("healing_potion", "healing_potion:berry", "inventory")
        self.assertEqual(result.result, "RESOLVED")
        self.assertEqual(result.stack_family_id, "item:healing_potion")

    def test_derived_variant_cannot_change_family(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["variants"][7]["override_values"]["stack_family_id"] = "item:moon_ore"
        with self.assertRaisesRegex(ItemPropContractError, "STACK_FAMILY_VARIANT_MISMATCH"):
            validate_item_prop_manifest(manifest)

    def test_cache_identity_rejects_poisoned_cross_item_result(self) -> None:
        registry = self.registry()
        good = registry.resolve("iron_sword", "iron_sword:base", "inventory")
        registry.poison_cache_for_test(good.cache_key, replace(good, item_or_prop_id="moon_ore"))
        result = registry.resolve("iron_sword", "iron_sword:base", "inventory")
        self.assertEqual((result.result, result.error_code), ("REJECTED", "STALE_ITEM_PROP_CACHE_CONTEXT"))

    def test_unsupported_equipment_is_fail_closed_without_preview_bytes(self) -> None:
        result = self.registry().resolve("moon_ore", "moon_ore:base", "equipment-preview", request_mode="preview", allow_preview_fallback=True)
        self.assertEqual((result.result, result.error_code), ("REJECTED", "REPRESENTATION_CONTEXT_UNSUPPORTED"))

    def test_production_registry_has_no_records(self) -> None:
        production = {**copy.deepcopy(self.manifest), "production_registry": True, "registry_authority": "PRODUCTION_APPROVED_ASSETS_ONLY", "items": [], "variants": []}
        registry = ItemPropRegistry(production)
        self.assertEqual(registry.cache_stats()["entries"], 0)

    def test_authority_contains_exact_frozen_fixture_set(self) -> None:
        self.assertEqual(len(self.authority.assets), 8)
        self.assertEqual(self.authority.sha256, "8257C38E1F08834E08B35943DBD371460FBF89C2791A9759A3B6D33422175628")
        self.assertEqual(self.authority.blob_id, "75d19401b2489288fe85d3147cc84940edcbb578")


if __name__ == "__main__":
    unittest.main()
