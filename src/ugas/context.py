"""Bounded, explainable consumer project inspection."""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path


SKIP_DIRECTORIES = {
    ".git", "node_modules", "library", "temp", "logs", "obj", "bin", "build", "dist", ".cache",
    ".venv", "venv", "models", "outputs", "review", ".next", ".nuxt", "target", "coverage",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".idea", ".vscode",
}
MAX_SCAN_FILES = 5000
MAX_SCAN_DIRECTORIES = 512
PACKAGE_READ_BYTES = 256 * 1024


@dataclass(frozen=True)
class ProjectContext:
    root: str
    engine: str
    language: str
    dimension: str
    detected_files: list[str]
    confidence: str
    profile_recommendation: str | None
    profile_confidence: str
    profile_evidence: list[str]
    scan_summary: dict

    def to_dict(self) -> dict:
        return asdict(self)


def _bounded_scan(root: Path) -> tuple[list[str], dict]:
    evidence: set[str] = set()
    skipped = Counter()
    files_scanned = 0
    directories_scanned = 0
    truncated = False
    if not root.exists() or not root.is_dir():
        return [], {"files_scanned": 0, "directories_scanned": 0, "skipped_directories": {}, "truncated": False, "max_files": MAX_SCAN_FILES, "max_directories": MAX_SCAN_DIRECTORIES}

    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        directories_scanned += 1
        kept: list[str] = []
        for dirname in sorted(dirnames, key=str.casefold):
            lowered = dirname.casefold()
            if lowered in SKIP_DIRECTORIES:
                skipped[dirname] += 1
                continue
            directory = Path(current) / dirname
            if directory.is_symlink():
                skipped[dirname] += 1
                continue
            if directories_scanned + len(kept) >= MAX_SCAN_DIRECTORIES:
                truncated = True
                skipped[dirname] += 1
                continue
            kept.append(dirname)
        dirnames[:] = kept
        for filename in sorted(filenames, key=str.casefold):
            if files_scanned >= MAX_SCAN_FILES:
                truncated = True
                dirnames[:] = []
                break
            files_scanned += 1
            path = Path(current) / filename
            if path.is_symlink():
                continue
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if relative == "project.godot" or relative == "package.json" or relative == "ProjectSettings/ProjectVersion.txt" or relative.endswith(".uproject"):
                evidence.add(relative)
    summary = {
        "files_scanned": files_scanned,
        "directories_scanned": directories_scanned,
        "skipped_directories": dict(sorted(skipped.items(), key=lambda item: item[0].casefold())),
        "truncated": truncated,
        "max_files": MAX_SCAN_FILES,
        "max_directories": MAX_SCAN_DIRECTORIES,
    }
    return sorted(evidence), summary


def _package_signals(root: Path) -> tuple[set[str], list[str]]:
    package_path = root / "package.json"
    if not package_path.is_file() or package_path.is_symlink():
        return set(), []
    try:
        raw = package_path.read_bytes()[:PACKAGE_READ_BYTES]
        package = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return set(), ["package.json present but dependencies could not be parsed"]
    names: set[str] = set()
    for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        values = package.get(field, {})
        if isinstance(values, dict):
            names.update(str(name).casefold() for name in values)
    known = {"phaser", "pixi.js", "@pixi/core", "three", "@babylonjs/core"}
    return names, [f"package.json dependency {name}" for name in sorted(names) if name in known]


def _profile_recommendation(engine: str, dimension: str, evidence: list[str], requested_profile: str | None) -> tuple[str | None, str, list[str]]:
    if requested_profile:
        return requested_profile, "high", ["explicit profile selection"]
    if engine in {"phaser", "pixijs"}:
        return "generic-2d", "medium", evidence or [f"engine {engine}"]
    if engine in {"threejs", "babylonjs"}:
        return "stylized-3d", "medium", evidence or [f"engine {engine}"]
    if dimension == "2d":
        return "generic-2d", "low", evidence or ["explicit 2D dimension"]
    if dimension == "3d":
        return "stylized-3d", "low", evidence or ["explicit 3D dimension"]
    return None, "unknown", []


def resolve_project_context(
    root: Path,
    requested_dimension: str | None = None,
    requested_profile: str | None = None,
) -> ProjectContext:
    root = root.resolve()
    detected_files, scan_summary = _bounded_scan(root)
    evidence: list[str] = list(detected_files)
    package_names, package_evidence = _package_signals(root)
    evidence.extend(package_evidence)

    project_godot = "project.godot" in detected_files
    unity_project = "ProjectSettings/ProjectVersion.txt" in detected_files
    unreal_project = any(name.endswith(".uproject") for name in detected_files)
    if project_godot:
        engine, language, confidence = "godot", "GDScript", "high"
    elif unity_project:
        engine, language, confidence = "unity", "C#", "high"
    elif unreal_project:
        engine, language, confidence = "unreal", "C++/Blueprints", "high"
    elif "phaser" in package_names:
        engine, language, confidence = "phaser", "JavaScript/TypeScript", "medium"
    elif "pixi.js" in package_names or "@pixi/core" in package_names:
        engine, language, confidence = "pixijs", "JavaScript/TypeScript", "medium"
    elif "three" in package_names:
        engine, language, confidence = "threejs", "JavaScript/TypeScript", "medium"
    elif "@babylonjs/core" in package_names:
        engine, language, confidence = "babylonjs", "JavaScript/TypeScript", "medium"
    elif "package.json" in detected_files:
        engine, language, confidence = "web-or-custom", "JavaScript/TypeScript", "low"
    elif (root / "Cargo.toml").is_file():
        engine, language, confidence = "custom", "Rust", "low"
    elif (root / "pyproject.toml").is_file():
        engine, language, confidence = "custom", "Python", "low"
    else:
        engine, language, confidence = "unknown", "unknown", "low"

    if requested_dimension is not None and requested_dimension not in {"2d", "3d", "unknown"}:
        raise ValueError("dimension must be one of: 2d, 3d, unknown")
    if requested_dimension:
        dimension = requested_dimension
    elif engine in {"phaser", "pixijs"}:
        dimension = "2d"
    elif engine in {"threejs", "babylonjs"}:
        dimension = "3d"
    else:
        dimension = "unknown"
    profile_recommendation, profile_confidence, profile_evidence = _profile_recommendation(engine, dimension, evidence, requested_profile)
    return ProjectContext(
        root=str(root),
        engine=engine,
        language=language,
        dimension=dimension,
        detected_files=sorted(set(detected_files + package_evidence))[:50],
        confidence=confidence,
        profile_recommendation=profile_recommendation,
        profile_confidence=profile_confidence,
        profile_evidence=profile_evidence,
        scan_summary=scan_summary,
    )
