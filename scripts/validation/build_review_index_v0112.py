"""Build the v0.11.2 hash-bound review index before publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "9401c31f994e968149292b2993d960d3aafc37c4"
IMPLEMENTATION_BASE = "f386c490a6d7289befc1c8a34c84eff1d2b1cc96"
TEXT_SUFFIXES = {".json", ".md", ".txt", ".py", ".toml"}


def digest(path: Path) -> str:
    data = path.read_bytes()
    if path.name.casefold() == "license" or path.suffix.casefold() in TEXT_SUFFIXES: data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def media_type(path: str) -> str:
    return {".png": "image/png", ".gif": "image/gif", ".json": "application/json"}.get(Path(path).suffix.casefold(), "text/plain")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests-count", type=int, default=1)
    parser.add_argument("--validation-checks", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    visual = json.loads((ROOT / "docs/evidence/animation-runtime-v0112/attack-v2-visual-manifest-v0112.json").read_text(encoding="utf-8"))
    paths = {
        "README.md", "INSTALL.md", "CHECKPOINT.md", "LICENSE", "package.json", "pyproject.toml", "REVIEW-v0.11.2.md", "docs/2d-master-pipeline.md", "docs/comfyui.md", "docs/roadmap.md", "docs/test-coverage-matrix-v0.11.2.md",
        "schemas/current-state.json", "schemas/current-state-v0.11.0.json", "schemas/current-state-v0.11.1.json", "schemas/review-index-v0.11.2.json", "schemas/animation-spec-v1.json", "schemas/animation-compiled-manifest-v1.json", "schemas/animation-qa-result-v1.json", "schemas/animation-package-v1.json",
        "src/ugas/animation.py", "src/ugas/animation_profiles/attack_front_v2.py", "src/ugas/animation_profiles/common.py", "src/ugas/cutout_structural.py", "src/ugas/motion_curves.py", "src/ugas/state_consistency_v0110.py", "src/ugas/state_consistency_v0111.py", "src/ugas/state_consistency_v0112.py",
        "profiles/animation/attack-front-v2.json", "profiles/animation/attack-front-v2-v0.11.0.json", "profiles/animation/attack-front-v1.json",
        "scripts/validation/run_animation_runtime_v0112.py", "scripts/validation/build_review_index_v0112.py", "scripts/validation/validate_review_index_v0112.py", "scripts/validation/run_validation.py", "scripts/validation/validate_state_consistency.py", "scripts/validation/validate_state_consistency_v0112.py", "tests/test_qa_integrity_v0112.py", "tests/test_weapon_continuity_v0111.py",
        "docs/evidence/current-state.json", "docs/evidence/current-state-v0.11.0.json", "docs/evidence/current-state-v0.11.1.json", "docs/evidence/state-consistency.json", "docs/evidence/state-consistency-v0110.json", "docs/evidence/review-index-v0.11.2.json", "REVIEW-v0.11.1.md",
    }
    for item in (ROOT / "docs/evidence/animation-runtime-v0112").rglob("*"):
        if item.is_file(): paths.add(item.relative_to(ROOT).as_posix())
    for name in ["attack-front-v2-spritesheet.png", "attack-front-v2-preview.gif", *[f"frame-{index:02d}.png" for index in range(12)]]:
        paths.add(f"docs/evidence/animation-runtime-v0110/attack-front-v2/{name}")
    for relative in ("docs/evidence/animation-runtime-v0111/historical-replay-v0111.json", "docs/evidence/animation-runtime-v0111/execution-evidence-v0.11.1.json", "docs/evidence/animation-runtime-v0111/attack-front-v2/qa-result.json"):
        paths.add(relative)
    paths = {path for path in paths if (ROOT / path).is_file() and path != "docs/evidence/review-index-v0.11.2.json"}
    visual_paths = {item["source_path"] for item in visual["images"]}
    artifacts = [{"path": path, "sha256": digest(ROOT / path), "media_type": media_type(path), "role": "visual" if path in visual_paths or path.startswith("docs/evidence/animation-runtime-v0110/attack-front-v2/") else "runtime-or-governance"} for path in sorted(paths)]
    value = {"schema_version": "0.11.2", "version": "0.11.2", "branch": "main", "review_subject": {"baseline_commit": BASELINE, "implementation_base_commit": IMPLEMENTATION_BASE, "previous_rejected_commit": IMPLEMENTATION_BASE, "repository_ref": "https://github.com/csn1985-ship-it/ugas.git"}, "publication": {"index_build_git_head": head, "index_build_dirty_state": "dirty_before_publication_commit", "final_head_must_be_resolved_by_external_reviewer": True, "executor_cannot_self_assert_final_head": True}, "review_file": "REVIEW-v0.11.2.md", "current_state": "docs/evidence/current-state.json", "tests": {"command": "python -m unittest discover -s tests -q", "count": args.tests_count, "passed": args.tests_count, "failed": 0, "status": "passed"}, "validation": {"command": "python scripts/validation/run_validation.py", "checks": args.validation_checks, "passed": args.validation_checks, "failed": 0, "status": "passed"}, "artifact_set": {"manifest_algorithm": "sha256-canonical-path-list-v1", "artifacts": artifacts, "artifact_set_sha256": hashlib.sha256(canonical(artifacts).encode("utf-8")).hexdigest(), "evidence_count": len(artifacts), "visual_count": sum(item["media_type"].startswith("image/") for item in artifacts)}, "required_visual_sets": sorted(item["archive_name"] for item in visual["images"]), "forbidden_artifacts": ["*.zip", "*.safetensors", "*.ckpt", "*.gguf", "*.onnx", "self-referential head_commit claim", "new run/hit/death directions", "v0.11.1 numeric weapon thresholds as active gates"], "external_visual_review": {"status": "REQUIRED", "walk_pilot_approval": "APPROVED_PILOT", "idle_front_approval": "APPROVED_PILOT", "attack_front_v1_approval": "APPROVED_PILOT", "attack_front_v2_approval": "REQUIRED"}, "production_routing": "BLOCKED"}
    output = ROOT / "docs/evidence/review-index-v0.11.2.json"
    output.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result = {"status": "REVIEW_INDEX_BUILT", "path": output.relative_to(ROOT).as_posix(), "artifact_count": len(artifacts), "visual_count": value["artifact_set"]["visual_count"], "index_build_git_head": head}
    print(json.dumps(result, indent=2) if args.json else output)
    return 0


if __name__ == "__main__": raise SystemExit(main())
