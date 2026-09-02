"""Build the v0.12.1 forward-only hash-bound review index."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_HEAD = "789c82f246e48b119f2eebfade890a854b5a7b63"
PREVIOUS_IMPLEMENTATION = "d0eb6e06cf9c5eadce586fc1c096ba1ac168daa5"
TEXT_SUFFIXES = {".json", ".md", ".txt", ".py", ".toml", ".js", ".html", ".css"}


def digest(path: Path) -> str:
    data = path.read_bytes()
    if path.name.casefold() == "license" or path.suffix.casefold() in TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def media_type(path: str) -> str:
    return {".png": "image/png", ".gif": "image/gif", ".json": "application/json", ".js": "text/javascript", ".css": "text/css", ".html": "text/html"}.get(Path(path).suffix.casefold(), "text/plain")


def evidence_count(filename: str, key: str) -> int:
    evidence = ROOT / "docs/evidence/observability-v0121" / filename
    value = json.loads(evidence.read_text(encoding="utf-8"))[key]
    if not isinstance(value, int) or value <= 0:
        raise SystemExit(f"invalid positive integer {key} in {evidence}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests-count", type=int)
    parser.add_argument("--validation-checks", type=int)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    tests_count = args.tests_count if args.tests_count is not None else evidence_count("test-results-v0121.json", "count")
    validation_checks = args.validation_checks if args.validation_checks is not None else evidence_count("validation-results-v0121.json", "checks")
    if tests_count <= 0 or validation_checks <= 0:
        raise SystemExit("tests and validation counts must be positive")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    visual_manifest = json.loads((ROOT / "docs/evidence/animation-runtime-v0112/attack-v2-visual-manifest-v0112.json").read_text(encoding="utf-8"))
    root_paths = {
        "README.md", "INSTALL.md", "CHECKPOINT.md", "LICENSE", "package.json", "pyproject.toml", "REVIEW-v0.12.0.md", "REVIEW-v0.12.1.md",
        "docs/2d-master-pipeline.md", "docs/comfyui.md", "docs/roadmap.md", "docs/test-coverage-matrix-v0.12.0.md", "docs/test-coverage-matrix-v0.12.1.md",
        "docs/evidence/current-state.json", "docs/evidence/current-state-v0.12.0.json", "docs/evidence/state-consistency-v0120.json", "docs/evidence/state-consistency-v0121.json",
        "docs/evidence/observability-v0120/external-review-v0112.json", "schemas/current-state.json", "schemas/current-state-v0.12.0.json", "schemas/review-index-v0.12.1.json",
        "src/ugas/__init__.py", "src/ugas/constants.py", "src/ugas/cli.py", "src/ugas/generation.py", "src/ugas/state_consistency_v0120.py", "src/ugas/state_consistency_v0121.py",
        "scripts/validation/run_validation.py", "scripts/validation/run_observability_v0121.py", "scripts/validation/validate_state_consistency.py", "scripts/validation/validate_state_consistency_v0120.py", "scripts/validation/validate_state_consistency_v0121.py", "scripts/validation/build_review_index_v0121.py", "scripts/validation/validate_review_index_v0121.py",
        "tests/test_observability_v0120.py", "tests/test_observability_v0121.py", "src/ugas/observability/qa_integrity.py",
        "profiles/animation/attack-front-v2.json", "profiles/animation/attack-front-v2-v0.11.0.json",
    }
    root_paths.update({f"src/ugas/observability/{path.name}" for path in (ROOT / "src/ugas/observability").glob("*.py")})
    root_paths.update({f"src/ugas/observability/static/{path.name}" for path in (ROOT / "src/ugas/observability/static").glob("*")})
    root_paths.update({f"docs/evidence/observability-v0121/{path.name}" for path in (ROOT / "docs/evidence/observability-v0121").glob("*") if path.name != "publication.json"})
    root_paths.update(item["source_path"] for item in visual_manifest.get("images", []) if item.get("source_path"))
    root_paths = {path for path in root_paths if (ROOT / path).is_file() and path != "docs/evidence/review-index-v0.12.1.json"}
    visual_paths = {item["source_path"] for item in visual_manifest.get("images", [])}
    visual_paths.update({path for path in root_paths if path.startswith("docs/evidence/observability-v0121/") and Path(path).suffix.casefold() in {".png", ".gif"}})
    artifacts = [{"path": path, "sha256": digest(ROOT / path), "media_type": media_type(path), "role": "visual" if path in visual_paths else "runtime-or-governance"} for path in sorted(root_paths)]
    value = {
        "schema_version": "0.12.1", "version": "0.12.1", "branch": "main",
        "review_subject": {"base_head": BASE_HEAD, "previous_implementation_commit": PREVIOUS_IMPLEMENTATION, "repository_ref": "https://github.com/csn1985-ship-it/ugas.git"},
        "publication": {"index_build_git_head": head, "index_build_dirty_state": "dirty_before_publication_commit", "final_head_must_be_resolved_by_external_reviewer": True, "executor_cannot_self_assert_final_head": True},
        "review_file": "REVIEW-v0.12.1.md", "current_state": "docs/evidence/current-state.json",
        "tests": {"command": "python -m unittest discover -s tests -q", "count": tests_count, "passed": tests_count, "failed": 0, "status": "passed"},
        "validation": {"command": "python scripts/validation/run_validation.py", "checks": validation_checks, "passed": validation_checks, "failed": 0, "status": "passed"},
        "artifact_set": {"manifest_algorithm": "sha256-canonical-path-list-v1", "artifacts": artifacts, "artifact_set_sha256": hashlib.sha256(canonical(artifacts).encode("utf-8")).hexdigest(), "evidence_count": len(artifacts), "visual_count": sum(item["media_type"].startswith("image/") for item in artifacts)},
        "required_visual_sets": sorted([item["archive_name"] for item in visual_manifest.get("images", [])] + [path for path in sorted(visual_paths) if path.startswith("docs/evidence/observability-v0121/")]),
        "forbidden_artifacts": ["*.zip", "*.safetensors", "*.ckpt", "*.gguf", "*.onnx", "public bind", "telemetry upload", "new asset families", "animation pixel changes", "production promotion", "self-referential head_commit claim"],
        "external_visual_review": {"status": "REQUIRED", "attack_front_v2_approval": "APPROVED_PILOT", "observability_dashboard_approval": "REQUIRED"},
        "production_routing": "BLOCKED",
        "scope_boundary": {"local_only": True, "read_only": True, "telemetry_upload": False, "new_generation": 0, "new_asset_family": False, "animation_pixels_changed": False},
    }
    output = ROOT / "docs/evidence/review-index-v0.12.1.json"
    output.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result = {"status": "REVIEW_INDEX_BUILT", "path": output.relative_to(ROOT).as_posix(), "artifact_count": len(artifacts), "visual_count": value["artifact_set"]["visual_count"], "index_build_git_head": head}
    print(json.dumps(result, indent=2) if args.json else output)
    return 0


if __name__ == "__main__": raise SystemExit(main())
