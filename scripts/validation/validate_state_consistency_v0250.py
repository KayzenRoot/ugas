"""Validate the active v0.25.0 V1 final acceptance state and its closure binding."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.acceptance_v0250 import observability_binding
from ugas.state_consistency_v0250 import validate_state_consistency


def main() -> int:
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    checkpoint = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")
    matrix = json.loads((ROOT / "docs/ugas-v1-capability-matrix.json").read_text(encoding="utf-8"))
    audit_path = ROOT / "docs/evidence/v1-final-acceptance/capability-matrix-audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.is_file() else None
    audit_input = None
    if isinstance(audit, dict):
        audit_input = {
            "capability_count": audit.get("capability_count"),
            "production_routing": state.get("production_routing"),
            "new_generation": state.get("new_generation"),
            "status": audit.get("status"),
            "observability": {"visual_review_status": observability_binding(ROOT).get("visual_review_status")},
        }
    result = validate_state_consistency(state, checkpoint, roadmap, matrix, audit_input)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] != "V1_FINAL_ACCEPTANCE_STATE_FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
