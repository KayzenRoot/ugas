"""Validate the frozen v0.24.7 orchestration state and its forward-only correction binding."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.state_consistency_v0247 import validate_state_consistency

FROZEN_ROOT = ROOT / "docs/evidence/orchestration-runtime-v0247"
FROZEN_AUTHORITY_COMMIT = "6c6d53dab5a95226bf9578a6099d755d51327d8e"
FROZEN_SOURCES = {
    "state": ("docs/evidence/current-state.json", "state-snapshot-v0247.json"),
    "matrix": ("docs/ugas-v1-capability-matrix.json", "matrix-snapshot-v0247.json"),
}
FROZEN_DOCUMENTS = {"checkpoint": ("CHECKPOINT.md", "checkpoint_text"), "roadmap": ("docs/roadmap.md", "roadmap_text")}


def _normalized_bytes(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def validate_frozen_snapshots() -> list[str]:
    """Prove the frozen v0.24.7 snapshots still equal their authority-commit sources when Git is present.

    In an isolated no-git snapshot the historical Git authority is intentionally absent; the
    committed snapshot bytes remain the frozen authority and are re-bound by the acceptance run.
    """

    failures: list[str] = []
    if not (ROOT / ".git").exists():
        return failures
    for label, (source, snapshot) in FROZEN_SOURCES.items():
        result = subprocess.run(["git", "show", f"{FROZEN_AUTHORITY_COMMIT}:{source}"], cwd=ROOT, capture_output=True, check=False)
        if result.returncode != 0:
            failures.append(f"{label}:git-source-unavailable")
            continue
        if _normalized_bytes(result.stdout) != _normalized_bytes((FROZEN_ROOT / snapshot).read_bytes()):
            failures.append(f"{label}:snapshot-mutated")
    docs = json.loads((FROZEN_ROOT / "tracked-docs-snapshot-v0247.json").read_text(encoding="utf-8"))
    for label, (source, key) in FROZEN_DOCUMENTS.items():
        result = subprocess.run(["git", "show", f"{FROZEN_AUTHORITY_COMMIT}:{source}"], cwd=ROOT, capture_output=True, check=False)
        if result.returncode != 0:
            failures.append(f"{label}:git-source-unavailable")
            continue
        if _normalized_bytes(result.stdout) != _normalized_bytes(str(docs.get(key, "")).encode("utf-8")):
            failures.append(f"{label}:snapshot-mutated")
    return failures


def main() -> int:
    state = json.loads((FROZEN_ROOT / "state-snapshot-v0247.json").read_text(encoding="utf-8"))
    matrix = json.loads((FROZEN_ROOT / "matrix-snapshot-v0247.json").read_text(encoding="utf-8"))
    tracked_docs = json.loads((FROZEN_ROOT / "tracked-docs-snapshot-v0247.json").read_text(encoding="utf-8"))
    binding_path = FROZEN_ROOT / "correction-history-v0247.json"
    binding = json.loads(binding_path.read_text(encoding="utf-8")) if binding_path.is_file() else None
    result = validate_state_consistency(state, str(tracked_docs.get("checkpoint_text", "")), str(tracked_docs.get("roadmap_text", "")), matrix, binding, state.get("evidence", {}))
    result["frozen_snapshot_failures"] = validate_frozen_snapshots()
    if result["frozen_snapshot_failures"]:
        result["status"] = "ORCHESTRATION_STATE_FAILED"
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] != "ORCHESTRATION_STATE_FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
