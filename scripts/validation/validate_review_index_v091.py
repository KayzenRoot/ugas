"""Validate the active v0.9.1 review index v2 artifact set."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt"}: data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def validate(path: Path = ROOT / "docs/evidence/review-index-v0.9.1.json") -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8")); failures: list[str] = []
    if "head_commit" in value: failures.append("v2_must_not_use_top_level_head_commit")
    if value.get("schema_version") != "0.9.1" or value.get("version") != "0.9.1": failures.append("schema_version_or_version_invalid")
    subject = value.get("review_subject", {}); expected_subject = {"baseline_commit": "46ba3ae87558ff26055e14aa8d9c6f3ee147333c", "implementation_base_commit": "16c60c9ff934a55adefc82a99d81dafb52d1047c"}
    if any(subject.get(key) != expected for key, expected in expected_subject.items()) or subject.get("implementation_base_commit") == subject.get("baseline_commit"): failures.append("review_subject_commit_binding_invalid")
    publication = value.get("publication", {}); build_head = str(publication.get("index_build_git_head", "")); has_git = (ROOT / ".git").exists(); final_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip() if has_git else build_head
    if len(build_head) != 40: failures.append("index_build_git_head_invalid")
    elif has_git:
        ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", build_head, final_head], cwd=ROOT, check=False); failures.extend(["index_build_git_head_must_be_ancestor_of_final_head"] if ancestor.returncode != 0 else [])
    if publication.get("final_head_must_be_resolved_by_external_reviewer") is not True or publication.get("executor_cannot_self_assert_final_head") is not True: failures.append("external_final_head_resolution_required")
    artifacts = value.get("artifact_set", {}).get("artifacts", []) if isinstance(value.get("artifact_set"), dict) else []; listed: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict): failures.append("artifact_item_invalid"); continue
        relative = str(item.get("path")); listed.add(relative); local = ROOT / relative
        if not local.is_file(): failures.append(f"artifact_missing:{relative}")
        elif has_git and digest(local) != item.get("sha256"): failures.append(f"artifact_hash_mismatch:{relative}")
    artifact_set = value.get("artifact_set", {}); expected_hash = hashlib.sha256(canonical(artifacts).encode("utf-8")).hexdigest()
    if artifact_set.get("manifest_algorithm") != "sha256-canonical-path-list-v1" or artifact_set.get("artifact_set_sha256") != expected_hash: failures.append("artifact_set_hash_invalid")
    visual_manifest = json.loads((ROOT / "docs/evidence/review-visuals-v0.9.0.json").read_text(encoding="utf-8")); failures.extend(f"visual_not_in_artifact_set:{item.get('source_path')}" for item in visual_manifest.get("images", []) if item.get("source_path") not in listed)
    required = ["generic-runtime-contract-v091.json", "timing-alternative-qualification-v091.json", "generic-dummy-package-qualification-v091.json", "walk-replay-qualification-v091.json", "idle-dual-foot-drift-qa-v091.json", "idle-layer-bbox-temporal-qa-v091.json", "idle-occlusion-policy-v091.json", "idle-requalification-v091.json", "execution-evidence-v0.9.1.json"]
    failures.extend(f"required_evidence_not_in_artifact_set:{name}" for name in required if f"docs/evidence/animation-runtime-v091/{name}" not in listed)
    if any(item.casefold().endswith(".zip") for item in listed): failures.append("zip_must_not_be_in_index")
    return {"status": "REVIEW_INDEX_V2_PASSED" if not failures else "REVIEW_INDEX_V2_FAILED", "failures": failures, "checked": {"artifact_count": len(artifacts), "visual_count": artifact_set.get("visual_count"), "index_build_git_head": build_head, "final_head": final_head, "ancestor_semantics": has_git}}


if __name__ == "__main__":
    result = validate(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/evidence/review-index-v0.9.1.json"); print(json.dumps(result, indent=2, ensure_ascii=False)); raise SystemExit(0 if result["status"] == "REVIEW_INDEX_V2_PASSED" else 1)
