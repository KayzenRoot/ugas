from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from ugas.direction_runtime import CANONICAL_DIRECTIONS, DirectionResolver, normalize_direction_result


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/multi-direction-runtime-v0162"
MANIFEST = EVIDENCE / "coverage-manifest-v0162.json"


class DirectionRuntimeV0162Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def _resolver(self) -> DirectionResolver:
        return DirectionResolver.from_manifest(MANIFEST)

    def test_forward_manifest_is_v0162_and_south_only(self) -> None:
        self.assertEqual(self.manifest["schema_version"], "0.16.2")
        self.assertEqual(tuple(self.manifest["canonical_directions"]), CANONICAL_DIRECTIONS)
        self.assertEqual({item["direction"] for item in self.manifest["assets"]}, {"south"})
        self.assertEqual(self.manifest["carried_forward_from"]["path"], "docs/evidence/multi-direction-runtime-v0161/coverage-manifest-v0161.json")

    def test_unknown_then_invalid_does_not_share_unresolved_cache_entry(self) -> None:
        resolver = self._resolver()
        unknown = resolver.resolve("death_animation_front", "sideways")
        invalid = resolver.resolve("death_animation_front", {"dx": math.nan, "dy": 0}, retained_facing="south")
        self.assertEqual(unknown.error_code, "DIRECTION_UNRESOLVED")
        self.assertEqual(invalid.error_code, "INVALID_VECTOR_UNRESOLVED")
        self.assertNotEqual(unknown.cache_key, invalid.cache_key)
        self.assertIn("UNKNOWN_DIRECTION_UNRESOLVED", unknown.cache_key)
        self.assertIn("INVALID_VECTOR_UNRESOLVED", invalid.cache_key)

    def test_invalid_then_unknown_does_not_share_unresolved_cache_entry(self) -> None:
        resolver = self._resolver()
        invalid = resolver.resolve("death_animation_front", {"dx": math.nan, "dy": 0})
        unknown = resolver.resolve("death_animation_front", "sideways")
        self.assertEqual(invalid.error_code, "INVALID_VECTOR_UNRESOLVED")
        self.assertEqual(unknown.error_code, "DIRECTION_UNRESOLVED")
        self.assertNotEqual(invalid.cache_key, unknown.cache_key)

    def test_zero_and_invalid_order_controls_are_isolated(self) -> None:
        resolver = self._resolver()
        zero = resolver.resolve("death_animation_front", (0, 0))
        invalid = resolver.resolve("death_animation_front", (math.nan, 0))
        self.assertEqual(zero.error_code, "DIRECTION_UNRESOLVED")
        self.assertEqual(invalid.error_code, "INVALID_VECTOR_UNRESOLVED")
        self.assertIn("ZERO_VECTOR_UNRESOLVED", zero.cache_key)
        self.assertIn("INVALID_VECTOR_UNRESOLVED", invalid.cache_key)

    def test_same_unresolved_class_reuses_identical_cached_result(self) -> None:
        resolver = self._resolver()
        first = resolver.resolve("death_animation_front", {"dx": math.nan, "dy": 0})
        second = resolver.resolve("death_animation_front", {"dx": math.nan, "dy": 0})
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(resolver.cache_stats(), {"hits": 1, "misses": 1, "entries": 1})

    def test_test_only_cache_mode_is_truthful(self) -> None:
        asset = dict(self.manifest["assets"][0], test_only=True, asset_id="test-only-south")
        resolver = DirectionResolver([asset], production_registry=False)
        result = resolver.resolve(asset["capability_id"], "south")
        self.assertFalse(result.production_safe)
        self.assertIn("request_mode=direct", result.cache_key)
        self.assertIn("registry_mode=test", result.cache_key)
        self.assertNotIn("registry_mode=production", result.cache_key)

    def test_production_cache_mode_is_distinct_from_test_mode(self) -> None:
        test_asset = dict(self.manifest["assets"][0], test_only=True, asset_id="test-only-south")
        test_result = DirectionResolver([test_asset], production_registry=False).resolve(test_asset["capability_id"], "south")
        production_result = self._resolver().resolve("death_animation_front", "south")
        self.assertIn("registry_mode=test", test_result.cache_key)
        self.assertIn("registry_mode=production", production_result.cache_key)
        self.assertNotEqual(test_result.cache_key, production_result.cache_key)

    def test_invalid_vectors_stay_invalid_with_retained_facing(self) -> None:
        for value in ((math.nan, 0), (math.inf, 0), ("1", 0), {"dx": 1}, (1, 0, 2)):
            with self.subTest(value=repr(value)):
                result = normalize_direction_result(value, retained_facing="west")
                self.assertEqual(result.outcome, "INVALID_VECTOR_UNRESOLVED")
                self.assertIsNone(result.direction)

    def test_state_and_qa_evidence_bind_v0162(self) -> None:
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        cache_qa = json.loads((EVIDENCE / "cache-unresolved-class-qa-v0162.json").read_text(encoding="utf-8"))
        mode_qa = json.loads((EVIDENCE / "test-only-cache-mode-qa-v0162.json").read_text(encoding="utf-8"))
        self.assertEqual(state["version"], "0.16.2")
        self.assertEqual(state["previous_release"]["version"], "0.15.1")
        self.assertEqual(state["review"]["pr_number"], 6)
        self.assertEqual(state["review"]["pr_state"], "OPEN")
        self.assertTrue(state["review"]["real_pr_checks_green"])
        self.assertEqual(state["review"]["merge_authorization"], "APPROVED_TO_MERGE")
        self.assertEqual(state["multi_direction_animation_runtime"], "APPROVED_FOUNDATION")
        self.assertEqual(cache_qa["status"], "CACHE_UNRESOLVED_CLASS_QA_PASSED")
        self.assertEqual(mode_qa["status"], "TEST_ONLY_CACHE_MODE_QA_PASSED")


if __name__ == "__main__":
    unittest.main()
