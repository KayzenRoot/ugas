"""Verify and self-validate a UGAS review archive without relying on Git."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image

from ugas.review import validate_review_visual_manifest
from ugas.review_snapshot import security_exclusion_reason


CANONICAL_LANE_OUTPUTS = tuple(
    f"docs/evidence/v054-lanes/{lane}-seed-{seed}.png"
    for lane in ("a", "c", "r")
    for seed in (54701, 54702, 54703)
)
FORBIDDEN_WEIGHT_SUFFIXES = {
    ".safetensors", ".task", ".ckpt", ".gguf", ".onnx", ".pt", ".pth", ".bin",
}
REQUIRED_ARCHIVE_METADATA = {
    "__REVIEW__/manifest.json",
    "__REVIEW__/tree.txt",
    "__REVIEW__/git-status.txt",
    "__REVIEW__/git-branch.txt",
    "__REVIEW__/git-head.txt",
    "__REVIEW__/git-log.txt",
    "__REVIEW__/git-diff.patch",
    "__REVIEW__/git-diff-staged.patch",
    "__REVIEW__/excluded-files.txt",
    "docs/evidence/review-visuals-v0.5.5.json",
    "REVIEW-v0.5.5.md",
    "docs/evidence/v054-pose-error-table.json",
}


class ReviewArchiveError(RuntimeError):
    """Raised when a review archive is not a complete executable snapshot."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_visual_digest(name: str, data: bytes) -> str:
    """Match the repository review digest while preserving archive copy bytes."""
    if Path(name).suffix.casefold() in {".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    return _sha256(data)


def _safe_archive_name(name: str) -> None:
    if not name or name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name):
        raise ReviewArchiveError(f"absolute archive path: {name}")
    if "\\" in name:
        raise ReviewArchiveError(f"non-canonical archive separator: {name}")
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise ReviewArchiveError(f"path traversal archive entry: {name}")


def _read_json(archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
    try:
        value = json.loads(archive.read(name).decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewArchiveError(f"invalid JSON archive entry: {name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReviewArchiveError(f"JSON archive entry is not an object: {name}")
    return value


def _verify_png(data: bytes, name: str) -> None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
    except Exception as exc:  # Pillow raises several format-specific errors.
        raise ReviewArchiveError(f"invalid PNG: {name}: {exc}") from exc


def _validate_snapshot_contents(archive: zipfile.ZipFile, names: set[str]) -> dict[str, Any]:
    active_visual_name = next(
        (
            name
            for name in (
                "docs/evidence/review-visuals-v0.6.1.json",
                "docs/evidence/review-visuals-v0.6.0.json",
                "docs/evidence/review-visuals-v0.5.5.json",
                "docs/evidence/review-visuals-v0.5.4.json",
            )
            if name in names
        ),
        None,
    )
    if active_visual_name is None:
        raise ReviewArchiveError("no supported active review visual manifest is present")
    required_metadata = set(REQUIRED_ARCHIVE_METADATA)
    if active_visual_name.endswith("v0.6.1.json"):
        required_metadata.update(
            {
                "docs/evidence/review-visuals-v0.6.1.json",
                "REVIEW-v0.6.1.md",
                "docs/evidence/current-state.json",
                "docs/evidence/current-state-v0.6.0.json",
                "docs/evidence/state-consistency.json",
                "docs/evidence/custom-node-audit-ipadapter-plus.json",
                "docs/evidence/sdxl-model-stack-qualification.json",
                "docs/evidence/sdxl-base-model-qualification.json",
                "docs/evidence/sdxl-openpose-controlnet-qualification.json",
                "docs/evidence/ipadapter-sdxl-model-qualification.json",
                "docs/evidence/clip-vision-qualification.json",
                "docs/evidence/runtime-doctor-v0.6.0.json",
                "docs/evidence/sdxl-provider-workflow-qualification.json",
                "docs/evidence/sdxl-provider-workflow-qualification-v0.6.1.json",
                "docs/evidence/sdxl-provider-qualification.json",
                "docs/evidence/sdxl-provider-qualification-v0.6.1.json",
                "docs/evidence/execution-evidence-v0.6.0.json",
                "docs/evidence/execution-evidence-v0.6.1.json",
                "docs/evidence/sdxl-smoke-phase-table.json",
                "docs/evidence/sdxl-identity-hard-gates.json",
                "docs/evidence/review-visuals-v0.6.0.json",
            }
        )
    elif active_visual_name.endswith("v0.6.0.json"):
        required_metadata.update(
            {
                "docs/evidence/review-visuals-v0.6.0.json",
                "REVIEW-v0.6.0.md",
                "docs/evidence/current-state.json",
                "docs/evidence/state-consistency.json",
                "docs/evidence/custom-node-audit-ipadapter-plus.json",
                "docs/evidence/sdxl-model-stack-qualification.json",
                "docs/evidence/sdxl-base-model-qualification.json",
                "docs/evidence/sdxl-openpose-controlnet-qualification.json",
                "docs/evidence/ipadapter-sdxl-model-qualification.json",
                "docs/evidence/clip-vision-qualification.json",
                "docs/evidence/runtime-doctor-v0.6.0.json",
                "docs/evidence/sdxl-provider-workflow-qualification.json",
                "docs/evidence/sdxl-provider-qualification.json",
                "docs/evidence/execution-evidence-v0.6.0.json",
                "docs/evidence/sdxl-identity-drift-contact.json",
            }
        )
    missing = sorted(required_metadata - names)
    if missing:
        raise ReviewArchiveError("archive metadata missing: " + ", ".join(missing))
    for name in sorted(names):
        _safe_archive_name(name)
        path = Path(name)
        if path.suffix.casefold() in FORBIDDEN_WEIGHT_SUFFIXES:
            raise ReviewArchiveError(f"forbidden weight/model artifact in archive: {name}")
        if not name.startswith("__REVIEW__/") and security_exclusion_reason(path):
            raise ReviewArchiveError(f"forbidden secret path in archive: {name}")
    if "docs/evidence/v054-lanes/" not in "\n".join(sorted(names)):
        raise ReviewArchiveError("canonical v0.5.4 lane directory is missing")

    visual_manifest = _read_json(archive, active_visual_name)
    expected_visual_schema = active_visual_name.split("review-visuals-v", 1)[1].removesuffix(".json")
    if visual_manifest.get("schema_version") != expected_visual_schema:
        raise ReviewArchiveError(f"active review visual manifest is not {expected_visual_schema}")
    visual_result = validate_review_visual_manifest(visual_manifest)
    if visual_result["status"] != "REVIEW_VISUAL_MANIFEST_PASSED":
        raise ReviewArchiveError("invalid review visual manifest: " + "; ".join(visual_result["failures"]))
    for item in visual_manifest.get("images", []):
        source_path = str(item.get("source_path", ""))
        if source_path not in names:
            raise ReviewArchiveError(f"required visual source omitted: {source_path}")
        copy_name = f"__REVIEW__/visual-evidence/{item['archive_name']}"
        if copy_name not in names:
            raise ReviewArchiveError(f"review visual copy missing: {copy_name}")
        source_bytes = archive.read(source_path)
        copy_bytes = archive.read(copy_name)
        if source_bytes != copy_bytes:
            raise ReviewArchiveError(f"review visual copy differs from canonical source: {source_path}")
        expected = str(item.get("sha256", ""))
        if expected and _canonical_visual_digest(source_path, source_bytes) != expected:
            raise ReviewArchiveError(f"review visual manifest hash mismatch: {source_path}")

    table = _read_json(archive, "docs/evidence/v054-pose-error-table.json")
    rows = table.get("rows") if isinstance(table.get("rows"), list) else []
    expected_outputs = {
        str(row.get("output_path")): str(row.get("output_sha256"))
        for row in rows
        if isinstance(row, dict) and row.get("output_path")
    }
    if set(expected_outputs) != set(CANONICAL_LANE_OUTPUTS):
        raise ReviewArchiveError("v0.5.4 error table does not enumerate exactly the nine canonical outputs")
    excluded_text = archive.read("__REVIEW__/excluded-files.txt").decode("utf-8", errors="replace")
    for relative in CANONICAL_LANE_OUTPUTS:
        if relative not in names:
            raise ReviewArchiveError(f"canonical lane output missing: {relative}")
        if relative in excluded_text:
            raise ReviewArchiveError(f"canonical lane output appears in excluded-files.txt: {relative}")
        data = archive.read(relative)
        _verify_png(data, relative)
        if _sha256(data) != expected_outputs[relative]:
            raise ReviewArchiveError(f"canonical lane output hash mismatch: {relative}")

    manifest = _read_json(archive, "__REVIEW__/manifest.json")
    head_commit = str(manifest.get("head_commit", ""))
    recorded_head = archive.read("__REVIEW__/git-head.txt").decode("utf-8", errors="replace").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", head_commit) or recorded_head != head_commit:
        raise ReviewArchiveError("review manifest head_commit does not match __REVIEW__/git-head.txt")
    if manifest.get("review_script_version") != "1.8.0":
        raise ReviewArchiveError("review manifest was not produced by review script 1.8.0")
    included_count = sum(1 for name in names if not name.startswith("__REVIEW__/"))
    if manifest.get("total_files_included") != included_count:
        raise ReviewArchiveError("review manifest file count does not match archive")
    return {
        "head_commit": head_commit,
        "canonical_output_count": len(CANONICAL_LANE_OUTPUTS),
        "visual_manifest": visual_result,
        "included_file_count": included_count,
    }


def _run(command: list[str], cwd: Path, timeout: int) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False, timeout=timeout)
    output = completed.stdout + completed.stderr
    return {
        "command": command,
        "exit_code": completed.returncode,
        "output_tail": output[-4000:],
    }


def _self_validate_extracted(extraction: Path) -> dict[str, Any]:
    compile_result = _run([sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"], extraction, 180)
    unit_result = _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], extraction, 480)
    validation_result = _run([sys.executable, "scripts/validation/run_validation.py"], extraction, 480)
    unit_output = unit_result["output_tail"]
    validation_output = validation_result["output_tail"]
    test_match = re.findall(r"Ran (\d+) tests", unit_output)
    summary_match = re.findall(r"SUMMARY checks=(\d+) passed=(\d+) failed=(\d+)", validation_output)
    exact_test_count = int(test_match[-1]) if test_match else None
    summary = {
        "checks": int(summary_match[-1][0]),
        "passed": int(summary_match[-1][1]),
        "failed": int(summary_match[-1][2]),
    } if summary_match else None
    if compile_result["exit_code"] != 0:
        raise ReviewArchiveError("extracted compileall failed")
    if unit_result["exit_code"] != 0 or exact_test_count is None or exact_test_count < 129:
        raise ReviewArchiveError(f"extracted unittest failed or count is below 129: {exact_test_count}")
    if validation_result["exit_code"] != 0 or not summary or summary["failed"] != 0:
        raise ReviewArchiveError(f"extracted repository validation failed: {summary}")
    return {
        "compileall": compile_result,
        "unit_tests": {**unit_result, "exact_test_count": exact_test_count},
        "repository_validation": {**validation_result, "summary": summary},
    }


def verify_archive(archive_path: Path | str) -> dict[str, Any]:
    """Verify archive structure, hashes and a clean extracted self-validation."""

    path = Path(archive_path).resolve()
    if not path.is_file():
        raise ReviewArchiveError(f"review archive does not exist: {path}")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            bad_name = archive.testzip()
            if bad_name is not None:
                raise ReviewArchiveError(f"ZIP CRC test failed: {bad_name}")
            names = set(archive.namelist())
            content = _validate_snapshot_contents(archive, names)
            with tempfile.TemporaryDirectory(prefix="ugas-review-archive-") as directory:
                extraction = Path(directory) / "extracted"
                extraction.mkdir()
                archive.extractall(extraction)
                if (extraction / ".git").exists():
                    raise ReviewArchiveError("extracted review archive unexpectedly contains .git")
                execution = _self_validate_extracted(extraction)
    except zipfile.BadZipFile as exc:
        raise ReviewArchiveError(f"invalid ZIP: {exc}") from exc
    return {
        "status": "REVIEW_ARCHIVE_VERIFIED",
        "archive": str(path),
        **content,
        "extracted_self_validation": execution,
    }


def main(argv: list[str] | None = None) -> int:
    parser = __import__("argparse").ArgumentParser(description="Verify a UGAS review ZIP and self-test its clean extraction")
    parser.add_argument("archive", type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_archive(args.archive)
    except (OSError, ReviewArchiveError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "REVIEW_ARCHIVE_INVALID", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
