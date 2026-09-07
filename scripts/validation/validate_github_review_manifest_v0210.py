"""Fail-closed validation of the bounded v0.21.3 review manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


def _artifact_path(artifact: Path, relative: str) -> Path:
    direct = artifact / relative
    if direct.is_file():
        return direct
    prefix = "docs/evidence/maps-minimap-runtime-v0213/"
    if relative.startswith(prefix):
        return artifact / "maps-minimap" / relative[len(prefix):]
    return direct


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("manifest", type=Path); parser.add_argument("--result-output", type=Path, required=True); args = parser.parse_args()
    failures: list[str] = []
    try:
        value = json.loads(args.manifest.read_text(encoding="utf-8"))
        required = ("schema_version", "manifest_type", "repository", "pull_request", "scope", "tests", "validation", "gates", "maps_minimap_evidence", "production_boundary", "review_boundary")
        failures.extend(f"missing:{name}" for name in required if name not in value)
        if value.get("schema_version") != "0.21.3" or value.get("manifest_type") not in {"github-ci-maps-minimap-v0213-review", "github-ci-maps-minimap-v0213-post-merge-closure"}: failures.append("manifest-identity-invalid")
        pr = value.get("pull_request", {}); current_head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
        if pr.get("number") is None or pr.get("number") < 0 or not pr.get("head_sha") or not pr.get("base_sha") or not pr.get("head_branch"): failures.append("pull-request-binding-invalid")
        if current_head and current_head != pr.get("head_sha"): failures.append("head-sha-does-not-match-checked-out-head")
        scope = value.get("scope", {})
        post_merge = value.get("manifest_type") == "github-ci-maps-minimap-v0213-post-merge-closure"
        expected_gate = "MAPS_MINIMAP_APPROVED_FOUNDATION_MERGED" if post_merge else "MAPS_MINIMAP_RASTER_GOVERNANCE_INTEGRITY_TECHNICALLY_QUALIFIED"
        expected_action = ["resolve_post_merge_closure_gate_pr_12"] if post_merge else ["bookkeeping_reproof_and_governed_merge_pr_11"]
        if scope.get("version") != "0.21.3" or scope.get("phase") != "MAPS_MINIMAP" or scope.get("current_gate") != expected_gate or scope.get("allowed_next_actions") != expected_action: failures.append("active-scope-invalid")
        if post_merge and (scope.get("baseline_main_sha") != "0c9b721b43d3cc12605ce009f6e0deb232b00045" or "main_sha" in scope): failures.append("baseline-main-anchor-invalid")
        if value.get("production_boundary") != {"approved": False, "routing": "BLOCKED", "new_generation": 0, "real_map_asset_coverage": "NONE", "real_minimap_asset_coverage": "NONE", "synthetic_map_fixture": "TEST_ONLY"}: failures.append("production-boundary-invalid")
        review = value.get("review_boundary", {})
        expected_authorization = "NOT_AUTHORIZED_UNTIL_SOL_APPROVAL" if post_merge else "APPROVED_TO_MERGE_AFTER_BOOKKEEPING_REPROOF"
        if review.get("external_review_required") is not True or review.get("do_not_merge") is not True or review.get("merge_authorization") != expected_authorization: failures.append("review-boundary-invalid")
        if value.get("tests", {}).get("status") != "passed" or value.get("tests", {}).get("failed") != 0: failures.append("unit-tests-not-pass")
        if value.get("validation", {}).get("status") != "passed" or value.get("validation", {}).get("failed") != 0: failures.append("official-validation-not-pass")
        if not value.get("gates") or any(item.get("status") != "PASS" for item in value["gates"].values()): failures.append("gates-not-pass")
        if value.get("overall_status") != "PASS": failures.append("overall-status-not-pass")
        evidence = value.get("maps_minimap_evidence", {})
        if len(evidence) < 15: failures.append("evidence-list-incomplete")
        for relative in evidence.values():
            if not _artifact_path(args.manifest.parent, relative).is_file(): failures.append(f"evidence-missing:{relative}")
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        failures.append(f"manifest-read:{type(exc).__name__}:{exc}")
    result = {"schema_version": "0.21.3", "status": "PASS" if not failures else "FAIL", "failures": failures, "checked_manifest": str(args.manifest)}
    args.result_output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
