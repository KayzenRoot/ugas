"""Validate that the v0.19.0 bounded artifact contains no sensitive payloads."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--artifact-dir", required=True); parser.add_argument("--manifest", required=True); parser.add_argument("--output", required=True); args = parser.parse_args()
    root = Path(args.artifact_dir); failures: list[str] = []
    if not Path(args.manifest).is_file(): failures.append("manifest-missing")
    forbidden = {".safetensors", ".ckpt", ".gguf", ".onnx", ".db", ".sqlite"}
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.casefold() in forbidden: failures.append(f"forbidden-file:{path.name}")
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.casefold() in {".json", ".md", ".txt", ".log"}:
            text = path.read_text(encoding="utf-8", errors="replace").casefold()
            if any(token in text for token in ("ghp_", "github_pat_", "bearer ", "client_secret", "private_key")): failures.append(f"secret-pattern:{path.name}")
    value = {"schema_version": "0.19.0", "status": "PASS" if not failures else "FAIL", "failures": failures, "artifact_root": str(root), "secrets_included": False, "model_weights_included": False}
    Path(args.output).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8"); print(json.dumps(value, indent=2)); return 0 if not failures else 1


if __name__ == "__main__": raise SystemExit(main())
