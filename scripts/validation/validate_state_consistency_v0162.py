"""Validate and persist the active v0.16.2 direction cache/state correction."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402
from ugas.state_consistency_v0162 import CURRENT_GATE, validate_state_consistency  # noqa: E402


def main() -> int:
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/current-state-v0162.json").read_text(encoding="utf-8"))
    validate_schema_document(schema)
    validate_instance(state, schema)
    result = validate_state_consistency(
        state,
        (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"),
        (ROOT / "REVIEW-v0.16.2.md").read_text(encoding="utf-8"),
        (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"),
    )
    evidence = {"schema_version": "0.16.2", "validator": "src/ugas/state_consistency_v0162.py", **result}
    destination = ROOT / "docs/evidence/multi-direction-runtime-v0162/state-consistency-v0162.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, ensure_ascii=False))
    return 0 if result["status"] == CURRENT_GATE else 2


if __name__ == "__main__":
    raise SystemExit(main())
