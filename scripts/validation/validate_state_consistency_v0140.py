"""Validate frozen v0.14.0 HIT_REACTION_FRONT state without rewriting live v0.14.1 evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document
from ugas.state_consistency_v0140 import validate_state_consistency


def main() -> int:
    state = json.loads((ROOT / "docs/evidence/current-state-v0.14.0.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/current-state-v0.14.0.json").read_text(encoding="utf-8"))
    validate_schema_document(schema)
    validate_instance(state, schema)
    review = (ROOT / "REVIEW-v0.14.0.md").read_text(encoding="utf-8")
    result = validate_state_consistency(state, review, review, review)
    print(json.dumps({"schema_version": "0.14.0", "validator": "src/ugas/state_consistency_v0140.py", "frozen": True, **result}, indent=2, ensure_ascii=False))
    return 0 if result["failures"] == [] else 2


if __name__ == "__main__":
    raise SystemExit(main())
