"""Fail-closed exact-head validator for the v0.22.2 review manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("manifest", type=Path); parser.add_argument("--result-output", type=Path, required=True); args = parser.parse_args(); failures: list[str] = []
    try:
        value = json.loads(args.manifest.read_text(encoding="utf-8")); current = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip(); pr = value.get("pull_request", {}); scope = value.get("scope", {}); production = value.get("production_boundary", {}); gates = value.get("gates", {}); controls = value.get("negative_controls", {}).get("controls", {})
        if value.get("schema_version") != "0.22.2" or value.get("manifest_type") != "github-ci-ui-asset-family-v0222-review": failures.append("manifest-identity-invalid")
        if pr.get("base_sha") != "1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3" or pr.get("head_sha") != current or pr.get("number") != 13 or not pr.get("head_branch"): failures.append("exact-head-pr-binding-invalid")
        expected_scope = {"version": "0.22.2", "phase": "UI_ASSET_FAMILY", "current_gate": "UI_ASSET_FAMILY_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED", "baseline_main_sha": "1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3", "allowed_next_actions": ["external_review_ui_asset_family_v0222"], "next_candidate": "UI_ASSET_FAMILY", "new_generation": 0}; failures.extend(f"scope:{key}" for key, expected in expected_scope.items() if scope.get(key) != expected)
        expected_production = {"approved": False, "routing": "BLOCKED", "new_generation": 0, "real_ui_asset_coverage": "NONE", "synthetic_ui_fixture": "TEST_ONLY", "production_registry_empty": True}; failures.extend(f"production:{key}" for key, expected in expected_production.items() if production.get(key) != expected)
        review = value.get("review_boundary", {}); failures.extend(["review-boundary"] if review.get("external_review_required") is not True or review.get("do_not_merge") is not True or review.get("merge_authorization") != "NOT_AUTHORIZED_UNTIL_SOL_APPROVAL" else [])
        if value.get("tests", {}).get("status") != "passed" or value.get("tests", {}).get("failed") != 0: failures.append("tests")
        if value.get("validation", {}).get("status") != "passed" or value.get("validation", {}).get("failed") != 0: failures.append("validation")
        if len(gates) < 22 or any(item.get("status") != "PASS" or type(item.get("observed")) is not bool or item.get("observed") is not True for item in gates.values()): failures.append("hard-gates")
        if len(controls) < 22 or any(item.get("status") != "PASS" or item.get("result") != "REJECT" or item.get("expected_rejection_class") != item.get("observed_rejection_class") for item in controls.values()): failures.append("negative-controls")
        if value.get("governance", {}).get("validation", {}).get("status") != "PASS" or value.get("determinism", {}).get("status") != "PASS" or value.get("overall_status") != "PASS": failures.append("overall")
        for relative in value.get("ui_evidence", {}).values():
            if not (args.manifest.parent / relative).is_file(): failures.append(f"evidence-missing:{relative}")
        for relative in ("docs/evidence/ui-asset-family-runtime-v0220/", "docs/evidence/ui-asset-family-runtime-v0221/", "docs/evidence/maps-minimap-runtime-v0213/", "docs/evidence/github-governance-v0220/v0213-post-merge-binding.json"):
            if not (args.manifest.parent / relative).exists(): failures.append(f"immutable-or-governance-missing:{relative}")
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc: failures.append(f"manifest-read:{type(exc).__name__}:{exc}")
    result = {"schema_version": "0.22.2", "status": "PASS" if not failures else "FAIL", "failures": failures, "checked_manifest": str(args.manifest)}; args.result_output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8"); print(json.dumps(result, ensure_ascii=False)); return 0 if not failures else 1


if __name__ == "__main__": raise SystemExit(main())
