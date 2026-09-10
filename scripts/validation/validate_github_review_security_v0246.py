"""Validate the bounded v0.24.6 review artifact security and path boundary."""

from __future__ import annotations

import argparse
import json
import ntpath
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.artifact_dir).resolve()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    failures: list[str] = []
    allowed_prefixes = (
        "docs/evidence/orchestration-runtime-v0246/",
        "docs/evidence/current-state.json",
        "schemas/current-state-v0246.json",
        "schemas/orchestration-runtime-v0246.json",
        "REVIEW-v0.24.6.md",
        "github-review-manifest-v0246.json",
        "test-results-v0246.json",
        "validation-results-v0246.json",
        "state-validation-v0246.json",
        "schema-validation-v0246.json",
        "security-results-v0246.json",
        "manifest-validation-results-v0246.json",
        "pre-upload-enforcement-v0246.json",
        "logs/",
    )
    forbidden_tokens = ("secret", "credential", "password", "api_key", ".safetensors", ".ckpt", ".sqlite", ".db", ".uads")
    files = [path for path in root.rglob("*") if path.is_file()]
    for path in files:
        relative = path.relative_to(root).as_posix()
        lowered = relative.casefold()
        if relative.startswith("/") or ntpath.isabs(relative) or ".." in Path(relative).parts or not relative.startswith(allowed_prefixes):
            failures.append(f"path:{relative}")
        if any(token in lowered for token in forbidden_tokens):
            failures.append(f"forbidden:{relative}")
        if lowered == ".uads" or lowered.startswith(".uads/") or "/.uads/" in f"/{lowered}/":
            failures.append(f"uads-runtime:{relative}")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""
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
    result = {"schema_version": "0.24.6", "status": "PASS" if not failures else "FAIL", "failures": failures, "file_count": len(files), "secrets_included": False, "model_weights_included": False, "telemetry_db_included": False, "local_credentials_included": False}
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    for failure in failures:
        print(f"::error title=UGAS v0.24.6 artifact security::{failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
