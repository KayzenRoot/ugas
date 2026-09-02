"""Validate only the v0.12.3 visual transport manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_github_review_manifest import validate_visual_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="?", default=str(ROOT / "docs/evidence/github-review-v0123/visual-manifest.json"))
    parser.add_argument("--result-output")
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    try:
        visuals = json.loads(manifest_path.read_text(encoding="utf-8"))
        result = validate_visual_manifest(visuals, ROOT)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        result = {"status": "FAIL", "failures": [f"visual-manifest-read:{type(exc).__name__}:{exc}"], "visual_count": 0}
    if args.result_output:
        Path(args.result_output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
