"""Durable JSON job state transitions with bounded retries."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

STATES = ("planned", "validated", "queued", "running", "succeeded", "failed", "postprocessed", "validated_output", "registered")
ALLOWED = {"planned": {"validated", "failed"}, "validated": {"queued", "failed"}, "queued": {"running", "failed"}, "running": {"succeeded", "failed"}, "succeeded": {"postprocessed", "failed"}, "postprocessed": {"validated_output", "failed"}, "validated_output": {"registered", "failed"}, "registered": set(), "failed": set()}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class JobError(RuntimeError):
    pass


def new_job(*, consumer_project_id: str | None, asset_request_id: str, profile: str, provider: str, capability: str, workflow: dict, models: list[dict], prompts: dict, seed: int, dimensions: dict, parameters: dict, input_hashes: dict | None = None) -> dict:
    stamp = now()
    return {"schema_version": "0.4.3", "job_id": f"job-{uuid.uuid4().hex}", "state": "planned", "consumer_project_id": consumer_project_id, "asset_request_id": asset_request_id, "profile": profile, "provider": provider, "capability": capability, "workflow": workflow, "models": models, "prompts": prompts, "seed": int(seed), "dimensions": dimensions, "parameters": parameters, "timestamps": {"created": stamp, "updated": stamp}, "retry_count": 0, "input_hashes": input_hashes or {}, "output_hashes": {}, "execution_evidence": {}, "validation": {}, "provenance_event": {}, "history": [{"state": "planned", "at": stamp}], "error": None}


def transition(job: dict, state: str, *, error: str | None = None, max_retries: int = 2) -> dict:
    current = job.get("state")
    if state not in STATES or state not in ALLOWED.get(current, set()):
        raise JobError(f"Invalid job transition {current!r} -> {state!r}")
    if state == "failed" and job.get("retry_count", 0) >= max_retries:
        raise JobError("retry limit reached")
    value = json.loads(json.dumps(job))
    stamp = now()
    value["state"] = state
    value["timestamps"]["updated"] = stamp
    value.setdefault("history", []).append({"state": state, "at": stamp})
    if state == "failed":
        value["retry_count"] = int(value.get("retry_count", 0)) + 1
        value["error"] = error or "job failed"
    return value


def persist(job: dict, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{job['job_id']}.json"
    path.write_text(json.dumps(job, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
