"""Focused unit coverage for the v0.23.0 VFX semantic/runtime foundation."""

from __future__ import annotations

from copy import deepcopy
import tempfile
from pathlib import Path
import unittest

from ugas.vfx_asset_family_runtime_v0230 import (
    CLASS_SPECS,
    EFFECT_CLASSES,
    VFXAssetFamilyContractError,
    build_effect_fixture,
    cache_key_for,
    generate_fixture_pack,
    strict_boolean_observation,
    validate_effect_record,
    validate_production_registry,
    validate_vfx_manifest,
)


class VfxAssetFamilyRuntimeV0230Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="ugas-test-vfx-v0230-")
        self.root = Path(self.tmp.name)
        self.pack = generate_fixture_pack(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_exact_ten_effect_classes_have_stable_specs(self) -> None:
        self.assertEqual(tuple(CLASS_SPECS), EFFECT_CLASSES)
        self.assertEqual(len({item["stable_id"] for item in CLASS_SPECS.values()}), 10)

    def test_manifest_validates_against_runtime_outputs(self) -> None:
        self.assertEqual(validate_vfx_manifest(self.pack["manifest"], self.root)["status"], "VFX_ASSET_FAMILY_MANIFEST_VALID")

    def test_each_effect_has_class_specific_semantics(self) -> None:
        for record in self.pack["records"]:
            required = set(CLASS_SPECS[record["effect_class"]]["required_semantics"])
            self.assertTrue(required.issubset(record["semantic_input"]["semantics"]))

    def test_lifecycle_loop_policy_is_class_specific(self) -> None:
        for record in self.pack["records"]:
            self.assertEqual(record["lifecycle"]["loop"], record["lifecycle"]["mode"] == "OWNER_BOUND_LOOP")

    def test_cache_key_rejects_semantic_mutation(self) -> None:
        record = deepcopy(self.pack["records"][0])
        record["semantic_input"]["semantics"]["fixture_seed"] += 1
        with self.assertRaises(VFXAssetFamilyContractError) as context:
            validate_effect_record(record, self.root)
        self.assertEqual(context.exception.rejection_class, "VFX_SEMANTIC_HASH_INVALID")

    def test_frame_hash_rejects_pixel_metadata_mutation(self) -> None:
        record = deepcopy(self.pack["records"][0])
        record["frames"][0]["sha256"] = "0" * 64
        with self.assertRaises(VFXAssetFamilyContractError) as context:
            validate_effect_record(record, self.root)
        self.assertEqual(context.exception.rejection_class, "VFX_FRAME_SET_HASH_INVALID")

    def test_cache_key_is_complete_and_stable(self) -> None:
        for record in self.pack["records"]:
            self.assertEqual(record["cache_key"], cache_key_for(record))

    def test_production_boundary_is_empty(self) -> None:
        result = validate_production_registry([])
        self.assertEqual(result["status"], "PASS")
        with self.assertRaises(VFXAssetFamilyContractError):
            validate_production_registry([{"id": "not-allowed"}])

    def test_non_boolean_observations_fail_closed(self) -> None:
        for value in (None, 0, 1, "", "PASS", [], {}, object()):
            self.assertFalse(strict_boolean_observation(value))
        self.assertTrue(strict_boolean_observation(True))
        self.assertFalse(strict_boolean_observation(False))

    def test_fixture_is_test_only_and_provider_free(self) -> None:
        for record in self.pack["records"]:
            self.assertTrue(record["test_only"])
            self.assertIsNone(record["provenance"]["provider"])
            self.assertIsNone(record["provenance"]["generation_model"])

    def test_deterministic_replay_is_byte_equivalent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ugas-test-vfx-replay-") as second_dir:
            second = generate_fixture_pack(Path(second_dir))
            self.assertEqual(self.pack["manifest"], second["manifest"])

    def test_read_only_integration_is_explicit(self) -> None:
        for record in self.pack["records"]:
            self.assertEqual(record["integration"]["mode"], "READ_ONLY")
            self.assertFalse(record["integration"]["event_binding"]["gameplay_authoritative"])

    def test_all_frames_are_rgba_pngs_with_visible_alpha(self) -> None:
        for record in self.pack["records"]:
            for frame in record["frames"]:
                path = self.root / frame["path"]
                self.assertTrue(path.is_file())
                self.assertEqual(frame["width"], 96)
                self.assertGreater(frame["alpha_range"][1], 0)


if __name__ == "__main__":
    unittest.main()
