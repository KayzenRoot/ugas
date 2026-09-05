"""Check the v0.20.0 bounded review artifact for forbidden material."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--artifact-dir", type=Path, required=True); parser.add_argument("--manifest", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    failures: list[str] = []
    forbidden_suffixes = {".safetensors", ".ckpt", ".gguf", ".onnx", ".sqlite", ".db"}
    for path in args.artifact_dir.rglob("*"):
        if path.is_file() and path.suffix.casefold() in forbidden_suffixes: failures.append(f"forbidden-file:{path.relative_to(args.artifact_dir).as_posix()}")
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        boundary = manifest.get("security_boundary", {})
        for key in ("secrets_included", "model_weights_included", "telemetry_db_included", "local_credentials_included"):
            if boundary.get(key) is not False: failures.append(f"security-boundary:{key}")
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"manifest:{type(exc).__name__}")
    result = {"schema_version": "0.20.0", "status": "PASS" if not failures else "FAIL", "failures": failures, "file_count": sum(1 for path in args.artifact_dir.rglob("*") if path.is_file())}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
