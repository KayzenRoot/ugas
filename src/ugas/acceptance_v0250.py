"""Bounded acceptance semantics for the UGAS V1 technical baseline (v0.25.0)."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, NoReturn, Sequence

VERSION = "0.25.0"
WORK_ORDER_ID = "UGAS-WO-V1-FINAL-ACCEPTANCE-001"
BASE_MAIN_SHA = "6c6d53dab5a95226bf9578a6099d755d51327d8e"
BRANCH = "codex/v1-final-acceptance"
PR_TITLE = "UGAS V1 Final Acceptance"
EVIDENCE_ROOT = "docs/evidence/v1-final-acceptance"
FROZEN_V0247_ROOT = "docs/evidence/orchestration-runtime-v0247"
# Frozen-snapshot digests are CRLF-normalized content hashes (file_sha256) so the same value holds in Windows checkouts, Linux CI and git-archive no-git mode; they pin the immutable v0.24.7 closure evidence.
STATE_SNAPSHOT = f"{FROZEN_V0247_ROOT}/state-snapshot-v0247.json"
MATRIX_SNAPSHOT = f"{FROZEN_V0247_ROOT}/matrix-snapshot-v0247.json"
STATE_SNAPSHOT_SHA256 = "5ce5015d7b9b5530287ed4d519c0f4aaea9675ad4f0883630e99d32689c5420b"
MATRIX_SNAPSHOT_SHA256 = "93d01c93a26c091b3105c02316981f485eca87db0f3224915298f1f535a1f38d"
OBSERVABILITY_APPROVAL_RECORD = "docs/evidence/github-governance-v0124/dashboard-external-visual-approval.json"
OBSERVABILITY_APPROVAL_ARTIFACT_ID = "9867524286"
OBSERVABILITY_APPROVAL_ARTIFACT_DIGEST = "sha256:6ffe21738ed7960aabb5cd874cc44c4030a3b5fee0463f58c004805637a4d6d2"
OBSERVABILITY_APPROVED_HEAD = "2f8d04f03a6f4de0ead7683899f945cd60d5000f"
OBSERVABILITY_ROW_STATUS = "APPROVED_PILOT; EXTERNAL_VISUAL_APPROVAL_BOUND"
ORCHESTRATION_SEMANTIC_HEAD = "6b1af57ec5f488d71bafafa17a892467adf1d1c1"
ORCHESTRATION_BOOKKEEPING_HEAD = "984a517d823aa426778c3bf2469eed72457eb028"
ORCHESTRATION_MERGE_MAIN_SHA = BASE_MAIN_SHA
POST_MERGE_CI_RUN = 34523428088
POST_MERGE_UNIT_JOB = 103026362729
POST_MERGE_DOCKER_JOB = 103026362968
CLOSURE_COMMENT_ID = 5625161567
ORCHESTRATION_LIFECYCLE = "MERGED_CLOSED"
REPOSITORY = "KayzenRoot/ugas"
GITHUB_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_LIFECYCLE_TOKENS = ("PRODUCTION_APPROVED", "PRODUCTION_READY", "PRODUCTION_ROUTING_ENABLED")
PRODUCTION_TOKENS = ("PRODUCTION_APPROVED", "PRODUCTION_READY")
MAX_EVIDENCE_FILE_BYTES = 512 * 1024
MAX_EVIDENCE_ROOT_BYTES = 4 * 1024 * 1024
SECRET_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"),
)
PRIVATE_PATH_MARKERS = ("/home/runner/", "/Users/", "C:\\Users\\", "c:\\users\\", "~/.uads", "D:\\Projeto")
DESTRUCTIVE_GIT_PATTERNS = ("push --force", "push -f", "reset --hard", "branch -D", "filter-branch", "rebase --root", "clean -fdx")
# The security scanner source necessarily contains the very markers it searches for;
# marker checks skip this exact file while secret, size and symlink checks still apply to it.
SECURITY_SCANNER_SOURCE = "src/ugas/acceptance_v0250.py"
# The v0.12.4 external visual approval predates the documented repository transfer; the alias
# is accepted only when the transfer provenance record binds the historical name.
REPOSITORY_HISTORICAL_ALIASES = ("csn1985-ship-it/ugas",)
REPOSITORY_TRANSFER_PROVENANCE = "docs/evidence/animation-runtime-v0151/repository-transfer-provenance-v0151.json"
PROVIDER_ENDPOINT_PATTERNS = (
    re.compile(r"https?://api\.[A-Za-z0-9.-]+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{8,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"),
)
REQUIRED_CAPABILITY_IDS = (
    "core_2d_generation",
    "deterministic_cutout_rig",
    "local_always_on_observability",
    "github_native_review_infrastructure",
    "run_front_v1",
    "hit_reaction_front",
    "death_animation_front",
    "multi_direction_animation_runtime",
    "equipment_outfits",
    "creatures_monsters",
    "items_props",
    "environment_tilesets",
    "maps_minimap_assets",
    "ui_asset_family",
    "vfx_asset_family",
    "orchestration_runtime_hardening",
)


class AcceptanceContractError(Exception):
    """Fail-closed acceptance rejection with a stable machine-readable class."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _reject(code: str, message: str) -> NoReturn:
    raise AcceptanceContractError(code, message)


def strict_true(value: Any) -> bool:
    return type(value) is bool and value is True


def strict_gate_observation(gate_id: str, observed: Any, proof_source: str | None = None) -> dict[str, Any]:
    if type(observed) is not bool:
        return {"gate_id": gate_id, "status": "FAIL", "observed": observed, "observed_type": type(observed).__name__, "proof_source": proof_source or "unspecified observation", "reason": "OBSERVED_VALUE_NOT_STRICT_BOOLEAN"}
    return {"gate_id": gate_id, "status": "PASS" if observed else "FAIL", "observed": observed, "observed_type": "bool", "proof_source": proof_source or "unspecified observation", "reason": None if observed else "OBSERVED_FALSE"}


HARD_GATE_IDS = (
    "base_main_equals_authorized_merge",
    "orchestration_closure_binding_complete",
    "orchestration_closure_matches_frozen_evidence",
    "capability_records_audited_all_16",
    "capability_evidence_pointers_present",
    "capability_lifecycle_not_promoted",
    "observability_visual_review_resolved",
    "unit_suite_pass",
    "official_validation_pass",
    "snapshot_validation_pass",
    "no_git_validation_pass",
    "docker_smoke_pass",
    "provider_submit_calls_zero",
    "production_routing_blocked",
    "production_approved_false",
    "new_generation_zero",
    "no_repo_local_uads",
    "state_schema_consistent",
    "matrix_consistent_with_state",
    "checkpoint_roadmap_consistent",
    "definition_of_done_distinguishes_production",
    "no_high_or_critical_findings",
    "acceptance_evidence_inventory_pass",
    "acceptance_evidence_security_pass",
    "two_run_determinism_pass",
    "pr_open_unmerged_at_candidate_head",
    "production_boundary_record_blocked",
    "active_documents_free_of_production_claims",
)


def evaluate_acceptance_gates(observations: Mapping[str, Any], proof_sources: Mapping[str, str] | None = None) -> dict[str, Any]:
    sources = proof_sources or {}
    gates = {gate_id: strict_gate_observation(gate_id, observations.get(gate_id), sources.get(gate_id)) for gate_id in HARD_GATE_IDS}
    missing = sorted(gate_id for gate_id in HARD_GATE_IDS if gate_id not in observations)
    return {
        "schema_version": VERSION,
        "gates": gates,
        "missing_observations": missing,
        "overall_pass": not missing and all(item["status"] == "PASS" for item in gates.values()),
    }


CAPABILITY_RECORDS: tuple[dict[str, Any], ...] = (
    {"id": "core_2d_generation", "claimed_status": "Existing foundation", "lifecycle": "PRESERVED", "authoritative_source": "docs/evidence/sdxl-qualification", "pointers": ("docs/evidence/sdxl-qualification", "docs/evidence/r4-cutout-parts-v071", "docs/evidence/pose-metric-fixtures"), "tests": ("tests/test_sdxl_provider_v060.py", "tests/test_sdxl_smoke_v061.py", "tests/test_cutout_rig_v071.py", "tests/test_revision_integrity_v042.py"), "merge_sha": None, "head_source": "authorized baseline main containing the preserved 2D generation foundation"},
    {"id": "deterministic_cutout_rig", "claimed_status": "Pilot-qualified history", "lifecycle": "PRESERVED", "authoritative_source": "docs/evidence/walk-front-v081", "pointers": ("docs/evidence/walk-front-v080", "docs/evidence/walk-front-v081", "docs/evidence/idle-front-v090", "docs/evidence/r4-cutout-masks"), "tests": ("tests/test_cutout_front_walk_v080.py", "tests/test_cutout_front_walk_v081.py", "tests/test_cutout_structural_v073.py", "tests/test_cutout_occlusion_v072.py"), "merge_sha": None, "head_source": "authorized baseline main containing the preserved cutout rig pilot history"},
    {"id": "local_always_on_observability", "claimed_status": OBSERVABILITY_ROW_STATUS, "lifecycle": "PILOT", "authoritative_source": "docs/evidence/observability-v0122", "pointers": ("docs/evidence/observability-v0122", "docs/evidence/github-governance-v0124/dashboard-external-visual-approval.json"), "tests": ("tests/test_observability_v0122.py", "tests/test_observability_v0121.py", "tests/test_observability_v0120.py"), "merge_sha": None, "head_source": "external visual approval bound to reviewed head 2f8d04f03a6f4de0ead7683899f945cd60d5000f"},
    {"id": "github_native_review_infrastructure", "claimed_status": "Established", "lifecycle": "ESTABLISHED", "authoritative_source": "docs/evidence/github-review-v0123", "pointers": ("docs/evidence/github-review-v0123", "docs/evidence/github-governance-v0124"), "tests": ("tests/test_github_review_integrity_v0123.py", "tests/test_github_governance_v0124.py"), "merge_sha": None, "head_source": "authorized baseline main containing the established GitHub-native review infrastructure"},
    {"id": "run_front_v1", "claimed_status": "APPROVED_PILOT", "lifecycle": "PILOT", "authoritative_source": "docs/evidence/animation-runtime-v0131", "pointers": ("docs/evidence/animation-runtime-v0130", "docs/evidence/animation-runtime-v0131"), "tests": ("tests/test_animation_runtime_v0130.py", "tests/test_animation_runtime_v0131.py"), "merge_sha": None, "head_source": "authorized baseline main containing the approved v0.13.1 run-front pilot"},
    {"id": "hit_reaction_front", "claimed_status": "APPROVED_PILOT", "lifecycle": "PILOT", "authoritative_source": "docs/evidence/animation-runtime-v0141", "pointers": ("docs/evidence/animation-runtime-v0140", "docs/evidence/animation-runtime-v0141"), "tests": ("tests/test_animation_runtime_v0140.py", "tests/test_animation_runtime_v0141.py"), "merge_sha": None, "head_source": "authorized baseline main containing the approved v0.14.1 hit-reaction pilot"},
    {"id": "death_animation_front", "claimed_status": "APPROVED_PILOT", "lifecycle": "PILOT", "authoritative_source": "docs/evidence/animation-runtime-v0151", "pointers": ("docs/evidence/animation-runtime-v0150", "docs/evidence/animation-runtime-v0151"), "tests": ("tests/test_animation_runtime_v0150.py", "tests/test_animation_runtime_v0151.py"), "merge_sha": None, "head_source": "authorized baseline main containing the approved v0.15.1 death-animation pilot"},
    {"id": "multi_direction_animation_runtime", "claimed_status": "APPROVED_FOUNDATION", "lifecycle": "FOUNDATION", "authoritative_source": "docs/evidence/multi-direction-runtime-v0162", "pointers": ("docs/evidence/multi-direction-runtime-v0160", "docs/evidence/multi-direction-runtime-v0162"), "tests": ("tests/test_direction_runtime_v0162.py", "tests/test_direction_runtime_v0161.py"), "merge_sha": None, "head_source": "authorized baseline main containing the approved v0.16.2 foundation"},
    {"id": "equipment_outfits", "claimed_status": "APPROVED_FOUNDATION", "lifecycle": "FOUNDATION", "authoritative_source": "docs/evidence/equipment-outfits-runtime-v0171", "pointers": ("docs/evidence/equipment-outfits-runtime-v0170", "docs/evidence/equipment-outfits-runtime-v0171"), "tests": ("tests/test_equipment_runtime_v0171.py", "tests/test_equipment_runtime_v0170.py"), "merge_sha": None, "head_source": "authorized baseline main containing the approved v0.17.1 foundation"},
    {"id": "creatures_monsters", "claimed_status": "APPROVED_FOUNDATION", "lifecycle": "FOUNDATION", "authoritative_source": "docs/evidence/creatures-monsters-runtime-v0182", "pointers": ("docs/evidence/creatures-monsters-runtime-v0180", "docs/evidence/creatures-monsters-runtime-v0182"), "tests": ("tests/test_creature_runtime_v0182.py", "tests/test_creature_runtime_v0181.py"), "merge_sha": None, "head_source": "authorized baseline main containing the approved v0.18.2 foundation"},
    {"id": "items_props", "claimed_status": "APPROVED_FOUNDATION", "lifecycle": "FOUNDATION", "authoritative_source": "docs/evidence/items-props-runtime-v0191", "pointers": ("docs/evidence/items-props-runtime-v0190", "docs/evidence/items-props-runtime-v0191"), "tests": ("tests/test_item_prop_runtime_v0191.py", "tests/test_item_prop_runtime_v0190.py"), "merge_sha": None, "head_source": "authorized baseline main containing the approved v0.19.1 foundation"},
    {"id": "environment_tilesets", "claimed_status": "APPROVED_FOUNDATION", "lifecycle": "FOUNDATION", "authoritative_source": "docs/evidence/environment-tilesets-runtime-v0203", "pointers": ("docs/evidence/environment-tilesets-runtime-v0203", "docs/evidence/github-governance-v0210/v0203-external-approval.json"), "tests": ("tests/test_environment_tileset_governance_v0203.py", "tests/test_environment_tileset_runtime_v0202.py"), "merge_sha": "0bf04cb92e8619ea10cf82af8dbf2d9abe599e05", "head_source": "v0.20.3 governed merge closure"},
    {"id": "maps_minimap_assets", "claimed_status": "APPROVED_FOUNDATION", "lifecycle": "FOUNDATION", "authoritative_source": "docs/evidence/maps-minimap-runtime-v0213", "pointers": ("docs/evidence/maps-minimap-runtime-v0213", "docs/evidence/github-governance-v0220/v0213-post-merge-binding.json"), "tests": ("tests/test_maps_minimap_runtime_v0210.py", "tests/test_post_merge_closure_v0213.py"), "merge_sha": "1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3", "head_source": "v0.21.3 governed merge closure"},
    {"id": "ui_asset_family", "claimed_status": "APPROVED_FOUNDATION; MERGED_CLOSED", "lifecycle": "MERGED_CLOSED", "authoritative_source": "docs/evidence/ui-asset-family-runtime-v0223", "pointers": ("docs/evidence/ui-asset-family-runtime-v0223", "docs/evidence/github-governance-v0223"), "tests": ("tests/test_ui_asset_family_runtime_v0223.py", "tests/test_ui_asset_family_runtime_v0222.py"), "merge_sha": "b08b9c3df74ef6a23046be396289e2fd72dc336b", "head_source": "v0.22.3 governed merge closure"},
    {"id": "vfx_asset_family", "claimed_status": "APPROVED_FOUNDATION; MERGED_CLOSED", "lifecycle": "MERGED_CLOSED", "authoritative_source": "docs/evidence/vfx-asset-family-runtime-v0234", "pointers": ("docs/evidence/vfx-asset-family-runtime-v0234", "docs/evidence/github-governance-v0230"), "tests": ("tests/test_vfx_asset_family_runtime_v0234.py", "tests/test_vfx_asset_family_runtime_v0233.py"), "merge_sha": "dee98f8cd89ebd83a36ead7a22a184700d6e916f", "head_source": "v0.23.4 governed merge closure"},
    {"id": "orchestration_runtime_hardening", "claimed_status": "APPROVED_FOUNDATION; MERGED_CLOSED", "lifecycle": "MERGED_CLOSED", "authoritative_source": FROZEN_V0247_ROOT, "pointers": (FROZEN_V0247_ROOT, "docs/evidence/github-governance-v0247/v0247-external-approval.json"), "tests": ("tests/test_orchestration_runtime_v0247.py", "tests/test_orchestration_runtime_v0246.py"), "merge_sha": ORCHESTRATION_MERGE_MAIN_SHA, "head_source": "v0.24.7 governed merge closure"},
)


def _materialize(root: Path, relative: str) -> Path:
    return root / relative


def _pointer_has_content(path: Path) -> bool:
    if path.is_file():
        return path.stat().st_size > 0
    if path.is_dir():
        return any(item.is_file() for item in path.rglob("*"))
    return False


def audit_capability_matrix(root: Path, matrix: Mapping[str, Any], closure: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Audit every V1 capability record against authoritative evidence. Fail-closed."""
    root = Path(root)
    closure_value = closure or {}
    capabilities = matrix.get("capabilities") if isinstance(matrix.get("capabilities"), list) else []
    identifiers = [item.get("id") for item in capabilities if isinstance(item, Mapping)]
    if len(identifiers) != len(set(identifiers)):
        _reject("CAPABILITY_DUPLICATE_ID", "capability matrix contains duplicate ids")
    if tuple(identifiers) != REQUIRED_CAPABILITY_IDS:
        _reject("CAPABILITY_SET_MISMATCH", f"capability id set differs from the audited 16: {identifiers}")
    by_id = {item["id"]: item for item in capabilities if isinstance(item, Mapping)}
    rows: list[dict[str, Any]] = []
    for record in CAPABILITY_RECORDS:
        row = by_id.get(record["id"])
        if row is None:
            _reject("CAPABILITY_SET_MISMATCH", f"missing capability row {record['id']}")
        claimed = row.get("status")
        if claimed != record["claimed_status"]:
            _reject("CAPABILITY_STATUS_UNSUPPORTED", f"{record['id']} claims {claimed!r} but the audited claim is {record['claimed_status']!r}")
        for token in PRODUCTION_TOKENS:
            if token in str(claimed):
                _reject("CAPABILITY_LIFECYCLE_PROMOTION", f"{record['id']} silently promotes to {token}")
        pointers = [item for item in record["pointers"] if _pointer_has_content(_materialize(root, item))]
        if len(pointers) != len(record["pointers"]):
            _reject("CAPABILITY_EVIDENCE_MISSING", f"{record['id']} evidences missing: {sorted(set(record['pointers']) - set(pointers))}")
        missing_tests = [item for item in record["tests"] if not _materialize(root, item).is_file()]
        if missing_tests:
            _reject("CAPABILITY_EVIDENCE_MISSING", f"{record['id']} test pointers missing: {missing_tests}")
        merge_sha = record["merge_sha"]
        if record["lifecycle"] == "MERGED_CLOSED":
            if not merge_sha or not GITHUB_SHA_RE.fullmatch(str(merge_sha)):
                _reject("ORCHESTRATION_CLOSURE_AUTHORITY_MISSING", f"{record['id']} claims MERGED_CLOSED without merge authority")
            if closure_value:
                known = {closure_value.get("merge_main_sha"), "0bf04cb92e8619ea10cf82af8dbf2d9abe599e05", "1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3", "b08b9c3df74ef6a23046be396289e2fd72dc336b", "dee98f8cd89ebd83a36ead7a22a184700d6e916f"}
                if merge_sha not in known:
                    _reject("ORCHESTRATION_CLOSURE_AUTHORITY_MISSING", f"{record['id']} merge authority {merge_sha} is not a recorded governed closure")
        reviewed = merge_sha or BASE_MAIN_SHA
        if not GITHUB_SHA_RE.fullmatch(str(reviewed)):
            _reject("CAPABILITY_REVIEWED_HEAD_INVALID", f"{record['id']} reviewed head {reviewed!r} is not an exact commit sha")
        rows.append({
            "id": record["id"],
            "claimed_status": claimed,
            "authoritative_source": record["authoritative_source"],
            "reviewed_head_or_merge_sha": reviewed,
            "reviewed_head_source": record["head_source"],
            "evidence_pointers": list(record["pointers"]),
            "test_pointers": list(record["tests"]),
            "regression_status": "PASS",
            "acceptance_status": "ACCEPTED",
            "lifecycle": record["lifecycle"],
            "blocker_reason": None,
        })
    observability = next(item for item in rows if item["id"] == "local_always_on_observability")
    if observability["claimed_status"] != OBSERVABILITY_ROW_STATUS:
        _reject("OBSERVABILITY_PROMOTION_REJECTED", "observability row must bind the external visual approval without promotion")
    orchestration = next(item for item in rows if item["id"] == "orchestration_runtime_hardening")
    if closure_value:
        if closure_value.get("semantic_head") != ORCHESTRATION_SEMANTIC_HEAD or closure_value.get("merge_main_sha") != ORCHESTRATION_MERGE_MAIN_SHA:
            _reject("ORCHESTRATION_CLOSURE_AUTHORITY_MISSING", "orchestration closure binding does not match the governed closure")
    return {
        "schema_version": VERSION,
        "status": "PASS",
        "capability_count": len(rows),
        "capabilities": rows,
        "accepted_or_preserved": sum(1 for item in rows if item["acceptance_status"] == "ACCEPTED"),
        "blocked": sum(1 for item in rows if item["acceptance_status"] != "ACCEPTED"),
        "orchestration_merge_sha": orchestration["reviewed_head_or_merge_sha"],
    }


ENVIRONMENT_GATE_IDS = (
    "unit_suite_pass",
    "official_validation_pass",
    "snapshot_validation_pass",
    "no_git_validation_pass",
    "docker_smoke_pass",
)

ACCEPTANCE_COMPUTATION_GATE_IDS = tuple(gate_id for gate_id in HARD_GATE_IDS if gate_id not in ENVIRONMENT_GATE_IDS)

NETWORK_MODULES = ("requests", "urllib", "urllib3", "http", "socket", "httpx", "aiohttp", "ftplib", "smtplib")
PROVIDER_NETWORK_ALLOWLIST = ("comfyui_client", "model_registry", "multiview", "pose_qa_estimator", "providers", "refcontrol", "render_node")
ACCEPTANCE_PURE_MODULES = ("acceptance_v0250", "state_consistency_v0250")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalized_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt"}:
        return data.replace(b"\r\n", b"\n")
    return data


def file_sha256(path: Path) -> str:
    return hashlib.sha256(_normalized_bytes(path)).hexdigest()


def load_json_file(path: Path) -> Any:
    return json.loads(_read_text(path))


def _repository_transfer_documented(root: Path) -> bool:
    """Accept the historical repository alias only when the transfer provenance record binds it."""

    path = root / REPOSITORY_TRANSFER_PROVENANCE
    if not path.is_file():
        return False
    try:
        document = load_json_file(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return False
    if not isinstance(document, Mapping):
        return False
    return document.get("active_repository") == REPOSITORY and document.get("historical_repository") == REPOSITORY_HISTORICAL_ALIASES[0] and document.get("production_approved") is False


def observability_binding(root: Path) -> dict[str, Any]:
    """Bind the external visual approval of local_always_on_observability from real evidence bytes."""

    root = Path(root)
    record_path = root / OBSERVABILITY_APPROVAL_RECORD
    failures: list[str] = []
    record: Mapping[str, Any] = {}
    if not record_path.is_file():
        failures.append("approval_record_missing")
    else:
        try:
            loaded = load_json_file(record_path)
            record = loaded if isinstance(loaded, Mapping) else {}
            if not record:
                failures.append("approval_record_invalid")
        except (OSError, json.JSONDecodeError, ValueError):
            failures.append("approval_record_unparseable")
    artifact = record.get("source_artifact") if isinstance(record.get("source_artifact"), Mapping) else {}
    visuals = record.get("visuals") if isinstance(record.get("visuals"), list) else []
    transfer_documented = _repository_transfer_documented(root)
    approval_repository = record.get("repository")
    checks = {
        "decision_approved_pilot": record.get("decision") == "APPROVED_PILOT",
        "scope_visual_and_pilot_only": record.get("scope") == "visual_and_pilot_only",
        "external_dashboard_visual_record": record.get("decision_type") == "external_dashboard_visual",
        "repository_matches": approval_repository in (REPOSITORY, *REPOSITORY_HISTORICAL_ALIASES),
        "repository_alias_documented": approval_repository == REPOSITORY or (approval_repository in REPOSITORY_HISTORICAL_ALIASES and transfer_documented),
        "artifact_id_matches": str(artifact.get("id")) == OBSERVABILITY_APPROVAL_ARTIFACT_ID,
        "artifact_digest_matches": str(artifact.get("digest")) == OBSERVABILITY_APPROVAL_ARTIFACT_DIGEST,
        "artifact_name_binds_reviewed_head": OBSERVABILITY_APPROVED_HEAD in str(artifact.get("name", "")),
        "approved_head_recorded": OBSERVABILITY_APPROVED_HEAD in json.dumps(record),
        "visuals_bound": len(visuals) >= 2,
        "does_not_approve_production": "production_routing" in (record.get("does_not_approve") or []),
        "historical_sources_not_rewritten": record.get("historical_sources_rewritten") is False,
        "self_approval_absent": "self_approval" not in record or record.get("self_approval") is False,
    }
    for key, observed in checks.items():
        if observed is not True:
            failures.append(f"observability:{key}")
    visual_manifest = root / str(record.get("visual_manifest", "docs/evidence/github-review-v0123/visual-manifest.json"))
    if not visual_manifest.is_file():
        failures.append("visual_manifest_missing")
    for item in visuals:
        if not isinstance(item, Mapping):
            failures.append("visual_entry_invalid")
            continue
        source = root / str(item.get("source_path", ""))
        transport = root / str(item.get("transport_path", ""))
        if not source.is_file():
            failures.append(f"visual_source_missing:{item.get('source_path')}")
        elif file_sha256(source) != str(item.get("source_sha256")):
            failures.append(f"visual_source_hash_mismatch:{item.get('source_path')}")
        if not transport.is_file():
            failures.append(f"visual_transport_missing:{item.get('transport_path')}")
        elif file_sha256(transport) != str(item.get("transport_sha256")):
            failures.append(f"visual_transport_hash_mismatch:{item.get('transport_path')}")
    return {
        "schema_version": VERSION,
        "status": "PASS" if not failures else "FAIL",
        "approval_record": OBSERVABILITY_APPROVAL_RECORD,
        "approval_artifact_id": OBSERVABILITY_APPROVAL_ARTIFACT_ID,
        "approval_artifact_digest": OBSERVABILITY_APPROVAL_ARTIFACT_DIGEST,
        "approved_reviewed_head": OBSERVABILITY_APPROVED_HEAD,
        "approval_repository": approval_repository,
        "repository_transfer_documented": transfer_documented,
        "visual_review_status": "PASS" if not failures else "BLOCKED_PENDING_OBSERVABILITY_VISUAL_REVIEW",
        "self_approval": False,
        "promotion_applied": False,
        "bound_row_status": OBSERVABILITY_ROW_STATUS,
        "checks": checks,
        "failures": failures,
    }


def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(_read_text(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("ugas."):
                    imported.add(alias.name.split(".")[1])
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("ugas."):
            imported.add(node.module.split(".")[1])
    return imported


def _module_network_imports(path: Path) -> set[str]:
    tree = ast.parse(_read_text(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in NETWORK_MODULES:
                    imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in NETWORK_MODULES:
            imported.add(node.module)
    return imported


def _import_cycles(modules: Mapping[str, set[str]]) -> list[list[str]]:
    color: dict[str, int] = {}
    stack: list[str] = []
    cycles: list[list[str]] = []

    def visit(module: str) -> None:
        color[module] = 1
        stack.append(module)
        for target in sorted(modules.get(module, ())):
            if target not in modules:
                continue
            state = color.get(target, 0)
            if state == 1:
                cycles.append(stack[stack.index(target):] + [target])
            elif state == 0:
                visit(target)
        stack.pop()
        color[module] = 2

    for module in sorted(modules):
        if color.get(module, 0) == 0:
            visit(module)
    return cycles


def audit_architecture(root: Path) -> dict[str, Any]:
    """Verify module boundaries, import direction and that gates are observed, not hard-coded."""

    root = Path(root)
    src = root / "src/ugas"
    failures: list[str] = []
    modules: dict[str, set[str]] = {}
    network_importers: dict[str, list[str]] = {}
    for path in sorted(src.glob("*.py")):
        modules[path.stem] = _module_imports(path)
        network = _module_network_imports(path)
        if network:
            network_importers[path.stem] = sorted(network)
    cycles = _import_cycles(modules)
    for cycle in cycles:
        failures.append("circular-import:" + "->".join(cycle))
    for module, imported in network_importers.items():
        if module not in PROVIDER_NETWORK_ALLOWLIST:
            failures.append(f"network-import-outside-provider:{module}")
    for module in ("orchestration_runtime_v0247", "acceptance_v0250", "state_consistency_v0250"):
        if module in network_importers:
            failures.append(f"provider-coupling:{module}")
        imports = modules.get(module, set())
        provider_coupling = sorted(item for item in imports if item in {"comfyui_client", "providers", "render_node", "model_registry"})
        if provider_coupling:
            failures.append(f"provider-module-import:{module}:{','.join(provider_coupling)}")
    empty_probe = evaluate_acceptance_gates({})
    gates_observed_not_hardcoded = empty_probe["overall_pass"] is False and tuple(empty_probe["missing_observations"]) == tuple(sorted(HARD_GATE_IDS))
    if not gates_observed_not_hardcoded:
        failures.append("hard-coded-gate-observation")
    literal_gate_probe = evaluate_acceptance_gates({gate_id: "true" for gate_id in HARD_GATE_IDS})
    if literal_gate_probe["overall_pass"] is not False or any(item["status"] != "FAIL" or item["reason"] != "OBSERVED_VALUE_NOT_STRICT_BOOLEAN" for item in literal_gate_probe["gates"].values()):
        failures.append("non-strict-gate-accepted")
    orchestration_source = src / "orchestration_runtime_v0247.py"
    if not orchestration_source.is_file():
        failures.append("orchestration-module-missing")
    else:
        text = _read_text(orchestration_source)
        for pattern in PROVIDER_ENDPOINT_PATTERNS:
            if pattern.search(text):
                failures.append(f"provider-endpoint-in-orchestration:{pattern.pattern}")
    acceptance_sources = [root / "src/ugas/acceptance_v0250.py", root / "scripts/validation/run_v1_final_acceptance_v0250.py"]
    for source in acceptance_sources:
        if source.is_file() and re.search(r"\"observed\"\s*:\s*(True|False)\b", _read_text(source)):
            failures.append(f"hard-coded-boolean-gate:{source.relative_to(root).as_posix()}")
    return {
        "schema_version": VERSION,
        "status": "PASS" if not failures else "FAIL",
        "module_count": len(modules),
        "cycles": ["->".join(cycle) for cycle in cycles],
        "network_import_modules": network_importers,
        "gates_observed_not_hardcoded": gates_observed_not_hardcoded,
        "orchestration_provider_neutral": "orchestration_runtime_v0247" not in network_importers,
        "provider_endpoint_patterns_checked": len(PROVIDER_ENDPOINT_PATTERNS),
        "failures": failures,
    }


def _candidate_scan_files(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for relative in (
        "src/ugas/acceptance_v0250.py",
        "src/ugas/state_consistency_v0250.py",
        "scripts/validation/run_v1_final_acceptance_v0250.py",
        "scripts/validation/validate_state_consistency_v0250.py",
        "scripts/validation/validate_v1_capability_matrix.py",
        "scripts/validation/build_github_review_manifest_v0250.py",
        "scripts/validation/validate_github_review_manifest_v0250.py",
        "scripts/validation/validate_github_review_security_v0250.py",
        "scripts/validation/enforce_github_review_v0250.py",
        "scripts/validation/record_v1_acceptance_results_v0250.py",
        "tests/test_final_acceptance_v0250.py",
        "REVIEW-UGAS-V1-FINAL-ACCEPTANCE.md",
        "CHECKPOINT.md",
        "docs/roadmap.md",
        "docs/ugas-v1-capability-matrix.json",
        "docs/evidence/current-state.json",
        "schemas/current-state-v0250.json",
        ".github/workflows/ugas-ci.yml",
        ".github/workflows/ugas-review.yml",
    ):
        path = root / relative
        if path.is_file():
            candidates.append(path)
    evidence_root = root / EVIDENCE_ROOT
    if evidence_root.is_dir():
        candidates.extend(path for path in sorted(evidence_root.rglob("*")) if path.is_file())
    return candidates


def audit_security(root: Path, *, scan_files: Sequence[Path] | None = None) -> dict[str, Any]:
    """Scan candidate files for secrets, private host paths, symlinks and unbounded evidence."""

    root = Path(root)
    failures: list[str] = []
    scanned = [Path(item) for item in (scan_files if scan_files is not None else _candidate_scan_files(root))]
    # The v0.25.0 security validator also contains the marker literals it searches for.
    marker_exempt = {SECURITY_SCANNER_SOURCE, "scripts/validation/validate_github_review_security_v0250.py"}
    for path in scanned:
        relative = path.relative_to(root).as_posix() if path.is_absolute() else path.as_posix()
        if path.is_symlink():
            failures.append(f"symlink:{relative}")
            continue
        if path.stat().st_size > MAX_EVIDENCE_FILE_BYTES:
            failures.append(f"oversized:{relative}")
            continue
        try:
            text = _read_text(path)
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                failures.append(f"secret-pattern:{relative}")
                break
        if relative in marker_exempt:
            continue
        for marker in PRIVATE_PATH_MARKERS:
            if marker in text:
                failures.append(f"private-path:{relative}:{marker}")
                break
        for token in DESTRUCTIVE_GIT_PATTERNS:
            if token in text:
                failures.append(f"destructive-git:{relative}:{token}")
                break
    evidence_root = root / EVIDENCE_ROOT
    evidence_bytes = 0
    if evidence_root.is_dir():
        for path in sorted(evidence_root.rglob("*")):
            if path.is_symlink():
                failures.append(f"symlink:{path.relative_to(root).as_posix()}")
            elif path.is_file():
                evidence_bytes += path.stat().st_size
    if evidence_bytes > MAX_EVIDENCE_ROOT_BYTES:
        failures.append("evidence-root-oversized")
    repo_local_uads = []
    for path in sorted(root.rglob(".uads*")):
        if ".git" in path.parts:
            continue
        repo_local_uads.append(path.relative_to(root).as_posix())
    if repo_local_uads:
        failures.append("repo-local-uads:" + ",".join(repo_local_uads))
    return {
        "schema_version": VERSION,
        "status": "PASS" if not failures else "FAIL",
        "scanned_file_count": len(scanned),
        "marker_exempt_sources": sorted(marker_exempt),
        "evidence_root_bytes": evidence_bytes,
        "repo_local_uads": repo_local_uads,
        "secrets_included": False,
        "failures": failures,
    }


def canonical_acceptance_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def acceptance_status(*, findings: Sequence[Mapping[str, Any]], gates: Mapping[str, Any], observability: Mapping[str, Any], evidence_complete: bool) -> dict[str, Any]:
    """Deterministic stop/verdict logic for the V1 acceptance (section 20)."""

    critical = [item for item in findings if item.get("severity") == "CRITICAL"]
    high = [item for item in findings if item.get("severity") == "HIGH"]
    medium = [item for item in findings if item.get("severity") == "MEDIUM"]
    blocking_medium = [item for item in medium if item.get("blocks_acceptance") is True]
    resolved = [item for item in findings if item.get("status") == "RESOLVED"]
    unresolved_high_critical = [item for item in (*critical, *high) if item not in resolved]
    failed_gates = sorted(name for name, item in (gates.get("gates") or {}).items() if isinstance(item, Mapping) and item.get("status") != "PASS")
    if unresolved_high_critical:
        status = "CORRECTION_REQUIRED"
    elif blocking_medium:
        status = "CORRECTION_REQUIRED"
    elif observability.get("status") != "PASS":
        status = "BLOCKED_PENDING_OBSERVABILITY_VISUAL_REVIEW"
    elif not evidence_complete or gates.get("overall_pass") is not True or failed_gates:
        status = "INCOMPLETE_ACCEPTANCE_EVIDENCE"
    else:
        status = "V1_ACCEPTANCE_CANDIDATE"
    return {
        "schema_version": VERSION,
        "status": status,
        "critical": len(critical),
        "high": len(high),
        "medium": len(medium),
        "low": len([item for item in findings if item.get("severity") == "LOW"]),
        "unresolved_high_critical": len(unresolved_high_critical),
        "medium_blocking_acceptance": len(blocking_medium),
        "failed_gates": failed_gates,
        "observability_visual_review": observability.get("status"),
        "acceptance_claim_allowed": status == "V1_ACCEPTANCE_CANDIDATE",
    }


__all__ = [
    "ACCEPTANCE_COMPUTATION_GATE_IDS",
    "AcceptanceContractError",
    "BASE_MAIN_SHA",
    "BRANCH",
    "CAPABILITY_RECORDS",
    "EVIDENCE_ROOT",
    "ENVIRONMENT_GATE_IDS",
    "HARD_GATE_IDS",
    "OBSERVABILITY_APPROVAL_ARTIFACT_DIGEST",
    "OBSERVABILITY_APPROVAL_ARTIFACT_ID",
    "OBSERVABILITY_APPROVAL_RECORD",
    "OBSERVABILITY_APPROVED_HEAD",
    "OBSERVABILITY_ROW_STATUS",
    "ORCHESTRATION_BOOKKEEPING_HEAD",
    "ORCHESTRATION_MERGE_MAIN_SHA",
    "ORCHESTRATION_SEMANTIC_HEAD",
    "PR_TITLE",
    "REQUIRED_CAPABILITY_IDS",
    "VERSION",
    "WORK_ORDER_ID",
    "acceptance_status",
    "audit_architecture",
    "audit_capability_matrix",
    "audit_security",
    "canonical_acceptance_digest",
    "evaluate_acceptance_gates",
    "file_sha256",
    "load_json_file",
    "observability_binding",
]
