"""Immutable Git-head authority binding for v0.20.3 preservation gates."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any, Mapping


V0200_REJECTED_HEAD = "ae335ba198bb7f23210873e30948e8a19bc71cbd"
V0201_REJECTED_HEAD = "0353e6785017c08db6e55c9448d9fa60e5908802"
V0202_REJECTED_HEAD = "6022cf3c6158ebb762519a04e79ed42378438ccc"

V0200_BOUND_FILE = "docs/evidence/environment-tilesets-runtime-v0200/negative-controls-v0200.json"
V0201_BOUND_ROOT = "docs/evidence/environment-tilesets-runtime-v0201"
V0202_BOUND_ROOT = "docs/evidence/environment-tilesets-runtime-v0202"


def _git(repo_root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or "git authority lookup failed")
    return result.stdout


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_current_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    return data


def _blob(repo_root: Path, head: str, path: str) -> dict[str, Any]:
    object_id = _git(repo_root, "rev-parse", f"{head}:{path}").decode("ascii").strip()
    data = _git(repo_root, "show", f"{head}:{path}")
    return {"path": path, "blob_sha": object_id, "bytes_sha256": _sha256(data), "size": len(data)}


def _tree(repo_root: Path, head: str, prefix: str) -> list[dict[str, Any]]:
    raw = _git(repo_root, "ls-tree", "-r", "--full-tree", "-z", head, "--", f"{prefix}/")
    records: list[dict[str, Any]] = []
    for record in raw.split(b"\x00"):
        if not record:
            continue
        header, path_bytes = record.split(b"\t", 1)
        mode, object_type, object_id = header.decode("ascii").split(" ", 2)
        path = path_bytes.decode("utf-8")
        data = _git(repo_root, "show", f"{head}:{path}")
        records.append({"path": path, "mode": mode, "type": object_type, "blob_sha": object_id, "bytes_sha256": _sha256(data), "size": len(data)})
    return records


def build_historical_authority_manifest(repo_root: Path) -> dict[str, Any]:
    """Resolve expected immutable blobs from fixed rejected review heads."""

    return {
        "schema_version": "0.20.3",
        "status": "IMMUTABLE_AUTHORITY_BOUND",
        "authorities": {
            "v0200_negative_controls": {"head": V0200_REJECTED_HEAD, "kind": "file", "records": [_blob(repo_root, V0200_REJECTED_HEAD, V0200_BOUND_FILE)]},
            "v0201_evidence_root": {"head": V0201_REJECTED_HEAD, "kind": "tree", "prefix": V0201_BOUND_ROOT, "records": _tree(repo_root, V0201_REJECTED_HEAD, V0201_BOUND_ROOT)},
            "v0202_evidence_root": {"head": V0202_REJECTED_HEAD, "kind": "tree", "prefix": V0202_BOUND_ROOT, "records": _tree(repo_root, V0202_REJECTED_HEAD, V0202_BOUND_ROOT)},
        },
    }


def validate_historical_preservation(root: Path, authority: Mapping[str, Any]) -> dict[str, Any]:
    """Compare current bytes against the fixed authority manifest, never itself."""

    failures: list[str] = []
    checked = 0
    authority_results: dict[str, Any] = {}
    for name, binding in authority.get("authorities", {}).items():
        expected_records = list(binding.get("records", []))
        expected_paths = {str(record["path"]) for record in expected_records}
        current_paths: set[str] = set()
        entries: list[dict[str, Any]] = []
        for record in expected_records:
            path = root / str(record["path"])
            checked += 1
            current_exists = path.is_file()
            current_raw_sha = _sha256(path.read_bytes()) if current_exists else None
            current_sha = _sha256(_canonical_current_bytes(path)) if current_exists else None
            current_paths.add(str(record["path"])) if current_exists else None
            passed = current_exists and current_sha == record.get("bytes_sha256")
            if not passed:
                failures.append(f"{name}:{record['path']}")
            entries.append({"path": record["path"], "expected_blob_sha": record.get("blob_sha"), "expected_bytes_sha256": record.get("bytes_sha256"), "current_raw_bytes_sha256": current_raw_sha, "current_bytes_sha256": current_sha, "status": "PASS" if passed else "FAIL"})
        if binding.get("kind") == "tree":
            prefix = str(binding.get("prefix", ""))
            actual = {path.relative_to(root).as_posix() for path in (root / prefix).rglob("*") if path.is_file()} if (root / prefix).is_dir() else set()
            unexpected = sorted(actual - expected_paths)
            if unexpected:
                failures.extend(f"{name}:unexpected:{path}" for path in unexpected)
            authority_results[name] = {"head": binding.get("head"), "kind": "tree", "prefix": prefix, "expected_file_count": len(expected_paths), "current_file_count": len(actual), "unexpected_paths": unexpected, "records": entries, "status": "PASS" if not unexpected and all(item["status"] == "PASS" for item in entries) else "FAIL"}
        else:
            authority_results[name] = {"head": binding.get("head"), "kind": "file", "records": entries, "status": "PASS" if all(item["status"] == "PASS" for item in entries) else "FAIL"}
    return {"schema_version": "0.20.3", "status": "PASS" if not failures else "FAIL", "failures": failures, "checked_records": checked, "authorities": authority_results}


__all__ = [
    "V0200_BOUND_FILE",
    "V0200_REJECTED_HEAD",
    "V0201_BOUND_ROOT",
    "V0201_REJECTED_HEAD",
    "V0202_BOUND_ROOT",
    "V0202_REJECTED_HEAD",
    "build_historical_authority_manifest",
    "validate_historical_preservation",
]
