"""Fail-closed bounded-artifact security check for the v0.12.3 review flow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


FORBIDDEN_SUFFIXES = (".safetensors", ".ckpt", ".gguf", ".onnx", ".pth")
FORBIDDEN_NAMES = {"telemetry.db", ".env", ".env.local", ".env.production", "credentials.json"}
MAX_FILE_BYTES = 25 * 1024 * 1024


def validate(artifact_dir: Path, manifest_path: Path | None = None) -> dict[str, Any]:
    failures: list[str] = []
    if not artifact_dir.is_dir():
        failures.append("artifact-directory-missing")
    else:
        for path in artifact_dir.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(artifact_dir).as_posix()
            name = path.name.casefold()
            if name in FORBIDDEN_NAMES or name.endswith(FORBIDDEN_SUFFIXES):
                failures.append(f"forbidden-artifact:{relative}")
            if path.stat().st_size > MAX_FILE_BYTES:
                failures.append(f"artifact-too-large:{relative}")
    if manifest_path is not None:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for item in manifest.get("changed_files", []):
                path = str(item.get("path", ""))
                if path.startswith(("/", "\\")) or ":\\" in path or path.casefold().endswith(FORBIDDEN_SUFFIXES):
                    failures.append(f"forbidden-change-path:{path}")
            boundary = manifest.get("security_boundary", {})
            for key in ("secrets_included", "model_weights_included", "telemetry_db_included", "local_credentials_included"):
                if boundary.get(key) is not False:
                    failures.append(f"security-boundary-not-false:{key}")
        except (OSError, json.JSONDecodeError, TypeError, AttributeError) as exc:
            failures.append(f"manifest-read:{type(exc).__name__}:{exc}")
    return {"schema_version": "0.12.3", "status": "PASS" if not failures else "FAIL", "failures": failures, "artifact_dir": artifact_dir.as_posix()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--manifest")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = validate(Path(args.artifact_dir), Path(args.manifest) if args.manifest else None)
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
