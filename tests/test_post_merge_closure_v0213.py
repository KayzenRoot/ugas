from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ugas.state_consistency_post_merge_v0213 import (  # noqa: E402
    BASELINE_MAIN_SHA,
    CLOSURE_ACTION,
    UI_ACTION,
    resolve_next_actions,
    validate_main_ci_provenance,
    validate_post_merge_state,
    validate_progress_response,
)


LIVE_MAIN_SHA = "f" * 40


class PostMergeClosureV0213Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        self.binding = json.loads((ROOT / "docs/evidence/github-governance-v0220/v0213-post-merge-binding.json").read_text(encoding="utf-8"))
        self.checkpoint = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8")
        self.continuity = (ROOT / "docs/chat-continuity-protocol.md").read_text(encoding="utf-8")
        self.response_protocol = (ROOT / "docs/project-review-response-protocol.md").read_text(encoding="utf-8")

    def validate(self, state=None, binding=None):
        return validate_post_merge_state(
            state or self.state,
            binding or self.binding,
            self.checkpoint,
            self.continuity,
            self.response_protocol,
        )

    def valid_response(self, live_main_sha: str = LIVE_MAIN_SHA) -> dict:
        response = {key: "present" for key in (
            "capability_current", "ugas_v1_overall", "completed_capabilities", "remaining_gates",
            "estimated_cycles", "eta_optimistic", "eta_realistic", "eta_conservative", "confidence",
            "critical_path", "status_delta",
        )}
        response.update(
            source_live_main_sha=live_main_sha,
            source_baseline_main_sha=self.state["baseline_main_sha"],
            source_current_gate=self.state["current_gate"],
            source_mode="LIVE_REPOSITORY_AND_GITHUB",
        )
        return response

    def test_post_merge_state_and_binding_are_consistent(self) -> None:
        result = self.validate()
        self.assertEqual("MAPS_MINIMAP_APPROVED_FOUNDATION_MERGED", result["status"], result)
        self.assertEqual([], result["failures"])
        self.assertNotIn("main_sha", self.state)
        self.assertEqual(BASELINE_MAIN_SHA, self.state["baseline_main_sha"])

    def test_nc_pm_01_open_pr11_cannot_survive_merged_binding(self) -> None:
        state = copy.deepcopy(self.state)
        state["review"]["pr_state"] = "OPEN"
        result = self.validate(state=state)
        self.assertEqual("POST_MERGE_STATE_FAILED", result["status"])
        self.assertIn("review:pr_state", result["failures"])

    def test_nc_pm_02_missing_merge_sha_is_rejected(self) -> None:
        state = copy.deepcopy(self.state)
        state["bookkeeping_approval"]["merged_main_sha"] = None
        result = self.validate(state=state)
        self.assertEqual("POST_MERGE_STATE_FAILED", result["status"])
        self.assertIn("bookkeeping:merged_main_sha", result["failures"])

    def test_nc_cc_01_future_live_main_does_not_invalidate_historical_baseline(self) -> None:
        result = self.validate()
        self.assertEqual("MAPS_MINIMAP_APPROVED_FOUNDATION_MERGED", result["status"])
        progress = validate_progress_response(self.valid_response(LIVE_MAIN_SHA), self.state, LIVE_MAIN_SHA)
        self.assertEqual("PROGRESS_RESPONSE_PASSED", progress["status"], progress)

    def test_nc_cc_01_conflicting_baseline_is_rejected(self) -> None:
        state = copy.deepcopy(self.state)
        state["baseline_main_sha"] = "0" * 40
        result = self.validate(state=state)
        self.assertEqual("POST_MERGE_STATE_FAILED", result["status"])
        self.assertIn("baseline_main_sha_invalid", result["failures"])

    def test_nc_cc_02_conflicting_closure_base_is_rejected(self) -> None:
        binding = copy.deepcopy(self.binding)
        binding["closure_base_sha"] = "0" * 40
        result = self.validate(binding=binding)
        self.assertEqual("POST_MERGE_STATE_FAILED", result["status"])
        self.assertIn("binding:closure_base_sha", result["failures"])

    def test_nc_gate_01_ui_cannot_be_allowed_while_closure_is_open(self) -> None:
        state = copy.deepcopy(self.state)
        state["allowed_next_actions"] = [UI_ACTION]
        result = self.validate(state=state)
        self.assertEqual("POST_MERGE_STATE_FAILED", result["status"])
        self.assertIn("allowed_next_actions_invalid", result["failures"])

    def test_nc_gate_02_unblocked_ui_contradicts_unresolved_closure(self) -> None:
        state = copy.deepcopy(self.state)
        state["ui_start_gate"]["status"] = "UNBLOCKED"
        result = self.validate(state=state)
        self.assertEqual("POST_MERGE_STATE_FAILED", result["status"])
        self.assertIn("ui_start_gate:status", result["failures"])

    def test_nc_gate_03_live_approved_merge_resolves_ui_without_mutation(self) -> None:
        state_before = copy.deepcopy(self.state)
        binding_before = copy.deepcopy(self.binding)
        result = resolve_next_actions(self.state, {
            "pr_number": 12,
            "pr_state": "MERGED",
            "external_approval": True,
            "merged": True,
            "source_mode": "GITHUB_LIVE",
        })
        self.assertEqual("UI_ASSET_FAMILY_UNBLOCKED", result["status"])
        self.assertEqual([UI_ACTION], result["allowed_next_actions"])
        self.assertEqual(state_before, self.state)
        self.assertEqual(binding_before, self.binding)

    def test_main_ci_provenance_contains_exactly_two_real_contexts(self) -> None:
        result = validate_main_ci_provenance(self.binding, ["UGAS CI / unit-and-validation", "UGAS CI / docker-smoke"])
        self.assertEqual("PASS", result["status"], result)

    def test_nc_gate_04_main_ci_cannot_include_pr_only_review_context(self) -> None:
        binding = copy.deepcopy(self.binding)
        binding["post_merge_main_ci"]["contexts"].append({
            "name": "UGAS Review / evidence",
            "status": "completed",
            "conclusion": "success",
            "head_sha": self.binding["merge_commit"],
            "check_run_id": 1,
            "workflow_run_id": 1,
        })
        result = validate_main_ci_provenance(binding)
        self.assertEqual("FAIL", result["status"])
        self.assertIn("context_set", result["failures"])

    def test_nc_pr_01_missing_progress_field_is_rejected(self) -> None:
        response = self.valid_response()
        response.pop("eta_realistic")
        result = validate_progress_response(response, self.state, LIVE_MAIN_SHA)
        self.assertEqual("PROGRESS_RESPONSE_FAILED", result["status"])
        self.assertIn("missing:eta_realistic", result["failures"])

    def test_nc_pr_02_stale_progress_source_cannot_override_live_state(self) -> None:
        response = self.valid_response("0" * 40)
        result = validate_progress_response(response, self.state, LIVE_MAIN_SHA)
        self.assertEqual("PROGRESS_RESPONSE_FAILED", result["status"])
        self.assertIn("source_live_main_sha_mismatch", result["failures"])

    def test_nc_pr_03_legacy_main_source_field_is_rejected(self) -> None:
        response = self.valid_response()
        response["source_main_sha"] = LIVE_MAIN_SHA
        result = validate_progress_response(response, self.state, LIVE_MAIN_SHA)
        self.assertEqual("PROGRESS_RESPONSE_FAILED", result["status"])
        self.assertIn("source_main_sha_forbidden", result["failures"])


if __name__ == "__main__":
    unittest.main()
