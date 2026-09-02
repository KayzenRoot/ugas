"""Allowlisted repository file activity and safe media preview handling."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Any

MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
EXCLUDED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", "tmp", "build", "dist", ".ugas"}
SECRET_NAMES = {".env", ".env.local", ".env.production", "credentials.json", "secrets.json", "token.json"}
WEIGHT_SUFFIXES = {".safetensors", ".ckpt", ".gguf", ".onnx", ".pth"}
RUNTIME_ACTIVITY_EXCLUDED_NAMES = {"telemetry.db", "telemetry.db-wal", "telemetry.db-shm"}


@dataclass(frozen=True, slots=True)
class ApprovedRoot:
    key: str
    path: Path
    label: str


def approved_roots(repo_root: Path) -> tuple[ApprovedRoot, ...]:
    root = Path(repo_root).resolve()
    return (
        ApprovedRoot("runtime", root / ".ugas" / "runtime", "runtime"),
        ApprovedRoot("output", root / "output", "output"),
        ApprovedRoot("outputs", root / "outputs", "outputs"),
        ApprovedRoot("evidence", root / "docs" / "evidence", "evidence"),
        # Keep the broad repository root last so specific roots retain their
        # preview namespace and cannot be shadowed by this fallback.
        ApprovedRoot("repository", root, "repository"),
    )


def _encode(root_key: str, relative: str) -> str:
    raw = f"{root_key}:{relative}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode(value: str) -> tuple[str, str] | None:
    if not value or len(value) > 512 or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for character in value):
        return None
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("utf-8")
        key, relative = raw.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return None
    return key, relative


def classify_file(path: Path) -> str:
    suffix = path.suffix.casefold()
    name = path.name.casefold()
    if "spritesheet" in name or "sprite-sheet" in name:
        return "spritesheet"
    if suffix in MEDIA_TYPES:
        return "gif" if suffix == ".gif" else "image"
    if "manifest" in name or suffix == ".json" and "registry" in name:
        return "manifest"
    if "qa" in name or "validation" in name or "test" in name:
        return "qa"
    if "evidence" in name or "review" in name or "checkpoint" in name:
        return "evidence"
    if suffix in {".log", ".txt"}:
        return "log"
    if "model" in name or "provenance" in name:
        return "model_metadata"
    return "unknown"


def _is_excluded(path: Path, repo_root: Path, *, allow_runtime: bool = False) -> bool:
    try:
        relative = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return True
    excluded = EXCLUDED_DIRS - {".ugas"} if allow_runtime else EXCLUDED_DIRS
    return any(part.casefold() in excluded for part in relative.parts)


class AssetActivityTracker:
    def __init__(self, repo_root: Path, *, max_files: int = 20000) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.roots = approved_roots(self.repo_root)
        self.max_files = max(100, int(max_files))
        self._known: dict[str, dict[str, Any]] = {}
        self._bootstrapped = False

    def _iter_files(self):
        seen: set[str] = set()
        count = 0
        # Docker Desktop bind mounts can make a recursive repository walk very
        # expensive (especially across the Windows/VM boundary). The
        # container dashboard only needs operational activity: runtime files
        # and generated output roots. Native mode retains the full allowlisted
        # repository scan for local development and review diagnostics.
        roots = self.roots[:3] if os.environ.get("UGAS_CONTAINERIZED") == "1" else self.roots
        for root in roots:
            if not root.path.is_dir():
                continue
            for directory, dirs, files in os.walk(root.path, followlinks=False):
                dirs[:] = [item for item in dirs if item.casefold() not in EXCLUDED_DIRS]
                for filename in files:
                    # The telemetry database is an output of this observer;
                    # reporting its own writes would create an endless
                    # file-event -> telemetry-write feedback loop.
                    if root.key == "runtime" and filename.casefold() in RUNTIME_ACTIVITY_EXCLUDED_NAMES:
                        continue
                    path = Path(directory) / filename
                    if path.is_symlink() or _is_excluded(path, self.repo_root, allow_runtime=root.key == "runtime"):
                        continue
                    try:
                        canonical = str(path.resolve())
                    except OSError:
                        continue
                    if canonical in seen:
                        continue
                    seen.add(canonical); count += 1
                    if count > self.max_files:
                        return
                    yield root, path

    def _record(self, root: ApprovedRoot, path: Path, *, action: str, stat: os.stat_result, sha256: str | None) -> dict[str, Any]:
        relative = path.resolve().relative_to(root.path.resolve()).as_posix()
        project_relative = path.resolve().relative_to(self.repo_root).as_posix()
        media_type = MEDIA_TYPES.get(path.suffix.casefold())
        return {"safe_id": _encode(root.key, relative), "path": project_relative, "root": root.label, "file_kind": classify_file(path), "action": action, "size_bytes": stat.st_size, "mtime": stat.st_mtime, "sha256": sha256, "status": "STABLE" if sha256 else "STABILIZING", "media_type": media_type, "previewable": bool(media_type and root.key != "repository"), "timestamp": stat.st_mtime}

    @staticmethod
    def _hash(path: Path) -> str | None:
        try:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except OSError:
            return None

    def scan(self) -> list[dict[str, Any]]:
        current: dict[str, dict[str, Any]] = {}
        changes: list[dict[str, Any]] = []
        for root, path in self._iter_files() or ():
            try:
                stat = path.stat()
            except OSError:
                continue
            key = str(path.resolve())
            prior = self._known.get(key)
            same = bool(prior and prior.get("size") == stat.st_size and prior.get("mtime_ns") == stat.st_mtime_ns)
            sha256 = prior.get("sha256") if same and prior else None
            if not same:
                sha256 = None
            elif not sha256 and not (prior or {}).get("baseline"):
                sha256 = self._hash(path)
            current[key] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": sha256, "path": path, "root": root, "baseline": not self._bootstrapped and prior is None}
            if self._bootstrapped and (prior is None or not same):
                changes.append(self._record(root, path, action="created" if prior is None else "updated", stat=stat, sha256=sha256))
            elif self._bootstrapped and prior and same and not prior.get("sha256") and sha256:
                stable = self._record(root, path, action="stable", stat=stat, sha256=sha256)
                stable["transition"] = "STABILIZING->STABLE"
                changes.append(stable)
        self._known = current
        self._bootstrapped = True
        return changes

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = min(max(int(limit), 1), 500)
        items: list[dict[str, Any]] = []
        for item in self._known.values():
            path = item["path"]
            try:
                stat = path.stat()
            except OSError:
                continue
            items.append(self._record(item["root"], path, action="observed", stat=stat, sha256=item.get("sha256")))
        return sorted(items, key=lambda value: value["mtime"], reverse=True)[:limit]

    def resolve_preview(self, safe_id: str) -> tuple[Path, str] | None:
        decoded = _decode(safe_id)
        if decoded is None:
            return None
        key, relative = decoded
        root = next((item for item in self.roots if item.key == key and item.key != "repository"), None)
        if root is None or not relative or "\x00" in relative:
            return None
        candidate = (root.path / Path(relative)).resolve()
        try:
            candidate.relative_to(root.path.resolve())
        except ValueError:
            return None
        if candidate.name.casefold() in SECRET_NAMES or candidate.name.casefold().startswith(".env") or candidate.suffix.casefold() in WEIGHT_SUFFIXES or candidate.suffix.casefold() not in MEDIA_TYPES or not candidate.is_file() or candidate.is_symlink():
            return None
        return candidate, MEDIA_TYPES[candidate.suffix.casefold()]
