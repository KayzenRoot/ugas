"""v0.5.4 license, estimator and provider-lane evidence regressions."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))

from ugas.pose_qa_estimator import EXPECTED_MODEL_SHA256, PREPROCESS_POLICIES
from ugas.schema_validation import validate_instance, validate_schema_document
from ugas.state_consistency import validate_state_consistency
from scripts.validation.run_v054_lane_recheck import _validate_thresholds


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


class PoseQAV054Tests(unittest.TestCase):
    def test_official_license_is_local_only(self):
        license_evidence = load("docs/evidence/pose-qa-license-resolution.json")
        self.assertEqual("POSE_QA_LOCAL_USE_LICENSE_RESOLVED", license_evidence["status"])
        self.assertEqual("Pose landmarker (Full)", license_evidence["official_task_docs"]["bundle_variant"])
        self.assertEqual("Apache-2.0", license_evidence["official_model_card"]["license"])
        self.assertFalse(license_evidence["policy"]["redistribute_bundle_in_ugas"])

    def test_bundle_hash_is_versioned_and_not_published(self):
        model = load("docs/evidence/pose-qa-estimator-model-v054.json")["model"]
        self.assertEqual(EXPECTED_MODEL_SHA256, model["sha256"])
        self.assertGreater(model["bytes"], 0)
        self.assertEqual("RESOLVED_LOCAL_QA", model["license_status"])
        self.assertTrue(model["outside_git"])
        self.assertTrue(model["outside_review_zip"])

    def test_single_global_preprocess_policy_and_detectability(self):
        detectability = load("docs/evidence/pose-qa-estimator-detectability.json")
        self.assertEqual("transparent_neutral_gray", detectability["selected_preprocess_policy"])
        self.assertEqual(4, len(detectability["policy_selection"]["policy_matrix"]))
        self.assertEqual(tuple(PREPROCESS_POLICIES), tuple(item["policy"] for item in detectability["policy_selection"]["policy_matrix"]))
        self.assertEqual(10, detectability["summary"]["measurable_images"])
        self.assertEqual(8, detectability["summary"]["walk_frames_measurable"])
        self.assertGreaterEqual(detectability["summary"]["median_measurable_body_joints"], 12)
        self.assertEqual(0, detectability["summary"]["left_right_inversion_count"])

    def test_thresholds_reject_wrong_seed_or_range_policy(self):
        thresholds = load("docs/evidence/pose-thresholds-v054.json")
        _validate_thresholds(thresholds)
        wrong = copy.deepcopy(thresholds)
        wrong["fresh_execution"]["seeds"] = [1, 2, 3]
        with self.assertRaisesRegex(RuntimeError, "seed"):
            _validate_thresholds(wrong)
        wrong = copy.deepcopy(thresholds)
        wrong["range_validation"]["bounded_metrics"]["pck"] = [0.0, 2.0]
        with self.assertRaisesRegex(RuntimeError, "range"):
            _validate_thresholds(wrong)

    def test_provider_decision_is_after_estimator_and_is_fail_closed(self):
        provider = load("docs/evidence/v054-provider-qualification.json")
        self.assertEqual("POSE_QA_ESTIMATOR_QUALIFIED", provider["estimator_status"])
        self.assertEqual("LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED", provider["status"])
        self.assertEqual({"A", "C", "R"}, set(provider["lanes"]))
        self.assertEqual(9, provider["record_count"])
        self.assertIsNone(provider["decision"]["qualified_lane"])
        self.assertFalse(provider["walk_authorized"])
        self.assertFalse(provider["new_provider_used"])
        self.assertFalse(provider["new_strength_used"])

    def test_all_lane_outputs_are_fresh_and_identity_is_separate(self):
        execution = load("docs/evidence/execution-evidence-v0.5.4.json")
        provider = load("docs/evidence/v054-provider-qualification.json")
        self.assertEqual(9, execution["record_count"])
        self.assertTrue(execution["all_fresh_binding"])
        self.assertTrue(execution["no_previous_frame_chaining"])
        self.assertTrue(execution["no_walk_executed"])
        self.assertTrue(all(item["fresh_binding"] for item in provider["records"]))
        self.assertTrue(all(item["identity_pass"] and item["weapon_present"] for item in provider["records"]))
        self.assertEqual({54701, 54702, 54703}, {item["seed"] for item in provider["records"]})

    def test_state_schema_and_active_documents_match(self):
        state = load("docs/evidence/current-state.json")
        schema = load("schemas/current-state.json")
        validate_schema_document(schema)
        validate_instance(state, schema)
        result = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.6.2.md").read_text(encoding="utf-8"))
        self.assertEqual("STATE_CONSISTENCY_PASSED", result["status"], result)
        self.assertEqual("0.6.2", state["version"])
        self.assertEqual(state["current_gate"], state["state_consistency"]["status"])
        self.assertEqual("LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED", state["pose_lane_status"])
        self.assertGreaterEqual(state["state_consistency"]["new_generation_jobs"], 0)

    def test_nine_individual_pngs_and_contacts_are_present(self):
        table = load("docs/evidence/v054-pose-error-table.json")
        self.assertEqual(9, len(table["rows"]))
        self.assertTrue((ROOT / "docs/evidence/v054-pose-overlays-contact-sheet.png").is_file())
        self.assertTrue((ROOT / "docs/evidence/v054-lanes-contact-sheet.png").is_file())
        for row in table["rows"]:
            self.assertTrue((ROOT / row["output_path"]).is_file(), row)


if __name__ == "__main__":
    unittest.main()
