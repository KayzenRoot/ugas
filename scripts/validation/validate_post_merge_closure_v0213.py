"""Validate the v0.21.3 post-merge governance closure state."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402
from ugas.state_consistency_post_merge_v0213 import validate_post_merge_state  # noqa: E402


def main() -> int:
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/current-state-v0213-merged.json").read_text(encoding="utf-8"))
    binding = json.loads((ROOT / "docs/evidence/github-governance-v0220/v0213-post-merge-binding.json").read_text(encoding="utf-8"))
    validate_schema_document(schema)
    validate_instance(state, schema)
    result = validate_post_merge_state(
        state,
        binding,
        (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"),
        (ROOT / "docs/chat-continuity-protocol.md").read_text(encoding="utf-8"),
        (ROOT / "docs/project-review-response-protocol.md").read_text(encoding="utf-8"),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "MAPS_MINIMAP_APPROVED_FOUNDATION_MERGED" and not result["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
