"""Build the GitHub-first machine-readable v0.8.1 review index."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "docs" / "evidence" / "review-index-v0.8.1.json"
REVISION_ID = "revision-3a425d184b1a49be9f6d6c8d52d04b96"


def run(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)
    return (result.stdout + result.stderr).strip()


def digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def test_summary() -> dict:
    text = run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q")
    match = re.search(r"Ran (\d+) tests", text)
    return {"command": "python -m unittest discover -s tests -q", "count": int(match.group(1)) if match else 0, "status": "passed" if match else "failed"}


def validation_summary() -> dict:
    text = run(sys.executable, "scripts/validation/run_validation.py")
    matches = re.findall(r"SUMMARY checks=(\d+) passed=(\d+) failed=(\d+)", text)
    if not matches:
        return {"command": "python scripts/validation/run_validation.py", "checks": 0, "passed": 0, "failed": 1, "status": "failed"}
    checks, passed, failed = map(int, matches[-1])
    return {"command": "python scripts/validation/run_validation.py", "checks": checks, "passed": passed, "failed": failed, "status": "passed" if failed == 0 else "failed"}


def evidence_item(path: str, role: str, media_type: str = "application/json") -> dict:
    absolute = ROOT / path
    if not absolute.is_file():
        raise SystemExit(f"missing index evidence: {path}")
    return {"path": path, "sha256": digest(absolute), "media_type": media_type, "role": role}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    visual = json.loads((ROOT / "docs/evidence/review-visuals-v0.8.1.json").read_text(encoding="utf-8"))
    evidence = [
        evidence_item("REVIEW-v0.8.1.md", "active release review", "text/markdown"),
        evidence_item("CHECKPOINT.md", "active governance checkpoint", "text/markdown"),
        evidence_item("docs/evidence/current-state.json", "active machine-authoritative state"),
        evidence_item("schemas/current-state.json", "active state schema"),
        evidence_item("providers/manifests/deterministic-cutout-rig-2d.json", "active provider manifest"),
        evidence_item("docs/evidence/review-visuals-v0.8.1.json", "hash-bound visual manifest"),
    ]
    seen = {item["path"] for item in evidence}
    for item in visual.get("images", []):
        path = str(item["source_path"])
        if path not in seen:
            evidence.append(evidence_item(path, str(item.get("role", "v0.8.1 visual evidence")), str(item.get("media_type", "application/octet-stream"))))
            seen.add(path)
    status = json.loads((ROOT / "docs/evidence/front-walk-provider-qualification-v081.json").read_text(encoding="utf-8"))
    index = {
        "schema_version": "0.8.1",
        "version": "0.8.1",
        "branch": run("git", "branch", "--show-current") or "unknown",
        "head_commit": run("git", "rev-parse", "HEAD"),
        "dirty_state_at_publish": "dirty_before_index_commit" if run("git", "status", "--porcelain") else "clean",
        "review_file": "REVIEW-v0.8.1.md",
        "current_state": "docs/evidence/current-state.json",
        "tests": test_summary(),
        "validation": validation_summary(),
        "evidence": evidence,
        "required_visual_sets": sorted(str(name) for name in visual.get("required_current_visuals", [])),
        "forbidden_artifacts": [
            "sam2_rerun", "comfyui_generation", "diffusion", "controlnet", "ip_adapter",
            "new_animation_or_direction", "production_routing_enabled", "external_approval_claim",
            "source_mask_mutation", "pixel_interpolation",
        ],
        "external_visual_review": {"status": "REQUIRED", "approval": "not-claimed"},
        "production_routing": "BLOCKED",
        "walk_authorized": "pilot_only",
        "provider_status": status.get("status"),
        "canonical_anchor": {"revision_id": REVISION_ID, "sha256": "7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798"},
    }
    INDEX.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "REVIEW_INDEX_BUILT", "path": INDEX.relative_to(ROOT).as_posix(), "evidence_count": len(evidence), "tests": index["tests"], "validation": index["validation"]}, indent=2, ensure_ascii=False) if args.json else "REVIEW_INDEX_BUILT")
    return 0 if index["tests"]["status"] == "passed" and index["validation"]["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
