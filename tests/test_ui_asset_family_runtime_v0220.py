from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PIL import Image

from ugas.ui_asset_family_runtime_v0220 import (
    FAMILY_ID, STYLE_TOKEN_SET_ID, UI_COMPONENT_CLASSES, UI_STATES,
    UIAssetFamilyContractError, build_cache_key, build_component_manifest,
    build_test_only_style_tokens, build_ui_manifest, cache_key_for,
    compare_generated_outputs, generate_fixture_pack, render_component,
    style_token_hash, validate_cache_record, validate_determinism,
    validate_historical_authority, validate_integration_linkage,
    validate_nine_slice, validate_production_registry, validate_provenance_output,
    validate_rendered_output, validate_safe_geometry, validate_state_materiality,
    validate_style_tokens, validate_ui_manifest,
)


class UIAssetFamilyRuntimeV0220Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tokens = build_test_only_style_tokens()
        self.manifest = build_ui_manifest(self.tokens)
        self.component = self.manifest["components"][0]

    def test_manifest_has_fourteen_stable_classes(self):
        self.assertEqual(tuple(self.manifest["component_classes"]), UI_COMPONENT_CLASSES)
        self.assertEqual(len({item["component_id"] for item in self.manifest["components"]}), 14)
        self.assertEqual(validate_ui_manifest(self.manifest, self.tokens)["status"], "UI_ASSET_FAMILY_MANIFEST_VALID")

    def test_state_vocabulary_is_exact(self):
        self.assertEqual(tuple(self.manifest["state_vocabulary"]), UI_STATES)
        self.assertEqual(tuple(self.component["supported_states"]), UI_STATES)

    def test_unsupported_state_rejects(self):
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_STATE_UNSUPPORTED"):
            render_component(self.component, "unknown", 1, self.tokens)

    def test_state_bytes_are_materially_distinct(self):
        outputs = {state: render_component(self.component, state, 1, self.tokens).tobytes() for state in UI_STATES}
        validate_state_materiality(outputs)
        self.assertEqual(len(set(outputs.values())), len(UI_STATES))

    def test_style_authority_is_hashed(self):
        validate_style_tokens(self.tokens)
        self.assertEqual(self.component["style_token_hash"], style_token_hash(self.tokens))
        stale = dict(self.component); stale["style_token_hash"] = "0" * 64
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_STYLE_TOKEN_HASH_STALE"):
            from ugas.ui_asset_family_runtime_v0220 import validate_component_record
            validate_component_record(stale, self.tokens)

    def test_nine_slice_and_safe_geometry(self):
        self.assertGreater(validate_nine_slice(self.component)["center_area"][0], 0)
        self.assertTrue(validate_safe_geometry(self.component)["visual_hit_separate"])

    def test_visual_and_hit_bounds_are_separate(self):
        self.assertNotEqual(self.component["visual_bounds"], self.component["hit_bounds"])

    def test_scale_outputs_are_one_x_and_two_x(self):
        one = render_component(self.component, "normal", 1, self.tokens)
        two = render_component(self.component, "normal", 2, self.tokens)
        self.assertEqual(two.size, (one.width * 2, one.height * 2))
        self.assertEqual(validate_rendered_output(one, self.component, "normal", 1)["mode"], "RGBA")

    def test_alpha_bounds_reject_empty_image(self):
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_ALPHA_BOUNDS_INVALID"):
            validate_rendered_output(Image.new("RGBA", tuple(self.component["logical_size"])), self.component, "normal", 1)

    def test_integration_linkage_is_read_only(self):
        self.assertFalse(validate_integration_linkage(self.component)["mutation_allowed"])
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_MINIMAP_LINKAGE_MUTATION_FORBIDDEN"):
            validate_integration_linkage(next(item for item in self.manifest["components"] if item["component_class"] == "minimap_frame"), attempted_mutation=True)

    def test_cache_identity_contains_state_style_and_scale(self):
        key = cache_key_for(self.component, "normal", 1, self.tokens)
        self.assertNotEqual(key, cache_key_for(self.component, "hover", 1, self.tokens))
        self.assertNotEqual(key, cache_key_for(self.component, "normal", 2, self.tokens))
        record = {"family_id": FAMILY_ID, "component_id": self.component["component_id"], "revision": self.component["revision"], "state": "normal", "scale_factor": 1, "style_token_hash": self.component["style_token_hash"], "semantic_input_hash": self.component["semantic_input_hash"], "cache_key": key}
        validate_cache_record(record, self.component, self.tokens)

    def test_provenance_uses_exact_png_bytes(self):
        image = render_component(self.component, "normal", 1, self.tokens)
        record = {"output_sha256": __import__("hashlib").sha256(image.tobytes()).hexdigest(), "relative_path": "fixture.png"}
        validate_provenance_output(record, image.tobytes())

    def test_production_registry_is_empty_and_blocked(self):
        self.assertTrue(validate_production_registry([], production_safe=False))
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_PRODUCTION_REGISTRY_NON_EMPTY"):
            validate_production_registry([{"id": "real"}], production_safe=False)
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_TEST_ONLY_PRODUCTION_SAFE"):
            validate_production_registry([], production_safe=True)

    def test_historical_authority_rejects_mutation(self):
        authority = b"immutable\n"
        self.assertTrue(validate_historical_authority(authority, authority, authority_ref="fixture")["status"].endswith("VALID"))
        with self.assertRaisesRegex(UIAssetFamilyContractError, "HISTORICAL_EVIDENCE_MUTATION_REJECTED"):
            validate_historical_authority(authority, b"mutated\n", authority_ref="fixture")

    def test_two_runs_are_deterministic(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            a = generate_fixture_pack(Path(first)); b = generate_fixture_pack(Path(second))
            self.assertTrue(compare_generated_outputs(a["outputs"], b["outputs"]))
            validate_determinism(a["outputs"], b["outputs"])

    def test_cache_key_is_complete(self):
        fields = {"family_id": FAMILY_ID, "component_id": self.component["component_id"], "revision": "r", "state": "normal", "scale_factor": 1, "style_token_hash_value": "style", "semantic_input_hash": "semantic"}
        self.assertEqual(len(build_cache_key(**fields)), 64)

    def test_all_classes_build(self):
        self.assertEqual({build_component_manifest(name, self.tokens)["component_class"] for name in UI_COMPONENT_CLASSES}, set(UI_COMPONENT_CLASSES))


if __name__ == "__main__":
    unittest.main()
