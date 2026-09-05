from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from ugas.direction_runtime import (
    CANONICAL_DIRECTIONS,
    DirectionResolver,
    normalize_direction_result,
    validate_coverage_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/multi-direction-runtime-v0161"
MANIFEST = EVIDENCE / "coverage-manifest-v0161.json"


class DirectionRuntimeV0161Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.resolver = DirectionResolver.from_manifest(MANIFEST)

    def test_v0161_manifest_preserves_canonical_eight_and_south_only_coverage(self) -> None:
        self.assertEqual(self.manifest["schema_version"], "0.16.1")
        self.assertEqual(tuple(self.manifest["canonical_directions"]), CANONICAL_DIRECTIONS)
        self.assertEqual(validate_coverage_manifest(MANIFEST, ROOT)["status"], "DIRECTION_COVERAGE_MANIFEST_PASSED")
        self.assertEqual({item["direction"] for item in self.manifest["assets"]}, {"south"})

    def test_only_finite_numeric_zero_may_use_retained_facing(self) -> None:
        retained = normalize_direction_result((0, 0), retained_facing="west")
        self.assertEqual(retained.direction, "west")
        self.assertEqual(retained.outcome, "ZERO_VECTOR_RETAINED_FACING")
        invalid_values = [
            (math.nan, 0),
            (math.inf, 0),
            (-math.inf, 0),
            ("1", 0),
            {"dx": 1},
            (1, 0, 2),
        ]
        for value in invalid_values:
            with self.subTest(value=repr(value)):
                result = normalize_direction_result(value, retained_facing="west")
                self.assertIsNone(result.direction)
                self.assertEqual(result.outcome, "INVALID_VECTOR_UNRESOLVED")
                self.assertEqual(result.error_code, "INVALID_VECTOR_UNRESOLVED")

    def test_invalid_vector_resolver_is_fail_closed_even_with_retained_facing(self) -> None:
        result = self.resolver.resolve("death_animation_front", {"dx": math.nan, "dy": 0}, retained_facing="south")
        self.assertIsNone(result.asset_id)
        self.assertEqual(result.fallback_mode, "INVALID_VECTOR_UNRESOLVED")
        self.assertEqual(result.error_code, "INVALID_VECTOR_UNRESOLVED")
        self.assertFalse(result.production_safe)

    def test_test_only_exact_resolution_is_not_production_safe(self) -> None:
        asset = dict(self.manifest["assets"][0], test_only=True, asset_id="test-only-south")
        resolver = DirectionResolver([asset], production_registry=False)
        result = resolver.resolve(asset["capability_id"], "south")
        self.assertEqual(result.asset_id, "test-only-south")
        self.assertFalse(result.production_safe)

    def test_real_negative_controls_have_observed_rejections(self) -> None:
        evidence = json.loads((EVIDENCE / "negative-controls-v0161.json").read_text(encoding="utf-8"))
        controls = evidence["controls"]
        self.assertEqual(evidence["status"], "DIR_NC_01_TO_12_PASSED")
        self.assertEqual(set(controls), {f"DIR-NC-{index:02d}" for index in range(1, 13)})
        for control, record in controls.items():
            with self.subTest(control=control):
                self.assertTrue(record["rejected"])
                self.assertTrue(record["mutation"])
                self.assertTrue(record["target_gate"])
                self.assertIn("observed", record)
                self.assertIn("error_code", record["observed"])
        self.assertNotIn("positive_gate_boolean", json.dumps(evidence))

    def test_v0161_state_evidence_is_frozen_and_active_state_advanced(self) -> None:
        state = json.loads((ROOT / "docs/evidence/current-state-v0.16.2.json").read_text(encoding="utf-8"))
        frozen = json.loads((EVIDENCE / "state-consistency-v0161.json").read_text(encoding="utf-8"))
        self.assertEqual(frozen["status"], "MULTI_DIRECTION_ANIMATION_RUNTIME_INTEGRITY_TECHNICALLY_QUALIFIED")
        self.assertEqual(state["version"], "0.16.2")
        self.assertEqual(state["review"]["pr_number"], 6)
        self.assertEqual(state["review"]["pr_state"], "OPEN")
        self.assertTrue(state["review"]["real_pr_checks_green"])
        self.assertEqual(state["review"]["feature_branch"], "codex/v0.16.0-multi-direction-runtime-foundation")
        self.assertFalse(state["production_approved"])
        self.assertEqual(state["production_routing"], "BLOCKED")
        self.assertEqual(state["new_generation"], 0)


if __name__ == "__main__":
    unittest.main()
