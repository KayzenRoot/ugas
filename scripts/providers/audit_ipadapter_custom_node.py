"""Audit and optionally install only the exact IP-Adapter custom-node commit.

The audit runs in a temporary directory and never vendors upstream source in
UGAS. Installation is intentionally a separate explicit flag and is blocked
unless the audit result is clean.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SOURCE = "https://github.com/cubiq/ComfyUI_IPAdapter_plus.git"
COMMIT = "a0f451a5113cf9becb0847b92884cb10cbdec0ef"
LICENSE = "GPL-3.0-only"
EVIDENCE = ROOT / "docs" / "evidence" / "custom-node-audit-ipadapter-plus.json"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    result = subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=False, timeout=180)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _python_audit(path: Path) -> dict[str, Any]:
    imports: list[str] = []
    calls: list[str] = []
    syntax_failures: list[str] = []
    for source_file in path.rglob("*.py"):
        try:
            tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        except (OSError, SyntaxError) as exc:
            syntax_failures.append(f"{source_file.name}: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.append(f"{node.func.attr}")
    blocked_imports = sorted({name for name in imports if name.split(".", 1)[0] in {"subprocess", "socket", "requests", "urllib", "httpx", "ftplib", "paramiko"}})
    blocked_calls = sorted({name for name in calls if name in {"eval", "exec", "compile", "system", "Popen", "run"}})
    unsafe_serialization = sorted({name for name in calls if name == "load"})
    return {
        "python_files": len(list(path.rglob("*.py"))),
        "syntax_failures": syntax_failures,
        "imports": sorted(set(imports)),
        "blocked_network_or_process_imports": blocked_imports,
        "blocked_dynamic_or_process_calls": blocked_calls,
        "local_serialization_load_calls": unsafe_serialization,
    }


def audit() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ugas-ipadapter-audit-") as temporary:
        checkout = Path(temporary) / "ComfyUI_IPAdapter_plus"
        clone_code, clone_out, clone_err = _run(["git", "clone", "--quiet", SOURCE, str(checkout)])
        if clone_code != 0:
            return {"schema_version": "0.6.0", "audit_status": "IPADAPTER_CUSTOM_NODE_SECURITY_GAP", "source": SOURCE, "commit": COMMIT, "error": f"clone failed: {clone_err or clone_out}"}
        checkout_code, checkout_out, checkout_err = _run(["git", "checkout", "--quiet", COMMIT], checkout)
        actual_code, actual_commit, actual_err = _run(["git", "rev-parse", "HEAD"], checkout)
        tracked_code, tracked, _ = _run(["git", "status", "--porcelain"], checkout)
        py_audit = _python_audit(checkout)
        files = sorted(str(item.relative_to(checkout)).replace("\\", "/") for item in checkout.rglob("*") if item.is_file() and ".git" not in item.parts)
        required = {"LICENSE", "pyproject.toml", "__init__.py", "IPAdapterPlus.py", "CrossAttentionPatch.py", "image_proj_models.py", "utils.py"}
        missing = sorted(required - set(files))
        pyproject = (checkout / "pyproject.toml").read_text(encoding="utf-8") if (checkout / "pyproject.toml").is_file() else ""
        source_hashes = {relative: _sha256(checkout / relative) for relative in files if relative.endswith((".py", ".toml", "LICENSE"))}
        failures: list[str] = []
        if clone_code or checkout_code or actual_code or actual_commit != COMMIT:
            failures.append("exact_commit_checkout_failed")
        if tracked_code or tracked:
            failures.append("checkout_is_dirty")
        if missing:
            failures.append("required_source_files_missing")
        if py_audit["syntax_failures"]:
            failures.append("python_syntax_failure")
        if py_audit["blocked_network_or_process_imports"] or py_audit["blocked_dynamic_or_process_calls"]:
            failures.append("network_or_process_capability_detected")
        if "GPL-3.0" not in pyproject:
            failures.append("declared_license_not_found_in_pyproject")
        return {
            "schema_version": "0.6.0",
            "audit_status": "CUSTOM_NODE_AUDIT_PASSED" if not failures else "IPADAPTER_CUSTOM_NODE_SECURITY_GAP",
            "audited_at": _now(),
            "source": SOURCE,
            "commit": COMMIT,
            "actual_commit": actual_commit or None,
            "license": LICENSE,
            "distribution_boundary": "local-only",
            "source_vendored_in_ugas": False,
            "required_source_files": sorted(required),
            "missing_source_files": missing,
            "source_file_sha256": source_hashes,
            "python_static_audit": py_audit,
            "network_access": "not detected in Python source",
            "subprocess_access": "not detected in Python source",
            "credential_access": "not detected in Python source",
            "dynamic_download": "not detected in Python source",
            "local_file_io": "model path registration, local model loading and optional local output/embed files",
            "residual_risks": [
                "IPAdapterLoadEmbeds uses torch.load on a local .ipadpt file; this optional node is not used by the qualified workflow and untrusted embed files must not be loaded.",
                "The GPL-3.0 source remains outside UGAS distribution and is locally removable.",
            ],
            "failures": failures,
            "install_allowed": not failures,
            "install_path": "<ComfyUI>/custom_nodes/ComfyUI_IPAdapter_plus",
            "required_nodes": ["IPAdapterModelLoader", "IPAdapterAdvanced", "IPAdapterApply", "IPAdapterUnifiedLoader"],
        }


def install(audit_result: dict[str, Any], target: Path) -> dict[str, Any]:
    if audit_result.get("audit_status") != "CUSTOM_NODE_AUDIT_PASSED" or audit_result.get("commit") != COMMIT:
        raise RuntimeError("custom-node installation blocked: audit did not pass for the exact commit")
    if target.exists():
        existing_code, existing_commit, _ = _run(["git", "rev-parse", "HEAD"], target)
        if existing_code != 0 or existing_commit != COMMIT:
            raise RuntimeError(f"refusing to overwrite non-pinned custom node: {target}")
        return {"status": "ALREADY_INSTALLED_PINNED", "path": str(target), "commit": existing_commit}
    target.parent.mkdir(parents=True, exist_ok=True)
    code, out, err = _run(["git", "clone", "--quiet", SOURCE, str(target)])
    if code != 0:
        raise RuntimeError(f"custom-node clone failed: {err or out}")
    code, out, err = _run(["git", "checkout", "--quiet", COMMIT], target)
    if code != 0:
        raise RuntimeError(f"custom-node checkout failed: {err or out}")
    return {"status": "INSTALLED_PINNED", "path": str(target), "commit": COMMIT}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--comfy-root", type=Path, default=Path.home() / "AppData" / "Local" / "UGAS" / "comfyui")
    args = parser.parse_args()
    result = audit()
    if args.install and result.get("audit_status") == "CUSTOM_NODE_AUDIT_PASSED":
        target = args.comfy_root / "custom_nodes" / "ComfyUI_IPAdapter_plus"
        result["installation"] = install(result, target)
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("audit_status") == "CUSTOM_NODE_AUDIT_PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
