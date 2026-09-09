"""Validate the v0.24.0 bounded artifact and security boundary."""

from __future__ import annotations

import argparse
import json
import ntpath
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--artifact-dir", required=True); parser.add_argument("--manifest", required=True); parser.add_argument("--output", required=True); args = parser.parse_args()
    root = Path(args.artifact_dir).resolve(); manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8")); failures: list[str] = []
    allowed_prefixes = ("docs/evidence/orchestration-runtime-v0240/", "docs/evidence/current-state.json", "schemas/current-state-v0240.json", "schemas/orchestration-runtime-v0240.json", "REVIEW-v0.24.0.md", "github-review-manifest-v0240.json", "logs/")
    forbidden_tokens = ("secret", "credential", "password", "token", ".safetensors", ".ckpt", ".sqlite", ".db")
    for path in root.rglob("*"):
        if not path.is_file(): continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith("/") or ntpath.isabs(relative) or ".." in Path(relative).parts or not relative.startswith(allowed_prefixes): failures.append(f"path:{relative}")
        if any(token in relative.casefold() for token in forbidden_tokens): failures.append(f"forbidden:{relative}")
    if manifest.get("overall_status") != "PASS": failures.append("manifest-overall")
    boundary = manifest.get("production_boundary", {})
    if boundary.get("approved") is not False or boundary.get("routing") != "BLOCKED" or boundary.get("new_generation") != 0: failures.append("production-boundary")
    result = {"schema_version": "0.24.0", "status": "PASS" if not failures else "FAIL", "failures": failures, "file_count": sum(1 for path in root.rglob("*") if path.is_file()), "secrets_included": False, "model_weights_included": False, "telemetry_db_included": False}
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); print(json.dumps(result, ensure_ascii=False)); return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
