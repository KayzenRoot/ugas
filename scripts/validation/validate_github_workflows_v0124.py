"""Repository-side structural guard for the two UGAS GitHub workflows.

This is deliberately not a replacement for GitHub's runner/parser. It catches
the high-impact shape errors that can be checked without network access; the
real pull-request run remains the authoritative proof.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SHA = r"[0-9a-f]{40}"
ACTION_RE = re.compile(r"^\s*uses:\s*[^\s@]+@(" + SHA + r")\s*(?:#.*)?$", re.MULTILINE)
MUTABLE_ACTION_RE = re.compile(r"uses:\s*[^\s@]+@(?:v?\d+(?:\.\d+){0,2})(?:\s|#|$)", re.MULTILINE)


def validate_workflow(path: Path, *, kind: str) -> dict[str, Any]:
    failures: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"status": "FAIL", "workflow": path.as_posix(), "failures": [f"read:{exc}"]}
    if not text.lstrip().startswith("name:"):
        failures.append("name-missing")
    if "pull_request:" not in text or "workflow_dispatch:" not in text:
        failures.append("pull-request-or-dispatch-trigger-missing")
    if "jobs:" not in text:
        failures.append("jobs-missing")
    if not ACTION_RE.findall(text):
        failures.append("no-immutable-action-pin")
    if "@master" in text or "@main" in text or MUTABLE_ACTION_RE.search(text):
        failures.append("mutable-action-reference")
    if kind == "ci":
        for stable in ("UGAS CI / unit-and-validation", "UGAS CI / docker-smoke"):
            if stable not in text:
                failures.append(f"stable-job-missing:{stable}")
        if "docker compose -f compose.yaml config" not in text or "docker compose -f compose.yaml build dashboard" not in text or "docker compose -f compose.yaml up -d dashboard" not in text:
            failures.append("docker-smoke-lifecycle-incomplete")
        if "docker compose -f compose.yaml rm -sf dashboard" not in text:
            failures.append("docker-smoke-runner-cleanup-missing")
        if "docker compose -f compose.yaml down" in text or "--volumes" in text:
            failures.append("persistent-dashboard-teardown-forbidden")
        if re.search(r"UGAS_RUNTIME_PATH:\s*\$\{\{\s*runner\.", text):
            failures.append("job-env-runner-context-invalid")
    elif kind == "review":
        if "UGAS Review / evidence" not in text:
            failures.append("stable-review-job-missing")
        if "if: always()" not in text:
            failures.append("failure-safe-evidence-missing")
        if "actions/upload-artifact@" not in text:
            failures.append("artifact-upload-missing")
        if "Enforce final review result after artifact upload" not in text:
            failures.append("post-upload-enforcement-missing")
        upload = text.find("Upload bounded GitHub review artifact")
        enforce = text.find("Enforce final review result after artifact upload")
        if upload < 0 or enforce <= upload:
            failures.append("enforcement-order-invalid")
    else:
        failures.append("unknown-workflow-kind")
    return {"status": "PASS" if not failures else "FAIL", "workflow": path.as_posix(), "kind": kind, "action_pin_count": len(ACTION_RE.findall(text)), "failures": failures}


def validate_repository(root: Path) -> dict[str, Any]:
    results = [validate_workflow(root / ".github/workflows/ugas-ci.yml", kind="ci"), validate_workflow(root / ".github/workflows/ugas-review.yml", kind="review")]
    for item in results:
        workflow_path = Path(item["workflow"])
        try:
            item["workflow"] = workflow_path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            item["workflow"] = workflow_path.as_posix()
    failures = [f"{item['workflow']}:{failure}" for item in results for failure in item["failures"]]
    return {"schema_version": "0.12.4", "status": "PASS" if not failures else "FAIL", "workflows": results, "failures": failures, "real_github_run_required": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = validate_repository(Path(args.root).resolve())
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
