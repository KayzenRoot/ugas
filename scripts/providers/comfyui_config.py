"""Render a safe ComfyUI configuration plan without writing secrets."""

from pathlib import Path
import argparse
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a non-secret ComfyUI configuration plan")
    parser.add_argument("--endpoint", default=os.environ.get("UGAS_COMFYUI_ENDPOINT", "http://127.0.0.1:8188"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = {
        "provider": "provider-comfyui",
        "status": "dry-run-ready" if args.dry_run else "plan-only",
        "endpoint": args.endpoint.rstrip("/"),
        "install": {"required": True, "performed": False, "models_downloaded": False},
        "configuration": {"private_bind": True, "credentials_source": "environment-or-secret-manager", "workflow_registry": "providers/workflows"},
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
