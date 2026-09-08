"""Git-object-bound historical evidence validation for v0.23.3."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .vfx_asset_family_runtime_v0233 import VFXAssetFamilyContractError, canonical_json, sha256_bytes

REJECTION_CLASS = "VFX_HISTORICAL_IMMUTABILITY_REJECTED"


def _git(repo_root: Path, *args: str, text: bool = False) -> bytes | str:
    result = subprocess.run(["git", *args], cwd=repo_root, capture_output=True, check=False, text=text)
    if result.returncode != 0:
        raise VFXAssetFamilyContractError(REJECTION_CLASS, f"git command failed: {' '.join(args)}")
    return result.stdout


def _authority_tree(repo_root: Path, authority_ref: str, relative_root: str) -> str:
    return str(_git(repo_root, "rev-parse", f"{authority_ref}:{relative_root}", text=True)).strip()


def _authority_paths(repo_root: Path, authority_ref: str, relative_root: str) -> list[str]:
    listing = str(_git(repo_root, "ls-tree", "-r", "--name-only", authority_ref, "--", relative_root, text=True))
    paths = [line.strip() for line in listing.splitlines() if line.strip()]
    if not paths:
        raise VFXAssetFamilyContractError(REJECTION_CLASS, f"authority path unresolved: {authority_ref}:{relative_root}")
    return paths


def _authority_bytes(repo_root: Path, authority_ref: str, path: str) -> bytes:
    return bytes(_git(repo_root, "show", f"{authority_ref}:{path}"))


def _authority_entries(repo_root: Path, authority_ref: str, relative_root: str) -> list[tuple[str, str, bytes]]:
    listing = str(_git(repo_root, "ls-tree", "-r", authority_ref, "--", relative_root, text=True))
    entries: list[tuple[str, str]] = []
    for line in listing.splitlines():
        fields = line.split("\t", 1)
        if len(fields) != 2:
            continue
        header, path = fields
        header_fields = header.split()
        if len(header_fields) == 3 and header_fields[1] == "blob":
            entries.append((path, header_fields[2]))
    if not entries:
        raise VFXAssetFamilyContractError(REJECTION_CLASS, f"authority path unresolved: {authority_ref}:{relative_root}")
    batch_input = b"".join(f"{blob}\n".encode("ascii") for _, blob in entries)
    result = subprocess.run(["git", "cat-file", "--batch"], cwd=repo_root, input=batch_input, capture_output=True, check=False)
    if result.returncode != 0:
        raise VFXAssetFamilyContractError(REJECTION_CLASS, f"git cat-file failed: {authority_ref}:{relative_root}")
    output = result.stdout
    offset = 0
    values: list[tuple[str, str, bytes]] = []
    for path, blob in entries:
        end = output.find(b"\n", offset)
        if end < 0:
            raise VFXAssetFamilyContractError(REJECTION_CLASS, f"git cat-file response truncated: {path}")
        header = output[offset:end].split()
        offset = end + 1
        if len(header) != 3 or header[0].decode("ascii") != blob or header[1] != b"blob":
            raise VFXAssetFamilyContractError(REJECTION_CLASS, f"git cat-file header mismatch: {path}")
        size = int(header[2])
        data = output[offset : offset + size]
        if len(data) != size:
            raise VFXAssetFamilyContractError(REJECTION_CLASS, f"git cat-file blob truncated: {path}")
        offset += size
        if output[offset : offset + 1] == b"\n":
            offset += 1
        values.append((path, blob, data))
    return values


def _fingerprint(items: list[dict[str, str]]) -> str:
    comparable = [{"path": item["path"], "sha256": item["sha256"]} for item in items]
    return sha256_bytes(canonical_json(sorted(comparable, key=lambda item: item["path"])))


def validate_historical_root(
    repo_root: Path,
    authority_ref: str,
    relative_root: str,
    candidate_root: Path | None = None,
) -> dict[str, Any]:
    """Compare a candidate root with bytes resolved from an immutable git ref."""

    tracked_candidate = candidate_root is None
    candidate_root = candidate_root or repo_root / relative_root
    authority_tree = _authority_tree(repo_root, authority_ref, relative_root)
    entries = _authority_entries(repo_root, authority_ref, relative_root)
    paths = [path for path, _, _ in entries]
    authority_items: list[dict[str, str]] = []
    observed_items: list[dict[str, str]] = []
    failures: list[str] = []
    expected_relative = {str(Path(path).relative_to(relative_root)).replace("\\", "/") for path in paths}
    actual_paths = {
        str(path.relative_to(candidate_root)).replace("\\", "/")
        for path in candidate_root.rglob("*")
        if path.is_file()
    } if candidate_root.is_dir() and not tracked_candidate else expected_relative
    if actual_paths != expected_relative:
        failures.append("file-set")
    for path, authority_blob, authority in entries:
        relative = str(Path(path).relative_to(relative_root)).replace("\\", "/")
        candidate = candidate_root / Path(relative)
        observed = bytes(_git(repo_root, "show", f"HEAD:{path}")) if tracked_candidate else (candidate.read_bytes() if candidate.is_file() else b"")
        authority_sha = sha256_bytes(authority)
        observed_sha = sha256_bytes(observed)
        authority_items.append({"path": relative, "blob": authority_blob, "sha256": authority_sha})
        observed_items.append({"path": relative, "sha256": observed_sha})
        if authority != observed:
            failures.append(relative)
    authority_fingerprint = _fingerprint(authority_items)
    observed_fingerprint = _fingerprint(observed_items)
    if authority_fingerprint != observed_fingerprint:
        failures.append("fingerprint")
    if failures:
        raise VFXAssetFamilyContractError(REJECTION_CLASS, f"{authority_ref}:{relative_root}:{','.join(sorted(set(failures)))}")
    return {
        "status": "PASS",
        "authority_ref": authority_ref,
        "authority_root": relative_root,
        "authority_tree": authority_tree,
        "authority_fingerprint": authority_fingerprint,
        "observed_fingerprint": observed_fingerprint,
        "file_count": len(paths),
        "equality": True,
        "files": [{"path": item["path"], "authority_blob": item["blob"], "authority_sha256": item["sha256"], "observed_sha256": next(x["sha256"] for x in observed_items if x["path"] == item["path"]), "equal": True} for item in authority_items],
    }


def validate_historical_file(
    repo_root: Path,
    authority_ref: str,
    relative_path: str,
    candidate_path: Path | None = None,
) -> dict[str, Any]:
    tracked_candidate = candidate_path is None
    candidate_path = candidate_path or repo_root / relative_path
    authority = _authority_bytes(repo_root, authority_ref, relative_path)
    observed = bytes(_git(repo_root, "show", f"HEAD:{relative_path}")) if tracked_candidate else (candidate_path.read_bytes() if candidate_path.is_file() else b"")
    authority_blob = str(_git(repo_root, "rev-parse", f"{authority_ref}:{relative_path}", text=True)).strip()
    authority_sha = sha256_bytes(authority)
    observed_sha = sha256_bytes(observed)
    if authority != observed:
        raise VFXAssetFamilyContractError(REJECTION_CLASS, f"{authority_ref}:{relative_path}")
    return {
        "status": "PASS",
        "authority_ref": authority_ref,
        "path": relative_path,
        "authority_blob": authority_blob,
        "authority_sha256": authority_sha,
        "observed_sha256": observed_sha,
        "equality": True,
    }


def validate_historical_immutability(repo_root: Path, candidate_root: Path | None = None) -> dict[str, Any]:
    candidate_root = candidate_root or repo_root
    roots = [
        validate_historical_root(repo_root, "c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72", "docs/evidence/vfx-asset-family-runtime-v0230"),
        validate_historical_root(repo_root, "136079540f674c7467d93bd28e9834addbfce5c3", "docs/evidence/vfx-asset-family-runtime-v0231"),
    ]
    reviews = [
        validate_historical_file(repo_root, "c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72", "REVIEW-v0.23.0.md"),
        validate_historical_file(repo_root, "136079540f674c7467d93bd28e9834addbfce5c3", "REVIEW-v0.23.1.md"),
    ]
    return {"status": "PASS", "historical_evidence_unchanged": True, "roots": roots, "reviews": reviews}
