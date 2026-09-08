"""Validate the active v0.23.2 state and live-only PR boundary."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.state_consistency_v0232 import CURRENT_GATE, validate_state_consistency


def main() -> int:
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    matrix = json.loads((ROOT / "docs/ugas-v1-capability-matrix.json").read_text(encoding="utf-8"))
    result = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"), matrix)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == CURRENT_GATE and not result["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
