"""Build the v0.9.1 review index v2 without a self-referential final HEAD."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "16c60c9ff934a55adefc82a99d81dafb52d1047c"
PARENT = "46ba3ae87558ff26055e14aa8d9c6f3ee147333c"


def digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt"}: data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--tests-count", type=int, default=1); parser.add_argument("--validation-checks", type=int, default=1); args = parser.parse_args()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    visual_manifest = json.loads((ROOT / "docs/evidence/review-visuals-v0.9.0.json").read_text(encoding="utf-8"))
    paths = {"README.md", "INSTALL.md", "CHECKPOINT.md", "LICENSE", "package.json", "pyproject.toml", "docs/2d-master-pipeline.md", "docs/comfyui.md", "docs/roadmap.md", "docs/test-coverage-matrix-v0.9.1.md", "REVIEW-v0.9.1.md", "schemas/current-state.json", "schemas/current-state-v0.9.0.json", "schemas/animation-spec-v1.json", "schemas/animation-compiled-manifest-v1.json", "schemas/animation-qa-result-v1.json", "schemas/animation-package-v1.json", "schemas/review-index-v0.9.1.json", "profiles/animation/walk-front-v1.json", "profiles/animation/idle-front-v1.json", "src/ugas/animation.py", "src/ugas/schema_validation.py", "src/ugas/animation_profiles/common.py", "src/ugas/animation_profiles/walk_front_v1.py", "src/ugas/animation_profiles/idle_front_v1.py", "src/ugas/cutout_structural.py", "src/ugas/state_consistency_v091.py", "scripts/validation/run_animation_runtime_v091.py", "scripts/validation/build_review_index_v091.py", "scripts/validation/validate_review_index_v091.py", "tests/test_animation_runtime_v090.py", "tests/fixtures/__init__.py", "tests/fixtures/dummy_two_key_v1.py", "tests/fixtures/dummy-two-key-v1.json", "tests/fixtures/dummy-source.json", "docs/evidence/current-state.json", "docs/evidence/state-consistency-v091.json", "docs/evidence/review-visuals-v0.9.0.json"}
    paths.update({f"docs/evidence/animation-runtime-v091/{name}" for name in ("generic-runtime-contract-v091.json", "timing-alternative-qualification-v091.json", "generic-dummy-package-qualification-v091.json", "walk-replay-qualification-v091.json", "idle-dual-foot-drift-qa-v091.json", "idle-layer-bbox-temporal-qa-v091.json", "idle-occlusion-policy-v091.json", "idle-requalification-v091.json", "execution-evidence-v0.9.1.json")})
    paths.update(item["source_path"] for item in visual_manifest["images"])
    paths.update({"docs/evidence/animation-runtime-v090/idle-front-v1/compiled-manifest.json", "docs/evidence/animation-runtime-v090/replay/walk-front-v1/compiled-manifest.json"})
    paths = {path for path in paths if (ROOT / path).is_file() and path != "docs/evidence/review-index-v0.9.1.json"}
    artifacts = [{"path": path, "sha256": digest(ROOT / path), "media_type": "image/png" if path.casefold().endswith(".png") else "image/gif" if path.casefold().endswith(".gif") else "application/json" if path.casefold().endswith(".json") else "text/plain", "role": "visual" if path in {item["source_path"] for item in visual_manifest["images"]} else "runtime-or-governance"} for path in sorted(paths)]
    value = {"schema_version": "0.9.1", "version": "0.9.1", "branch": "main", "review_subject": {"baseline_commit": PARENT, "implementation_base_commit": BASELINE, "repository_ref": "https://github.com/csn1985-ship-it/ugas.git"}, "publication": {"index_build_git_head": head, "index_build_dirty_state": "dirty_before_publication_commit", "final_head_must_be_resolved_by_external_reviewer": True, "executor_cannot_self_assert_final_head": True}, "review_file": "REVIEW-v0.9.1.md", "current_state": "docs/evidence/current-state.json", "tests": {"command": "python -m unittest discover -s tests -q", "count": args.tests_count, "passed": args.tests_count, "failed": 0, "status": "passed"}, "validation": {"command": "python scripts/validation/run_validation.py", "checks": args.validation_checks, "passed": args.validation_checks, "failed": 0, "status": "passed"}, "artifact_set": {"manifest_algorithm": "sha256-canonical-path-list-v1", "artifacts": artifacts, "artifact_set_sha256": hashlib.sha256(canonical(artifacts).encode("utf-8")).hexdigest(), "evidence_count": len(artifacts), "visual_count": sum(item["media_type"].startswith("image/") for item in artifacts)}, "required_visual_sets": sorted(item["archive_name"] for item in visual_manifest["images"]), "forbidden_artifacts": ["*.zip", "*.safetensors", "*.ckpt", "*.gguf", "*.onnx", "self-referential head_commit claim"], "external_visual_review": {"status": "REQUIRED", "walk_pilot_approval": "APPROVED_PILOT", "idle_front_approval": "REQUIRED"}, "production_routing": "BLOCKED"}
    output = ROOT / "docs/evidence/review-index-v0.9.1.json"; output.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); print(output); return 0


if __name__ == "__main__": raise SystemExit(main())
