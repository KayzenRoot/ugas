"""Validate the bounded v0.24.7 review artifact security, inventory and path boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import ntpath
import os
import re
from pathlib import Path
from typing import Any


SELF_ATTESTATION = "security-results-v0247.json"
REQUIRED_BASE_SHA = "dee98f8cd89ebd83a36ead7a22a184700d6e916f"
REQUIRED_BRANCH = "codex/v0.24.0-orchestration-runtime-hardening-foundation"
PRIVATE_PATH_MARKERS = ("/home/runner/", "/Users/", "C:\\Users\\", "c:\\users\\", "~/.uads")
ALLOWED_PREFIXES = (
    "docs/evidence/orchestration-runtime-v0247/",
    "docs/evidence/github-governance-v0247/",
    "docs/evidence/current-state.json",
    "schemas/current-state-v0247.json",
    "schemas/orchestration-runtime-v0247.json",
    "REVIEW-v0.24.7.md",
    "github-review-manifest-v0247.json",
    "test-results-v0247.json",
    "validation-results-v0247.json",
    "state-validation-v0247.json",
    "schema-validation-v0247.json",
    "security-results-v0247.json",
    "manifest-validation-results-v0247.json",
    "pre-upload-enforcement-v0247.json",
    "logs/",
    "docs/evidence/post-merge-canonical-promotion-v0252/",
    "schemas/current-state-v0252.json",
    "REVIEW-v0.25.2.md",
    "post-merge-canonical-promotion-v0252.json",
    "state-validation-v0252.json",
)
FORBIDDEN_TOKENS = ("secret", "credential", "password", "api_key", ".safetensors", ".ckpt", ".sqlite", ".db", ".uads")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def list_artifact_files(root: Path) -> list[Path]:
    return sorted((path for path in root.rglob("*") if path.is_file()), key=lambda path: path.relative_to(root).as_posix())


def file_inventory_entry(root: Path, path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": path.relative_to(root).as_posix(), "size": len(data), "sha256": sha256_bytes(data)}


def canonical_inventory_bytes(entries: list[dict[str, Any]]) -> bytes:
    return json.dumps(entries, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def build_artifact_inventory(root: Path, *, excluded_paths: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    excluded = set(excluded_paths)
    entries = [file_inventory_entry(root, path) for path in list_artifact_files(root) if path.relative_to(root).as_posix() not in excluded]
    return {
        "entries": entries,
        "inventory_digest": sha256_bytes(canonical_inventory_bytes(entries)),
        "scanned_file_count": len(entries),
        "excluded_paths": sorted(excluded),
    }


def verify_artifact_inventory(root: Path, inventory: dict[str, Any], *, excluded_paths: tuple[str, ...] | list[str] = (SELF_ATTESTATION,)) -> dict[str, Any]:
    excluded = list(excluded_paths)
    unique_excluded = sorted(set(excluded))
    if len(unique_excluded) > 1:
        return {"status": "FAIL", "reason": "ARTIFACT_MULTI_SELF_EXCLUSION", "failures": ["multi-self-exclusion"], "inventory_consistency": "FAIL"}
    current = {path.relative_to(root).as_posix(): path for path in list_artifact_files(root)}
    recorded_entries = inventory.get("entries") if isinstance(inventory.get("entries"), list) else []
    recorded = {item.get("path"): item for item in recorded_entries if isinstance(item, dict) and isinstance(item.get("path"), str)}
    scanned_expected = {path for path in current if path not in set(unique_excluded)}
    recorded_paths = set(recorded)
    added = scanned_expected - recorded_paths
    removed = recorded_paths - scanned_expected
    modified: list[str] = []
    size_tamper: list[str] = []
    sha_tamper: list[str] = []
    for relative in sorted(scanned_expected & recorded_paths):
        disk = file_inventory_entry(root, current[relative])
        item = recorded[relative]
        if disk["sha256"] != item.get("sha256") and disk["size"] != item.get("size"):
            modified.append(relative)
        elif disk["size"] != item.get("size"):
            size_tamper.append(relative)
        elif disk["sha256"] != item.get("sha256"):
            sha_tamper.append(relative)
    rebuilt = build_artifact_inventory(root, excluded_paths=tuple(unique_excluded))
    stale_digest = rebuilt["inventory_digest"] != inventory.get("inventory_digest") and not added and not removed and not modified and not size_tamper and not sha_tamper
    reason = None
    failures: list[str] = []
    if len(unique_excluded) > 1:
        reason = "ARTIFACT_MULTI_SELF_EXCLUSION"
        failures.append("multi-self-exclusion")
    elif stale_digest:
        reason = "ARTIFACT_STALE_DIGEST"
        failures.append("stale-inventory-digest")
    elif size_tamper:
        reason = "ARTIFACT_SIZE_TAMPER"
        failures.extend(f"size:{name}" for name in size_tamper)
    elif sha_tamper:
        reason = "ARTIFACT_SHA_TAMPER"
        failures.extend(f"sha256:{name}" for name in sha_tamper)
    elif modified:
        reason = "ARTIFACT_FILE_MODIFIED"
        failures.extend(f"modified:{name}" for name in modified)
    elif added and removed and len(added) == 1 and len(removed) == 1:
        reason = "ARTIFACT_FILE_RENAMED"
        failures.append(f"renamed:{next(iter(removed))}->{next(iter(added))}")
    elif removed and not added:
        reason = "ARTIFACT_FILE_REMOVED"
        failures.extend(f"removed:{name}" for name in sorted(removed))
    elif added and not removed:
        unexpected = [name for name in sorted(added) if not name.startswith(ALLOWED_PREFIXES)]
        if unexpected:
            reason = "ARTIFACT_UNEXPECTED_EXTRA"
            failures.extend(f"unexpected:{name}" for name in unexpected)
        else:
            reason = "ARTIFACT_FILE_ADDED"
            failures.extend(f"added:{name}" for name in sorted(added))
    status = "PASS" if reason is None else "FAIL"
    final_staged_file_count = len(current)
    scanned_file_count = inventory.get("scanned_file_count", rebuilt["scanned_file_count"])
    return {
        "status": status,
        "reason": reason,
        "failures": failures,
        "inventory_consistency": "PASS" if status == "PASS" else "FAIL",
        "scanned_file_count": scanned_file_count,
        "final_staged_file_count": final_staged_file_count,
        "inventory_digest": inventory.get("inventory_digest"),
        "excluded_paths": unique_excluded,
    }


def sanitize_exported_text(text: str) -> str:
    replacements: list[tuple[str, str]] = []
    for key, token in (("GITHUB_WORKSPACE", "<workspace>"), ("RUNNER_WORKSPACE", "<workspace>"), ("RUNNER_TEMP", "<tmp>"), ("TMPDIR", "<tmp>"), ("TEMP", "<tmp>"), ("TMP", "<tmp>")):
        value = os.environ.get(key)
        if value:
            replacements.append((value.replace("\\", "/"), token))
            replacements.append((value, token))
    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    sanitized = text
    for source, token in replacements:
        if source:
            sanitized = sanitized.replace(source, token)
            sanitized = sanitized.replace(source.replace("\\", "/"), token)
    return sanitized


def _contains_private_path(text: str) -> bool:
    lowered = text.casefold()
    return any(marker.casefold() in lowered for marker in PRIVATE_PATH_MARKERS)


def evaluate_artifact_security(root: Path, manifest: dict[str, Any], *, self_attestation: str = SELF_ATTESTATION) -> dict[str, Any]:
    failures: list[str] = []
    inventory = build_artifact_inventory(root, excluded_paths=(self_attestation,))
    files = list_artifact_files(root)
    for path in files:
        relative = path.relative_to(root).as_posix()
        if relative == self_attestation:
            continue
        lowered = relative.casefold()
        if relative.startswith("/") or ntpath.isabs(relative) or ".." in Path(relative).parts or not relative.startswith(ALLOWED_PREFIXES):
            failures.append(f"path:{relative}")
        if any(token in lowered for token in FORBIDDEN_TOKENS):
            failures.append(f"forbidden:{relative}")
        if lowered == ".uads" or lowered.startswith(".uads/") or "/.uads/" in f"/{lowered}/":
            failures.append(f"uads-runtime:{relative}")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""
        if text and _contains_private_path(text):
            failures.append(f"private-path:{relative}")
        if ".uads" in text.casefold() and ("~/.uads" in text.casefold() or "c:\\users\\" in text.casefold() or "/users/" in text.casefold()):
            failures.append(f"uads-unsafe:{relative}")
    if manifest.get("overall_status") != "PASS":
        failures.append("manifest-overall")
    boundary = manifest.get("production_boundary", {})
    if boundary.get("approved") is not False or boundary.get("routing") != "BLOCKED" or boundary.get("new_generation") != 0 or boundary.get("provider_submit_calls") != 0:
        failures.append("production-boundary")
    security = manifest.get("security_boundary", {})
    if any(value is not False for value in security.values()):
        failures.append("security-boundary")
    pull_request = manifest.get("pull_request", {}) if isinstance(manifest.get("pull_request"), dict) else {}
    result = {
        "schema_version": "0.24.7",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "file_count": len([path for path in files if path.relative_to(root).as_posix() != self_attestation]),
        "scanned_file_count": inventory["scanned_file_count"],
        "inventory_digest": inventory["inventory_digest"],
        "inventory": inventory["entries"],
        "excluded_paths": [self_attestation],
        "base_sha": pull_request.get("base_sha"),
        "head_sha": pull_request.get("head_sha"),
        "pr_number": pull_request.get("number"),
        "production_boundary": boundary,
        "inventory_consistency": "PASS" if not failures else "FAIL",
        "secrets_included": False,
        "model_weights_included": False,
        "telemetry_db_included": False,
        "local_credentials_included": False,
    }
    if manifest.get("scope", {}).get("version") == "0.24.7" and pull_request.get("number") == 15 and pull_request.get("base_sha") != REQUIRED_BASE_SHA:
        result["failures"] = [*result["failures"], "identity-base-sha"]
        result["status"] = "FAIL"
        result["inventory_consistency"] = "FAIL"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.artifact_dir).resolve()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    output = Path(args.output).resolve()
    result = evaluate_artifact_security(root, manifest, self_attestation=SELF_ATTESTATION)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        relative_output = output.relative_to(root).as_posix()
    except ValueError:
        relative_output = None
    if relative_output == SELF_ATTESTATION:
        verification = verify_artifact_inventory(root, {"entries": result["inventory"], "inventory_digest": result["inventory_digest"], "scanned_file_count": result["scanned_file_count"]}, excluded_paths=(SELF_ATTESTATION,))
        result["final_staged_file_count"] = verification["final_staged_file_count"]
        result["inventory_consistency"] = verification["inventory_consistency"]
        if verification["status"] != "PASS" or verification["final_staged_file_count"] != result["scanned_file_count"] + 1:
            result["status"] = "FAIL"
            result["failures"] = [*result.get("failures", []), *(verification.get("failures") or ["self-attestation-count"])]
            result["reason"] = verification.get("reason") or "ARTIFACT_SELF_ATTESTATION_COUNT"
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in result if key != "inventory"}, ensure_ascii=False))
    for failure in result.get("failures", []):
        print(f"::error title=UGAS v0.24.7 artifact security::{failure}")
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
