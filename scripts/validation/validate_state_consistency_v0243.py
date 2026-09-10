"""Validate the active v0.24.3 state and its forward-only correction binding."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.state_consistency_v0243 import validate_state_consistency


def main() -> int:
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    checkpoint = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")
    matrix = json.loads((ROOT / "docs/ugas-v1-capability-matrix.json").read_text(encoding="utf-8"))
    binding_path = ROOT / "docs/evidence/orchestration-runtime-v0243/correction-history-v0243.json"
    binding = json.loads(binding_path.read_text(encoding="utf-8")) if binding_path.is_file() else None
    evidence = _evidence = state.get("evidence", {})
    result = validate_state_consistency(state, checkpoint, roadmap, matrix, binding, evidence)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] != "ORCHESTRATION_STATE_FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
