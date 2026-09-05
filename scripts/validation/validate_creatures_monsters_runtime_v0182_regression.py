"""Read-only regression check for the frozen v0.18.2 creatures foundation."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.creature_runtime_v0182 import validate_creature_manifest  # noqa: E402
from ugas.schema_validation import validate_instance  # noqa: E402


def main() -> int:
    evidence = ROOT / "docs/evidence/creatures-monsters-runtime-v0182"
    failures: list[str] = []
    try:
        manifest = json.loads((evidence / "creature-runtime-manifest-v0182.json").read_text(encoding="utf-8"))
        schema = json.loads((ROOT / "schemas/creature-runtime-v0182.json").read_text(encoding="utf-8"))
        validate_instance(manifest, schema)
        validate_creature_manifest(manifest)
        execution = json.loads((evidence / "execution-evidence-v0182.json").read_text(encoding="utf-8"))
        if execution.get("status") != "CREATURES_MONSTERS_DERIVED_VARIANT_AND_STATE_CONTRACT_TECHNICALLY_QUALIFIED" or execution.get("failed") != 0:
            failures.append("execution")
    except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
        failures.append(f"exception:{type(exc).__name__}:{exc}")
    result = {"status": "V0182_REGRESSION_PASSED" if not failures else "V0182_REGRESSION_FAILED", "failures": failures, "read_only": True}
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
