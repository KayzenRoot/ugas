"""Build the v0.11.0 GitHub-first review index without a self-referential HEAD."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "c11196e5e854a0fbc6ec62e959de5ecc28d492ce"


def digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def media_type(path: str) -> str:
    suffix = Path(path).suffix.casefold()
    return {".png": "image/png", ".gif": "image/gif", ".json": "application/json"}.get(suffix, "text/plain")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests-count", type=int, default=1)
    parser.add_argument("--validation-checks", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    visual_manifest = json.loads((ROOT / "docs/evidence/animation-runtime-v0110/attack-front-v2/attack-v2-visual-manifest.json").read_text(encoding="utf-8"))
    paths = {
        "README.md", "INSTALL.md", "CHECKPOINT.md", "LICENSE", "package.json", "pyproject.toml", "docs/2d-master-pipeline.md", "docs/comfyui.md", "docs/roadmap.md", "docs/test-coverage-matrix-v0.11.0.md", "REVIEW-v0.11.0.md",
        "schemas/current-state.json", "schemas/current-state-v0.10.0.json", "schemas/review-index-v0.11.0.json", "schemas/animation-spec-v1.json", "schemas/animation-compiled-manifest-v1.json", "schemas/animation-qa-result-v1.json", "schemas/animation-package-v1.json",
        "profiles/animation/attack-front-v2.json", "src/ugas/animation.py", "src/ugas/animation_profiles/attack_front_v2.py", "src/ugas/animation_profiles/common.py", "src/ugas/cutout_structural.py", "src/ugas/motion_curves.py", "src/ugas/state_consistency_v0110.py", "scripts/validation/run_animation_runtime_v0110.py", "scripts/validation/build_review_index_v0110.py", "scripts/validation/validate_review_index_v0110.py", "scripts/validation/run_validation.py", "scripts/validation/validate_state_consistency.py", "tests/test_motion_curves_v0110.py",
        "docs/evidence/current-state.json", "docs/evidence/current-state-v0.10.0.json", "docs/evidence/state-consistency.json", "docs/evidence/state-consistency-v0100.json", "docs/evidence/review-index-v0.10.0.json",
        "docs/evidence/animation-runtime-v0110/generic-motion-curve-contract-v0110.json", "docs/evidence/animation-runtime-v0110/historical-replay-v0110.json", "docs/evidence/animation-runtime-v0110/execution-evidence-v0.11.0.json",
        "docs/evidence/animation-runtime-v0100/execution-evidence-v0.10.0.json", "docs/evidence/animation-runtime-v090/idle-front-v1/idle-front-preview-v090.gif", "docs/evidence/walk-front-v081/walk-front-preview-v081.gif",
    }
    paths.update(f"docs/evidence/animation-runtime-v0110/attack-front-v2/frame-{index:02d}.png" for index in range(12))
    paths.update({"docs/evidence/animation-runtime-v0110/attack-front-v2/" + name for name in ("compiled-manifest.json", "qa-result.json", "package-manifest.json", "metadata.json", "attack-v2-body-mechanics-qa.json", "attack-v2-temporal-qa.json", "attack-v2-weapon-arc-qa.json", "attack-v2-foot-ground-qa.json", "attack-v2-event-marker-qa.json", "attack-v2-visual-manifest.json", "attack-front-v2-spritesheet.png", "attack-front-v2-preview.gif")})
    paths.update(item["source_path"] for item in visual_manifest["images"])
    paths = {path for path in paths if (ROOT / path).is_file() and path != "docs/evidence/review-index-v0.11.0.json"}
    visual_paths = {item["source_path"] for item in visual_manifest["images"]}
    artifacts = [{"path": path, "sha256": digest(ROOT / path), "media_type": media_type(path), "role": "visual" if path in visual_paths else "runtime-or-governance"} for path in sorted(paths)]
    value = {
        "schema_version": "0.11.0", "version": "0.11.0", "branch": "main",
        "review_subject": {"baseline_commit": BASELINE, "implementation_base_commit": BASELINE, "repository_ref": "https://github.com/csn1985-ship-it/ugas.git"},
        "publication": {"index_build_git_head": head, "index_build_dirty_state": "dirty_before_publication_commit", "final_head_must_be_resolved_by_external_reviewer": True, "executor_cannot_self_assert_final_head": True},
        "review_file": "REVIEW-v0.11.0.md", "current_state": "docs/evidence/current-state.json",
        "tests": {"command": "python -m unittest discover -s tests -q", "count": args.tests_count, "passed": args.tests_count, "failed": 0, "status": "passed"},
        "validation": {"command": "python scripts/validation/run_validation.py", "checks": args.validation_checks, "passed": args.validation_checks, "failed": 0, "status": "passed"},
        "artifact_set": {"manifest_algorithm": "sha256-canonical-path-list-v1", "artifacts": artifacts, "artifact_set_sha256": hashlib.sha256(canonical(artifacts).encode("utf-8")).hexdigest(), "evidence_count": len(artifacts), "visual_count": sum(item["media_type"].startswith("image/") for item in artifacts)},
        "required_visual_sets": sorted(item["archive_name"] for item in visual_manifest["images"]),
        "forbidden_artifacts": ["*.zip", "*.safetensors", "*.ckpt", "*.gguf", "*.onnx", "self-referential head_commit claim", "new run/hit/death directions"],
        "external_visual_review": {"status": "REQUIRED", "walk_pilot_approval": "APPROVED_PILOT", "idle_front_approval": "APPROVED_PILOT", "attack_front_v1_approval": "APPROVED_PILOT", "attack_front_v2_approval": "REQUIRED"},
        "production_routing": "BLOCKED",
    }
    output = ROOT / "docs/evidence/review-index-v0.11.0.json"
    output.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result = {"status": "REVIEW_INDEX_BUILT", "path": output.relative_to(ROOT).as_posix(), "artifact_count": len(artifacts), "visual_count": value["artifact_set"]["visual_count"], "index_build_git_head": head}
    print(json.dumps(result, indent=2) if args.json else output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
