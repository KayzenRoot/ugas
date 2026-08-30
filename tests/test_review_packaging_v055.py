"""v0.5.5 review matcher and archive-boundary regression tests."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.validation.verify_review_archive import ReviewArchiveError, _safe_archive_name, verify_archive
from ugas.review_snapshot import security_exclusion_reason, self_test_sensitive_matcher


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = tuple(
    f"docs/evidence/v054-lanes/{lane}-seed-{seed}.png"
    for lane in ("a", "c", "r")
    for seed in (54701, 54702, 54703)
)


class ReviewPackagingV055Tests(unittest.TestCase):
    def test_anchored_matcher_allows_generation_metadata_and_blocks_explicit_secrets(self):
        result = self_test_sensitive_matcher()
        self.assertEqual("SENSITIVE_MATCHER_SELF_TEST_PASSED", result["status"])
        for name in ("a-seed-54701.png", "some-model-seed-metadata.json", "tokenizer.json", "monkey.png"):
            self.assertIsNone(security_exclusion_reason(Path(name)))
        for name in (".env", ".env.local", "credentials.json", "private_key.pem", "api_token.txt", "seed_phrase.txt"):
            self.assertIsNotNone(security_exclusion_reason(Path(name)))

    def test_archive_path_and_weight_guards_are_fail_closed(self):
        with self.assertRaises(ReviewArchiveError):
            _safe_archive_name("../outside.txt")
        with self.assertRaises(ReviewArchiveError):
            _safe_archive_name("C:/outside.txt")

    def test_nine_canonical_outputs_are_not_secret_paths(self):
        for path in CANONICAL:
            self.assertIsNone(security_exclusion_reason(Path(path)), path)
            self.assertTrue((ROOT / path).is_file(), path)

    def _archive_fixture(self, directory: Path, *, remove_output: str | None = None, mismatch_copy: str | None = None) -> Path:
        visual = json.loads((ROOT / "docs/evidence/review-visuals-v0.5.5.json").read_text(encoding="utf-8"))
        table = json.loads((ROOT / "docs/evidence/v054-pose-error-table.json").read_text(encoding="utf-8"))
        entries: dict[str, bytes] = {
            "REVIEW-v0.5.5.md": b"review",
            "docs/evidence/review-visuals-v0.5.5.json": json.dumps(visual).encode("utf-8"),
            "docs/evidence/v054-pose-error-table.json": json.dumps(table).encode("utf-8"),
        }
        for item in visual["images"]:
            source = str(item["source_path"])
            entries[source] = (ROOT / source).read_bytes()
            copy = f"__REVIEW__/visual-evidence/{item['archive_name']}"
            entries[copy] = entries[source]
            if mismatch_copy == source:
                entries[copy] = b"different"
        for path in CANONICAL:
            if remove_output == path:
                entries.pop(path, None)
        metadata = {
            "__REVIEW__/tree.txt": b"tree\n",
            "__REVIEW__/git-status.txt": b"## main\n",
            "__REVIEW__/git-branch.txt": b"main\n",
            "__REVIEW__/git-head.txt": b"a" * 40 + b"\n",
            "__REVIEW__/git-log.txt": b"a" * 40 + b" commit\n",
            "__REVIEW__/git-diff.patch": b"",
            "__REVIEW__/git-diff-staged.patch": b"",
            "__REVIEW__/excluded-files.txt": b"secret.txt\tsecurity: exact sensitive filename\n",
        }
        entries.update(metadata)
        non_review_count = sum(not name.startswith("__REVIEW__/") for name in entries)
        manifest = {
            "project_name": "ugas",
            "generated_at": "2026-08-30T00:00:00-03:00",
            "branch": "main",
            "head_commit": "a" * 40,
            "total_files_included": non_review_count,
            "review_script_version": "1.8.0",
        }
        entries["__REVIEW__/manifest.json"] = json.dumps(manifest).encode("utf-8")
        path = directory / "fixture.zip"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        return path

    def test_archive_verifier_detects_missing_single_lane_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._archive_fixture(Path(directory), remove_output=CANONICAL[0])
            with self.assertRaisesRegex(ReviewArchiveError, "required visual source omitted|canonical lane output missing"):
                verify_archive(path)

    def test_archive_verifier_detects_divergent_review_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._archive_fixture(Path(directory), mismatch_copy=CANONICAL[0])
            with self.assertRaisesRegex(ReviewArchiveError, "review visual copy differs"):
                verify_archive(path)


if __name__ == "__main__":
    unittest.main()
