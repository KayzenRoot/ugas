"""Validate the active v0.25.2 canonical state and split post-merge evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402
from ugas.state_consistency_v0252 import (  # noqa: E402
    PROMOTION_BINDING,
    validate_post_merge_binding,
    validate_state_consistency,
)


def main() -> int:
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/current-state-v0252.json").read_text(encoding="utf-8"))
    binding = json.loads((ROOT / PROMOTION_BINDING).read_text(encoding="utf-8"))
    validate_schema_document(schema)
    validate_instance(state, schema)
    result = validate_state_consistency(
        state,
        (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"),
        (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"),
        json.loads((ROOT / "docs/ugas-v1-capability-matrix.json").read_text(encoding="utf-8")),
        binding,
    )
    result["schema"] = {"status": "PASS", "version": state.get("version")}
    result["binding"] = {"status": "PASS" if not validate_post_merge_binding(binding) else "FAIL"}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] != "V1_CANONICAL_STATE_PROMOTION_FAILED" and result["binding"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
