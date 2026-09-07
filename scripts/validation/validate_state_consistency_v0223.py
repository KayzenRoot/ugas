"""Validate the machine-authoritative v0.22.3 active state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from ugas.state_consistency_v0223 import validate_state_consistency


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path); args = parser.parse_args()
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8")); binding = json.loads((ROOT / "docs/evidence/github-governance-v0223/v0223-ui-closure-binding.json").read_text(encoding="utf-8"))
    result = validate_state_consistency(state, binding, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.22.3.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")); payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(payload, encoding="utf-8")
    print(payload, end=""); return 0 if result["status"] == "UI_ASSET_FAMILY_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED" and not result["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
