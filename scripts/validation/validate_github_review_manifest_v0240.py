"""Validate the bounded v0.24.0 exact-head review manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("manifest"); parser.add_argument("--result-output", required=True); args = parser.parse_args()
    value = json.loads(Path(args.manifest).read_text(encoding="utf-8")); failures: list[str] = []
    if value.get("schema_version") != "0.24.0" or value.get("manifest_type") != "github-ci-orchestration-runtime-v0240-review": failures.append("identity")
    scope = value.get("scope", {}); expected = {"version": "0.24.0", "phase": "ORCHESTRATION_RUNTIME_HARDENING", "current_gate": "ORCHESTRATION_RUNTIME_HARDENING_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED", "baseline_main_sha": "dee98f8cd89ebd83a36ead7a22a184700d6e916f", "allowed_next_actions": ["external_review_orchestration_runtime_v0240"], "next_candidate": "V1_FINAL_ACCEPTANCE", "new_generation": 0, "test_only": True}
    failures.extend(f"scope:{key}" for key, expected_value in expected.items() if scope.get(key) != expected_value)
    pr = value.get("pull_request", {}); failures.extend(f"pr:{key}" for key in ("base_sha", "head_sha", "head_branch") if not pr.get(key))
    gates = value.get("gates", {}); controls = value.get("negative_controls", {})
    if len(gates) < 30 or any(item.get("status") != "PASS" or type(item.get("observed")) is not bool or item.get("observed") is not True for item in gates.values()): failures.append("gates")
    if controls.get("status") != "PASS" or len(controls.get("controls", {})) < 30 or any(item.get("status") != "PASS" or item.get("result") != "REJECT" or item.get("expected_rejection_class") != item.get("observed_rejection_class") for item in controls.get("controls", {}).values()): failures.append("negative-controls")
    production = value.get("production_boundary", {}); boundary = production.get("routing") == "BLOCKED" and production.get("approved") is False and production.get("new_generation") == 0 and production.get("provider_submit_calls") == 0
    if not boundary: failures.append("production-boundary")
    if value.get("overall_status") != "PASS": failures.append("overall-status")
    result = {"schema_version": "0.24.0", "status": "PASS" if not failures else "FAIL", "failures": failures, "manifest": str(args.manifest)}
    Path(args.result_output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); print(json.dumps(result, ensure_ascii=False)); return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
