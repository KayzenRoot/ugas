"""Materialize deterministic v0.5.3 pose-metric calibration evidence."""

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.pose_metric_calibration import calibrate_synthetic_metrics, calibration_error_table


if __name__ == "__main__":
    result = calibrate_synthetic_metrics(ROOT)
    table = calibration_error_table(result)
    (ROOT / "docs/evidence/v053-pose-error-table.json").write_text(
        json.dumps(table, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": result["status"], "target_score": result["target_score"], "negative_scores": result["negative_scores"]}, indent=2))
    raise SystemExit(0 if result["status"] == "METRIC_CALIBRATION_PASSED" else 1)
