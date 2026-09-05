"""Read-only regression check for the approved v0.15.1 front animation."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/animation-runtime-v0151"


def main() -> int:
    execution = json.loads((EVIDENCE / "execution-evidence-v0.15.1.json").read_text(encoding="utf-8"))
    failures = []
    if execution.get("status") != "CUTOUT_ANIMATION_RUNTIME_V1_DEATH_ANIMATION_FRONT_V0151_TECHNICALLY_QUALIFIED":
        failures.append("status")
    for key, expected in (("new_generation", 0), ("production_approved", False), ("production_routing", "BLOCKED"), ("source_only_pixels", True), ("sam2_runs", 0), ("comfyui_generation_jobs", 0), ("diffusion_runs", 0)):
        if execution.get(key) != expected:
            failures.append(key)
    if execution.get("approved_assets_untouched") != "APPROVED_ASSETS_UNTOUCHED" or execution.get("frozen_evidence_integrity") != "FROZEN_V0141_EVIDENCE_RESTORED_AND_VERIFIED":
        failures.append("approved-assets-boundary")
    result = {"status": "V0151_FRONT_REGRESSION_PASSED" if not failures else "V0151_FRONT_REGRESSION_FAILED", "failures": failures, "read_only": True}
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
