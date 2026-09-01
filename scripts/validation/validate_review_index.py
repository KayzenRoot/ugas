"""Validate the GitHub-first v0.8.1 review index and its evidence hashes."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("index", nargs="?", default="docs/evidence/review-index-v0.8.1.json")
    args = parser.parse_args()
    path = ROOT / args.index
    failures: list[str] = []
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REVIEW_INDEX_INVALID", "failures": [str(exc)]}, indent=2))
        return 1
    required = {"schema_version", "version", "branch", "head_commit", "dirty_state_at_publish", "review_file", "current_state", "tests", "validation", "evidence", "required_visual_sets", "forbidden_artifacts", "external_visual_review", "production_routing"}
    failures.extend(f"missing:{key}" for key in sorted(required - set(index)))
    if index.get("schema_version") != "0.8.1" or index.get("version") != "0.8.1":
        failures.append("index_version_must_be_0.8.1")
    if index.get("branch") != "main":
        failures.append("index_branch_must_be_main")
    if index.get("production_routing") != "BLOCKED":
        failures.append("production_routing_must_be_blocked")
    if index.get("external_visual_review", {}).get("status") != "REQUIRED" or index.get("external_visual_review", {}).get("approval") != "not-claimed":
        failures.append("external_visual_review_boundary_invalid")
    if index.get("tests", {}).get("status") != "passed" or int(index.get("tests", {}).get("count", 0)) < 1:
        failures.append("tests_not_recorded_as_passed")
    if index.get("validation", {}).get("status") != "passed" or int(index.get("validation", {}).get("failed", 1)) != 0:
        failures.append("validation_not_recorded_as_passed")
    for item in index.get("evidence", []):
        if not isinstance(item, dict):
            failures.append("evidence_item_not_object")
            continue
        source = ROOT / str(item.get("path", ""))
        if not source.is_file():
            failures.append(f"missing:{source}")
        elif item.get("sha256") != digest(source):
            failures.append(f"hash_mismatch:{item.get('path')}")
        if not item.get("media_type") or not item.get("role"):
            failures.append(f"evidence_metadata_missing:{item.get('path')}")
    visual = ROOT / "docs/evidence/review-visuals-v0.8.1.json"
    if visual.is_file():
        manifest = json.loads(visual.read_text(encoding="utf-8"))
        listed = {str(item.get("source_path")) for item in manifest.get("images", [])}
        indexed = {str(item.get("path")) for item in index.get("evidence", [])}
        missing = sorted(listed - indexed)
        failures.extend(f"visual_not_indexed:{item}" for item in missing)
    head = index.get("head_commit")
    current = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False).stdout.strip()
    if head and current and head != current:
        ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", str(head), current], cwd=ROOT, capture_output=True, check=False)
        if ancestor.returncode != 0:
            failures.append("recorded_head_is_not_current_or_ancestor")
    result = {"status": "REVIEW_INDEX_VALID" if not failures else "REVIEW_INDEX_INVALID", "failures": failures, "evidence_count": len(index.get("evidence", [])), "visual_set_count": len(index.get("required_visual_sets", []))}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
