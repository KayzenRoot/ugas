"""Validate active v0.12.3 navigation and write machine-readable evidence."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document
from ugas.state_consistency_v0123 import BASELINE_HEAD, FEATURE_BRANCH, CURRENT_GATE, NEXT_ACTION, validate_state_consistency


def main() -> int:
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/current-state.json").read_text(encoding="utf-8"))
    validate_schema_document(schema)
    validate_instance(state, schema)
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", BASELINE_HEAD, "HEAD"], cwd=ROOT, capture_output=True, check=False).returncode == 0
    checkpoint = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")
    review = (ROOT / "REVIEW-v0.12.3.md").read_text(encoding="utf-8")
    consistency = validate_state_consistency(state, checkpoint, review, roadmap)
    active_checkpoint = checkpoint.split("## Historical", 1)[0]
    active_roadmap = roadmap.split("## Historical v0.12.2", 1)[0]
    failures = list(consistency.get("failures", []))
    if branch != FEATURE_BRANCH:
        failures.append("feature_branch_not_checked_out")
    if not ancestor:
        failures.append("baseline_is_not_ancestor")
    if "external_review_github_native_v0123_and_dashboard_v0122" not in active_checkpoint or "external_review_github_native_v0123_and_dashboard_v0122" not in active_roadmap:
        failures.append("active_navigation_next_gate_invalid")
    if "external_review_observability_dashboard_v0121" in active_checkpoint or "external_review_observability_dashboard_v0121" in active_roadmap:
        failures.append("stale_v0121_active_navigation")
    result = {"status": "GOVERNANCE_CONSISTENT_V0123" if not failures else "GOVERNANCE_CONSISTENCY_FAILED", "failures": failures, "branch": branch, "head": head, "baseline_head": BASELINE_HEAD, "baseline_is_ancestor": ancestor, "current_gate": CURRENT_GATE, "allowed_next_action": NEXT_ACTION, "active_checkpoint_gate": CURRENT_GATE in active_checkpoint, "active_roadmap_gate": CURRENT_GATE in active_roadmap, "historical_v0122_section_preserved": "v0.12.2" in checkpoint and "v0.12.2" in roadmap}
    output = ROOT / "docs/evidence/github-review-v0123/governance-consistency-v0123.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
