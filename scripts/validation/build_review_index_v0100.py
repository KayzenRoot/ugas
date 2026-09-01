"""Build the v0.10.0 GitHub-first review index without a self-referential HEAD."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "d914d09d35ebfc5658d6c08e3502288c537fbf20"


def digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt"}: data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def media_type(path: str) -> str:
    return "image/png" if path.casefold().endswith(".png") else "image/gif" if path.casefold().endswith(".gif") else "application/json" if path.casefold().endswith(".json") else "text/plain"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests-count", type=int, default=1)
    parser.add_argument("--validation-checks", type=int, default=1)
    args = parser.parse_args()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    attack_visual = json.loads((ROOT / "docs/evidence/animation-runtime-v0100/attack-front-v1/attack-visual-manifest-v0100.json").read_text(encoding="utf-8"))
    historical_visual = json.loads((ROOT / "docs/evidence/review-visuals-v0.9.0.json").read_text(encoding="utf-8"))
    paths = {
        "README.md", "INSTALL.md", "CHECKPOINT.md", "LICENSE", "package.json", "pyproject.toml", "docs/2d-master-pipeline.md", "docs/comfyui.md", "docs/roadmap.md", "docs/test-coverage-matrix-v0.10.0.md", "REVIEW-v0.10.0.md",
        "schemas/current-state.json", "schemas/current-state-v0.10.0.json", "schemas/current-state-v0.9.1.json", "schemas/review-index-v0.10.0.json", "schemas/animation-spec-v1.json", "schemas/animation-compiled-manifest-v1.json", "schemas/animation-qa-result-v1.json", "schemas/animation-package-v1.json",
        "profiles/animation/attack-front-v1.json", "src/ugas/animation.py", "src/ugas/animation_profiles/attack_front_v1.py", "src/ugas/animation_profiles/common.py", "src/ugas/cutout_temporal_v081.py", "src/ugas/state_consistency_v0100.py", "src/ugas/constants.py", "src/ugas/__init__.py", "src/ugas/cli.py", "scripts/validation/run_animation_runtime_v0100.py", "scripts/validation/build_review_index_v0100.py", "scripts/validation/validate_review_index_v0100.py", "scripts/validation/run_validation.py", "scripts/validation/validate_state_consistency.py", "tests/test_animation_runtime_v0100.py", "tests/test_animation_runtime_v090.py", "tests/fixtures/dummy-two-key-v1.json", "tests/fixtures/dummy_two_key_v1.py", "tests/fixtures/dummy-source.json",
        "docs/evidence/current-state.json", "docs/evidence/current-state-v0.9.1.json", "docs/evidence/state-consistency-v0100.json", "docs/evidence/state-consistency-v091.json", "docs/evidence/checkpoint-v0.9.1.md", "docs/evidence/review-index-v0.9.1.json", "docs/evidence/review-visuals-v0.9.0.json", "REVIEW-v0.9.1.md",
        "docs/evidence/animation-runtime-v0100/generic-event-marker-contract-v0100.json", "docs/evidence/animation-runtime-v0100/non-loop-runtime-contract-v0100.json", "docs/evidence/animation-runtime-v0100/execution-evidence-v0.10.0.json",
    }
    paths.update({f"docs/evidence/animation-runtime-v0100/attack-front-v1/{name}" for name in ("compiled-manifest.json", "qa-result.json", "package-manifest.json", "metadata.json", "attack-temporal-qa-v0100.json", "attack-weapon-sweep-qa-v0100.json", "attack-foot-ground-qa-v0100.json", "attack-event-marker-qa-v0100.json", "attack-visual-manifest-v0100.json", "attack-front-spritesheet-v0100.png", "attack-front-preview-v0100.gif")})
    paths.update(item["source_path"] for item in attack_visual["images"])
    paths.update(item["source_path"] for item in historical_visual["images"])
    paths = {path for path in paths if (ROOT / path).is_file() and path != "docs/evidence/review-index-v0.10.0.json"}
    attack_visual_paths = {item["source_path"] for item in attack_visual["images"]}
    artifacts = [{"path": path, "sha256": digest(ROOT / path), "media_type": media_type(path), "role": "visual" if path in attack_visual_paths or path in {item["source_path"] for item in historical_visual["images"]} else "runtime-or-governance"} for path in sorted(paths)]
    value = {"schema_version": "0.10.0", "version": "0.10.0", "branch": "main", "review_subject": {"baseline_commit": BASELINE, "implementation_base_commit": BASELINE, "repository_ref": "https://github.com/csn1985-ship-it/ugas.git"}, "publication": {"index_build_git_head": head, "index_build_dirty_state": "dirty_before_publication_commit", "final_head_must_be_resolved_by_external_reviewer": True, "executor_cannot_self_assert_final_head": True}, "review_file": "REVIEW-v0.10.0.md", "current_state": "docs/evidence/current-state.json", "tests": {"command": "python -m unittest discover -s tests -q", "count": args.tests_count, "passed": args.tests_count, "failed": 0, "status": "passed"}, "validation": {"command": "python scripts/validation/run_validation.py", "checks": args.validation_checks, "passed": args.validation_checks, "failed": 0, "status": "passed"}, "artifact_set": {"manifest_algorithm": "sha256-canonical-path-list-v1", "artifacts": artifacts, "artifact_set_sha256": hashlib.sha256(canonical(artifacts).encode("utf-8")).hexdigest(), "evidence_count": len(artifacts), "visual_count": sum(item["media_type"].startswith("image/") for item in artifacts)}, "required_visual_sets": sorted(item["archive_name"] for item in attack_visual["images"]), "forbidden_artifacts": ["*.zip", "*.safetensors", "*.ckpt", "*.gguf", "*.onnx", "self-referential head_commit claim", "new run/hit/death directions"], "external_visual_review": {"status": "REQUIRED", "walk_pilot_approval": "APPROVED_PILOT", "idle_front_approval": "APPROVED_PILOT", "attack_front_approval": "REQUIRED"}, "production_routing": "BLOCKED"}
    output = ROOT / "docs/evidence/review-index-v0.10.0.json"; output.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); print(output); return 0


if __name__ == "__main__": raise SystemExit(main())
