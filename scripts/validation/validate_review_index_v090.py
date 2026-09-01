"""Validate the v0.9.0 review index v2 artifact set and publication semantics."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt"}: data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


HISTORICAL_V090_COMMIT = "16c60c9ff934a55adefc82a99d81dafb52d1047c"


def _git_blob(commit: str, relative: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{commit}:{relative}"], cwd=ROOT)


def validate(path: Path, root: Path = ROOT, final_head: str | None = None, _historical: bool = False, source_commit: str | None = None) -> dict[str, object]:
    """Validate the immutable v0.9.0 index against its release snapshot."""
    path = path.resolve()
    if not _historical and root.resolve() == ROOT.resolve() and path == (ROOT / "docs/evidence/review-index-v0.9.0.json").resolve() and (ROOT / ".git").exists():
        current_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
        return validate(path, ROOT, current_head, True, HISTORICAL_V090_COMMIT)
    value = json.loads(path.read_text(encoding="utf-8")); failures: list[str] = []
    if "head_commit" in value: failures.append("v2_must_not_use_top_level_head_commit")
    if value.get("schema_version") != "0.9.0" or value.get("version") != "0.9.0": failures.append("schema_version_or_version_invalid")
    subject = value.get("review_subject", {})
    if subject.get("baseline_commit") != "46ba3ae87558ff26055e14aa8d9c6f3ee147333c" or subject.get("implementation_base_commit") != subject.get("baseline_commit"): failures.append("review_subject_commit_binding_invalid")
    publication = value.get("publication", {}); build_head = str(publication.get("index_build_git_head", "")); final_head = final_head or subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    if len(build_head) != 40: failures.append("index_build_git_head_invalid")
    else:
        ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", build_head, final_head], cwd=ROOT, check=False); failures.extend(["index_build_git_head_must_be_ancestor_of_final_head"] if ancestor.returncode != 0 else [])
    if publication.get("final_head_must_be_resolved_by_external_reviewer") is not True: failures.append("external_final_head_resolution_required")
    artifact_set = value.get("artifact_set", {}); artifacts = artifact_set.get("artifacts", []) if isinstance(artifact_set, dict) else []
    if artifact_set.get("manifest_algorithm") != "sha256-canonical-path-list-v1": failures.append("manifest_algorithm_invalid")
    seen: set[str] = set(); visual_manifest = json.loads((_git_blob(source_commit, "docs/evidence/review-visuals-v0.9.0.json") if source_commit else (root / "docs/evidence/review-visuals-v0.9.0.json").read_bytes()).decode("utf-8")); listed = {item.get("path") for item in artifacts if isinstance(item, dict)}
    for item in artifacts:
        if not isinstance(item, dict): failures.append("artifact_item_invalid"); continue
        artifact_path = str(item.get("path")); seen.add(artifact_path); local = root / artifact_path
        if source_commit:
            blob = subprocess.run(["git", "cat-file", "-e", f"{source_commit}:{artifact_path}"], cwd=ROOT, check=False)
            raw = _git_blob(source_commit, artifact_path) if blob.returncode == 0 else None
            if raw is not None and Path(artifact_path).suffix.casefold() in {".json", ".md", ".txt"}:
                raw = raw.replace(b"\r\n", b"\n")
            actual = hashlib.sha256(raw).hexdigest() if raw is not None else None
        else:
            actual = digest(local) if local.is_file() else None
        if actual is None: failures.append(f"artifact_missing:{artifact_path}")
        elif actual != item.get("sha256"): failures.append(f"artifact_hash_mismatch:{artifact_path}")
    expected_hash = hashlib.sha256(canonical(artifacts).encode("utf-8")).hexdigest()
    if artifact_set.get("artifact_set_sha256") != expected_hash: failures.append("artifact_set_hash_mismatch")
    for item in visual_manifest.get("images", []):
        if item.get("source_path") not in listed: failures.append(f"visual_not_in_artifact_set:{item.get('source_path')}")
    if any(str(item).casefold().endswith(".zip") for item in seen): failures.append("zip_must_not_be_in_index")
    return {"status": "REVIEW_INDEX_V2_PASSED" if not failures else "REVIEW_INDEX_V2_FAILED", "failures": failures, "checked": {"artifact_count": len(artifacts), "visual_count": artifact_set.get("visual_count"), "index_build_git_head": build_head, "final_head": final_head, "ancestor_semantics": True}}


def main(argv: list[str] | None = None) -> int:
    path = ROOT / (argv[0] if argv else "docs/evidence/review-index-v0.9.0.json"); result = validate(path); print(json.dumps(result, indent=2, ensure_ascii=False)); return 0 if result["status"] == "REVIEW_INDEX_V2_PASSED" else 1


if __name__ == "__main__": raise SystemExit(main(sys.argv[1:]))
