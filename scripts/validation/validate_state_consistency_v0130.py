"""Validate the frozen historical v0.13.0 RUN_FRONT_V1 snapshot. Does not rewrite live state."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document
from ugas.state_consistency_v0130 import validate_state_consistency


def main() -> int:
    state = json.loads((ROOT / "docs/evidence/current-state-v0.13.0.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/current-state-v0.13.0.json").read_text(encoding="utf-8"))
    validate_schema_document(schema)
    validate_instance(state, schema)
    review = (ROOT / "REVIEW-v0.13.0.md").read_text(encoding="utf-8")
    result = validate_state_consistency(state, review, review, review)
    evidence = {"schema_version": "0.13.0", "validator": "src/ugas/state_consistency_v0130.py", **result}
    destination = ROOT / "docs/evidence/animation-runtime-v0130/state-consistency-v0130.json"
    if destination.is_file() and result["status"] != "CUTOUT_ANIMATION_RUNTIME_V1_RUN_FRONT_TECHNICALLY_QUALIFIED":
        print(json.dumps(evidence, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(evidence, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "CUTOUT_ANIMATION_RUNTIME_V1_RUN_FRONT_TECHNICALLY_QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
