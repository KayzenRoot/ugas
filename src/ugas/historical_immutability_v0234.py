"""Exact tracked-tree and filesystem-root immutability for v0.23.4."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

from .vfx_asset_family_runtime_v0233 import VFXAssetFamilyContractError, canonical_json, sha256_bytes

REJECTION_CLASS = "VFX_HISTORICAL_IMMUTABILITY_REJECTED"


def _git(repo_root: Path, *args: str, text: bool = False, input_bytes: bytes | None = None) -> bytes | str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        check=False,
        text=text,
        input=input_bytes,
    )
    if result.returncode != 0:
        raise VFXAssetFamilyContractError(REJECTION_CLASS, f"git command failed: {' '.join(args)}")
    return result.stdout


def _tree_id(repo_root: Path, ref: str, relative_root: str) -> str:
    tree = str(_git(repo_root, "rev-parse", f"{ref}:{relative_root}", text=True)).strip()
    if len(tree) != 40 or any(character not in "0123456789abcdef" for character in tree.lower()):
        raise VFXAssetFamilyContractError(REJECTION_CLASS, f"tree unresolved: {ref}:{relative_root}")
    return tree


def _relative_path(path: str, relative_root: str) -> str:
    try:
        return PurePosixPath(path).relative_to(PurePosixPath(relative_root)).as_posix()
    except ValueError as error:
        raise VFXAssetFamilyContractError(REJECTION_CLASS, f"path outside historical root: {path}") from error


def _blob_bytes(repo_root: Path, blob_ids: list[str]) -> dict[str, bytes]:
    if not blob_ids:
        return {}
    payload = b"".join(f"{blob}\n".encode("ascii") for blob in blob_ids)
    output = bytes(_git(repo_root, "cat-file", "--batch", input_bytes=payload))
    values: dict[str, bytes] = {}
    offset = 0
    for blob in blob_ids:
        end = output.find(b"\n", offset)
        if end < 0:
            raise VFXAssetFamilyContractError(REJECTION_CLASS, f"git cat-file response truncated: {blob}")
        header = output[offset:end].split()
        offset = end + 1
        if len(header) != 3 or header[0].decode("ascii") != blob or header[1] != b"blob":
            raise VFXAssetFamilyContractError(REJECTION_CLASS, f"git cat-file object mismatch: {blob}")
        size = int(header[2])
        data = output[offset : offset + size]
        if len(data) != size:
            raise VFXAssetFamilyContractError(REJECTION_CLASS, f"git cat-file blob truncated: {blob}")
        offset += size
        if output[offset : offset + 1] == b"\n":
            offset += 1
        values[blob] = data
    return values


def _tracked_entries(repo_root: Path, ref: str, relative_root: str) -> list[dict[str, Any]]:
    listing = str(_git(repo_root, "ls-tree", "-r", ref, "--", relative_root, text=True))
    parsed: list[dict[str, Any]] = []
    for line in listing.splitlines():
        fields = line.split("\t", 1)
        if len(fields) != 2:
            raise VFXAssetFamilyContractError(REJECTION_CLASS, f"malformed tree entry: {ref}:{relative_root}")
        header, path = fields
        header_fields = header.split()
        if len(header_fields) != 3:
            raise VFXAssetFamilyContractError(REJECTION_CLASS, f"malformed tree header: {path}")
        mode, object_type, blob = header_fields
        if object_type != "blob":
            raise VFXAssetFamilyContractError(REJECTION_CLASS, f"unsupported historical entry type: {path}")
        parsed.append({"path": _relative_path(path, relative_root), "mode": mode, "type": object_type, "blob": blob})
    if not parsed:
        raise VFXAssetFamilyContractError(REJECTION_CLASS, f"historical path unresolved: {ref}:{relative_root}")
    blobs = _blob_bytes(repo_root, [item["blob"] for item in parsed])
    for item in parsed:
        item["sha256"] = sha256_bytes(blobs[item["blob"]])
    return sorted(parsed, key=lambda item: item["path"])


def _git_blob_id(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _filesystem_entries(candidate_root: Path) -> list[dict[str, Any]]:
    if not candidate_root.is_dir():
        raise VFXAssetFamilyContractError(REJECTION_CLASS, f"candidate root unresolved: {candidate_root}")
    entries: list[dict[str, Any]] = []
    for path in sorted(candidate_root.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        relative = path.relative_to(candidate_root).as_posix()
        path_stat = path.lstat()
        if stat.S_ISLNK(path_stat.st_mode):
            data = os.readlink(path).encode("utf-8")
            mode = "120000"
        elif stat.S_ISREG(path_stat.st_mode):
            data = path.read_bytes()
            mode = "100755" if path_stat.st_mode & stat.S_IXUSR else "100644"
        else:
            raise VFXAssetFamilyContractError(REJECTION_CLASS, f"unsupported candidate entry type: {relative}")
        entries.append(
            {
                "path": relative,
                "mode": mode,
                "type": "blob",
                "blob": _git_blob_id(data),
                "sha256": sha256_bytes(data),
            }
        )
    return entries


def _fingerprint(items: list[dict[str, Any]]) -> str:
    comparable = [
        {
            "path": item["path"],
            "mode": item["mode"],
            "type": item["type"],
            "blob": item["blob"],
            "sha256": item["sha256"],
        }
        for item in items
    ]
    return sha256_bytes(canonical_json(sorted(comparable, key=lambda item: item["path"])))


def _compare_entries(authority: list[dict[str, Any]], observed: list[dict[str, Any]]) -> list[str]:
    authority_by_path = {item["path"]: item for item in authority}
    observed_by_path = {item["path"]: item for item in observed}
    failures: list[str] = []
    if set(authority_by_path) != set(observed_by_path):
        failures.append("file-set")
    for path in sorted(set(authority_by_path) | set(observed_by_path)):
        expected = authority_by_path.get(path)
        actual = observed_by_path.get(path)
        if expected is None or actual is None:
            continue
        for field in ("mode", "type", "blob", "sha256"):
            if expected[field] != actual[field]:
                failures.append(f"{field}:{path}")
    return failures


def _evidence_entries(authority: list[dict[str, Any]], observed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observed_by_path = {item["path"]: item for item in observed}
    return [
        {
            "path": item["path"],
            "authority_mode": item["mode"],
            "authority_type": item["type"],
            "authority_blob": item["blob"],
            "authority_sha256": item["sha256"],
            "observed_mode": observed_by_path.get(item["path"], {}).get("mode"),
            "observed_type": observed_by_path.get(item["path"], {}).get("type"),
            "observed_blob": observed_by_path.get(item["path"], {}).get("blob"),
            "observed_sha256": observed_by_path.get(item["path"], {}).get("sha256"),
            "equal": observed_by_path.get(item["path"], {}).get("sha256") == item["sha256"],
        }
        for item in authority
    ]


def validate_historical_root(
    repo_root: Path,
    authority_ref: str,
    relative_root: str,
    candidate_root: Path | None = None,
    *,
    observed_ref: str = "HEAD",
) -> dict[str, Any]:
    """Require exact authority/observed tree and file-set equality."""

    authority_tree = _tree_id(repo_root, authority_ref, relative_root)
    authority_entries = _tracked_entries(repo_root, authority_ref, relative_root)
    if candidate_root is None:
        observed_ref_label = observed_ref
        observed_tree = _tree_id(repo_root, observed_ref, relative_root)
        observed_entries = _tracked_entries(repo_root, observed_ref, relative_root)
    else:
        observed_ref_label = "filesystem-candidate"
        observed_tree = None
        observed_entries = sorted(_filesystem_entries(candidate_root), key=lambda item: item["path"])
    failures = _compare_entries(authority_entries, observed_entries)
    if candidate_root is None and authority_tree != observed_tree:
        failures.append("tree")
    authority_fingerprint = _fingerprint(authority_entries)
    observed_fingerprint = _fingerprint(observed_entries)
    if authority_fingerprint != observed_fingerprint:
        failures.append("fingerprint")
    if failures:
        raise VFXAssetFamilyContractError(
            REJECTION_CLASS,
            f"{authority_ref}:{relative_root}:{observed_ref_label}:{','.join(sorted(set(failures)))}",
        )
    return {
        "status": "PASS",
        "authority_ref": authority_ref,
        "authority_root": relative_root,
        "authority_tree": authority_tree,
        "observed_ref": observed_ref_label,
        "observed_tree": observed_tree,
        "authority_file_count": len(authority_entries),
        "observed_file_count": len(observed_entries),
        "file_count": len(authority_entries),
        "authority_fingerprint": authority_fingerprint,
        "observed_fingerprint": observed_fingerprint,
        "equality": True,
        "files": _evidence_entries(authority_entries, observed_entries),
    }


def validate_historical_file(
    repo_root: Path,
    authority_ref: str,
    relative_path: str,
    candidate_path: Path | None = None,
) -> dict[str, Any]:
    authority = bytes(_git(repo_root, "show", f"{authority_ref}:{relative_path}"))
    authority_blob = str(_git(repo_root, "rev-parse", f"{authority_ref}:{relative_path}", text=True)).strip()
    if candidate_path is None:
        observed_ref = "HEAD"
        observed = bytes(_git(repo_root, "show", f"HEAD:{relative_path}"))
    else:
        observed_ref = "filesystem-candidate"
        observed = candidate_path.read_bytes() if candidate_path.is_file() else b""
    authority_sha = sha256_bytes(authority)
    observed_sha = sha256_bytes(observed)
    observed_blob = _git_blob_id(observed)
    if authority != observed or authority_blob != observed_blob:
        raise VFXAssetFamilyContractError(REJECTION_CLASS, f"{authority_ref}:{relative_path}:{observed_ref}")
    return {
        "status": "PASS",
        "authority_ref": authority_ref,
        "path": relative_path,
        "authority_blob": authority_blob,
        "observed_blob": observed_blob,
        "authority_sha256": authority_sha,
        "observed_sha256": observed_sha,
        "observed_ref": observed_ref,
        "equality": True,
    }


def validate_historical_immutability(repo_root: Path, candidate_root: Path | None = None) -> dict[str, Any]:
    roots = [
        ("c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72", "docs/evidence/vfx-asset-family-runtime-v0230"),
        ("136079540f674c7467d93bd28e9834addbfce5c3", "docs/evidence/vfx-asset-family-runtime-v0231"),
    ]
    root_proofs = [
        validate_historical_root(repo_root, authority_ref, relative_root, None if candidate_root is None else candidate_root / relative_root)
        for authority_ref, relative_root in roots
    ]
    reviews = [
        validate_historical_file(repo_root, "c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72", "REVIEW-v0.23.0.md", None if candidate_root is None else candidate_root / "REVIEW-v0.23.0.md"),
        validate_historical_file(repo_root, "136079540f674c7467d93bd28e9834addbfce5c3", "REVIEW-v0.23.1.md", None if candidate_root is None else candidate_root / "REVIEW-v0.23.1.md"),
    ]
    return {"status": "PASS", "historical_evidence_unchanged": True, "roots": root_proofs, "reviews": reviews}
