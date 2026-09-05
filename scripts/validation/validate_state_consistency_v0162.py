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
    approval_path = ROOT / "docs/evidence/github-governance-v0162/v0162-external-approval.json"
    try:
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        contexts = approval.get("required_contexts", [])
        if (
            approval.get("reviewed_runtime_head") != "2864b8ca392725b6da0616916ef3a3c38ce0a0d6"
            or approval.get("decision") != "APPROVED_FOUNDATION / APPROVED_TO_MERGE"
            or approval.get("pull_request") != 6
            or len(contexts) != 3
            or any(item.get("status") != "completed" or item.get("conclusion") != "success" for item in contexts)
            or approval.get("artifact", {}).get("digest") != "sha256:45c720f0bed80722ade97bdc5137d1e78b4fa64b8a8c9ae692f1c3c86b3d6d08"
        ):
            result["failures"].append("external_approval_record_binding_invalid")
    except (OSError, json.JSONDecodeError, TypeError, AttributeError) as exc:
        result["failures"].append(f"external_approval_record_unreadable:{type(exc).__name__}:{exc}")
    if result["failures"]:
        result["status"] = "STATE_CONSISTENCY_FAILED"
    evidence = {"schema_version": "0.16.2", "validator": "src/ugas/state_consistency_v0162.py", **result}
    destination = ROOT / "docs/evidence/multi-direction-runtime-v0162/state-consistency-v0162.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, ensure_ascii=False))
    return 0 if result["status"] == CURRENT_GATE else 2


if __name__ == "__main__":
    raise SystemExit(main())
