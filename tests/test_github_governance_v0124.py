"""v0.12.4 governance recovery negative controls."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts/github"))
sys.path.insert(0, str(ROOT / "scripts/validation"))
sys.path.insert(0, str(ROOT / "src"))

from merge_policy_v0124 import can_merge
import validate_github_workflows_v0124 as workflow_validator
import validate_review_index_v0112 as historical_validator
from ugas.state_consistency_v0124 import validate_state_consistency


class GithubGovernanceRecoveryTests(unittest.TestCase):
    def test_gov_nc_01_red_or_pending_required_check_blocks(self) -> None:
        required = ["UGAS CI / unit-and-validation", "UGAS CI / docker-smoke", "UGAS Review / evidence"]
        approval = {"approved": True, "pr_number": 2, "head_sha": "a" * 40}
        for state in ("PENDING", "FAILURE"):
            checks = [{"name": required[0], "state": state}, {"name": required[1], "state": "SUCCESS"}, {"name": required[2], "state": "SUCCESS"}]
            self.assertFalse(can_merge(checks, required_names=required, external_approval=approval, expected_pr_number=2, expected_head_sha="a" * 40, actual_pr_number=2, actual_head_sha="a" * 40))

    def test_gov_nc_02_exact_external_approval_is_required(self) -> None:
        required = ["UGAS CI / unit-and-validation", "UGAS CI / docker-smoke", "UGAS Review / evidence"]
        checks = [{"name": name, "state": "SUCCESS"} for name in required]
        self.assertFalse(can_merge(checks, required_names=required, external_approval=None, expected_pr_number=2, expected_head_sha="a" * 40, actual_pr_number=2, actual_head_sha="a" * 40))
        self.assertFalse(can_merge(checks, required_names=required, external_approval={"approved": True, "pr_number": 2, "head_sha": "b" * 40}, expected_pr_number=2, expected_head_sha="a" * 40, actual_pr_number=2, actual_head_sha="a" * 40))

    def test_ci_nc_01_isolated_fixture_does_not_use_root_git(self) -> None:
        source = (ROOT / "tests/test_github_review_integrity_v0123.py").read_text(encoding="utf-8")
        self.assertIn("isolated_git_fixture", source)
        self.assertIn("repository_root", source)

    def test_ci_nc_02_no_git_builder_is_not_silently_passed(self) -> None:
        source = (ROOT / "scripts/validation/build_github_review_manifest_v0124.py").read_text(encoding="utf-8")
        self.assertIn("Live builds are intentionally Git-bound", source)
        self.assertIn("_resolve(base_ref, root)", source)

    def test_hist_nc_01_current_checkpoint_does_not_bind_old_index(self) -> None:
        expected = "8b129cd2e3979130dd121c1c235a09288e723e8bc55627d8055a282b27b17133"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "CHECKPOINT.md"
            bundled = root / "historical/CHECKPOINT.md"
            current.parent.mkdir(parents=True, exist_ok=True)
            bundled.parent.mkdir(parents=True)
            current.write_text("mutable current checkpoint\n", encoding="utf-8")
            bundled.write_bytes((ROOT / "docs/evidence/github-governance-v0124/historical/v0.11.2/CHECKPOINT.md").read_bytes())
            with patch.object(historical_validator, "ROOT", root):
                self.assertEqual(expected, historical_validator.historical_digest("CHECKPOINT.md", expected, "no-git", root / "historical"))
            bundled.write_text("tampered historical bytes\n", encoding="utf-8")
            with patch.object(historical_validator, "ROOT", root):
                self.assertNotEqual(expected, historical_validator.historical_digest("CHECKPOINT.md", expected, "no-git", root / "historical"))

    def test_wf_nc_01_malformed_workflow_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.yml"
            path.write_text("name: broken\njobs:\n  build:\n    runs-on: ubuntu-latest\n", encoding="utf-8")
            result = workflow_validator.validate_workflow(path, kind="ci")
            self.assertEqual("FAIL", result["status"])

    def test_wf_nc_01_job_env_runner_context_is_rejected(self) -> None:
        text = (ROOT / ".github/workflows/ugas-ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("UGAS_RUNTIME_PATH: ${{ runner.temp }}", text)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-runner.yml"
            path.write_text(text.replace("UGAS_REPO_PATH: ${{ github.workspace }}", "UGAS_REPO_PATH: ${{ github.workspace }}\n      UGAS_RUNTIME_PATH: ${{ runner.temp }}/ugas-runtime"), encoding="utf-8")
            result = workflow_validator.validate_workflow(path, kind="ci")
            self.assertEqual("FAIL", result["status"])
            self.assertIn("job-env-runner-context-invalid", result["failures"])

    def test_state_nc_01_production_and_generation_are_blocked(self) -> None:
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        checkpoint = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8")
        review = (ROOT / "REVIEW-v0.12.4.md").read_text(encoding="utf-8")
        mutant = copy.deepcopy(state); mutant["production_approved"] = True
        result = validate_state_consistency(mutant, checkpoint, review, (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"))
        self.assertIn("production_approved_must_remain_false", result["failures"])
        mutant = copy.deepcopy(state); mutant["new_generation"] = 1
        self.assertIn("new_generation_must_remain_zero", validate_state_consistency(mutant, checkpoint, review, "")["failures"])

    def test_handoff_has_no_merge_operation(self) -> None:
        source = (ROOT / "scripts/github/ugas-pr-handoff.ps1").read_text(encoding="utf-8")
        self.assertNotIn("'gh', 'pr', 'merge", source)
        self.assertIn("merge_performed = $false", source)


if __name__ == "__main__":
    unittest.main()
