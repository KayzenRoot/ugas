"""Validate the v0.12.0 review index, evidence hashes and governance boundary."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "bc1252992ff5b38096b7e9bd58b5ffe5cee41ffc"
TEXT_SUFFIXES = {".json", ".md", ".txt", ".py", ".toml", ".js", ".html", ".css"}


def digest(path: Path) -> str:
    data = path.read_bytes()
    if path.name.casefold() == "license" or path.suffix.casefold() in TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def validate(path: Path = ROOT / "docs/evidence/review-index-v0.12.0.json") -> dict[str, object]:
    failures: list[str] = []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        sys.path.insert(0, str(ROOT / "src"))
        from ugas.schema_validation import validate_instance, validate_schema_document
        schema = json.loads((ROOT / "schemas/review-index-v0.12.0.json").read_text(encoding="utf-8"))
        validate_schema_document(schema); validate_instance(value, schema)
    except Exception as exc:  # noqa: BLE001 - report all review failures as data
        return {"status": "REVIEW_INDEX_V0120_FAILED", "failures": [f"schema:{exc}"], "checked": {}}
    subject = value["review_subject"]
    if any(subject.get(key) != BASELINE for key in ("baseline_commit", "implementation_base_commit", "previous_release_commit")): failures.append("baseline_commit_binding_invalid")
    if subject.get("repository_ref") != "https://github.com/csn1985-ship-it/ugas.git": failures.append("repository_ref_invalid")
    publication = value["publication"]; build_head = publication["index_build_git_head"]; has_git = (ROOT / ".git").exists()
    final_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip() if has_git else build_head
    if has_git and subprocess.run(["git", "merge-base", "--is-ancestor", build_head, final_head], cwd=ROOT, check=False).returncode != 0: failures.append("index_build_git_head_must_be_ancestor_of_final_head")
    if publication["final_head_must_be_resolved_by_external_reviewer"] is not True or publication["executor_cannot_self_assert_final_head"] is not True: failures.append("external_final_head_resolution_required")
    artifacts = value["artifact_set"]["artifacts"]; listed = {item["path"] for item in artifacts}
    for item in artifacts:
        relative = item["path"]; local = ROOT / relative
        if not local.is_file(): failures.append(f"artifact_missing:{relative}")
        elif digest(local) != item["sha256"]: failures.append(f"artifact_hash_mismatch:{relative}")
        if relative.casefold().endswith((".zip", ".safetensors", ".ckpt", ".gguf", ".onnx")): failures.append(f"forbidden_binary_artifact:{relative}")
    artifact_set = value["artifact_set"]
    if artifact_set["artifact_set_sha256"] != hashlib.sha256(canonical(artifacts).encode("utf-8")).hexdigest(): failures.append("artifact_set_hash_invalid")
    if "docs/evidence/review-index-v0.12.0.json" in listed: failures.append("self_referential_review_index")
    required = ["dashboard-startup.json", "system-idle.json", "command-event.json", "file-activity.json", "api-snapshots.json", "security.json", "animation-regression-v0112.json", "test-results.json", "validation-results.json", "publication.json"]
    failures.extend(f"required_evidence_missing:{name}" for name in required if not (ROOT / "docs/evidence/observability-v0120" / name).is_file() or (name != "publication.json" and f"docs/evidence/observability-v0120/{name}" not in listed))
    screenshots = [f"docs/evidence/observability-v0120/{name}" for name in ("dashboard-overview.png", "dashboard-system-pipeline.png", "dashboard-assets-activity.png", "dashboard-qa-events.png", "dashboard-mobile.png")]
    failures.extend(f"required_screenshot_missing:{path}" for path in screenshots if not (ROOT / path).is_file() or path not in listed)
    external = value["external_visual_review"]
    if external["status"] != "REQUIRED" or external["attack_front_v2_approval"] != "APPROVED_PILOT" or external["observability_dashboard_approval"] != "REQUIRED": failures.append("external_review_boundary_invalid")
    if value["production_routing"] != "BLOCKED" or value["scope_boundary"] != {"local_only": True, "read_only": True, "telemetry_upload": False, "new_generation": 0, "new_asset_family": False, "animation_pixels_changed": False}: failures.append("scope_or_production_boundary_invalid")
    try:
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8")); schema = json.loads((ROOT / "schemas/current-state.json").read_text(encoding="utf-8")); validate_instance(state, schema)
        if state.get("version") != "0.12.0" or state.get("production_approved") is not False or state.get("production_routing") != "BLOCKED" or state.get("external_visual_review", {}).get("attack_front_v2") != "APPROVED_PILOT" or state.get("external_visual_review", {}).get("observability_dashboard") != "REQUIRED": failures.append("active_state_boundary_invalid")
        if state.get("state_consistency", {}).get("new_generation") != 0: failures.append("active_state_new_generation_nonzero")
    except Exception as exc: failures.append(f"active_state_invalid:{exc}")
    try:
        visual = json.loads((ROOT / "docs/evidence/animation-runtime-v0112/attack-v2-visual-manifest-v0112.json").read_text(encoding="utf-8"))
        if not all(item.get("source_path") in listed and (ROOT / item["source_path"]).is_file() and digest(ROOT / item["source_path"]) == item.get("sha256") for item in visual.get("images", [])): failures.append("historical_v0112_visual_hash_invalid")
    except Exception as exc: failures.append(f"historical_visual_manifest_invalid:{exc}")
    return {"status": "REVIEW_INDEX_V0120_PASSED" if not failures else "REVIEW_INDEX_V0120_FAILED", "failures": failures, "checked": {"artifact_count": len(artifacts), "visual_count": artifact_set.get("visual_count"), "index_build_git_head": build_head, "final_head": final_head}}


if __name__ == "__main__":
    result = validate(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/evidence/review-index-v0.12.0.json")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "REVIEW_INDEX_V0120_PASSED" else 1)
