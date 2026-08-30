"""Materialize independent MediaPipe pose QA qualification evidence."""

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.pose_qa_estimator import qualify_pose_estimator


if __name__ == "__main__":
    result = qualify_pose_estimator(ROOT)
    print(json.dumps({"status": result["status"], "reason": result["reason"], "library": result["library"], "model": result["model"]}, indent=2))
    raise SystemExit(0 if result["status"] == "POSE_QA_ESTIMATOR_QUALIFIED" else 1)
