"""Validate already materialized v0.4.3 review evidence.

The old v0.4.2 helper could overwrite shared historical evidence. Review
materialization is now performed by ``ugas reference-edit pilot`` and this
compatibility entry point is deliberately read-only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.review import validate_review_visual_manifest


def main() -> int:
    path = ROOT / "docs/evidence/review-visuals-v0.4.3.json"
    if not path.is_file():
        print("missing v0.4.3 review manifest")
        return 2
    result = validate_review_visual_manifest(json.loads(path.read_text(encoding="utf-8")), ROOT)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
