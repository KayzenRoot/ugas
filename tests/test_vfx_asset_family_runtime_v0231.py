"""Focused F-22..F-28 correction tests."""

from __future__ import annotations

from copy import deepcopy
import tempfile
from pathlib import Path
import unittest

from ugas.state_consistency_v0231 import (
    BASELINE_MAIN_SHA,
    CURRENT_GATE,
    FEATURE_BRANCH,
    NEXT_ACTION,
    ORCHESTRATION_ACTION,
    resolve_next_actions,
    validate_live_pr_binding,
    validate_state_consistency,
)
from ugas.vfx_asset_family_runtime_v0231 import (
    CLASS_SPECS,
    EFFECT_CLASSES,
    VFXAssetFamilyContractError,
    build_effect_fixture,
    cache_key_for,
    generate_fixture_pack,
    select_fallback,
    strict_boolean_observation,
    validate_effect_record,
    validate_fallback_result,
    validate_production_registry,
)


class VfxAssetFamilyRuntimeV0231Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="ugas-test-vfx-v0231-")
        self.root = Path(self.tmp.name)
        self.pack = generate_fixture_pack(self.root)
        self.profile = {
            "profile_id": "constrained-v1",
            "max_particles_per_instance": 8,
            "max_layers": 1,
            "max_spawn_events_per_second": 10,
            "max_visual_area_ratio": 0.20,
            "supported_steps": ["REDUCE_PARTICLE_COUNT", "REDUCE_LAYER_COUNT", "REDUCE_SPAWN_RATE", "REDUCE_VISUAL_AREA", "REDUCE_FRAME_COUNT", "REDUCE_OPACITY", "REDUCE_RADIUS", "SKIP_VISUAL"],
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_typed_class_semantics_are_not_placeholders(self) -> None:
        for record in self.pack["records"]:
            semantics = record["semantic_input"]["semantics"]
            self.assertTrue(set(CLASS_SPECS[record["effect_class"]]["required_semantics"]).issubset(semantics))
            self.assertFalse(any(isinstance(value, str) and value.startswith("fixture-") for key, value in semantics.items() if key not in {"owner_anchor", "weapon_anchor", "caster_anchor", "target_anchor", "ambient_region", "projectile_type", "facing", "charge_phase", "status_kind", "feedback_kind", "termination", "termination_condition"}))

    def test_gameplay_vocabulary_and_nested_authority_are_rejected(self) -> None:
        record = deepcopy(self.pack["records"][0])
        record["semantic_input"]["semantics"]["damage_amount"] = 10
        with self.assertRaises(VFXAssetFamilyContractError) as context:
            validate_effect_record(record, self.root)
        self.assertEqual(context.exception.rejection_class, "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN")
        record = deepcopy(self.pack["records"][0])
        record["semantic_input"]["semantics"]["gameplay_authority"] = "COMBAT_SYSTEM"
        with self.assertRaises(VFXAssetFamilyContractError) as context:
            validate_effect_record(record, self.root)
        self.assertEqual(context.exception.rejection_class, "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN")

    def test_loop_period_and_per_effect_budget_are_real_contracts(self) -> None:
        record = deepcopy(next(item for item in self.pack["records"] if item["effect_class"] == "projectile_trail"))
        record["lifecycle"]["loop_period_ms"] = None
        with self.assertRaises(VFXAssetFamilyContractError) as context:
            validate_effect_record(record, self.root)
        self.assertEqual(context.exception.rejection_class, "VFX_LOOP_PERIOD_INVALID")
        record = deepcopy(next(item for item in self.pack["records"] if item["effect_class"] == "projectile_trail"))
        record["budget_profile"]["max_particles_per_instance"] = 97
        with self.assertRaises(VFXAssetFamilyContractError) as context:
            validate_effect_record(record, self.root)
        self.assertEqual(context.exception.rejection_class, "VFX_BUDGET_EXCEEDED")

    def test_decoded_alpha_is_truthful_and_metadata_mutation_rejects(self) -> None:
        for record in self.pack["records"]:
            self.assertFalse(record["blend_alpha"]["premultiplied"])
        record = deepcopy(self.pack["records"][2])
        record["blend_alpha"]["alpha_mode"] = "PREMULTIPLIED"
        record["blend_alpha"]["premultiplied"] = True
        with self.assertRaises(VFXAssetFamilyContractError) as context:
            validate_effect_record(record, self.root)
        self.assertEqual(context.exception.rejection_class, "VFX_BLEND_ALPHA_INVALID")

    def test_deterministic_constrained_fallback_changes_visual_budget_only(self) -> None:
        record = self.pack["records"][2]
        result = select_fallback(record, self.profile)
        self.assertTrue(result["deterministic"])
        self.assertTrue(result["visual_degraded"])
        self.assertTrue(result["semantic_preserved"])
        self.assertFalse(result["changes_gameplay"])
        self.assertLessEqual(result["after"]["particles"], 8)
        with self.assertRaises(VFXAssetFamilyContractError):
            invalid = deepcopy(result)
            invalid["applied_steps"] = ["UNSUPPORTED_STEP"]
            validate_fallback_result(record, invalid, self.profile)

    def test_complete_semantic_contract_and_cache_identity_cover_mutations(self) -> None:
        record = deepcopy(self.pack["records"][0])
        record["lifecycle"]["duration_ms"] += 1
        with self.assertRaises(VFXAssetFamilyContractError) as context:
            validate_effect_record(record, self.root)
        self.assertEqual(context.exception.rejection_class, "VFX_TIMING_INVALID")
        record = deepcopy(self.pack["records"][0])
        record["integration"]["integration_revision"] = "mutated"
        with self.assertRaises(VFXAssetFamilyContractError) as context:
            validate_effect_record(record, self.root)
        self.assertEqual(context.exception.rejection_class, "VFX_INTEGRATION_MODE_INVALID")
        self.assertEqual(self.pack["records"][0]["cache_key"], cache_key_for(self.pack["records"][0]))

    def test_strict_boolean_gate_and_production_boundary(self) -> None:
        for value in (None, 0, 1, "", "PASS", [], {}, object()):
            self.assertFalse(strict_boolean_observation(value))
        self.assertTrue(strict_boolean_observation(True))
        self.assertFalse(strict_boolean_observation(False))
        self.assertEqual(validate_production_registry([])["status"], "PASS")


def _state() -> dict:
    return {
        "schema_version": "0.23.1", "version": "0.23.1", "phase": "VFX_ASSET_FAMILY", "baseline_main_sha": BASELINE_MAIN_SHA, "vfx_base_main_sha": BASELINE_MAIN_SHA,
        "current_gate": CURRENT_GATE, "next_candidate": "ORCHESTRATION_RUNTIME_HARDENING", "allowed_next_actions": [NEXT_ACTION], "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0,
        "vfx_asset_family": "TECHNICALLY_QUALIFIED_FOUNDATION", "vfx_asset_family_external_review": "REQUIRED", "ui_asset_family": "APPROVED_FOUNDATION", "ui_asset_family_lifecycle": "MERGED_CLOSED", "real_vfx_asset_coverage": "NONE", "synthetic_vfx_fixture": "TEST_ONLY",
        "forbidden_actions": ["direct_main_push", "force_push_or_history_rewrite", "enable_production_routing", "new_generation", "orchestration_runtime_hardening", "real_vfx_assets", "provider_generation", "diffusion_generation"],
        "review": {"repository": "KayzenRoot/ugas", "baseline_head": BASELINE_MAIN_SHA, "branch_base_commit": BASELINE_MAIN_SHA, "feature_branch": FEATURE_BRANCH, "execution_mode": "GITHUB_PR_FIRST", "merge_policy": "NO_SELF_MERGE_UNTIL_EXTERNAL_REVIEW", "pr_number": 14, "pr_state": "OPEN", "head_sha": None, "head_sha_source": "GitHub LIVE exact-head metadata", "external_review_required": True, "do_not_merge": True, "required_contexts": ["UGAS CI / unit-and-validation", "UGAS CI / docker-smoke", "UGAS Review / evidence"]},
        "evidence": {"vfx_root": "docs/evidence/vfx-asset-family-runtime-v0231/"},
    }


class StateConsistencyV0231Tests(unittest.TestCase):
    def test_null_tracked_head_is_valid_but_stale_current_head_is_not(self) -> None:
        state = _state()
        result = validate_state_consistency(state, "VFX_ASSET_FAMILY v0.23.1 " + CURRENT_GATE, "v0.23.1 " + NEXT_ACTION, {"version": "0.23.1", "next_candidate": "ORCHESTRATION_RUNTIME_HARDENING"})
        self.assertEqual(result["status"], CURRENT_GATE)
        state["review"]["head_sha"] = "c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72"
        self.assertIn("review-head-must-be-live-only", validate_state_consistency(state)["failures"])

    def test_orchestration_requires_exact_live_merge_and_two_contexts(self) -> None:
        sha = "a" * 40
        live = {"source": "GITHUB_LIVE", "repository": "KayzenRoot/ugas", "pr_number": 14, "branch": FEATURE_BRANCH, "base_sha": BASELINE_MAIN_SHA, "head_sha": sha, "pr_state": "MERGED", "merged": True, "external_approval": True, "merge_commit_sha": sha, "current_main_sha": sha, "post_merge_main_ci": {"commit_sha": sha, "context_records": [{"context": "UGAS CI / unit-and-validation", "status": "completed", "conclusion": "success", "head_sha": sha}, {"context": "UGAS CI / docker-smoke", "status": "completed", "conclusion": "success", "head_sha": sha}]}}
        self.assertEqual(resolve_next_actions(_state(), live)["allowed_next_actions"], [ORCHESTRATION_ACTION])
        for mutation in ({"current_main_sha": "b" * 40}, {"post_merge_main_ci": {"commit_sha": sha, "context_records": [{"context": "UGAS CI / unit-and-validation", "status": "completed", "conclusion": "success", "head_sha": sha}, {"context": "UGAS CI / docker-smoke", "status": "completed", "conclusion": "success", "head_sha": "b" * 40}]}}, {"post_merge_main_ci": {"commit_sha": sha, "context_records": [{"context": "UGAS CI / unit-and-validation", "status": "pending", "conclusion": None, "head_sha": sha}, {"context": "UGAS CI / docker-smoke", "status": "completed", "conclusion": "success", "head_sha": sha}]}}):
            candidate = deepcopy(live)
            candidate.update(mutation)
            self.assertFalse(resolve_next_actions(_state(), candidate)["orchestration_allowed"])

    def test_open_unapproved_pr_has_one_safe_action_and_live_binding_is_required(self) -> None:
        live = {"source": "GITHUB_LIVE", "repository": "KayzenRoot/ugas", "pr_number": 14, "branch": FEATURE_BRANCH, "base_sha": BASELINE_MAIN_SHA, "head_sha": "c" * 40, "pr_state": "OPEN", "merged": False, "external_approval": False}
        self.assertEqual(resolve_next_actions(_state(), live)["allowed_next_actions"], [NEXT_ACTION])
        invalid = dict(live); invalid["source"] = "TRACKED_STATE"
        self.assertEqual(validate_live_pr_binding(invalid)["status"], "LIVE_PR_BINDING_FAILED")


if __name__ == "__main__":
    unittest.main()
