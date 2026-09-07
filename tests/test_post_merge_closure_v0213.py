from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from ugas.state_consistency_post_merge_v0213 import validate_post_merge_state, validate_progress_response


ROOT = Path(__file__).resolve().parents[1]


class PostMergeClosureV0213Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        self.binding = json.loads((ROOT / "docs/evidence/github-governance-v0220/v0213-post-merge-binding.json").read_text(encoding="utf-8"))
        self.checkpoint = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8")
        self.continuity = (ROOT / "docs/chat-continuity-protocol.md").read_text(encoding="utf-8")
        self.response_protocol = (ROOT / "docs/project-review-response-protocol.md").read_text(encoding="utf-8")

    def validate(self, state=None, binding=None, checkpoint=None, continuity=None, response_protocol=None):
        return validate_post_merge_state(
            state or self.state,
            binding or self.binding,
            checkpoint if checkpoint is not None else self.checkpoint,
            continuity if continuity is not None else self.continuity,
            response_protocol if response_protocol is not None else self.response_protocol,
        )

    def test_post_merge_state_and_binding_are_consistent(self) -> None:
        result = self.validate()
        self.assertEqual("MAPS_MINIMAP_APPROVED_FOUNDATION_MERGED", result["status"], result)
        self.assertEqual([], result["failures"])

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

    def test_nc_cc_01_main_sha_conflict_is_rejected(self) -> None:
        state = copy.deepcopy(self.state)
        state["main_sha"] = "0" * 40
        result = self.validate(state=state)
        self.assertEqual("POST_MERGE_STATE_FAILED", result["status"])
        self.assertIn("main_sha_invalid", result["failures"])

    def test_nc_cc_02_multiple_next_actions_are_rejected(self) -> None:
        state = copy.deepcopy(self.state)
        state["allowed_next_actions"] = ["start_ui_asset_family_v0220", "start_vfx_asset_family"]
        result = self.validate(state=state)
        self.assertEqual("POST_MERGE_STATE_FAILED", result["status"])
        self.assertIn("allowed_next_actions_invalid", result["failures"])

    def test_nc_pr_01_missing_progress_field_is_rejected(self) -> None:
        response = {key: "present" for key in (
            "capability_current", "ugas_v1_overall", "completed_capabilities", "remaining_gates",
            "estimated_cycles", "eta_optimistic", "eta_realistic", "eta_conservative", "confidence",
            "critical_path", "status_delta",
        )}
        response.pop("eta_realistic")
        response.update(source_main_sha=self.state["main_sha"], source_current_gate=self.state["current_gate"], source_mode="LIVE_REPOSITORY_AND_GITHUB")
        result = validate_progress_response(response, self.state)
        self.assertEqual("PROGRESS_RESPONSE_FAILED", result["status"])
        self.assertIn("missing:eta_realistic", result["failures"])

    def test_nc_pr_02_stale_progress_source_cannot_override_live_state(self) -> None:
        response = {key: "present" for key in (
            "capability_current", "ugas_v1_overall", "completed_capabilities", "remaining_gates",
            "estimated_cycles", "eta_optimistic", "eta_realistic", "eta_conservative", "confidence",
            "critical_path", "status_delta",
        )}
        response.update(source_main_sha="0" * 40, source_current_gate=self.state["current_gate"], source_mode="LIVE_REPOSITORY_AND_GITHUB")
        result = validate_progress_response(response, self.state)
        self.assertEqual("PROGRESS_RESPONSE_FAILED", result["status"])
        self.assertIn("source_main_sha_mismatch", result["failures"])

