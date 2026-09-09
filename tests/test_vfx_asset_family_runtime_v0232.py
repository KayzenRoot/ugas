"""Focused F-23R/F-26R/F-27R correction tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from ugas.state_consistency_v0232 import BASELINE_MAIN_SHA, CURRENT_GATE, FEATURE_BRANCH, NEXT_ACTION, resolve_next_actions, validate_state_consistency
from ugas.vfx_asset_family_runtime_v0232 import (
    VFXAssetFamilyContractError,
    build_budget_fallback_sheet,
    generate_fixture_pack,
    render_fallback_output,
    select_fallback,
    strict_boolean_observation,
    validate_degraded_output,
    validate_effect_record,
)


class VfxAssetFamilyRuntimeV0232Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="ugas-test-vfx-v0232-")
        self.root = Path(self.tmp.name)
        self.pack = generate_fixture_pack(self.root)
        self.profile = {"profile_id": "constrained-v1", "max_particles_per_instance": 8, "max_layers": 1, "max_spawn_events_per_second": 10, "max_visual_area_ratio": 0.20, "supported_steps": ["REDUCE_PARTICLE_COUNT", "REDUCE_LAYER_COUNT", "REDUCE_SPAWN_RATE", "REDUCE_VISUAL_AREA", "REDUCE_FRAME_COUNT", "REDUCE_OPACITY", "REDUCE_RADIUS", "SKIP_VISUAL"]}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_exact_per_class_allowlist_rejects_unknown(self) -> None:
        record = deepcopy(self.pack["records"][0]); record["semantic_input"]["semantics"]["unknown_extra"] = True
        with self.assertRaises(VFXAssetFamilyContractError) as context:
            validate_effect_record(record, self.root)
        self.assertEqual(context.exception.rejection_class, "VFX_SEMANTIC_UNKNOWN_FIELD")

    def test_forbidden_gameplay_vocabulary_still_has_priority(self) -> None:
        record = deepcopy(self.pack["records"][0]); record["semantic_input"]["semantics"]["damage_amount"] = 1
        with self.assertRaises(VFXAssetFamilyContractError) as context:
            validate_effect_record(record, self.root)
        self.assertEqual(context.exception.rejection_class, "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN")

    def test_provenance_uses_complete_contract_and_preserves_narrow_hash(self) -> None:
        record = self.pack["records"][0]
        self.assertEqual(record["provenance"]["input_hash"], record["semantic_contract_hash"])
        self.assertEqual(record["provenance"]["raw_semantic_input_hash"], record["semantic_input_hash"])
        mutated = deepcopy(record); mutated["provenance"]["input_hash"] = mutated["semantic_input_hash"]
        with self.assertRaises(VFXAssetFamilyContractError) as context:
            validate_effect_record(mutated, self.root)
        self.assertEqual(context.exception.rejection_class, "VFX_PROVENANCE_HASH_INVALID")

    def test_fallback_changes_actual_bytes_and_is_deterministic(self) -> None:
        record = self.pack["records"][2]
        result = select_fallback(record, self.profile)
        first = render_fallback_output(record, result, self.root, self.root / "degraded-a")
        second = render_fallback_output(record, result, self.root, self.root / "degraded-b")
        validate_degraded_output(record, first, self.root / "degraded-a")
        validate_degraded_output(record, second, self.root / "degraded-b")
        self.assertNotEqual(first["output_hash"], record["content_hash"])
        self.assertEqual(first["output_hash"], second["output_hash"])
        self.assertEqual(first["frame_count"], result["after"]["frame_count"])
        self.assertLess(first["frames"][0]["alpha_bounds"][2] - first["frames"][0]["alpha_bounds"][0], 96)

    def test_three_degradation_mechanisms_and_terminal_skip_are_real(self) -> None:
        mechanisms = set()
        selected = ((self.pack["records"][1], {**self.profile, "max_particles_per_instance": 24, "max_layers": 2, "max_spawn_events_per_second": 12}), (self.pack["records"][2], self.profile), (self.pack["records"][5], {**self.profile, "max_layers": 3, "max_spawn_events_per_second": 30}))
        for record, profile in selected:
            result = select_fallback(record, profile)
            output = render_fallback_output(record, result, self.root, self.root / "outputs" / record["effect_class"])
            mechanisms.update(output["degradation_mechanisms"])
        self.assertTrue({"REDUCE_OPACITY", "REDUCE_PARTICLE_COUNT", "REDUCE_RADIUS"}.issubset(mechanisms))
        skipped = render_fallback_output(self.pack["records"][2], select_fallback(self.pack["records"][2], self.profile), self.root, self.root / "skip", force_skip=True)
        validate_degraded_output(self.pack["records"][2], skipped, self.root / "skip")
        self.assertEqual(skipped["terminal_step"], "SKIP_VISUAL")

    def test_full_and_degraded_qa_sheet_contains_actual_panels(self) -> None:
        record = self.pack["records"][2]; result = select_fallback(record, self.profile); degraded = render_fallback_output(record, result, self.root, self.root / "sheet-degraded")
        path = build_budget_fallback_sheet(self.root, self.root / "sheet-degraded", record, degraded, self.root / "sheet.png")
        self.assertTrue(path.is_file() and path.stat().st_size > 100)

    def test_strict_boolean_contract_rejects_truthy_non_bools(self) -> None:
        for value in (None, 0, 1, "", "PASS", [], {}, object()):
            self.assertFalse(strict_boolean_observation(value))
        self.assertTrue(strict_boolean_observation(True))
        self.assertFalse(strict_boolean_observation(False))


def _state() -> dict:
    return {"schema_version": "0.23.2", "version": "0.23.2", "phase": "VFX_ASSET_FAMILY", "baseline_main_sha": BASELINE_MAIN_SHA, "vfx_base_main_sha": BASELINE_MAIN_SHA, "current_gate": CURRENT_GATE, "next_candidate": "ORCHESTRATION_RUNTIME_HARDENING", "allowed_next_actions": [NEXT_ACTION], "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0, "vfx_asset_family": "TECHNICALLY_QUALIFIED_FOUNDATION", "vfx_asset_family_external_review": "REQUIRED", "real_vfx_asset_coverage": "NONE", "synthetic_vfx_fixture": "TEST_ONLY", "forbidden_actions": ["direct_main_push", "force_push_or_history_rewrite", "enable_production_routing", "new_generation", "orchestration_runtime_hardening", "real_vfx_assets", "provider_generation", "diffusion_generation"], "review": {"repository": "KayzenRoot/ugas", "baseline_head": BASELINE_MAIN_SHA, "branch_base_commit": BASELINE_MAIN_SHA, "feature_branch": FEATURE_BRANCH, "execution_mode": "GITHUB_PR_FIRST", "merge_policy": "NO_SELF_MERGE_UNTIL_EXTERNAL_REVIEW", "pr_number": 14, "pr_state": "OPEN", "head_sha": None, "head_sha_source": "GitHub LIVE exact-head metadata", "external_review_required": True, "do_not_merge": True, "required_contexts": ["UGAS CI / unit-and-validation", "UGAS CI / docker-smoke", "UGAS Review / evidence"]}, "evidence": {"vfx_root": "docs/evidence/vfx-asset-family-runtime-v0232/"}}


class StateConsistencyV0232Tests(unittest.TestCase):
    def test_open_pr_has_only_external_review_action(self) -> None:
        state = _state(); result = validate_state_consistency(state, "VFX_ASSET_FAMILY " + CURRENT_GATE + " v0.23.2", "v0.23.2 " + NEXT_ACTION, {"version": "0.23.2", "next_candidate": "ORCHESTRATION_RUNTIME_HARDENING"})
        self.assertEqual(result["status"], CURRENT_GATE)
        live = {"source": "GITHUB_LIVE", "repository": "KayzenRoot/ugas", "pr_number": 14, "branch": FEATURE_BRANCH, "base_sha": BASELINE_MAIN_SHA, "head_sha": "a" * 40, "pr_state": "OPEN", "merged": False, "external_approval": False}
        self.assertEqual(resolve_next_actions(state, live)["allowed_next_actions"], [NEXT_ACTION])


if __name__ == "__main__":
    unittest.main()
