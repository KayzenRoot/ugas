"""Check the remote Render Node contract without inspecting local GPU state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.providers import remote_render_node_healthcheck


def main() -> int:
    parser = argparse.ArgumentParser(description="Check or simulate the UGAS remote Render Node contract")
    parser.add_argument("--endpoint", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = remote_render_node_healthcheck(args.endpoint, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] in {"dry-run-ready", "healthy", "unknown"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
