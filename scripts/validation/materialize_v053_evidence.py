"""Materialize v0.5.3 evidence after metric and estimator gates are evaluated."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.pose_metric_calibration import provider_gap_emission_authorized
from ugas.pose_qa_estimator import qualify_pose_estimator


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    calibration = json.loads((ROOT / "docs/evidence/pose-metric-calibration.json").read_text(encoding="utf-8"))
    estimator = json.loads((ROOT / "docs/evidence/pose-qa-estimator-qualification.json").read_text(encoding="utf-8"))
    baseline = ROOT / "docs/evidence/v051-gap-baseline.png"
    baseline_copy = ROOT / "docs/evidence/v052-refcontrol-baseline-contact.png"
    shutil.copy2(baseline, baseline_copy)
    status = estimator.get("status")
    provider_authorized = provider_gap_emission_authorized(calibration_status=calibration.get("status", ""), estimator_status=status or "")
    provider = {
        "schema_version": "0.5.3",
        "status": status if status != "POSE_QA_ESTIMATOR_QUALIFIED" else "POSE_PROVIDER_RECHECK_REQUIRED",
        "calibration_status": calibration.get("status"),
        "estimator_status": status,
        "provider_gap_emission_authorized": provider_authorized,
        "lanes": {"A": {"status": "NOT_RUN"}, "C": {"status": "NOT_RUN"}, "R": {"status": "NOT_RUN"}},
        "seeds": [53701, 53702, 53703],
        "decision": "NO_PROVIDER_DECISION_AUTHORIZED" if not provider_authorized else "PENDING_FRESH_A_C_R_RECHECK",
        "reason": "provider recheck requires qualified metric and independent estimator; current estimator is blocked by task-bundle license gap",
        "new_generation_jobs_submitted": False,
        "walk_authorized": False,
        "outputs": [],
    }
    execution = {
        "schema_version": "0.5.3",
        "status": status,
        "records": [],
        "record_count": 0,
        "generation_jobs_authorized": False,
        "authorization_reason": "POSE_QA_MODEL_LICENSE_GAP",
        "seeds_reserved_but_not_used": [53701, 53702, 53703],
        "previous_frame_chaining": False,
        "all_prompt_ids_present": False,
        "all_history_bindings_exact": False,
        "stale_output_rejected": True,
        "provider_routing_used": False,
    }
    (ROOT / "docs/evidence/v053-provider-qualification.json").write_text(json.dumps(provider, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (ROOT / "docs/evidence/execution-evidence-v0.5.3.json").write_text(json.dumps(execution, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    images = [
        ("pose-metric-calibration-contact-sheet.png", "docs/evidence/pose-metric-calibration-contact-sheet.png", "v0.5.3-metric"),
        ("pose-metric-negative-controls-contact-sheet.png", "docs/evidence/pose-metric-negative-controls-contact-sheet.png", "v0.5.3-metric"),
        ("v052-refcontrol-baseline-contact.png", "docs/evidence/v052-refcontrol-baseline-contact.png", "v0.5.2-historical"),
        ("v053-pose-detection-overlay-contact.png", "docs/evidence/v053-pose-detection-overlay-contact.png", "v0.5.3-estimator"),
    ]
    manifest = {
        "schema_version": "0.5.3",
        "manifest_type": "review-visual-evidence",
        "review_state": "pose-qa-model-license-gap",
        "images": [{"archive_name": name, "source_path": source, "revision_id": revision, "sha256": digest(ROOT / source)} for name, source, revision in images],
        "human_visual_review": "required",
        "production_approval": "not-granted",
    }
    (ROOT / "docs/evidence/review-visuals-v0.5.3.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"provider": provider["status"], "execution_records": 0, "baseline_sha256": digest(baseline_copy)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
