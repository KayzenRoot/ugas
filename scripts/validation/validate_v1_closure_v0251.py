"""Validate the active v0.25.1 schema, merged closure evidence and frozen immutability proof."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document
from ugas.state_consistency_v0251 import (
    CLOSURE_EVIDENCE_FILES,
    CLOSURE_EVIDENCE_ROOT,
    HARD_GATE_COUNT,
    VERSION,
    closure_binding_failures,
    definition_of_done_hard_gate_count,
    immutability_failures,
    negative_control_failures,
)

STATE_PATH = ROOT / "docs/evidence/current-state.json"
SCHEMA_PATH = ROOT / "schemas/current-state-v0251.json"
DEFINITION_OF_DONE_PATH = ROOT / "docs/definition-of-done.md"
HARD_GATES_PATH = ROOT / "docs/evidence/v1-final-acceptance/hard-gates.json"
EVIDENCE_ROOT = ROOT / CLOSURE_EVIDENCE_ROOT
CLOSURE_BINDING = "closure-binding-v0251.json"
IMMUTABILITY_PROOF = "immutability-proof-v0251.json"
NEGATIVE_CONTROLS = "negative-controls-v0251.json"
UADS_HANDOFF = "uads-handoff-v0251.json"
HISTORICAL_V0251_HEAD = "5f4a56bf019cc10994ee2974430c3ffca3090a50"
HISTORICAL_V0251_STATE_SNAPSHOT = ROOT / "docs/evidence/post-merge-canonical-promotion-v0252/historical-v0251-current-state.json"
HISTORICAL_V0251_STATE_SNAPSHOT_SHA256 = "ddb7825b01fddcc92e938ffa7a709746ced22ceb38dc2fbc862e820cf95b3010"


def _load(relative: str) -> Any:
    return json.loads(Path(relative).read_text(encoding="utf-8"))


def _active_v0251_state() -> dict[str, Any]:
    current = _load(str(STATE_PATH))
    if current.get("version") == VERSION:
        return current
    result = subprocess.run(["git", "-C", str(ROOT), "show", f"{HISTORICAL_V0251_HEAD}:docs/evidence/current-state.json"], capture_output=True, check=False)
    if result.returncode == 0:
        return json.loads(result.stdout)
    try:
        snapshot = HISTORICAL_V0251_STATE_SNAPSHOT.read_bytes()
    except OSError as exc:
        raise OSError("historical v0.25.1 active state unavailable") from exc
    normalized = snapshot.replace(b"\r\n", b"\n")
    if hashlib.sha256(normalized).hexdigest() != HISTORICAL_V0251_STATE_SNAPSHOT_SHA256:
        raise OSError("historical v0.25.1 active state snapshot is not authoritative")
    return json.loads(snapshot)


def _closure_cross_binding(state: dict[str, Any], binding: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    closure = state.get("v1_closure") if isinstance(state.get("v1_closure"), dict) else {}
    record = binding.get("binding") if isinstance(binding.get("binding"), dict) else {}
    for key in ("semantic_head", "bookkeeping_head", "merge_main_sha", "post_merge_ci_run", "unit_job", "docker_job", "closure_comment_id", "audit_comment_id", "audit_verdict"):
        if closure.get(key) != record.get(key):
            failures.append(f"cross_binding:{key}")
    return failures


def _uads_failures(evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    handoff = evidence.get("handoff") if isinstance(evidence.get("handoff"), dict) else {}
    if evidence.get("status") != "PASS" or evidence.get("version") != VERSION:
        failures.append("uads:status")
    if evidence.get("validation", {}).get("status") != "PASS":
        failures.append("uads:validation")
    if ".uads" in json.dumps(evidence):
        failures.append("uads:repo_local_material")
    if handoff.get("execution_mode") != "GLOBAL_FIRST" or handoff.get("project_footprint") != "ZERO":
        failures.append("uads:execution_mode")
    if handoff.get("route_status") != "SELECTED":
        failures.append("uads:route_status")
    if handoff.get("repo_local_material") != "ABSENT":
        failures.append("uads:repo_local_material")
    if re.fullmatch(r"wo_[0-9a-f]{16}", str(handoff.get("work_order_id"))) is None:
        failures.append("uads:work_order_id")
    if re.fullmatch(r"er_[0-9a-f]{16}", str(handoff.get("run_or_dispatch_id"))) is None:
        failures.append("uads:run_or_dispatch_id")
    if handoff.get("dispatch_status") not in {"PREPARED", "DISPATCHED"}:
        failures.append("uads:dispatch_status")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    checks: list[dict[str, str]] = []
    failures: list[str] = []

    try:
        schema = _load(str(SCHEMA_PATH))
        state = _active_v0251_state()
        validate_schema_document(schema)
        validate_instance(state, schema)
        checks.append({"name": "current-state-v0251-schema", "status": "PASS"})
    except Exception as exc:  # fail closed on schema or instance errors
        checks.append({"name": "current-state-v0251-schema", "status": "FAIL", "error": type(exc).__name__})
        failures.append(f"current-state-v0251-schema:{type(exc).__name__}")
        state = {}

    if state.get("version") != VERSION or state.get("schema_version") != VERSION:
        failures.append("current-state:version")

    evidence: dict[str, dict[str, Any]] = {}
    for name in CLOSURE_EVIDENCE_FILES:
        try:
            evidence[name] = _load(str(EVIDENCE_ROOT / name))
            checks.append({"name": name, "status": "PASS"})
        except Exception as exc:  # missing or malformed closure evidence fails closed
            evidence[name] = {}
            checks.append({"name": name, "status": "FAIL", "error": type(exc).__name__})
            failures.append(f"{name}:{type(exc).__name__}")

    binding_failures = closure_binding_failures(evidence.get(CLOSURE_BINDING, {}))
    failures.extend(f"{CLOSURE_BINDING}:{item}" for item in binding_failures)
    failures.extend(_closure_cross_binding(state, evidence.get(CLOSURE_BINDING, {})))

    immutability = immutability_failures(evidence.get(IMMUTABILITY_PROOF, {}), ROOT)
    failures.extend(f"{IMMUTABILITY_PROOF}:{item}" for item in immutability)

    controls = negative_control_failures(evidence.get(NEGATIVE_CONTROLS, {}))
    failures.extend(f"{NEGATIVE_CONTROLS}:{item}" for item in controls)

    failures.extend(_uads_failures(evidence.get(UADS_HANDOFF, {})))

    try:
        definition = DEFINITION_OF_DONE_PATH.read_text(encoding="utf-8")
        hard_gates = _load(str(HARD_GATES_PATH))
        gate_records = hard_gates.get("gates") if isinstance(hard_gates.get("gates"), dict) else {}
        declared = definition_of_done_hard_gate_count(definition)
        if declared != HARD_GATE_COUNT or len(gate_records) != HARD_GATE_COUNT or hard_gates.get("overall_pass") is not True:
            failures.append(f"hard-gate-count:{declared}")
        else:
            checks.append({"name": "definition-of-done-hard-gate-count", "status": "PASS"})
    except Exception as exc:  # unreadable DoD or gates fails closed
        failures.append(f"hard-gate-count:{type(exc).__name__}")

    result = {"schema_version": VERSION, "version": VERSION, "status": "PASS" if not failures else "FAIL", "checks": checks, "failures": failures}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
