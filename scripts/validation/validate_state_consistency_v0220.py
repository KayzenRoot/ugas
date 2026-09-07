"""Validate the active v0.22.0 state, closure binding and live-review boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402
from ugas.state_consistency_v0220 import validate_state_consistency  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path); args = parser.parse_args()
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/current-state-v0220.json").read_text(encoding="utf-8"))
    binding = json.loads((ROOT / "docs/evidence/github-governance-v0220/v0213-closure-completion-binding.json").read_text(encoding="utf-8"))
    validate_schema_document(schema); validate_instance(state, schema)
    result = validate_state_consistency(state, binding, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "docs/project-review-response-protocol.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"))
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["status"] == "UI_ASSET_FAMILY_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED" and not result["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
