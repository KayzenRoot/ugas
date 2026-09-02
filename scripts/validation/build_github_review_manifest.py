"""Build the bounded GitHub-native review manifest and visual manifest.

The tracked repository remains the source of truth.  This builder only emits
review transport metadata and never copies secrets, local credentials, model
weights, telemetry or generated output directories.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "6b956b9299f3a2f75280f17706c38c59e3714034"
BRANCH = "codex/v0.12.3-github-native-review"
VISUALS = (
    "docs/evidence/observability-v0122/dashboard-docker-overview-v0122.png",
    "docs/evidence/observability-v0122/dashboard-docker-live-activity-v0122.png",
)
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def _run(args: list[str]) -> str:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    return result.stdout.strip()


def _resolve(ref: str) -> str:
    value = _run(["git", "rev-parse", ref])
    if not HEX40.fullmatch(value):
        raise ValueError(f"git ref did not resolve to a commit SHA: {ref}")
    return value


def _event_values() -> dict[str, Any]:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return {}
    try:
        value = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    pull_request = value.get("pull_request") if isinstance(value, dict) else {}
    pull_request = pull_request if isinstance(pull_request, dict) else {}
    base = pull_request.get("base") if isinstance(pull_request.get("base"), dict) else {}
    head = pull_request.get("head") if isinstance(pull_request.get("head"), dict) else {}
    return {
        "number": pull_request.get("number", 0),
        "base_ref": base.get("sha") or base.get("ref"),
        "head_ref": head.get("sha") or head.get("ref"),
        "head_branch": head.get("ref"),
    }


def _changed_files(base: str, head: str) -> tuple[list[dict[str, Any]], int, int]:
    records: list[dict[str, Any]] = []
    names = _run(["git", "diff", "--name-status", "--find-renames", f"{base}..{head}"]).splitlines()
    numstat = _run(["git", "diff", "--numstat", "--find-renames", f"{base}..{head}"]).splitlines()
    stats: dict[str, tuple[int, int]] = {}
    for line in numstat:
        parts = line.split("\t")
        if len(parts) >= 3:
            try:
                stats[parts[-1]] = (int(parts[0]), int(parts[1]))
            except ValueError:
                continue
    for line in names:
        parts = line.split("\t")
        if len(parts) == 2:
            status, path = parts
        elif len(parts) >= 3 and parts[0].startswith("R"):
            status, path = "R", parts[-1]
        else:
            continue
        additions, deletions = stats.get(path, (0, 0))
        records.append({"path": path.replace("\\", "/"), "status": status[0], "additions": additions, "deletions": deletions})

    # Local rehearsal happens before the feature commit, so include tracked
    # working-tree changes and untracked files.  On Actions these are empty.
    local_names = _run(["git", "diff", "--name-status", "--find-renames", base]).splitlines()
    known = {item["path"] for item in records}
    for line in local_names:
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0][0], parts[-1].replace("\\", "/")
        if path not in known:
            additions, deletions = stats.get(path, (0, 0))
            records.append({"path": path, "status": status, "additions": additions, "deletions": deletions})
            known.add(path)
    for path in _run(["git", "ls-files", "--others", "--exclude-standard"]).splitlines():
        normalized = path.replace("\\", "/")
        if normalized in known or normalized.startswith("tmp/") or normalized.startswith(".ugas/"):
            continue
        source = ROOT / normalized
        if not source.is_file():
            continue
        additions = len(source.read_text(encoding="utf-8", errors="replace").splitlines()) if source.suffix.casefold() not in {".png", ".gif", ".jpg", ".jpeg"} else 0
        records.append({"path": normalized, "status": "A", "additions": additions, "deletions": 0})
        known.add(normalized)
    records.sort(key=lambda item: item["path"])
    return records, sum(item.get("additions", 0) for item in records), sum(item.get("deletions", 0) for item in records)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_result(path: Path, *, validation: bool = False) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if validation and "checks" not in value:
        raise ValueError(f"validation result has no checks field: {path}")
    if not validation and "count" not in value:
        raise ValueError(f"test result has no count field: {path}")
    return value


def _load_gates(path: Path | None, tests: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    if path is not None:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("gates"), list):
            raise ValueError(f"gate result must contain a gates array: {path}")
        return value
    gates = [
        {"id": "unit_tests", "status": "PASS" if tests.get("status") == "passed" else "FAIL", "exit_code": tests.get("exit_code"), "detail": str(tests.get("status"))},
        {"id": "official_validation", "status": "PASS" if validation.get("status") == "passed" else "FAIL", "exit_code": validation.get("exit_code"), "detail": str(validation.get("status"))},
    ]
    return {"schema_version": "0.12.3", "overall_status": "FAIL", "gates": gates}


def _known_gaps(args: argparse.Namespace, event: dict[str, Any], pr_number: int) -> tuple[list[str], dict[str, Any]]:
    gaps = {str(item) for item in (args.known_gap or []) if str(item)}
    if args.preflight_json:
        preflight = json.loads(Path(args.preflight_json).read_text(encoding="utf-8"))
        for item in preflight.get("permission_gaps", []) if isinstance(preflight, dict) else []:
            if isinstance(item, dict) and item.get("code"):
                gaps.add(str(item["code"]))
    # PR creation is represented only by the tracked preflight when the PR
    # does not exist.  A manifest never carries that gap: on a real PR the
    # GitHub event is authoritative, and in a local rehearsal the explicit
    # LOCAL_REHEARSAL_PR_NOT_AVAILABLE context is used instead.
    gaps.discard("GITHUB_PR_CREATE_GAP")
    source = "github_event" if event else "local_rehearsal"
    if not event and pr_number == 0:
        gaps.add("LOCAL_REHEARSAL_PR_NOT_AVAILABLE")
    return sorted(gaps), {"source": source, "pr_number": pr_number, "pr_available": pr_number > 0, "explicit_gap_input": bool(args.known_gap or args.preflight_json)}


def build(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    event = _event_values()
    base_ref = args.base_ref or event.get("base_ref") or BASELINE
    head_ref = args.head_ref or event.get("head_ref") or "HEAD"
    base = _resolve(base_ref)
    head = _resolve(head_ref)
    merge_base = _resolve(_run(["git", "merge-base", base, head]))
    changed, additions, deletions = _changed_files(base, head)
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    tests = _load_result(Path(args.tests_json)) if args.tests_json else {"schema_version": "0.12.3", "command": "not-run-in-local-builder", "log_path": "not-run", "exit_code": 0, "parse_status": "not_run", "count": None, "passed": None, "failed": None, "status": "not_run"}
    validation = _load_result(Path(args.validation_json), validation=True) if args.validation_json else {"schema_version": "0.12.3", "command": "not-run-in-local-builder", "log_path": "not-run", "exit_code": 0, "parse_status": "not_run", "checks": None, "passed": None, "failed": None, "status": "not_run"}
    visual_path = Path(args.visual_manifest) if args.visual_manifest else ROOT / "docs/evidence/github-review-v0123/visual-manifest.json"
    visual_manifest = json.loads(visual_path.read_text(encoding="utf-8"))
    if not isinstance(visual_manifest, dict) or not isinstance(visual_manifest.get("visuals"), list):
        raise ValueError(f"visual manifest must contain a visuals array: {visual_path}")
    branch = args.head_branch or event.get("head_branch") or _run(["git", "branch", "--show-current"]) or BRANCH
    pr_number = args.pr_number if args.pr_number is not None else int(event.get("number") or 0)
    known_gaps, gap_context = _known_gaps(args, event, pr_number)
    gate_result = _load_gates(Path(args.gates_json) if args.gates_json else None, tests, validation)
    gates = gate_result["gates"]
    overall_status = "PASS" if gate_result.get("overall_status") == "PASS" and all(item.get("status") == "PASS" for item in gates) else "FAIL"
    manifest = {
        "schema_version": "1.0",
        "manifest_type": "github-native-review",
        "repository": {"name": "csn1985-ship-it/ugas", "url": "https://github.com/csn1985-ship-it/ugas", "default_branch": "main"},
        "pull_request": {"number": pr_number, "base_sha": base, "head_sha": head, "merge_base_sha": merge_base, "head_branch": branch, "base_branch": "main"},
        "scope": {"version": state["version"], "phase": state["phase"], "current_gate": state["current_gate"], "allowed_next_actions": state["allowed_next_actions"], "new_generation": state.get("new_generation", 0)},
        "changed_files": changed,
        "change_statistics": {"files": len(changed), "additions": additions, "deletions": deletions},
        "current_state": {"path": "docs/evidence/current-state.json", "version": state["version"], "phase": state["phase"], "current_gate": state["current_gate"], "production_approved": state["production_approved"], "production_routing": state["production_routing"], "external_visual_review": state["external_visual_review"], "allowed_next_actions": state["allowed_next_actions"]},
        "tests": tests,
        "validation": validation,
        "overall_status": overall_status,
        "gates": gates,
        "review_index": {"historical_path": "docs/evidence/review-index-v0.12.2.json", "historical_version": "0.12.2", "status": "PRESERVED_BASELINE_REHEARSAL", "active_manifest_path": "github-review-manifest.json"},
        "visual_manifest": "visual-manifest.json",
        "known_gaps": known_gaps,
        "gap_context": gap_context,
        "dashboard_policy": {"always_on": True, "runtime_mode": "DOCKER_ALWAYS_ON_LOCAL", "local_only": True, "url": "http://127.0.0.1:8765/", "must_remain_online_at_stop": True},
        "production_boundary": {"approved": False, "routing": "BLOCKED"},
        "security_boundary": {"secrets_included": False, "model_weights_included": False, "telemetry_db_included": False, "local_credentials_included": False},
    }
    return manifest, visual_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--base-ref")
    parser.add_argument("--head-ref")
    parser.add_argument("--head-branch")
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--tests-json")
    parser.add_argument("--validation-json")
    parser.add_argument("--gates-json")
    parser.add_argument("--visual-manifest")
    parser.add_argument("--preflight-json")
    parser.add_argument("--known-gap", action="append")
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest, visual_manifest = build(args)
    (output_dir / "github-review-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "visual-manifest.json").write_text(json.dumps(visual_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "GITHUB_REVIEW_MANIFEST_BUILT", "manifest": "github-review-manifest.json", "visual_manifest": "visual-manifest.json", "changed_files": len(manifest["changed_files"]), "base_sha": manifest["pull_request"]["base_sha"], "head_sha": manifest["pull_request"]["head_sha"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
