"""Contract tests for the v0.10.0 generic action runtime."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))

from ugas.animation import AnimationContractError, evaluate_lifecycle, event_markers_sha256, load_spec
from ugas.schema_validation import SchemaValidationError


class AnimationRuntimeV0100Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = ROOT / "profiles/animation/attack-front-v1.json"
        self.spec = json.loads(self.path.read_text(encoding="utf-8"))

    def _load_mutant(self, value: dict) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "mutant.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises((AnimationContractError, SchemaValidationError)):
                load_spec(path, ROOT)

    def test_attack_spec_is_frozen_front_non_loop_and_marker_bound(self) -> None:
        loaded = load_spec(self.path, ROOT)
        self.assertEqual(("attack-front-v1", "front", 10, 12.0, False), (loaded["animation_id"], loaded["direction"], loaded["frame_count"], loaded["fps"], loaded["loop"]))
        self.assertEqual([("windup_peak", 2), ("active_start", 3), ("hit_event", 5), ("active_end", 6), ("recovery_complete", 9)], [(item["event_id"], item["frame"]) for item in loaded["event_markers"]])
        self.assertEqual(64, len(event_markers_sha256(loaded)))

    def test_duplicate_out_of_range_and_noncanonical_markers_fail_closed(self) -> None:
        duplicate = copy.deepcopy(self.spec); duplicate["event_markers"] = [{"event_id": "x", "frame": 1, "kind": "phase"}, {"event_id": "x", "frame": 2, "kind": "phase"}]
        self._load_mutant(duplicate)
        out_of_range = copy.deepcopy(self.spec); out_of_range["event_markers"] = [{"event_id": "x", "frame": 10, "kind": "phase"}]
        self._load_mutant(out_of_range)
        noncanonical = copy.deepcopy(self.spec); noncanonical["event_markers"] = [{"event_id": "later", "frame": 5, "kind": "phase"}, {"event_id": "earlier", "frame": 2, "kind": "phase"}]
        self._load_mutant(noncanonical)

    def test_loop_closes_and_non_loop_does_not_close(self) -> None:
        frames = [{"index": index, "passed": True} for index in range(3)]
        loop = evaluate_lifecycle({"frame_count": 3, "loop": True, "event_markers": []}, frames)
        non_loop = evaluate_lifecycle({"frame_count": 3, "loop": False, "event_markers": []}, frames)
        self.assertEqual("ANIMATION_LIFECYCLE_PASSED", loop["status"])
        self.assertTrue(loop["closing_transition_evaluated"])
        self.assertEqual([2, 0], [loop["closing_transition"]["from_frame"], loop["closing_transition"]["to_frame"]])
        self.assertEqual("ANIMATION_LIFECYCLE_PASSED", non_loop["status"])
        self.assertFalse(non_loop["closing_transition_evaluated"])
        self.assertNotIn({"from_frame": 2, "to_frame": 0, "closing": True}, non_loop["transitions"])

    def test_non_loop_requires_final_frame_valid(self) -> None:
        frames = [{"index": 0, "passed": True}, {"index": 1, "passed": True}, {"index": 2, "passed": False}]
        result = evaluate_lifecycle({"frame_count": 3, "loop": False, "event_markers": [{"event_id": "done", "frame": 2, "kind": "phase"}]}, frames)
        self.assertEqual("ANIMATION_LIFECYCLE_GAP", result["status"])
        self.assertFalse(result["hard_gates"]["final_frame_valid"])


if __name__ == "__main__":
    unittest.main()
