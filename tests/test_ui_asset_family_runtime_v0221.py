from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from ugas.ui_asset_family_runtime_v0221 import (
    CLASS_SPECS, FAMILY_ID, UIAssetFamilyContractError, UI_COMPONENT_CLASSES,
    UI_STATES, build_ui_manifest, cache_key_for, compare_generated_outputs,
    generate_fixture_pack, render_component, render_component_to_size,
    validate_cache_record, validate_class_spec_table, validate_component_record,
    validate_determinism, validate_nine_slice, validate_reconstructed_output,
    validate_scale_pixel_relation, validate_state_applicability, validate_ui_manifest,
)


class UIAssetFamilyRuntimeV0221Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = build_ui_manifest()
        self.components = {item["component_class"]: item for item in self.manifest["components"]}

    def test_authoritative_class_table_is_material_and_complete(self):
        validate_class_spec_table()
        self.assertEqual(tuple(CLASS_SPECS), UI_COMPONENT_CLASSES)
        self.assertNotEqual(CLASS_SPECS["button"]["states"], CLASS_SPECS["panel_frame"]["states"])
        self.assertEqual(CLASS_SPECS["cursor"]["stretch_policy"], "NON_STRETCH")

    def test_manifest_has_class_metadata_and_semantic_hashes(self):
        self.assertEqual(validate_ui_manifest(self.manifest)["status"], "UI_ASSET_FAMILY_MANIFEST_VALID")
        for component in self.components.values():
            self.assertTrue(component["class_metadata"])
            self.assertEqual(len(component["content_hash"]), 64)
            self.assertEqual(len(component["semantic_input_hash"]), 64)

    def test_global_but_class_unsupported_state_rejects(self):
        panel = self.components["panel_frame"]
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_STATE_UNSUPPORTED_FOR_COMPONENT"):
            render_component(panel, "selected", 1)

    def test_state_matrix_is_not_flattened(self):
        self.assertTrue(any(tuple(item["supported_states"]) != UI_STATES for item in self.components.values()))
        for component in self.components.values():
            self.assertEqual(validate_state_applicability(component)["supported_states"], component["supported_states"])

    def test_window_and_progress_metadata_are_class_specific(self):
        self.assertIn("header_rect", self.components["window_frame"]["class_metadata"])
        self.assertIn("track_rect", self.components["progress_bar"]["class_metadata"])
        self.assertEqual(self.components["progress_bar"]["class_metadata"]["fill_axis"], "x")
        self.assertTrue(self.components["resource_meter_frame"]["class_metadata"]["frame_only"])

    def test_cursor_hotspot_is_inside_bounds(self):
        cursor = self.components["cursor"]
        hotspot = cursor["class_metadata"]["hotspot"]
        bounds = cursor["visual_bounds"]
        self.assertLess(hotspot["x"], bounds["width"])
        self.assertLess(hotspot["y"], bounds["height"])

    def test_real_nine_slice_reconstruction_at_odd_sizes(self):
        component = self.components["window_frame"]
        for target in ((component["logical_size"][0] + 5, component["logical_size"][1] + 7), (component["logical_size"][0] + 9, component["logical_size"][1] + 3)):
            output = render_component_to_size(component, "normal", 1, target)
            proof = validate_reconstructed_output(output, component, "normal", 1, target)
            self.assertTrue(proof["reconstruction_valid"])
            self.assertEqual(output.size, target)

    def test_nine_slice_small_target_rejects(self):
        component = self.components["window_frame"]
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_NINE_SLICE_TARGET_TOO_SMALL"):
            render_component_to_size(component, "normal", 1, (7, 7))

    def test_mutated_corner_rejects_real_reconstruction(self):
        component = self.components["window_frame"]
        target = (component["logical_size"][0] + 5, component["logical_size"][1] + 7)
        output = render_component_to_size(component, "normal", 1, target)
        output.putpixel((0, 0), (1, 2, 3, 255))
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_STRETCH_OUTPUT_MISMATCH"):
            validate_reconstructed_output(output, component, "normal", 1, target)

    def test_wrong_axis_edge_mutation_rejects(self):
        component = self.components["window_frame"]
        target = (component["logical_size"][0] + 5, component["logical_size"][1] + 7)
        output = render_component_to_size(component, "normal", 1, target)
        output.putpixel((component["stretch_geometry"]["slice_margins"]["left"], 1), (9, 8, 7, 255))
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_STRETCH_OUTPUT_MISMATCH"):
            validate_reconstructed_output(output, component, "normal", 1, target)

    def test_non_stretch_rejects_arbitrary_size(self):
        component = self.components["cursor"]
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_NON_STRETCH_TARGET_INVALID"):
            render_component_to_size(component, "normal", 1, (component["logical_size"][0] + 1, component["logical_size"][1]))

    def test_pixel_correspondence_is_decoded_and_exact(self):
        component = self.components["button"]
        one = render_component(component, "normal", 1)
        two = render_component(component, "normal", 2)
        proof = validate_scale_pixel_relation(one, two, component, "normal")
        self.assertEqual(proof["result"], "PASS")
        two.putpixel((0, 0), (255, 0, 255, 255))
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_SCALE_PIXEL_RELATION_INVALID"):
            validate_scale_pixel_relation(one, two, component, "normal")

    def test_cache_changes_on_geometry_and_class_metadata_mutation(self):
        component = self.components["button"]
        record = {"family_id": component["family_id"], "component_id": component["component_id"], "revision": component["revision"], "state": "normal", "scale_factor": 1, "style_token_hash": component["style_token_hash"], "semantic_input_hash": component["semantic_input_hash"], "content_hash": component["content_hash"], "cache_key": cache_key_for(component, "normal", 1)}
        validate_cache_record(record, component)
        mutated = deepcopy(component); mutated["content_safe_rect"]["x"] += 1
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_SEMANTIC_INPUT_HASH_STALE|UI_CONTENT_HASH_STALE"):
            validate_component_record(mutated)
        stale = deepcopy(component); stale["class_metadata"]["slot_type"] = "armor"
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_SEMANTIC_INPUT_HASH_STALE|UI_CONTENT_HASH_STALE|UI_CLASS_METADATA_INVALID"):
            validate_component_record(stale)

    def test_authority_fingerprint_mutation_rejects(self):
        component = deepcopy(self.components["minimap_frame"])
        component["integration_linkage"]["authority"]["git_blob_sha"] = "0" * 40
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_INTEGRATION_AUTHORITY_STALE"):
            validate_component_record(component)

    def test_two_isolated_fixture_runs_are_deterministic(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            a = generate_fixture_pack(Path(first)); b = generate_fixture_pack(Path(second))
            self.assertTrue(compare_generated_outputs(a["outputs"], b["outputs"]))
            validate_determinism(a["outputs"], b["outputs"])

    def test_production_boundary_remains_test_only(self):
        self.assertFalse(self.manifest["production_approved"])
        self.assertEqual(self.manifest["production_routing"], "BLOCKED")
        self.assertEqual(self.manifest["new_generation"], 0)


if __name__ == "__main__":
    unittest.main()
