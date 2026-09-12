"""Focused v0.25.2 post-merge canonical-state promotion tests."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402
from ugas.state_consistency_v0252 import (  # noqa: E402
    BASELINE_MAIN_SHA,
    CURRENT_GATE,
    NEGATIVE_CONTROL_IDS,
    PROMOTION_BINDING,
    PROMOTION_IMMUTABILITY,
    PROMOTION_NEGATIVE_CONTROLS,
    SOURCE_MERGE_SHA,
    VERSION,
    historical_immutability_failures,
    negative_control_failures,
    validate_main_ci_provenance,
    validate_post_merge_binding,
    validate_state_consistency,
)


def read_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def load_generator():
    path = ROOT / "scripts/validation/run_post_merge_canonical_promotion_v0252.py"
    spec = importlib.util.spec_from_file_location("run_post_merge_canonical_promotion_v0252", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PostMergeCanonicalPromotionV0252Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = read_json("docs/evidence/current-state.json")
        self.checkpoint = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8")
        self.roadmap = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")
        self.matrix = read_json("docs/ugas-v1-capability-matrix.json")
        self.binding = read_json(PROMOTION_BINDING)

    def test_active_schema_and_state_are_v0252(self) -> None:
        schema = read_json("schemas/current-state-v0252.json")
        validate_schema_document(schema)
        validate_instance(self.state, schema)
        self.assertEqual(self.state["version"], VERSION)
        self.assertEqual(self.state["baseline_main_sha"], BASELINE_MAIN_SHA)

    def test_state_is_valid_and_future_main_is_not_a_tracked_invariant(self) -> None:
        result = validate_state_consistency(self.state, self.checkpoint, self.roadmap, self.matrix, self.binding)
        self.assertEqual(result["status"], CURRENT_GATE)
        self.assertEqual(result["failures"], [])
        future = copy.deepcopy(self.state)
        future["simulated_live_main_sha"] = "a" * 40
        result = validate_state_consistency(future, self.checkpoint, self.roadmap, self.matrix, self.binding)
        self.assertEqual(result["failures"], [])

    def test_post_merge_binding_contains_exact_two_main_contexts(self) -> None:
        self.assertEqual(validate_post_merge_binding(self.binding), [])
        contexts = self.binding["provenance"]["post_merge_main_ci"]["contexts"]
        self.assertEqual({item["name"] for item in contexts}, {"UGAS CI / unit-and-validation", "UGAS CI / docker-smoke"})
        self.assertNotIn("UGAS Review / evidence", {item["name"] for item in contexts})
        self.assertEqual(self.binding["source_pr_18"]["merge_sha"], SOURCE_MERGE_SHA)

    def test_main_ci_rejects_pr_only_context(self) -> None:
        mutated = copy.deepcopy(self.binding["provenance"]["post_merge_main_ci"])
        mutated["contexts"].append({"name": "UGAS Review / evidence", "job_id": 1, "conclusion": "SUCCESS"})
        failures = validate_main_ci_provenance(mutated)
        self.assertIn("main_ci_result:context_set", failures)
        self.assertIn("main_ci_result:review_context_forbidden", failures)

    def test_stale_active_pr_and_merge_flags_fail_closed(self) -> None:
        for key, value, expected in (("pr_state", "MERGED", "review:pr_state_invalid"), ("do_not_merge", False, "review:do_not_merge_invalid")):
            mutated = copy.deepcopy(self.state)
            mutated["review"][key] = value
            result = validate_state_consistency(mutated, self.checkpoint, self.roadmap, self.matrix, self.binding)
            self.assertIn(expected, result["failures"])

    def test_production_and_readiness_drift_fail_closed(self) -> None:
        for key, value, expected in (("production_approved", True, "production_approved_invalid"), ("production_readiness_workstream", "STARTED", "production_readiness_workstream_invalid")):
            mutated = copy.deepcopy(self.state)
            mutated[key] = value
            result = validate_state_consistency(mutated, self.checkpoint, self.roadmap, self.matrix, self.binding)
            self.assertIn(expected, result["failures"])

    def test_historical_root_and_negative_controls_are_real(self) -> None:
        self.assertEqual(historical_immutability_failures(read_json(PROMOTION_IMMUTABILITY), ROOT), [])
        controls = read_json(PROMOTION_NEGATIVE_CONTROLS)
        self.assertEqual(set(controls["controls"]), set(NEGATIVE_CONTROL_IDS))
        self.assertEqual(negative_control_failures(controls), [])
        generated = load_generator().negative_controls(self.binding)
        self.assertEqual(generated["status"], "PASS")
        for item in generated["controls"].values():
            self.assertEqual(item["result"], "REJECT")
            self.assertGreater(item["actual_failure_count"], 0)

    def test_review_has_no_self_referential_head(self) -> None:
        self.assertNotIn("head_sha", self.state["review"])
        self.assertNotIn("head_sha_source", self.state["review"])
        self.assertEqual(self.state["review"]["current_exact_head_authority"], "GITHUB_LIVE_ONLY")


if __name__ == "__main__":
    unittest.main()
