"""Fail-closed validation for ENG-PROTOCOL-ADOPTION-001 artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORK_ORDER_ID = "ENG-PROTOCOL-ADOPTION-001"
BASELINE_SHA = "c573ab020106ee89a36e1edb9bfae8b526d5057e"
BRANCH = "chore/eng-protocol-adoption-001"
ALLOWED_PREFIXES = (".engineering/", ".github/", "AGENTS.md", "scripts/validation/validate_engineering_protocol.py")
REQUIRED_PATHS = (
    ".engineering/ENGINEERING-DELIVERY-PROTOCOL.md",
    ".engineering/work-orders/ENG-PROTOCOL-ADOPTION-001.md",
    ".engineering/context-locks/ENG-PROTOCOL-ADOPTION-001.json",
    ".engineering/context-locks/ENG-PROTOCOL-ADOPTION-001-after.json",
    ".engineering/reports/BASELINE-ENG-PROTOCOL-ADOPTION-001.md",
    ".engineering/reports/CLEANUP-INVENTORY.md",
    ".engineering/checkpoints/ENG-PROTOCOL-ADOPTION-001.md",
    ".engineering/evidence/ENG-PROTOCOL-ADOPTION-001.json",
    ".github/ISSUE_TEMPLATE/implementation.yml",
    ".github/ISSUE_TEMPLATE/defect.yml",
)


def load(relative: str) -> object:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def git_changed_paths() -> list[str]:
    result = subprocess.run(["git", "diff", "--name-only", BASELINE_SHA, "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    failures: list[str] = []
    for relative in REQUIRED_PATHS:
        if not (ROOT / relative).is_file():
            failures.append(f"missing:{relative}")

    contract_paths = [
        ".engineering/contracts/work-order.schema.json",
        ".engineering/contracts/context-lock.schema.json",
        ".engineering/contracts/evidence-bundle.schema.json",
        ".engineering/contracts/correction-delta.schema.json",
        ".engineering/contracts/checkpoint-delta.schema.json",
    ]
    template_paths = [
        ".engineering/templates/work-order.template.md",
        ".engineering/templates/context-lock.template.md",
        ".engineering/templates/evidence-bundle.template.md",
        ".engineering/templates/correction-delta.template.md",
        ".engineering/templates/checkpoint-delta.template.md",
    ]
    for relative in contract_paths:
        try:
            value = load(relative)
            if not isinstance(value, dict) or value.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                failures.append(f"invalid-contract:{relative}")
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"invalid-contract:{relative}:{exc}")
    for relative in template_paths:
        if not (ROOT / relative).is_file():
            failures.append(f"missing-template:{relative}")

    protocol = (ROOT / ".engineering/ENGINEERING-DELIVERY-PROTOCOL.md").read_text(encoding="utf-8")
    for marker in ("Source hierarchy", "Context Lock", "Evidence Bundle", "STALE", "VERIFIED_DEAD", "self-merge", "independent review"):
        if marker.casefold() not in protocol.casefold():
            failures.append(f"protocol-marker:{marker}")

    work_order = (ROOT / ".engineering/work-orders/ENG-PROTOCOL-ADOPTION-001.md").read_text(encoding="utf-8")
    for marker in (WORK_ORDER_ID, BASELINE_SHA, BRANCH, "product behavior", "Broad cleanup", "READY_FOR_REVIEW"):
        if marker.casefold() not in work_order.casefold():
            failures.append(f"work-order-marker:{marker}")

    baseline = load(".engineering/context-locks/ENG-PROTOCOL-ADOPTION-001.json")
    after = load(".engineering/context-locks/ENG-PROTOCOL-ADOPTION-001-after.json")
    evidence = load(".engineering/evidence/ENG-PROTOCOL-ADOPTION-001.json")
    required_same = ((baseline, "baseline"), (after, "after"), (evidence, "evidence"))
    for value, label in required_same:
        if value.get("work_order_id") != WORK_ORDER_ID:
            failures.append(f"identity:{label}")
        if value.get("baseline_git_sha", value.get("baseline_sha")) != BASELINE_SHA:
            failures.append(f"baseline-sha:{label}")
    if baseline.get("context_status") != "STALE":
        failures.append("baseline-lock-must-be-stale")
    if after.get("context_status") != "RELOCKED_AFTER_AUTHORIZED_ADOPTION":
        failures.append("after-lock-must-be-relocked")
    if evidence.get("branch") != BRANCH or evidence.get("status") not in {"DRAFT", "READY_FOR_REVIEW"}:
        failures.append("evidence-identity-or-status")
    if evidence.get("external_review", {}).get("approval_claimed") is not False:
        failures.append("external-approval-must-not-be-claimed")
    if evidence.get("production_boundary", {}).get("production_routing") != "BLOCKED":
        failures.append("production-must-remain-blocked")
    if evidence.get("production_boundary", {}).get("new_generation") != 0:
        failures.append("new-generation-must-remain-zero")

    inventory = (ROOT / ".engineering/reports/CLEANUP-INVENTORY.md").read_text(encoding="utf-8")
    for classification in ("VERIFIED_DEAD", "PROBABLY_DEAD", "DUPLICATE_OR_OBSOLETE", "GENERATED_OR_VENDORED", "UNKNOWN"):
        if classification not in inventory:
            failures.append(f"inventory-classification:{classification}")
    if "no cleanup was executed" not in inventory.casefold() or "verified_dead" not in inventory.casefold():
        failures.append("inventory-safety-statement")

    checkpoint = (ROOT / ".engineering/checkpoints/ENG-PROTOCOL-ADOPTION-001.md").read_text(encoding="utf-8")
    if "proposed" not in checkpoint.casefold() or "canonical change" not in checkpoint.casefold() or "`false`" not in checkpoint:
        failures.append("checkpoint-delta-must-be-proposed")

    changed = git_changed_paths()
    if changed:
        outside = [path for path in changed if not path.startswith(ALLOWED_PREFIXES)]
        if outside:
            failures.append("out-of-scope-changed-paths:" + ",".join(outside))
        for protected in ("CHECKPOINT.md", "docs/evidence/current-state.json", "pyproject.toml", "package.json", "compose.yaml"):
            if protected in changed:
                failures.append(f"protected-path-changed:{protected}")

    print(f"ENG_PROTOCOL_ADOPTION_ID={WORK_ORDER_ID}")
    print(f"ENG_PROTOCOL_ADOPTION_BASELINE={BASELINE_SHA}")
    print(f"ENG_PROTOCOL_ADOPTION_BRANCH={BRANCH}")
    print(f"ENG_PROTOCOL_ADOPTION_CHANGED_PATHS={len(changed)}")
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        print(f"SUMMARY checks={len(REQUIRED_PATHS) + len(contract_paths) + len(template_paths) + 12} passed=0 failed={len(failures)}")
        return 1
    checks = len(REQUIRED_PATHS) + len(contract_paths) + len(template_paths) + 12
    print(f"SUMMARY checks={checks} passed={checks} failed=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
