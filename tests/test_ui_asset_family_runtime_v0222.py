from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest

from ugas.state_consistency_v0222 import resolve_next_actions, validate_state_consistency
from ugas.ui_asset_family_runtime_v0222 import (
    UIAssetFamilyContractError, build_ui_manifest, cache_key_for, generate_fixture_pack,
    progress_fill_rect, render_component, render_component_to_size,
    validate_cache_record, validate_progress_bar_contract, verify_nine_slice_invariants,
)


ROOT = Path(__file__).resolve().parents[1]


class UIAssetFamilyRuntimeV0222Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = build_ui_manifest()
        self.components = {item["component_class"]: item for item in self.manifest["components"]}
        self.state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))

    def test_complete_progress_contract_and_three_values(self):
        progress = self.components["progress_bar"]
        proof = validate_progress_bar_contract(progress)
        self.assertIn("frame_rect", proof)
        self.assertEqual(progress_fill_rect(progress, 0.0)["width"], 0)
        self.assertEqual(progress_fill_rect(progress, 0.5)["width"], progress["class_metadata"]["fill_rect"]["width"] // 2)
        self.assertEqual(progress_fill_rect(progress, 1.0)["width"], progress["class_metadata"]["fill_rect"]["width"])

    def test_progress_invalid_range_origin_direction_and_geometry_reject(self):
        progress = self.components["progress_bar"]
        for field, value, rejection in (("domain", [-1.0, 2.0], "UI_PROGRESS_NORMALIZED_RANGE_INVALID"), ("origin", "right", "UI_PROGRESS_ORIGIN_INVALID"), ("direction", "negative", "UI_PROGRESS_DIRECTION_INVALID")):
            mutated = deepcopy(progress); mutated["class_metadata"]["normalized_fill"][field] = value
            with self.assertRaisesRegex(UIAssetFamilyContractError, rejection):
                validate_progress_bar_contract(mutated)
        mutated = deepcopy(progress); mutated["class_metadata"]["fill_rect"]["width"] = mutated["class_metadata"]["track_rect"]["width"] + 1
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_PROGRESS_GEOMETRY_INVALID"):
            validate_progress_bar_contract(mutated)

    def test_independent_nine_slice_proof_at_two_non_native_sizes_and_mutations(self):
        component = self.components["window_frame"]
        source = render_component(component, "normal", 1)
        for target_size in ((component["logical_size"][0] + 5, component["logical_size"][1] + 7), (component["logical_size"][0] + 9, component["logical_size"][1] + 3)):
            output = render_component_to_size(component, "normal", 1, target_size)
            self.assertEqual(verify_nine_slice_invariants(source, output, component["stretch_geometry"]["slice_margins"])["status"], "PASS")
        output.putpixel((0, 0), (1, 2, 3, 255))
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_NINE_SLICE_INVARIANT_INVALID"):
            verify_nine_slice_invariants(source, output, component["stretch_geometry"]["slice_margins"])

    def test_generic_ui_uses_local_authority_and_minimap_external_authority(self):
        self.assertEqual(self.components["button"]["integration_linkage"]["authority"]["authority_type"], "LOCAL_UI_STYLE_ART_DNA")
        self.assertEqual(self.components["minimap_frame"]["integration_linkage"]["authority"]["authority_type"], "EXTERNAL_CAPABILITY_CONTRACT")
        self.assertNotEqual(self.components["button"]["integration_linkage"]["authority"]["capability_id"], "maps_minimap_runtime")

    def test_cache_identity_includes_authority(self):
        component = self.components["button"]
        record = {"family_id": component["family_id"], "component_id": component["component_id"], "revision": component["revision"], "state": "normal", "scale_factor": 1, "style_token_hash": component["style_token_hash"], "semantic_input_hash": component["semantic_input_hash"], "content_hash": component["content_hash"], "authority_identity_hash": __import__("hashlib").sha256(__import__("json").dumps(component["integration_authority_identity"], sort_keys=True, separators=(",", ":")).encode() + b"\n").hexdigest(), "cache_key": cache_key_for(component, "normal", 1)}
        validate_cache_record(record, component)
        record["authority_identity_hash"] = "0" * 64
        with self.assertRaisesRegex(UIAssetFamilyContractError, "UI_CACHE_SEMANTIC_IDENTITY_STALE"):
            validate_cache_record(record, component)

    def test_lifecycle_four_live_scenarios(self):
        unresolved = resolve_next_actions(self.state, {"source_mode": "GITHUB_LIVE", "pr_number": 13, "external_approval": False, "merged": False})
        self.assertEqual(unresolved["allowed_next_actions"], ["external_review_ui_asset_family_v0222"])
        approved = resolve_next_actions(self.state, {"source_mode": "GITHUB_LIVE", "pr_number": 13, "external_approval": True, "merged": False})
        self.assertEqual(approved["allowed_next_actions"], ["governed_merge_pr_13"])
        pending = resolve_next_actions(self.state, {"source_mode": "GITHUB_LIVE", "pr_number": 13, "external_approval": True, "merged": True, "post_merge_main_ci": {"supported_contexts": ["UGAS CI / unit-and-validation", "UGAS CI / docker-smoke"], "contexts": [{"name": "UGAS CI / unit-and-validation", "status": "in_progress", "conclusion": None, "head_sha": "future"}, {"name": "UGAS CI / docker-smoke", "status": "in_progress", "conclusion": None, "head_sha": "future"}]}})
        self.assertFalse(pending["vfx_allowed"])
        closed = resolve_next_actions(self.state, {"source_mode": "GITHUB_LIVE", "pr_number": 13, "external_approval": True, "merged": True, "post_merge_main_ci": {"supported_contexts": ["UGAS CI / unit-and-validation", "UGAS CI / docker-smoke"], "contexts": [{"name": "UGAS CI / unit-and-validation", "status": "completed", "conclusion": "success", "head_sha": "future"}, {"name": "UGAS CI / docker-smoke", "status": "completed", "conclusion": "success", "head_sha": "future"}]}})
        self.assertEqual(closed["allowed_next_actions"], ["start_vfx_asset_family_v0230"])

    def test_two_isolated_fixture_runs_are_deterministic(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            one = generate_fixture_pack(Path(first)); two = generate_fixture_pack(Path(second))
            self.assertEqual(one["outputs"], two["outputs"])

    def test_production_boundary_is_blocked(self):
        self.assertFalse(self.manifest["production_approved"])
        self.assertEqual(self.manifest["production_routing"], "BLOCKED")
        self.assertEqual(self.manifest["new_generation"], 0)


if __name__ == "__main__":
    unittest.main()
