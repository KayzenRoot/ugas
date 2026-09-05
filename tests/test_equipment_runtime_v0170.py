from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from PIL import Image

from ugas.equipment_runtime import EquipmentContractError, EquipmentRegistry, sha256_image, sha256_json


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/equipment-outfits-runtime-v0170"
FIXTURE_MANIFEST = EVIDENCE / "synthetic-fixture-manifest-v0170.json"
BASE_FRAME = ROOT / "docs/evidence/animation-runtime-v0151/death-front-v1/frame-00.png"


def _refresh(record: dict) -> None:
    record["provenance_hash"] = sha256_json({key: value for key, value in record.items() if key != "provenance_hash"})


def _anchor_points() -> dict[str, dict[str, float]]:
    return {
        "nose": {"x": 270, "y": 79},
        "neck": {"x": 267, "y": 111},
        "shoulder_center": {"x": 267, "y": 126},
        "shoulder_left": {"x": 314, "y": 126},
        "shoulder_right": {"x": 220, "y": 126},
        "wrist_left": {"x": 349, "y": 259},
        "wrist_right": {"x": 195, "y": 257},
        "hip_left": {"x": 296, "y": 252},
        "hip_right": {"x": 243, "y": 253},
        "ankle_left": {"x": 309, "y": 449},
        "ankle_right": {"x": 234, "y": 447},
        "pelvis": {"x": 270, "y": 253},
    }


class EquipmentRuntimeV0170Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))

    def _registry(self, manifest: dict | None = None) -> EquipmentRegistry:
        return EquipmentRegistry(copy.deepcopy(manifest or self.manifest))

    def _record(self, equipment_id: str) -> dict:
        return next(item for item in self.manifest["assets"] if item["equipment_id"] == equipment_id)

    def _base_metadata(self) -> dict:
        return {
            "source_rig_revision": "r4-cutout-rig-v071",
            "base_sha256": "7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798",
            "approved_frame_hash": "death-front-v151-frame-00",
            "anchor_points": _anchor_points(),
            "joint_rotations": {"shoulder_left": 3.0},
            "timing": {"frame": 0, "duration_ms": 83},
            "event_markers": [],
        }

    def test_manifest_is_south_only_test_registry_with_explicit_contract_fields(self) -> None:
        registry = self._registry()
        self.assertEqual(registry.layer_order[-1], "accessory")
        self.assertEqual(len(registry._assets), 6)
        self.assertTrue(all(item["test_only"] and not item["production_safe"] for item in self.manifest["assets"]))

    def test_slot_identity_and_anchor_contract_reject_real_mutations(self) -> None:
        for mutation, expected in (("slot", "UNKNOWN_EQUIPMENT_SLOT"), ("anchor", "ANCHORS_MISSING")):
            manifest = copy.deepcopy(self.manifest)
            item = manifest["assets"][0]
            if mutation == "slot":
                item["slot"] = "unknown-slot"
            else:
                item["anchors"] = []
            _refresh(item)
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(EquipmentContractError, expected):
                    self._registry(manifest)

    def test_layer_order_and_replacement_conflicts_fail_closed(self) -> None:
        cycle = copy.deepcopy(self.manifest)
        cycle["layer_dependencies"]["behind_legs"] = ["accessory"]
        with self.assertRaisesRegex(EquipmentContractError, "LAYER_ORDER_CYCLE"):
            self._registry(cycle)
        conflict = copy.deepcopy(self.manifest)
        conflict["replacement_conflict_policy"] = None
        with self.assertRaisesRegex(EquipmentContractError, "REPLACEMENT_CONFLICT_POLICY_MISSING"):
            self._registry(conflict)

    def test_south_only_missing_direction_never_silently_mirrors(self) -> None:
        registry = self._registry()
        direct = registry.resolve("fixture-helmet-teal", "north")
        mirror = registry.resolve("fixture-helmet-teal", "north", allow_mirror=True)
        self.assertEqual(direct.error_code, "EQUIPMENT_DIRECTION_UNAVAILABLE")
        self.assertEqual(mirror.error_code, "EQUIPMENT_DIRECTION_UNAVAILABLE")
        self.assertEqual(mirror.result, "REJECTED")

    def test_asymmetric_fixture_cannot_be_granted_mirror_permission(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        item = manifest["assets"][0]
        item["mirror_safe"] = True
        item["mirror_permission"] = {"allowed": True, "from": "south", "to": "north"}
        _refresh(item)
        with self.assertRaisesRegex(EquipmentContractError, "ASYMMETRIC_MIRROR_UNSAFE"):
            self._registry(manifest)

    def test_cache_identity_contains_outfit_direction_animation_variant_and_registry(self) -> None:
        registry = self._registry()
        first = registry.resolve("fixture-helmet-teal", "south", animation_profile="idle-front-v1")
        second = registry.resolve("fixture-coat-amber", "south", animation_profile="idle-front-v1")
        north = registry.resolve("fixture-helmet-teal", "north", animation_profile="idle-front-v1")
        self.assertNotEqual(first.cache_key, second.cache_key)
        self.assertNotEqual(first.cache_key, north.cache_key)
        for token in ("equipment_id=fixture-helmet-teal", "slot=head", "variant=teal", "rig_revision=r4-cutout-rig-v071", "direction=south", "animation_capability=front-compatible", "animation_profile=idle-front-v1", "asset_revision=fixture-helmet-teal-r1", "registry_mode=test"):
            self.assertIn(token, first.cache_key)

    def test_provenance_mutation_and_production_fixture_boundary_reject(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["assets"][0]["provenance_hash"] = "0" * 64
        with self.assertRaisesRegex(EquipmentContractError, "PROVENANCE_HASH_MISMATCH"):
            self._registry(manifest)
        with self.assertRaisesRegex(EquipmentContractError, "TEST_ONLY_FIXTURE_IN_PRODUCTION_REGISTRY"):
            EquipmentRegistry(copy.deepcopy(self.manifest), production_registry=True)

    def test_composition_is_non_destructive_and_preserves_base_animation_metadata(self) -> None:
        registry = self._registry()
        base = Image.open(BASE_FRAME).convert("RGBA")
        before = sha256_image(base)
        metadata = self._base_metadata()
        result = registry.compose(base, metadata, ["fixture-helmet-teal", "fixture-coat-amber"], direction="south")
        self.assertEqual(before, sha256_image(base))
        self.assertEqual(result.base_sha256_before, result.base_sha256_after)
        self.assertTrue(result.base_animation_metadata_preserved)
        self.assertFalse(result.production_safe)
        self.assertEqual(result.result, "RESOLVED")

    def test_two_identical_compositions_are_byte_deterministic(self) -> None:
        registry = self._registry()
        base = Image.open(BASE_FRAME).convert("RGBA")
        one = registry.compose(base, self._base_metadata(), ["fixture-cape-blue", "fixture-helmet-teal", "fixture-boots-red"], direction="south")
        two = registry.compose(base, self._base_metadata(), ["fixture-boots-red", "fixture-helmet-teal", "fixture-cape-blue"], direction="south")
        self.assertEqual(sha256_image(one.image), sha256_image(two.image))
        self.assertEqual(one.layer_trace, two.layer_trace)
        self.assertEqual(one.cache_key, two.cache_key)

    def test_incompatible_rig_and_animation_profile_are_rejected(self) -> None:
        registry = self._registry()
        self.assertEqual(registry.resolve("fixture-coat-amber", "south", rig_revision="other-rig").error_code, "RIG_REVISION_INCOMPATIBLE")
        self.assertEqual(registry.resolve("fixture-coat-amber", "south", animation_profile="unknown-profile").error_code, "ANIMATION_PROFILE_INCOMPATIBLE")

    def test_production_routing_is_always_blocked(self) -> None:
        registry = self._registry()
        base = Image.open(BASE_FRAME).convert("RGBA")
        with self.assertRaisesRegex(EquipmentContractError, "PRODUCTION_ROUTING_BLOCKED"):
            registry.compose(base, self._base_metadata(), ["fixture-coat-amber"], direction="south", production_routing="ENABLED")


if __name__ == "__main__":
    unittest.main()
