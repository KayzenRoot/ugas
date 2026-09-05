from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from PIL import Image

from ugas.equipment_runtime import EquipmentContractError, EquipmentRegistry, compare_base_immutability, compare_compositions, sha256_image, sha256_json


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/equipment-outfits-runtime-v0171"
MANIFEST = EVIDENCE / "synthetic-fixture-manifest-v0171.json"
BASE_FRAME = ROOT / "docs/evidence/animation-runtime-v0151/death-front-v1/frame-00.png"


def _refresh(record: dict) -> None:
    record["provenance_hash"] = sha256_json({key: value for key, value in record.items() if key != "provenance_hash"})


class EquipmentRuntimeV0171Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.metadata = json.loads('{"source_rig_revision":"r4-cutout-rig-v071","approved_frame_hash":"death-front-v151-frame-00","anchor_points":{"nose":{"x":270,"y":79},"neck":{"x":267,"y":111},"shoulder_center":{"x":267,"y":126},"shoulder_left":{"x":314,"y":126},"shoulder_right":{"x":220,"y":126},"wrist_left":{"x":349,"y":259},"wrist_right":{"x":195,"y":257},"ankle_left":{"x":309,"y":449},"ankle_right":{"x":234,"y":447},"pelvis":{"x":270,"y":253}},"joint_rotations":{"shoulder_left":3.0},"timing":{"frame":0,"duration_ms":83},"event_markers":[]}')

    def registry(self, manifest: dict | None = None) -> EquipmentRegistry:
        return EquipmentRegistry(copy.deepcopy(manifest or self.manifest))

    def base(self) -> Image.Image:
        return Image.open(BASE_FRAME).convert("RGBA")

    def test_replacement_selects_one_winner_and_suppresses_loser(self) -> None:
        result = self.registry().compose(self.base(), self.metadata, ["fixture-coat-replacement-low", "fixture-coat-replacement-high"], direction="south")
        winner = next(item for item in result.layer_trace if item.get("equipment_id") == "fixture-coat-replacement-high")
        loser = next(item for item in result.layer_trace if item.get("equipment_id") == "fixture-coat-replacement-low")
        self.assertEqual(winner["winner"], "fixture-coat-replacement-high")
        self.assertEqual(winner["hidden_parts"], ["torso_pelvis"])
        self.assertGreater(winner["hidden_pixel_count"], 0)
        self.assertTrue(loser["loser_suppressed"])
        self.assertNotIn((214, 102, 32), [pixel[:3] for pixel in result.image.get_flattened_data()])

    def test_asset_bound_mask_has_actual_runtime_effect_and_trace(self) -> None:
        result = self.registry().compose(self.base(), self.metadata, ["fixture-helmet-teal"], direction="south")
        mask = result.layer_trace[0]["occlusion_masks"][0]
        self.assertEqual(mask["status"], "APPLIED")
        self.assertGreater(mask["affected_pixel_count"], 0)
        self.assertEqual(mask["policy"], "explicit-layer-alpha")

    def test_poisoned_cache_is_rejected(self) -> None:
        registry = self.registry()
        expected = registry.resolve("fixture-helmet-teal", "south")
        wrong = registry.resolve("fixture-coat-amber", "south")
        registry.poison_cache_for_test(expected.cache_key, wrong)
        observed = registry.resolve("fixture-helmet-teal", "south")
        self.assertEqual(observed.error_code, "STALE_CACHE_CONTEXT")
        self.assertEqual(observed.result, "REJECTED")

    def test_permitted_mirror_and_secondary_anchor_fail_closed(self) -> None:
        mirror_manifest = copy.deepcopy(self.manifest)
        item = mirror_manifest["assets"][0]
        item["asymmetry_flags"] = []
        item["mirror_safe"] = True
        item["mirror_permission"] = {"allowed": True, "from": "south", "to": "north"}
        _refresh(item)
        result = EquipmentRegistry(mirror_manifest).resolve("fixture-cape-blue", "north", allow_mirror=True)
        self.assertEqual(result.error_code, "MIRROR_RUNTIME_NOT_IMPLEMENTED")
        self.assertEqual(result.mirror_mode, "NONE")
        secondary_manifest = copy.deepcopy(self.manifest)
        secondary_manifest["assets"][0]["anchors"][0]["secondary_anchor"] = {"joint": "pelvis"}
        _refresh(secondary_manifest["assets"][0])
        with self.assertRaisesRegex(EquipmentContractError, "SECONDARY_ANCHOR_UNSUPPORTED"):
            self.registry(secondary_manifest)

    def test_shared_comparators_reject_mutated_outputs(self) -> None:
        base = self.base()
        changed = base.copy()
        x, y = next((x, y) for y in range(changed.height) for x in range(changed.width) if changed.getpixel((x, y))[3])
        red, green, blue, alpha = changed.getpixel((x, y))
        changed.putpixel((x, y), ((red + 1) % 256, green, blue, alpha))
        with self.assertRaisesRegex(EquipmentContractError, "BASE_PIXEL_MUTATION"):
            compare_base_immutability(base, changed)
        one = self.registry().compose(base, self.metadata, ["fixture-cape-blue"], direction="south")
        two = one.image.copy(); two.putpixel((x, y), ((two.getpixel((x, y))[0] + 1) % 256, *two.getpixel((x, y))[1:]))
        with self.assertRaisesRegex(EquipmentContractError, "NONDETERMINISTIC_SECOND_COMPOSITION"):
            compare_compositions(one.image, two)


if __name__ == "__main__":
    unittest.main()
