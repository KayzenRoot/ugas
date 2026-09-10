"""Validate the bounded v0.24.4 exact-head review manifest fail-closed."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from ugas.state_consistency_v0244 import CURRENT_GATE, NEXT_ACTION, REJECTED_REVIEWED_HEAD, VERSION as STATE_VERSION

VERSION = STATE_VERSION
BASE_MAIN = "dee98f8cd89ebd83a36ead7a22a184700d6e916f"
REJECTED_HEAD = REJECTED_REVIEWED_HEAD
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def strict_true(value: Any) -> bool:
    return type(value) is bool and value is True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--result-output", required=True)
    args = parser.parse_args()
    value = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    failures: list[str] = []
    if value.get("schema_version") != VERSION or value.get("manifest_type") != "github-ci-orchestration-runtime-v0244-review":
        failures.append("identity")
    scope = value.get("scope", {})
    expected_scope = {
        "version": VERSION,
        "phase": "ORCHESTRATION_RUNTIME_HARDENING",
        "current_gate": CURRENT_GATE,
        "baseline_main_sha": BASE_MAIN,
        "rejected_reviewed_head": REJECTED_HEAD,
        "allowed_next_actions": [NEXT_ACTION],
        "next_candidate": "V1_FINAL_ACCEPTANCE",
        "new_generation": 0,
        "test_only": True,
        "provider_neutral": True,
    }
    failures.extend(f"scope:{key}" for key, expected in expected_scope.items() if scope.get(key) != expected)
    pr = value.get("pull_request", {})
    if pr.get("number") != 15 or pr.get("base_sha") != BASE_MAIN or not GIT_SHA_RE.fullmatch(str(pr.get("head_sha", ""))) or not pr.get("head_branch"):
        failures.append("pull-request")
    gates = value.get("gates", {})
    if not isinstance(gates, dict) or len(gates) < 40 or any(not isinstance(item, dict) or item.get("status") != "PASS" or not strict_true(item.get("observed")) or item.get("observed_type") != "bool" for item in gates.values()):
        failures.append("gates")
    controls = value.get("negative_controls", {})
    controls_map = controls.get("controls", {}) if isinstance(controls, dict) else {}
    if controls.get("status") != "PASS" or len(controls_map) < 8:
        failures.append("negative-controls")
    for item in controls_map.values():
        if not isinstance(item, dict) or item.get("status") != "PASS":
            failures.append("negative-controls-result")
            continue
        if item.get("expected_rejection_class") is None:
            continue
        if item.get("result") != "REJECT":
            failures.append("negative-controls-result")
        elif item.get("control_id") == "NC-GATE-01":
            if item.get("observed_type") != "str" or item.get("observed_value") != "true" or item.get("observed_gate_status") != "FAIL":
                failures.append("strict-gate-negative-control")
        elif item.get("observed_rejection_class") != item.get("expected_rejection_class") or not item.get("actual_exception"):
            failures.append("negative-controls-class")
    determinism = value.get("determinism", {})
    if determinism.get("status") != "PASS" or determinism.get("run_1") != determinism.get("run_2"):
        failures.append("determinism")
    state_validation = value.get("state_validation", {})
    if state_validation.get("status") != CURRENT_GATE:
        failures.append("state-validation")
    production = value.get("production_boundary", {})
    if production.get("routing") != "BLOCKED" or production.get("approved") is not False or production.get("new_generation") != 0 or production.get("provider_submit_calls") != 0:
        failures.append("production-boundary")
    provider = value.get("provider_boundary", {})
    if provider.get("boundary", {}).get("status") != "PASS" or provider.get("snapshot", {}).get("provider_submit_calls") != 0:
        failures.append("provider-boundary")
    family = value.get("family_concurrency", {})
    if family.get("peak_global") != 3 or not family.get("batches"):
        failures.append("family-concurrency")
    if value.get("correction_history", {}).get("historical_evidence_unchanged") is not True:
        failures.append("historical-evidence")
    if value.get("overall_status") != "PASS":
        failures.append("overall-status")
    result = {"schema_version": VERSION, "status": "PASS" if not failures else "FAIL", "failures": failures, "manifest": str(args.manifest)}
    Path(args.result_output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
