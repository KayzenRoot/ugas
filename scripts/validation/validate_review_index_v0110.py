"""Validate the v0.11.0 review index and hash-bound current visual/evidence paths."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
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


def validate(path: Path = ROOT / "docs/evidence/review-index-v0.11.0.json") -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    failures: list[str] = []
    if "head_commit" in value:
        failures.append("v2_must_not_use_top_level_head_commit")
    if value.get("schema_version") != "0.11.0" or value.get("version") != "0.11.0":
        failures.append("schema_version_or_version_invalid")
    subject = value.get("review_subject", {})
    if subject.get("baseline_commit") != BASELINE or subject.get("implementation_base_commit") != BASELINE or subject.get("repository_ref") != "https://github.com/csn1985-ship-it/ugas.git":
        failures.append("review_subject_commit_binding_invalid")
    publication = value.get("publication", {})
    build_head = str(publication.get("index_build_git_head", ""))
    has_git = (ROOT / ".git").exists()
    final_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip() if has_git else build_head
    if len(build_head) != 40:
        failures.append("index_build_git_head_invalid")
    elif has_git and subprocess.run(["git", "merge-base", "--is-ancestor", build_head, final_head], cwd=ROOT, check=False).returncode != 0:
        failures.append("index_build_git_head_must_be_ancestor_of_final_head")
    if publication.get("final_head_must_be_resolved_by_external_reviewer") is not True or publication.get("executor_cannot_self_assert_final_head") is not True:
        failures.append("external_final_head_resolution_required")
    artifacts = value.get("artifact_set", {}).get("artifacts", []) if isinstance(value.get("artifact_set"), dict) else []
    listed: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            failures.append("artifact_item_invalid")
            continue
        relative = str(item.get("path"))
        listed.add(relative)
        local = ROOT / relative
        if not local.is_file():
            failures.append(f"artifact_missing:{relative}")
        elif has_git and digest(local) != item.get("sha256"):
            failures.append(f"artifact_hash_mismatch:{relative}")
    artifact_set = value.get("artifact_set", {})
    expected_hash = hashlib.sha256(canonical(artifacts).encode("utf-8")).hexdigest()
    if artifact_set.get("manifest_algorithm") != "sha256-canonical-path-list-v1" or artifact_set.get("artifact_set_sha256") != expected_hash:
        failures.append("artifact_set_hash_invalid")
    visual = json.loads((ROOT / "docs/evidence/animation-runtime-v0110/attack-front-v2/attack-v2-visual-manifest.json").read_text(encoding="utf-8"))
    failures.extend(f"visual_not_in_artifact_set:{item.get('source_path')}" for item in visual.get("images", []) if item.get("source_path") not in listed)
    failures.extend(f"visual_hash_mismatch:{item.get('source_path')}" for item in visual.get("images", []) if (ROOT / str(item.get("source_path"))).is_file() and digest(ROOT / str(item.get("source_path"))) != item.get("sha256"))
    required = ["generic-motion-curve-contract-v0110.json", "historical-replay-v0110.json", "execution-evidence-v0.11.0.json", "compiled-manifest.json", "qa-result.json", "package-manifest.json", "metadata.json", "attack-v2-body-mechanics-qa.json", "attack-v2-temporal-qa.json", "attack-v2-weapon-arc-qa.json", "attack-v2-foot-ground-qa.json", "attack-v2-event-marker-qa.json", "attack-v2-visual-manifest.json"]
    failures.extend(f"required_evidence_not_in_artifact_set:{name}" for name in required if f"docs/evidence/animation-runtime-v0110/{name}" not in listed and f"docs/evidence/animation-runtime-v0110/attack-front-v2/{name}" not in listed)
    if any(str(item.get("path", "")).casefold().endswith((".zip", ".safetensors", ".ckpt", ".gguf", ".onnx")) for item in artifacts if isinstance(item, dict)):
        failures.append("forbidden_binary_artifact_in_index")
    if value.get("external_visual_review", {}).get("attack_front_v2_approval") != "REQUIRED" or value.get("production_routing") != "BLOCKED":
        failures.append("external_or_production_boundary_invalid")
    return {"status": "REVIEW_INDEX_V2_PASSED" if not failures else "REVIEW_INDEX_V2_FAILED", "failures": failures, "checked": {"artifact_count": len(artifacts), "visual_count": artifact_set.get("visual_count"), "index_build_git_head": build_head, "final_head": final_head, "ancestor_semantics": has_git}}


if __name__ == "__main__":
    result = validate(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/evidence/review-index-v0.11.0.json")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "REVIEW_INDEX_V2_PASSED" else 1)
