"""Exact, license-aware model registry helpers for local render nodes."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Iterable


class ModelRegistryError(RuntimeError):
    pass


def validate_model_workflow_compatibility(model: dict, workflow: dict, *, allow_experimental: bool = False) -> dict:
    """Reject Base/Distilled parameter mismatches before a ComfyUI submission."""
    family = model.get("family")
    workflow_family = workflow.get("model_family", family)
    variant = model.get("variant")
    workflow_variant = workflow.get("model_variant", variant)
    steps = workflow.get("parameters", {}).get("steps")
    guidance = workflow.get("parameters", {}).get("guidance")
    capability_parameters = model.get("capability_parameters", {}).get(workflow.get("capability"), {})
    expected_steps = capability_parameters.get("steps", model.get("recommended_steps"))
    expected_guidance = capability_parameters.get("guidance", model.get("recommended_guidance"))
    mismatches = []
    if family != workflow_family:
        mismatches.append("model family differs from workflow family")
    if variant != workflow_variant:
        mismatches.append("model variant differs from workflow variant")
    if expected_steps is not None and steps != expected_steps:
        mismatches.append(f"{variant} expects steps={expected_steps}, workflow has steps={steps}")
    if expected_guidance is not None and float(guidance) != float(expected_guidance):
        mismatches.append(f"{variant} expects guidance={expected_guidance}, workflow has guidance={guidance}")
    experimental = bool(workflow.get("experimental_override"))
    if mismatches and not (allow_experimental and experimental):
        raise ModelRegistryError("incompatible model/workflow: " + "; ".join(mismatches))
    return {
        "compatible": not mismatches or (allow_experimental and experimental),
        "model_id": model.get("id"),
        "workflow_id": workflow.get("id"),
        "family": family,
        "variant": variant,
        "steps": steps,
        "guidance": guidance,
        "mismatches": mismatches,
        "experimental_override": bool(mismatches and allow_experimental and experimental),
    }


def load_registry(repo_root: Path) -> dict:
    path = repo_root / "providers" / "models" / "registry.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_model(repo_root: Path, model_id: str) -> dict:
    registry = load_registry(repo_root)
    for model in registry.get("models", []):
        if model.get("id") == model_id:
            return model
    raise ModelRegistryError(f"Unknown model id: {model_id}")


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_files(model: dict, model_root: Path) -> dict:
    """Verify every exact file and hash recorded by the manifest.

    An absent or hashless file is never considered qualified. This is deliberately
    stricter than a ComfyUI inventory because filenames alone do not prove identity.
    """
    checks = []
    all_ok = True
    expected_hashes = model.get("sha256", {})
    for relative in model.get("exact_files", []):
        path = model_root / relative
        expected = expected_hashes.get(relative)
        actual = file_sha256(path) if path.is_file() else None
        ok = bool(actual and expected and actual.casefold() == str(expected).casefold())
        all_ok = all_ok and ok
        checks.append({"file": relative, "present": path.is_file(), "expected_sha256": expected, "actual_sha256": actual, "ok": ok})
    license_ok = model.get("commercial_use_status") == "approved"
    return {"model_id": model.get("id"), "files": checks, "hashes_verified": all_ok, "license_approved": license_ok, "qualified": all_ok and license_ok}


def inventory_matches(model: dict, inventory: dict[str, list[str]]) -> dict:
    checks = []
    ok = True
    for relative in model.get("exact_files", []):
        folder = next((folder for folder, value in model.get("model_folders", {}).items() if value == relative.split("/", 1)[0]), None)
        basename = Path(relative).name
        available = inventory.get(folder or "", [])
        present = basename in available or relative in available
        checks.append({"file": relative, "folder": folder, "present": present})
        ok = ok and present
    return {"model_id": model.get("id"), "files": checks, "inventory_complete": ok}


def download_exact(url: str, destination: Path, expected_sha256: str, timeout: float = 60.0) -> dict:
    """Download one explicitly registered file, never silently accepting a mismatch."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
        actual = digest.hexdigest()
        if actual.casefold() != expected_sha256.casefold():
            temporary.unlink(missing_ok=True)
            raise ModelRegistryError(f"SHA256 mismatch for {destination.name}: {actual}")
        temporary.replace(destination)
        return {"path": str(destination), "sha256": actual, "verified": True}
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
