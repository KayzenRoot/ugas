"""Validate the active machine state for the v0.23.0 VFX slice."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from ugas.state_consistency_v0230 import validate_state_consistency


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    matrix = json.loads((ROOT / "docs/ugas-v1-capability-matrix.json").read_text(encoding="utf-8"))
    result = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"), matrix)
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["status"] == "VFX_ASSET_FAMILY_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED" and not result["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
