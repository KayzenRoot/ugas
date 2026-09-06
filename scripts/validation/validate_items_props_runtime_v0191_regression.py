"""Read-only regression check for the frozen v0.19.1 Items/Props foundation."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.item_prop_runtime_v0191 import load_equipment_authority, validate_item_prop_manifest  # noqa: E402
from ugas.schema_validation import validate_instance  # noqa: E402


def main() -> int:
    evidence = ROOT / "docs/evidence/items-props-runtime-v0191"
    manifest = json.loads((evidence / "item-prop-runtime-manifest-v0191.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/item-prop-runtime-v0191.json").read_text(encoding="utf-8"))
    validate_instance(manifest, schema)
    authority = load_equipment_authority(ROOT / "docs/evidence/equipment-outfits-runtime-v0171/synthetic-fixture-manifest-v0171.json")
    validate_item_prop_manifest(manifest, artifact_root=evidence, equipment_authority=authority)
    print(json.dumps({"status": "FROZEN_V0191_ITEMS_PROPS_REGRESSION_PASSED", "manifest": "items-props-runtime-v0191", "mutated": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
