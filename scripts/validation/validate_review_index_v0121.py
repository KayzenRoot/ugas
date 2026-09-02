"""Validate the v0.12.1 review index using the runtime's canonical checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.observability.qa_integrity import validate_review_index


def validate(path: Path = ROOT / "docs/evidence/review-index-v0.12.1.json") -> dict[str, object]:
    result = validate_review_index(ROOT, path)
    result["status"] = "REVIEW_INDEX_V0121_PASSED" if result.get("status") == "PASS" else "REVIEW_INDEX_V0121_FAILED"
    return result


if __name__ == "__main__":
    result = validate(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/evidence/review-index-v0.12.1.json")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "REVIEW_INDEX_V0121_PASSED" else 1)
