"""Validate the v0.11.2 hash-bound review index and evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "9401c31f994e968149292b2993d960d3aafc37c4"
IMPLEMENTATION_BASE = "f386c490a6d7289befc1c8a34c84eff1d2b1cc96"
TEXT_SUFFIXES = {".json", ".md", ".txt", ".py", ".toml"}


def digest(path: Path) -> str:
    data = path.read_bytes()
    if path.name.casefold() == "license" or path.suffix.casefold() in TEXT_SUFFIXES: data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> str: return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def validate(path: Path = ROOT / "docs/evidence/review-index-v0.11.2.json") -> dict[str, object]:
    failures: list[str] = []
    value = json.loads(path.read_text(encoding="utf-8"))
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from ugas.schema_validation import validate_instance, validate_schema_document
        schema = json.loads((ROOT / "schemas/review-index-v0.11.2.json").read_text(encoding="utf-8")); validate_schema_document(schema); validate_instance(value, schema)
    except Exception as exc: failures.append(f"schema:{exc}")
    subject, publication = value.get("review_subject", {}), value.get("publication", {})
    if subject.get("baseline_commit") != BASELINE or subject.get("implementation_base_commit") != IMPLEMENTATION_BASE or subject.get("previous_rejected_commit") != IMPLEMENTATION_BASE: failures.append("review_subject_commit_binding_invalid")
    build_head = str(publication.get("index_build_git_head", "")); has_git = (ROOT / ".git").exists(); final_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip() if has_git else build_head
    if len(build_head) != 40 or (has_git and subprocess.run(["git", "merge-base", "--is-ancestor", build_head, final_head], cwd=ROOT, check=False).returncode != 0): failures.append("index_build_git_head_must_be_ancestor_of_final_head")
    if publication.get("final_head_must_be_resolved_by_external_reviewer") is not True or publication.get("executor_cannot_self_assert_final_head") is not True: failures.append("external_final_head_resolution_required")
    artifacts = value.get("artifact_set", {}).get("artifacts", [])
    listed = set()
    for item in artifacts:
        relative = str(item.get("path")); listed.add(relative); local = ROOT / relative
        if not local.is_file(): failures.append(f"artifact_missing:{relative}")
        elif digest(local) != item.get("sha256"): failures.append(f"artifact_hash_mismatch:{relative}")
        if relative.casefold().endswith((".zip", ".safetensors", ".ckpt", ".gguf", ".onnx")): failures.append(f"forbidden_binary_artifact:{relative}")
    if value.get("artifact_set", {}).get("artifact_set_sha256") != hashlib.sha256(canonical(artifacts).encode("utf-8")).hexdigest(): failures.append("artifact_set_hash_invalid")
    try:
        visual = json.loads((ROOT / "docs/evidence/animation-runtime-v0112/attack-v2-visual-manifest-v0112.json").read_text(encoding="utf-8"))
        for item in visual.get("images", []):
            if item.get("source_path") not in listed: failures.append(f"visual_not_in_artifact_set:{item.get('source_path')}")
            elif digest(ROOT / item["source_path"]) != item.get("sha256"): failures.append(f"visual_hash_mismatch:{item.get('source_path')}")
        if value.get("required_visual_sets") != sorted(item["archive_name"] for item in visual.get("images", [])): failures.append("required_visual_sets_mismatch")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc: failures.append(f"visual_manifest:{exc}")
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8")); qa = json.loads((ROOT / "docs/evidence/animation-runtime-v0112/attack-front-v2/qa-result.json").read_text(encoding="utf-8")); execution = json.loads((ROOT / "docs/evidence/animation-runtime-v0112/execution-evidence-v0.11.2.json").read_text(encoding="utf-8")); identity = json.loads((ROOT / "docs/evidence/animation-runtime-v0112/identity-proof-v0112.json").read_text(encoding="utf-8"))
    if state.get("version") != "0.11.2" or state.get("allowed_next_actions") != ["external_review_attack_front_v2_v0112"] or state.get("state_consistency", {}).get("production_routing") != "BLOCKED": failures.append("active_state_boundary_invalid")
    if qa.get("decision") != "QUALIFIED" or qa.get("failures") != [] or not all(value is True for value in qa.get("hard_gates", {}).values()): failures.append("qa_hard_gates_invalid")
    if execution.get("negative_controls", {}).get("status") != "NC_01_TO_NC_10_PASSED" or execution.get("pixel_identity") != "PIXEL_IDENTITY_V0110_PASSED": failures.append("execution_integrity_evidence_invalid")
    if identity.get("visual", {}).get("status") != "PIXEL_IDENTITY_V0110_PASSED" or not identity.get("motion_tracks") or not identity.get("key_pose_bindings"): failures.append("identity_proof_invalid")
    if value.get("external_visual_review", {}).get("attack_front_v2_approval") != "REQUIRED" or value.get("production_routing") != "BLOCKED": failures.append("external_or_production_boundary_invalid")
    return {"status": "REVIEW_INDEX_V0112_PASSED" if not failures else "REVIEW_INDEX_V0112_FAILED", "failures": failures, "checked": {"artifact_count": len(artifacts), "visual_count": value.get("artifact_set", {}).get("visual_count"), "index_build_git_head": build_head, "final_head": final_head}}


if __name__ == "__main__":
    result = validate(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/evidence/review-index-v0.11.2.json")
    print(json.dumps(result, indent=2, ensure_ascii=False)); raise SystemExit(0 if result["status"] == "REVIEW_INDEX_V0112_PASSED" else 1)
