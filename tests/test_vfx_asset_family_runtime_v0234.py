"""Focused F-29R exact historical-tree and file-set integrity tests."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from ugas.historical_immutability_v0234 import (
    REJECTION_CLASS,
    validate_historical_file,
    validate_historical_immutability,
    validate_historical_root,
)
from ugas.state_consistency_v0234 import (
    BASELINE_MAIN_SHA,
    FEATURE_BRANCH,
    GOVERNED_MERGE_ACTION,
    PR_NUMBER,
    resolve_next_actions,
)
from ugas.vfx_asset_family_runtime_v0233 import VFXAssetFamilyContractError

ROOT = Path(__file__).resolve().parents[1]
AUTHORITIES = (
    ("c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72", "docs/evidence/vfx-asset-family-runtime-v0230"),
    ("136079540f674c7467d93bd28e9834addbfce5c3", "docs/evidence/vfx-asset-family-runtime-v0231"),
)


class VfxAssetFamilyRuntimeV0234Tests(unittest.TestCase):
    def test_live_approval_resolves_only_to_governed_merge(self) -> None:
        live = {
            "source": "GITHUB_LIVE",
            "repository": "KayzenRoot/ugas",
            "pr_number": PR_NUMBER,
            "branch": FEATURE_BRANCH,
            "base_sha": BASELINE_MAIN_SHA,
            "head_sha": "9f8030d2c0ee0e00d10d64a9331899e21ebd5842",
            "pr_state": "OPEN",
            "merged": False,
            "external_approval": True,
        }
        result = resolve_next_actions({}, live)
        self.assertEqual(result["allowed_next_actions"], [GOVERNED_MERGE_ACTION])
        self.assertFalse(result["orchestration_allowed"])

    def test_current_candidate_uses_exact_git_tree_for_both_authorities(self) -> None:
        if not (ROOT / ".git").is_dir():
            self.skipTest("exact current Git tree proof requires the repository object database")
        proof = validate_historical_immutability(ROOT)
        self.assertEqual(proof["status"], "PASS")
        self.assertTrue(all(item["equality"] for item in proof["roots"]))
        self.assertEqual([item["authority_file_count"] for item in proof["roots"]], [94, 97])

    def test_isolated_extra_file_is_rejected_for_each_authority(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ugas-test-history-v0234-extra-") as temp:
            for authority_ref, relative_root in AUTHORITIES:
                candidate_root = Path(temp) / authority_ref[:4] / relative_root
                shutil.copytree(ROOT / relative_root, candidate_root)
                (candidate_root / "UNAUTHORIZED-EXTRA-FILE.txt").write_text("extra\n", encoding="utf-8")
                with self.assertRaises(VFXAssetFamilyContractError) as context:
                    validate_historical_root(ROOT, authority_ref, relative_root, candidate_root)
                self.assertEqual(context.exception.rejection_class, REJECTION_CLASS)

    def test_isolated_byte_mutation_is_rejected_for_each_authority(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ugas-test-history-v0234-mutation-") as temp:
            for authority_ref, relative_root in AUTHORITIES:
                candidate_root = Path(temp) / authority_ref[:4] / relative_root
                shutil.copytree(ROOT / relative_root, candidate_root)
                target = next(path for path in candidate_root.rglob("*") if path.is_file())
                target.write_bytes(target.read_bytes() + b"\nmutation\n")
                with self.assertRaises(VFXAssetFamilyContractError) as context:
                    validate_historical_root(ROOT, authority_ref, relative_root, candidate_root)
                self.assertEqual(context.exception.rejection_class, REJECTION_CLASS)

    def test_historical_review_byte_mutations_use_same_rejection_class(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ugas-test-review-v0234-") as temp:
            for review, authority_ref in (("REVIEW-v0.23.0.md", AUTHORITIES[0][0]), ("REVIEW-v0.23.1.md", AUTHORITIES[1][0])):
                candidate = Path(temp) / review
                shutil.copy2(ROOT / review, candidate)
                candidate.write_bytes(candidate.read_bytes() + b"\nmutation\n")
                with self.assertRaises(VFXAssetFamilyContractError) as context:
                    validate_historical_file(ROOT, authority_ref, review, candidate)
                self.assertEqual(context.exception.rejection_class, REJECTION_CLASS)

    def test_tracked_candidate_tree_detects_extra_file_from_observed_head(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ugas-test-git-tree-v0234-") as temp:
            repo = Path(temp)
            relative_root = "docs/evidence/vfx-asset-family-runtime-v0230"
            shutil.copytree(ROOT / relative_root, repo / relative_root)
            self._git(repo, "init")
            self._git(repo, "config", "user.email", "ugas-tests@example.invalid")
            self._git(repo, "config", "user.name", "UGAS tests")
            self._git(repo, "add", ".")
            self._git(repo, "commit", "-m", "authority")
            authority_ref = self._git(repo, "rev-parse", "HEAD")
            (repo / relative_root / "UNAUTHORIZED-EXTRA-FILE.txt").write_text("extra\n", encoding="utf-8")
            self._git(repo, "add", ".")
            self._git(repo, "commit", "-m", "observed mutation")
            with self.assertRaises(VFXAssetFamilyContractError) as context:
                validate_historical_root(repo, authority_ref, relative_root)
            self.assertEqual(context.exception.rejection_class, REJECTION_CLASS)

    @staticmethod
    def _git(repo: Path, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise AssertionError(result.stderr)
        return result.stdout.strip()


if __name__ == "__main__":
    unittest.main()
