"""Validate active v0.24.0 state and orchestration evidence."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document
from ugas.state_consistency_v0240 import CURRENT_GATE, validate_state_consistency


def main() -> int:
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    state_schema = json.loads((ROOT / "schemas/current-state-v0240.json").read_text(encoding="utf-8"))
    runtime_schema = json.loads((ROOT / "schemas/orchestration-runtime-v0240.json").read_text(encoding="utf-8"))
    execution = json.loads((ROOT / "docs/evidence/orchestration-runtime-v0240/execution-evidence-v0240.json").read_text(encoding="utf-8"))
    binding = json.loads((ROOT / "docs/evidence/orchestration-runtime-v0240/v0234-post-merge-closure-binding-v0240.json").read_text(encoding="utf-8"))
    matrix = json.loads((ROOT / "docs/ugas-v1-capability-matrix.json").read_text(encoding="utf-8"))
    validate_schema_document(state_schema); validate_instance(state, state_schema)
    validate_schema_document(runtime_schema); validate_instance(execution, runtime_schema)
    result = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"), matrix, binding)
    result["evidence_overall_pass"] = execution.get("overall_pass") is True
    result["closure_binding_status"] = binding.get("evidence_status")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == CURRENT_GATE and not result["failures"] and result["evidence_overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
