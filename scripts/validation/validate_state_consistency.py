"""Run the active v0.10.0 fatal state-consistency gate and persist its evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.state_consistency_v0100 import validate_state_consistency
from ugas.schema_validation import validate_instance, validate_schema_document


def main() -> int:
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/current-state.json").read_text(encoding="utf-8"))
    validate_schema_document(schema)
    validate_instance(state, schema)
    result = validate_state_consistency(
        state,
        (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"),
        (ROOT / "REVIEW-v0.10.0.md").read_text(encoding="utf-8"),
    )
    evidence = {"schema_version": "0.10.0", "validator": "src/ugas/state_consistency_v0100.py", **result}
    (ROOT / "docs/evidence/state-consistency.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "STATE_CONSISTENCY_PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
