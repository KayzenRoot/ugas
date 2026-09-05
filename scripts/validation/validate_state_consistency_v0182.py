"""Validate the active v0.18.2 state and document bindings."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402
from ugas.state_consistency_v0182 import validate_state_consistency  # noqa: E402


def main() -> int:
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8")); schema = json.loads((ROOT / "schemas/current-state-v0182.json").read_text(encoding="utf-8")); validate_schema_document(schema); validate_instance(state, schema)
    result = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.18.2.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")); print(json.dumps(result, indent=2, ensure_ascii=False)); return 0 if result["status"] == state["current_gate"] and not result["failures"] else 1


if __name__ == "__main__": raise SystemExit(main())
