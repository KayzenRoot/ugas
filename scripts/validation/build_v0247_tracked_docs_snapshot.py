"""Freeze the v0.24.7 tracked CHECKPOINT/roadmap text from the git authority.

The active documents advance forward-only to v0.25.0, so the v0.24.7 state
validator must keep validating the *frozen* v0.24.7 documents instead of the
live forward-advanced ones.  This script records an immutable copy taken from
the governed merge commit so the historical validator never depends on
mutable active files.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_COMMIT = "6c6d53dab5a95226bf9578a6099d755d51327d8e"
OUTPUT = ROOT / "docs/evidence/orchestration-runtime-v0247/tracked-docs-snapshot-v0247.json"
SOURCES = {"checkpoint": "CHECKPOINT.md", "roadmap": "docs/roadmap.md"}


def _blob(relative: str) -> str:
    result = subprocess.run(["git", "show", f"{AUTHORITY_COMMIT}:{relative}"], cwd=ROOT, capture_output=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"cannot read {relative} at {AUTHORITY_COMMIT}: {result.stderr.decode(errors='replace')[-200:]}")
    return result.stdout.decode("utf-8")


def main() -> int:
    texts = {name: _blob(relative) for name, relative in SOURCES.items()}
    payload = {
        "schema_version": "0.24.7",
        "authority_commit": AUTHORITY_COMMIT,
        "authority_source": "git show <authority_commit>:<path>",
        "sources": SOURCES,
    }
    for name, text in texts.items():
        payload[f"{name}_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        payload[f"{name}_text"] = text
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "V0247_TRACKED_DOCS_FROZEN", "path": OUTPUT.relative_to(ROOT).as_posix(), "checkpoint_sha256": payload["checkpoint_sha256"], "roadmap_sha256": payload["roadmap_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())