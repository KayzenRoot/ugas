"""Fail-closed validation for v0.6.1 SDXL generation evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping


PROMPT_ID = "PROMPT-05C-UGAS-SDXL-SMOKE-EVIDENCE-HARD-GATES-v0.6.1"
EXPECTED_LANES = {"P", "I", "PI"}
EXPECTED_SEED = 61701


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_execution_evidence_v061(evidence: Mapping[str, Any], root: Path) -> dict[str, Any]:
    """Validate exact count, bindings and raw-file hashes for the corrective smoke."""
    failures: list[str] = []
    records = evidence.get("records") if isinstance(evidence.get("records"), list) else []
    if evidence.get("schema_version") != "0.6.1":
        failures.append("schema_version")
    if evidence.get("attempted_record_count") != 3 or len(records) != 3:
        failures.append("attempted_record_count_must_be_exactly_3")
    if evidence.get("generation_completed_count") != 3 or evidence.get("completed_execution_count") != 3:
        failures.append("generation_completed_count_must_be_exactly_3")
    if {item.get("lane") for item in records if isinstance(item, Mapping)} != EXPECTED_LANES:
        failures.append("lanes_must_be_exactly_P_I_PI")
    for item in records:
        if not isinstance(item, Mapping):
            failures.append("record_must_be_object")
            continue
        generation = item.get("generation") if isinstance(item.get("generation"), Mapping) else {}
        lane = str(item.get("lane"))
        if item.get("seed") != EXPECTED_SEED:
            failures.append(f"{lane}:seed")
        if generation.get("completed") is not True:
            failures.append(f"{lane}:generation_completed")
        if generation.get("prompt_id") != PROMPT_ID:
            failures.append(f"{lane}:prompt_id")
        if generation.get("history_key_matches_prompt_id") is not True:
            failures.append(f"{lane}:history_binding")
        if generation.get("target_existed_before_submission") is not False:
            failures.append(f"{lane}:stale_target")
        if generation.get("fresh_binding") is not True:
            failures.append(f"{lane}:fresh_binding")
        if generation.get("previous_frame_chaining") is not False:
            failures.append(f"{lane}:previous_frame_chaining")
        raw_path_value = generation.get("raw_output_path")
        raw_hash = generation.get("raw_output_sha256")
        raw_path = root / str(raw_path_value) if raw_path_value else None
        if not raw_path or not raw_path.is_file() or not raw_hash or _digest(raw_path) != raw_hash:
            failures.append(f"{lane}:raw_hash")
        if generation.get("raw_output_hash_matches_comfy") is not True:
            failures.append(f"{lane}:comfy_raw_hash_binding")
    if evidence.get("all_prompt_ids_present") is not True:
        failures.append("all_prompt_ids_present")
    if evidence.get("all_history_bindings_exact") is not True:
        failures.append("all_history_bindings_exact")
    if evidence.get("all_raw_outputs_hash_bound") is not True:
        failures.append("all_raw_outputs_hash_bound")
    if evidence.get("all_targets_fresh") is not True:
        failures.append("all_targets_fresh")
    if evidence.get("previous_frame_chaining") is not False:
        failures.append("aggregate_previous_frame_chaining")
    if evidence.get("weights_in_git") is not False:
        failures.append("weights_in_git")
    if evidence.get("custom_node_source_vendored") is not False:
        failures.append("custom_node_source_vendored")
    return {
        "status": "SDXL_V061_EXECUTION_EVIDENCE_PASSED" if not failures else "SDXL_V061_EXECUTION_EVIDENCE_FAILED",
        "failures": sorted(set(failures)),
        "checked_records": len(records),
    }
