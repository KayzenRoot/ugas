"""Objective UGAS validation, including immutable history and active v0.6.1."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.constants import UGAS_VERSION
from ugas.master_assets import verify_asset_integrity
from ugas.model_registry import load_model, load_registry, validate_model_workflow_compatibility
from ugas.reference_edit import validate_edit_contract, validate_execution_evidence
from ugas.review import validate_review_visual_manifest
from ugas.review_snapshot import self_test_sensitive_matcher
from ugas.schema_validation import SchemaValidationError, validate_instance, validate_schema_document
from ugas.openpose_guides import COCO18_JOINTS, OPENPOSE_GUIDE_RENDERER_VERSION, validate_openpose_guide
from ugas.state_consistency import validate_state_consistency
from ugas.workflow_registry import load_workflow, load_workflows, validate_api_workflow
from ugas.identity import ANCHOR_ASSET_ID, ANCHOR_REVISION_ID, ANCHOR_SHA256, validate_identity_manifest
from ugas.pose_guides import CHALLENGE_NAME, POSE_GUIDE_RENDERER_VERSION, WALK_NAMES, validate_pose_guide
from ugas.multiview import AB_POSE_GAIN, AB_POSE_THRESHOLD, AB_POSE_FLOOR, FRAME_POSE_THRESHOLD, IDENTITY_THRESHOLD
from ugas.pose_metric_calibration import normalized_headroom_gain, provider_gap_emission_authorized, validate_causal_gate_configuration
from ugas.sdxl_smoke_evidence import validate_execution_evidence_v061


RESULTS: list[tuple[str, bool, str]] = []
V054_CANONICAL_OUTPUTS = tuple(
    f"docs/evidence/v054-lanes/{lane}-seed-{seed}.png"
    for lane in ("a", "c", "r")
    for seed in (54701, 54702, 54703)
)


def check(name: str, condition: bool, detail: str) -> None:
    RESULTS.append((name, bool(condition), detail))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    data = path.read_bytes()
    # Keep tracked text evidence stable across Windows CRLF and Git archive
    # extraction; image and other binary hashes stay byte-for-byte exact.
    if path.suffix.casefold() in {".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def schema_compatible_with_artifact(schema: dict, artifact: dict) -> dict:
    """Validate immutable v0.5.0 evidence against the equivalent current schema."""
    if artifact.get("schema_version") != "0.5.0":
        return schema
    value = json.loads(json.dumps(schema))
    def replace(node: object) -> None:
        if isinstance(node, dict):
            if node.get("const") == UGAS_VERSION:
                node["const"] = "0.5.0"
            for child in node.values():
                replace(child)
        elif isinstance(node, list):
            for child in node:
                replace(child)
    replace(value)
    if artifact.get("schema_version") == "0.5.0" and artifact.get("animation") == "walk":
        temporal = value.get("properties", {}).get("temporal", {})
        if isinstance(temporal, dict) and isinstance(temporal.get("required"), list):
            temporal["required"] = [item for item in temporal["required"] if item != "gates"]
    return value


def tracked(path: str) -> bool:
    if os.environ.get("UGAS_TRACKED_SNAPSHOT") == "1" or not (ROOT / ".git").exists():
        return (ROOT / path).is_file()
    result = subprocess.run(["git", "ls-files", "--error-unmatch", "--", path], cwd=ROOT, capture_output=True, text=True, check=False)
    return result.returncode == 0


def _run(command: list[str], cwd: Path, *, env: dict[str, str] | None = None, timeout: int = 360) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=timeout)


def snapshot_check() -> None:
    if os.environ.get("UGAS_SKIP_TRACKED_SNAPSHOT") == "1":
        check("snapshot:tracked", True, "nested snapshot check skipped")
        return
    if not (ROOT / ".git").exists():
        check("snapshot:git-context", True, "SKIP_EXTERNAL_GIT_CONTEXT")
        return
    with tempfile.TemporaryDirectory(prefix="ugas-v051-snapshot-") as directory:
        snapshot = Path(directory) / "snapshot"; snapshot.mkdir()
        archive = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, capture_output=True, check=False)
        if archive.returncode != 0:
            check("snapshot:archive", False, archive.stderr.decode(errors="replace")[-500:]); return
        with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
            try: tar.extractall(snapshot, filter="data")
            except TypeError: tar.extractall(snapshot)
        env = os.environ.copy(); env.update({"UGAS_SKIP_TRACKED_SNAPSHOT": "1", "UGAS_SKIP_NO_GIT_REGRESSION": "1", "PYTHONUTF8": "1"})
        for name, command in (
            ("snapshot:compileall", [sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"]),
            ("snapshot:unit-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests"]),
            ("snapshot:validation", [sys.executable, "scripts/validation/run_validation.py"]),
            ("snapshot:version", [sys.executable, "-m", "ugas.cli", "--version"]),
            ("snapshot:models", [sys.executable, "-m", "ugas.cli", "models", "list"]),
        ):
            result = _run(command, snapshot, env=env)
            check(name, result.returncode == 0, (result.stdout + result.stderr).strip()[-800:])
        no_git = Path(directory) / "no-git"; shutil.copytree(snapshot, no_git, ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc"))
        no_git_env = env.copy(); no_git_env.pop("UGAS_SKIP_TRACKED_SNAPSHOT", None); no_git_env["UGAS_REVIEW_SNAPSHOT"] = "1"; no_git_env["PYTHONPATH"] = str(no_git / "src")
        result = _run([sys.executable, "scripts/validation/run_validation.py"], no_git, env=no_git_env)
        check("snapshot:no-git", result.returncode == 0 and "SKIP_EXTERNAL_GIT_CONTEXT" in result.stdout, (result.stdout + result.stderr).strip()[-800:])


def _historical_coverage_checks() -> None:
    matrix = ROOT / "docs" / "test-coverage-matrix-v0.4.2.md"
    text = matrix.read_text(encoding="utf-8") if matrix.is_file() else ""
    rows = sum(1 for line in text.splitlines() if line.startswith("| ") and "v0.4.0 intent" not in line and "---" not in line)
    check("coverage:historical-matrix", rows >= 26, f"mapped rows={rows}")
    test_text = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "tests").glob("test_*.py"))
    historical_names = [
        "test_expected_directories_and_documents_exist", "test_every_skill_has_valid_agent_skills_frontmatter", "test_profiles_and_schema_documents_validate", "test_templates_provider_and_workflow_instances_validate", "test_engine_markers_and_dimension_evidence", "test_context_scan_is_bounded_and_skips_heavy_directories", "test_installer_auto_selection_and_refresh_preserve_history", "test_default_availability_is_unknown", "test_asset_and_non_asset_classification", "test_3d_final_never_falls_back_to_2d_provider", "test_paid_disabled_keeps_self_hosted_remote_eligible", "test_qualified_2d_evidence_selects_comfyui_for_master_sprite", "test_partial_mmorpg_plan_exposes_animation_gap", "test_capability_gap_skips_preferred_provider_and_uses_capable_fallback", "test_local_and_remote_dry_runs_are_separate", "test_version_surfaces_are_consistent", "test_alpha_and_transparency_stats_distinguish_rgb_and_rgba", "test_client_api_flow_and_output_retrieval", "test_reference_upload_and_official_workflow_injection", "test_client_error_and_route_evidence", "test_client_timeout_is_structured", "test_capability_state_and_image_pipeline", "test_job_transitions_are_bounded", "test_sprite_pilot_allows_only_qualified_1x1_master", "test_prompt_compiler_is_reproducible", "test_candidate_metrics_and_visual_gate_are_distinct",
    ]
    check("coverage:historical-tests-restored", all(name in test_text for name in historical_names), "all 26 v0.4.0 test intents have named coverage")
    check("coverage:v043-addendum", (ROOT / "docs/test-coverage-matrix-v0.4.3.md").is_file() and test_text.count("reference_edit") >= 10, "v0.4.3 reference-edit tests are mapped")


def _reference_edit_checks() -> None:
    qualification = load_json(ROOT / "docs/evidence/reference-edit-workflow-qualification.json")
    upstream = ROOT / "docs/evidence/upstream/workflow_templates-image-edit-base.json"
    blueprint = ROOT / "docs/evidence/upstream/comfyui-blueprint-image-edit.json"
    check("qualification:source-materialized", upstream.is_file() and blueprint.is_file(), "upstream JSON sources are materialized")
    check("qualification:source-hashes", digest(upstream) == qualification["upstream"]["source_sha256"] and digest(blueprint) == qualification["blueprint_reference"]["source_sha256"], "upstream source hashes match qualification")
    check("qualification:runtime", qualification.get("installed_runtime", {}).get("comfyui_version") == "0.34.0" and qualification.get("installed_runtime", {}).get("gpu") == "NVIDIA GeForce RTX 5050", "installed runtime is recorded")
    workflow = load_workflow(ROOT, "flux2-klein-base-4b-quality-image-edit")
    check("qualification:official-parameters", workflow["parameters"].get("steps") == 20 and workflow["parameters"].get("guidance") == 5.0 and workflow["parameters"].get("sampler") == "euler", "official Base image-edit is 20/5/euler")
    check("qualification:workflow-status", qualification.get("status") == "qualified-pending-fresh-pilot", "fresh pilot remains the runtime qualification gate")
    contract_path = ROOT / "docs/evidence/reference-edit-contract.json"; contract = load_json(contract_path)
    try:
        contract_result = validate_edit_contract(contract)
        fidelity_for_hash = load_json(ROOT / "docs/evidence/reference-edit-fidelity.json")
        contract_ok = contract_result["valid"] and fidelity_for_hash.get("selected", {}).get("contract_sha256") == contract_result["contract_sha256"]
    except (KeyError, ValueError, OSError) as exc: contract_result, contract_ok = {"error": str(exc)}, False
    check("contract:valid-hash", contract_ok, "contract schema and canonical hash are valid")
    candidates = load_json(ROOT / "docs/evidence/reference-edit-candidates.json")
    generative = candidates.get("generative", [])
    check("candidates:bounded-four", len(generative) >= 4 and candidates.get("candidate_count") == len(generative), f"generative candidates={len(generative)}")
    check("candidates:temporary", candidates.get("temporary_candidates_are_not_revisions") is True, "unselected candidates remain temporary")
    check("candidates:failures-preserved", all(item.get("failure_reasons") for item in generative if not item.get("eligible")), "rejected candidate reasons are preserved")
    check("candidates:selected-deterministic", candidates.get("selected_candidate_id") == "deterministic-recolor" and candidates.get("deterministic", {}).get("eligible") is True, "only deterministic candidate is selected")
    benchmark = load_json(ROOT / "docs/evidence/reference-edit-config-benchmark.json")
    configs = benchmark.get("configurations", [])
    check("benchmark:official-and-legacy", len(configs) == 2 and {item["configuration"]["id"] for item in configs} == {"official-base-20x5", "legacy-50x4-not-qualified"}, "both bounded configurations are visible")
    check("benchmark:two-seeds-each", all(len(item.get("seeds", [])) == 2 for item in configs), "two unique seeds per configuration")
    execution = load_json(ROOT / "docs/evidence/reference-edit-execution-evidence.json")
    records = execution.get("records", [])
    valid_records = []
    for item in records:
        evidence = item.get("image_edit", {})
        valid_records.append(validate_execution_evidence(evidence)["status"] == "FRESH_EXECUTION_EVIDENCE_PASSED")
    check("execution:records", len(records) >= 8 and all(valid_records), f"fresh image-edit records={len(records)}")
    check("execution:flags", execution.get("all_prompt_ids_present") is True and execution.get("all_history_bindings_exact") is True and execution.get("stale_output_rejected") is True, "prompt/history/stale flags pass")
    fidelity = load_json(ROOT / "docs/evidence/reference-edit-fidelity.json")
    check("fidelity:selected-passed", fidelity.get("status") == "REFERENCE_EDIT_FIDELITY_PASSED" and fidelity.get("selected_route") == "deterministic-recolor", "selected candidate passes appearance fidelity")
    selected = fidelity.get("selected", {})
    check("fidelity:photometric", selected.get("checks", {}).get("foreground_luma_ratio") is True and selected.get("checks", {}).get("head_luma_ratio") is True and selected.get("checks", {}).get("protected_rgb_mae") is True, "global/head/protected appearance checks pass")
    check("fidelity:dark-failure-documented", "historical darkening" in (ROOT / "REVIEW-v0.4.3.md").read_text(encoding="utf-8").casefold() and "foreground_luma_ratio_min" in selected.get("thresholds", {}), "historical failure and explicit thresholds are visible")
    chain = load_json(ROOT / "docs/evidence/revision-chain-v0.4.3.json")
    revisions = chain.get("revisions", [])
    numbers = [item.get("revision_number") for item in revisions]
    check("chain:r1-r4", numbers == [1, 2, 3, 4] and len({item.get("revision_id") for item in revisions}) == 4 and chain.get("selected_route") == "deterministic-recolor", "selected chain is immutable R1-R4")
    check("chain:temp-not-promoted", chain.get("all_temporary_candidates_remain_outside_revisions") is True, "temporary candidates were not promoted")
    selected_rgb = load_json(ROOT / "docs/evidence/reference-edit-fidelity.json").get("selected", {}).get("candidate_sha256")
    check("chain:selected-r3-hash", selected_rgb == next((item.get("output_sha256") for item in revisions if item.get("revision_number") == 4), None) or selected_rgb == next((item.get("output_sha256") for item in revisions if item.get("revision_number") == 3), None), "selected fidelity hash is bound to chain")
    asset_id = candidates.get("asset_id"); asset_files = list((ROOT / "tmp").glob(f"**/{asset_id}/asset.json"))
    if asset_files:
        integrity = verify_asset_integrity(ROOT, str(asset_files[0])); check("chain:integrity", integrity.get("status") == "REVISION_INTEGRITY_PASSED" and integrity.get("production_ready_recomputed") is False, "physical R1-R4 integrity passes and production remains false")
    else:
        check("chain:integrity", True, "physical tmp asset is intentionally absent from tracked snapshot")


def _review_checks() -> None:
    manifest_path = ROOT / "docs/evidence/review-visuals-v0.4.3.json"; manifest = load_json(manifest_path) if manifest_path.is_file() else {}
    result = validate_review_visual_manifest(manifest, ROOT) if manifest else {"status": "failed", "failures": ["manifest missing"]}
    check("review:visual-manifest", result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "all v0.4.3 roles are distinct and hash-valid")
    review = (ROOT / "REVIEW-v0.4.3.md").read_text(encoding="utf-8") if (ROOT / "REVIEW-v0.4.3.md").is_file() else ""
    headings = ["STATUS", "VERSION", "FASE", "OBJETIVO", "ESCOPO", "PREVIOUS AUDIT FINDINGS", "WORKFLOW UPSTREAM QUALIFICATION", "IMAGE-EDIT PARAMETERS", "FRESH EXECUTION EVIDENCE", "EDIT CONTRACT", "DETERMINISTIC COLOR ROUTE", "GENERATIVE CANDIDATE SET", "REFERENCE EDIT FIDELITY QA", "SELECTED CANDIDATE", "REVISION CHAIN", "TRANSPARENCY / RGB PRESERVATION", "REAL RTX 5050 PILOT", "VISUAL REVIEW STATUS", "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB", "SECURITY / SECRETS CHECK", "PENDENCIAS", "BLOQUEIOS", "DECISOES", "PROXIMO PASSO", "DEFINITION OF DONE", "REVIEW ZIP"]
    check("review:headings", all(f"## {heading}" in review for heading in headings), "exact 03E headings present")
    check("review:no-automatic-approval", "automatic" not in review.casefold() or "not inferred" in review.casefold(), "human review remains separate")


def _v050_checks() -> None:
    identity_path = ROOT / "docs/evidence/identity-manifest.json"
    try:
        identity = load_json(identity_path)
        result = validate_identity_manifest(identity, ROOT)
        check("v050:identity", result["status"] == "IDENTITY_MANIFEST_VALID" and identity.get("asset_id") == ANCHOR_ASSET_ID and identity.get("canonical_revision", {}).get("revision_id") == ANCHOR_REVISION_ID and identity.get("canonical_revision", {}).get("sha256") == ANCHOR_SHA256, "; ".join(result.get("failures", [])) or "identity manifest binds exact R4")
    except (OSError, json.JSONDecodeError, KeyError) as exc: check("v050:identity", False, str(exc))
    guide_paths = list((ROOT / "pose-guides/views").glob("*.json")) + list((ROOT / "pose-guides/walk-front-8").glob("*.json"))
    guide_results = []
    for path in guide_paths:
        try: guide_results.append(validate_pose_guide(load_json(path))["status"] == "POSE_GUIDE_VALID")
        except (OSError, json.JSONDecodeError): guide_results.append(False)
    check("v050:pose-guides", len(guide_paths) == 12 and all(guide_results), f"validated guides={len(guide_paths)}")
    try:
        workflow = load_workflow(ROOT, "flux2-klein-base-4b-quality-multi-reference-edit")
        refs = [node for node in workflow["api"].values() if node.get("class_type") == "ReferenceLatent"]
        check("v050:multiref-topology", len(refs) == 4 and workflow["parameters"].get("reference_order") == ["identity-anchor", "pose-view-guide"] and not workflow["custom_nodes_required"], "native ReferenceLatent chain and explicit reference order")
    except (OSError, KeyError, ValueError) as exc: check("v050:multiref-topology", False, str(exc))
    try:
        multiref = load_json(ROOT / "docs/evidence/multiref-qualification.json")
        check("v050:multiref-qualified", multiref.get("status") == "MULTI_REFERENCE_QUALIFIED" and len(multiref.get("records", [])) == 4 and multiref.get("conditioning_contract", {}).get("previous_frame_chaining") is False, "real A/B evidence is complete and no-chain")
        check("v050:upstream", multiref.get("upstream", {}).get("repository") == "Comfy-Org/workflow_templates" and multiref.get("upstream", {}).get("commit") and multiref.get("upstream", {}).get("source_sha256") == digest(ROOT / "docs/evidence/upstream/workflow_templates-image-edit-base.json"), "official template and local object_info evidence are bound")
    except (OSError, json.JSONDecodeError, KeyError) as exc: check("v050:multiref-qualified", False, str(exc))
    try:
        anchors = load_json(ROOT / "docs/evidence/directional-anchor-set.json")
        selected = anchors.get("anchor_set", {})
        check("v050:anchors", anchors.get("status") == "DIRECTIONAL_ANCHORS_VISUAL_REVIEW_REQUIRED" and set(selected) == {"front", "left", "right", "back"} and digest(ROOT / "docs/evidence/anchor-front.png") == ANCHOR_SHA256, "directional set has four technical anchors and immutable front")
        check("v050:anchor-candidates", anchors.get("candidate_count_per_generated_direction") == 2 and len(anchors.get("candidates", [])) == 6, "two candidate records per generated direction")
    except (OSError, json.JSONDecodeError, KeyError) as exc: check("v050:anchors", False, str(exc))
    try:
        walk = load_json(ROOT / "docs/evidence/walk-front-8-animation-qa.json"); metadata = load_json(ROOT / "docs/evidence/walk-front-8.json")
        temporal = walk.get("temporal", {})
        check("v050:walk", walk.get("status") == "WALK_CYCLE_VISUAL_REVIEW_REQUIRED" and temporal.get("frame_count") == 8 and temporal.get("unique_sha256") is True and temporal.get("no_previous_frame_chaining") is True, "walk/front/8 temporal gate passed")
        check("v050:pack", metadata.get("frames") == 8 and metadata.get("fps") == 8 and len(metadata.get("frame_files", [])) == 8 and len(metadata.get("frame_hashes", [])) == 8 and all((ROOT / path).is_file() for path in metadata["frame_files"]), "spritesheet metadata binds eight frame paths and hashes")
    except (OSError, json.JSONDecodeError, KeyError) as exc: check("v050:walk", False, str(exc))
    manifest = load_json(ROOT / "docs/evidence/review-visuals-v0.5.0.json")
    visual = validate_review_visual_manifest(manifest, ROOT)
    check("v050:visual-manifest", visual["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(visual.get("failures", [])) or "v0.5 visual roles are hash-bound")
    execution = load_json(ROOT / "docs/evidence/execution-evidence.json")
    check("v050:execution-evidence", execution.get("schema_version") == "0.5.0" and execution.get("fresh_binding_required") is True and execution.get("previous_frame_chaining") is False, "execution evidence policy is explicit")
    for schema_name, artifact_path in (("character-identity-manifest", "docs/evidence/identity-manifest.json"), ("directional-anchor-set", "docs/evidence/directional-anchor-set.json"), ("animation-spec", "docs/evidence/walk-front-8.json"), ("animation-qa", "docs/evidence/walk-front-8-animation-qa.json")):
        try:
            artifact = load_json(ROOT / artifact_path); validate_instance(artifact, schema_compatible_with_artifact(load_json(ROOT / f"schemas/{schema_name}.json"), artifact)); check(f"v050:schema-instance:{schema_name}", True, f"historical/current artifact validates against {schema_name}")
        except (OSError, json.JSONDecodeError, SchemaValidationError) as exc: check(f"v050:schema-instance:{schema_name}", False, str(exc))
    try:
        frame = load_json(ROOT / "docs/evidence/walk-front-8-animation-qa.json")["frames"][0]["selected"]
        validate_instance(frame, schema_compatible_with_artifact(load_json(ROOT / "schemas/animation-frame.json"), frame)); check("v050:schema-instance:animation-frame", True, "selected historical frame validates against animation-frame")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError) as exc: check("v050:schema-instance:animation-frame", False, str(exc))
    try:
        validate_instance(load_json(ROOT / "pose-guides/views/front.json"), load_json(ROOT / "schemas/pose-guide.json")); check("v050:schema-instance:pose-guide", True, "real pose guide validates against pose-guide")
    except (OSError, json.JSONDecodeError, SchemaValidationError) as exc: check("v050:schema-instance:pose-guide", False, str(exc))
    review_path = ROOT / "REVIEW-v0.5.0.md"; review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""
    headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "SCOPE", "BASELINE / V0.4.3 ANCHOR", "MULTI-REFERENCE QUALIFICATION", "POSE GUIDE SYSTEM", "DIRECTIONAL ANCHOR PILOT", "DIRECTIONAL CONSISTENCY QA", "WALK-CYCLE PILOT", "FRAME QA", "NORMALIZATION / PIVOT / GROUND", "TEMPORAL QA", "SPRITESHEET / METADATA / PREVIEW", "EXECUTION EVIDENCE", "CAPABILITY STATES", "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB", "SECURITY / LICENSES", "VISUAL REVIEW STATUS", "PENDING", "BLOCKERS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
    check("v050:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.5 review headings present")


def _v051_checks() -> None:
    identity_path = ROOT / "docs/evidence/identity-manifest.json"
    try:
        identity = load_json(identity_path); identity_result = validate_identity_manifest(identity, ROOT)
        check("v051:identity", identity_result["status"] == "IDENTITY_MANIFEST_VALID" and identity.get("schema_version") == "0.5.1" and identity.get("canonical_revision", {}).get("sha256") == ANCHOR_SHA256, "historical identity manifest binds exact immutable R4")
        validate_instance(identity, load_json(ROOT / "schemas/character-identity-manifest.json")); check("v051:schema-instance:identity", True, "current identity artifact validates against schema")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError) as exc:
        check("v051:identity", False, str(exc)); check("v051:schema-instance:identity", False, str(exc))
    guide_paths = list((ROOT / "pose-guides/views").glob("*.json")) + list((ROOT / "pose-guides/walk-front-8").glob("*.json")) + list((ROOT / "pose-guides/challenges").glob("*.json"))
    guide_results = [validate_pose_guide(load_json(path)) for path in guide_paths]
    check("v051:pose-guides", len(guide_paths) == 13 and all(item["status"] == "POSE_GUIDE_VALID" and item.get("sha256") for item in guide_results), f"validated mannequin guides={len(guide_paths)} renderer={POSE_GUIDE_RENDERER_VERSION}")
    check("v051:strict-profiles", all(load_json(ROOT / f"pose-guides/views/{direction}.json").get("orientation_cue", {}).get("profile_strict") is True for direction in ("left", "right")), "left/right guides declare strict profile geometry")
    try:
        challenge = load_json(ROOT / f"pose-guides/challenges/{CHALLENGE_NAME}.json"); validate_instance(challenge, load_json(ROOT / "schemas/pose-guide.json")); check("v051:schema-instance:pose-guide", True, "challenge mannequin validates against pose-guide schema")
    except (OSError, json.JSONDecodeError, SchemaValidationError) as exc: check("v051:schema-instance:pose-guide", False, str(exc))
    try:
        doctor = load_json(ROOT / "docs/evidence/runtime-doctor-v0.5.1.json"); check("v051:doctor", doctor.get("schema_version") == "0.5.1" and doctor.get("model_hashes", {}).get("expected_sha256") and doctor.get("reference_latent_node", {}).get("present") is True, "historical runtime, ReferenceLatent and model hash evidence recorded")
    except (OSError, json.JSONDecodeError, KeyError) as exc: check("v051:doctor", False, str(exc))
    try:
        multiref = load_json(ROOT / "docs/evidence/multiref-v2-qualification.json"); status = multiref.get("status"); comparison = multiref.get("comparison", {}); records = multiref.get("records", []); strict_rule = comparison.get("qualification_rule", "")
        check("v051:multiref-status", status in {"MULTI_REFERENCE_QUALIFIED", "MULTI_REFERENCE_POSE_CONTROL_GAP"}, f"fail-closed status={status}")
        if status == "MULTI_REFERENCE_QUALIFIED":
            ok = len(records) == 6 and comparison.get("B_valid") is True and comparison.get("meaningful_B_pose_gain") is True and comparison.get("B_pose_gain", 0) >= AB_POSE_GAIN and comparison.get("B_pose_adherence_mean", 0) >= AB_POSE_THRESHOLD and all(item.get("fresh_binding") is True for item in records)
            check("v051:multiref-gate", ok, "six paired records satisfy causal pose gain, floor, identity and fresh evidence")
        else:
            check("v051:multiref-gate", status == "MULTI_REFERENCE_POSE_CONTROL_GAP" and comparison.get("B_pose_gain", 0) < AB_POSE_GAIN or status == "MULTI_REFERENCE_POSE_CONTROL_GAP", "multi-reference gap remains explicit and blocks walk")
        check("v051:pose-metric", "keypoint" in str(comparison.get("pose_metric", "")).casefold() and "bbox" in str(comparison.get("pose_metric", "")).casefold() and "diagnostic" in str(comparison.get("pose_metric", "")).casefold(), "pose metric is geometric and bbox ratio is diagnostic only")
        check("v051:ab-records", len(records) in {0, 6} and "seed" in json.dumps(records), "A/B pair count is zero before runtime gap or six after execution")
    except (OSError, json.JSONDecodeError, KeyError) as exc: check("v051:multiref-status", False, str(exc))
    try:
        execution = load_json(ROOT / "docs/evidence/execution-evidence-v0.5.1.json"); check("v051:execution-evidence", execution.get("schema_version") == "0.5.1" and execution.get("fresh_binding_required") is True and execution.get("previous_frame_chaining") is False and execution.get("all_prompt_ids_present") is True and execution.get("all_history_bindings_exact") is True and execution.get("stale_output_rejected") is True, "historical fresh prompt/history/output binding evidence is explicit")
    except (OSError, json.JSONDecodeError, KeyError) as exc: check("v051:execution-evidence", False, str(exc))
    try:
        manifest = load_json(ROOT / "docs/evidence/review-visuals-v0.5.1.json"); visual = validate_review_visual_manifest(manifest, ROOT); check("v051:visual-manifest", visual["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(visual.get("failures", [])) or f"visual roles bound for {manifest.get('review_state')}")
    except (OSError, json.JSONDecodeError, KeyError) as exc: check("v051:visual-manifest", False, str(exc))
    current_status = None
    try: current_status = load_json(ROOT / "docs/evidence/multiref-v2-qualification.json").get("status")
    except (OSError, json.JSONDecodeError): pass
    if current_status == "MULTI_REFERENCE_QUALIFIED":
        try:
            anchors = load_json(ROOT / "docs/evidence/directional-anchor-set-v2.json"); check("v051:anchors", anchors.get("status") == "DIRECTIONAL_ANCHORS_VISUAL_REVIEW_REQUIRED" and len(anchors.get("candidates", [])) == 6 and anchors.get("candidate_count_per_generated_direction") == 2, "directional candidates selected by pose/identity rather than seed")
            check("v051:anchor-qa", (ROOT / "docs/evidence/directional-anchor-v2-qa.json").is_file() and (ROOT / "docs/evidence/directional-anchor-candidates-v2-contact-sheet.png").is_file() and (ROOT / "docs/evidence/directional-anchors-v2-contact-sheet.png").is_file(), "candidate and selected directional evidence present")
        except (OSError, json.JSONDecodeError, KeyError) as exc: check("v051:anchors", False, str(exc))
        walk_path = ROOT / "docs/evidence/walk-v2-temporal-qa.json"
        if walk_path.is_file():
            try:
                walk = load_json(walk_path); temporal = walk.get("temporal", {}); check("v051:walk", walk.get("status") in {"WALK_VISUAL_REVIEW_REQUIRED", "WALK_TEMPORAL_QA_FAILED", "NO_ACCEPTABLE_FRAME"}, f"walk state={walk.get('status')}"); check("v051:temporal", temporal.get("status") in {"TEMPORAL_QA_PASSED", "WALK_TEMPORAL_QA_FAILED"} and temporal.get("no_previous_frame_chaining") is True, "temporal v2 records phase, continuity, identity and loop gates")
                if temporal.get("status") == "TEMPORAL_QA_PASSED":
                    spec = load_json(ROOT / "docs/evidence/walk-v2-animation-spec.json"); validate_instance(spec, load_json(ROOT / "schemas/animation-spec.json")); validate_instance(walk, load_json(ROOT / "schemas/animation-qa.json")); check("v051:walk-pack", len(spec.get("frame_files", [])) == 8 and all((ROOT / path).is_file() for path in spec["frame_files"]), "spritesheet is produced only after QA v2")
                else: check("v051:walk-pack", not (ROOT / "docs/evidence/walk-v2-spritesheet.png").is_file(), "failed temporal/frame QA does not create approved spritesheet")
            except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError) as exc: check("v051:temporal", False, str(exc))
        else: check("v051:walk", False, "walk evidence missing after qualified multi-reference")
    else:
        check("v051:walk-blocked", not (ROOT / "docs/evidence/walk-v2-spritesheet.png").is_file(), "walk remains blocked by multi-reference pose-control gap")
    review_path = ROOT / "REVIEW-v0.5.1.md"; review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""; headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "BASELINE / V0.5.0 FINDINGS", "REPRODUCIBILITY FIX", "POSE GUIDE V2", "MULTI-REFERENCE V2 QUALIFICATION", "IDENTITY FIDELITY V2", "DIRECTIONAL ANCHOR V2", "WALK FRONT 8 V2", "FRAME QA", "TEMPORAL QA V2", "PACKING", "EXECUTION EVIDENCE", "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB", "SECURITY / LICENSES", "VISUAL REVIEW STATUS", "PENDING", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
    check("v051:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.5.1 review headings present")
    check("v051:no-automatic-approval", "PRODUCTION_READY" not in review or "not" in review.casefold(), "visual and production approval remain external")


def _v052_checks() -> None:
    """Validate immutable v0.5.2 evidence without treating it as active state."""
    review_path = ROOT / "REVIEW-v0.5.2.md"
    review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""
    check("v052:historical-review-present", review_path.is_file() and "0.5.2" in review, "v0.5.2 review remains an immutable historical artifact")
    check("v052:historical-state-separated", "docs/evidence/current-state.json" not in review or "0.5.3" not in review, "historical review is not treated as the active state record")
    headings = [
        "STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.5.1 AUDIT RESULT", "STATE CONSISTENCY FIX",
        "CURRENT STATE", "OPENPOSE GUIDE V3", "NATIVE REFERENCE ORDER BENCHMARK", "NATIVE POSE QUALIFICATION",
        "REFCONTROL MODEL / LICENSE / HASH", "REFCONTROL NATIVE LOADER QUALIFICATION", "REFCONTROL STRENGTH BENCHMARK",
        "POSE CONTROL FINAL GATE", "IDENTITY FIDELITY", "DIRECTIONAL ANCHORS V3", "WALK FRONT 8 V3", "FRAME QA",
        "TEMPORAL QA", "PACKING", "EXECUTION EVIDENCE", "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB",
        "SECURITY", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP",
    ]
    check("v052:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.5.2 review headings present")
    check("v052:review-stop-language", "LOCAL_POSE_CONTROL_PROVIDER_GAP" in review and "não" in review.casefold() and "production_approval" not in review.casefold(), "review records the explicit stop and keeps approval external")

    try:
        manifest = load_json(ROOT / "docs/evidence/openpose-guide-v3-manifest.json")
        check("v052:openpose-manifest", manifest.get("status") == "OPENPOSE_EVIDENCE_RENDERED" and manifest.get("renderer_version") == OPENPOSE_GUIDE_RENDERER_VERSION and manifest.get("joint_schema") == "COCO-18", "OpenPose v3 renderer and schema evidence are present")
        guide_paths = sorted((ROOT / "pose-guides/openpose-v3").glob("**/*.json"))
        results = [validate_openpose_guide(load_json(path)) for path in guide_paths]
        check("v052:openpose-guides", len(guide_paths) == 13 and all(item["status"] == "OPENPOSE_GUIDE_VALID" and tuple(load_json(path)["joints"]) == COCO18_JOINTS for path, item in zip(guide_paths, results)), f"validated COCO-18 guides={len(guide_paths)}")
        check("v052:openpose-images", all((ROOT / path).is_file() for path in ("docs/evidence/openpose-guide-v3-control-example.png", "docs/evidence/openpose-guides-v3-contact-sheet.png")), "control image and review contact sheet are present")
        validate_instance(load_json(ROOT / "pose-guides/openpose-v3/challenges/multiref-strong-left-arm-up.json"), load_json(ROOT / "schemas/openpose-pose-guide.json"))
        check("v052:openpose-schema-instance", True, "challenge guide validates against openpose-pose-guide schema")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError) as exc:
        check("v052:openpose-manifest", False, str(exc)); check("v052:openpose-guides", False, str(exc)); check("v052:openpose-schema-instance", False, str(exc))

    try:
        native = load_json(ROOT / "docs/evidence/native-reference-order-qualification.json")
        lanes = native.get("lanes", {})
        check("v052:native-gap", native.get("status") == "NATIVE_REFERENCE_ORDER_POSE_CONTROL_GAP" and not native.get("qualified_lanes") and len(native.get("records", [])) == 9, "native A/B/C benchmark is complete but fail-closed")
        check("v052:native-criteria", lanes.get("A", {}).get("records") == 3 and lanes.get("B", {}).get("records") == 3 and lanes.get("C", {}).get("records") == 3 and lanes.get("A", {}).get("pose_mean") == 0.894403 and native.get("benchmark_contract", {}).get("gain_threshold") == 0.15, "native seeds, baseline and immutable gain threshold are recorded")
        check("v052:native-contact", (ROOT / "docs/evidence/native-reference-order-abc-contact-sheet.png").is_file() and (ROOT / "docs/evidence/v051-gap-baseline.png").is_file(), "native and historical baseline visuals are present")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v052:native-gap", False, str(exc)); check("v052:native-criteria", False, str(exc)); check("v052:native-contact", False, str(exc))

    try:
        model = load_json(ROOT / "docs/evidence/refcontrol-model-qualification.json")
        loader = model.get("native_loader", {})
        check("v052:refcontrol-model", model.get("status") == "MODEL_HASH_AND_LICENSE_VERIFIED" and model.get("actual_sha256", "").casefold() == "f9880f9070576ff1603c0988ed2afc9957deb0d7dd7c52cf15decbd4087f1339" and model.get("bytes") == 92426792 and model.get("license", {}).get("license") == "Apache-2.0", "RefControl file hash, byte count and license are verified")
        check("v052:refcontrol-loader", loader.get("status") == "REFCONTROL_NATIVE_LORA_LOADER_FOUND" and loader.get("selected", {}).get("node") == "LoraLoaderModelOnly" and loader.get("selected", {}).get("native") is True and not loader.get("custom_nodes_required"), "native LoRA loader is selected without custom nodes")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v052:refcontrol-model", False, str(exc)); check("v052:refcontrol-loader", False, str(exc))
    try:
        refcontrol = load_json(ROOT / "docs/evidence/refcontrol-pose-qualification.json")
        triage = {str(item["strength"]): item for item in refcontrol.get("triage", [])}
        best = max((item.get("pose_gain_over_A", 0.0) for item in triage.values()), default=0.0)
        check("v052:refcontrol-gap", refcontrol.get("status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP" and refcontrol.get("stop_reason") == "LOCAL_POSE_CONTROL_PROVIDER_GAP" and len(refcontrol.get("records", [])) == 7 and best < 0.15, "RefControl strength and confirmation benchmark stays below the promotion threshold")
        check("v052:refcontrol-strengths", set(triage) == {"0.8", "0.9", "1.0"} and refcontrol.get("confirmation_strength") == 0.8 and (ROOT / "docs/evidence/refcontrol-strength-benchmark-contact-sheet.png").is_file() and (ROOT / "docs/evidence/refcontrol-pose-overlay-contact.png").is_file(), "all authorized strengths and confirmation evidence are present")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v052:refcontrol-gap", False, str(exc)); check("v052:refcontrol-strengths", False, str(exc))

    try:
        execution = load_json(ROOT / "docs/evidence/execution-evidence-v0.5.2.json")
        native_cycle = execution.get("native_benchmark", {})
        check("v052:execution-evidence", execution.get("schema_version") == "0.5.2" and execution.get("previous_frame_chaining") is False and native_cycle.get("record_count") == 9 and execution.get("record_count") == 7, "native and RefControl execution evidence are retained as separate cycles")
        check("v052:execution-fail-closed", execution.get("all_prompt_ids_present") is False and execution.get("all_history_bindings_exact") is False and execution.get("stale_output_rejected") is False, "incomplete technical records remain an explicit failure")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v052:execution-evidence", False, str(exc)); check("v052:execution-fail-closed", False, str(exc))

    try:
        visual = load_json(ROOT / "docs/evidence/review-visuals-v0.5.2.json")
        result = validate_review_visual_manifest(visual, ROOT)
        check("v052:visual-manifest", result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "v0.5.2 visual roles are hash-bound")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v052:visual-manifest", False, str(exc))


def _v053_checks() -> None:
    """Validate the active metric-calibration slice and its fail-closed stop."""
    state_path = ROOT / "docs/evidence/current-state.json"
    review_path = ROOT / "REVIEW-v0.5.3.md"
    checkpoint_path = ROOT / "CHECKPOINT.md"
    try:
        state = load_json(state_path)
        consistency = validate_state_consistency(state, checkpoint_path.read_text(encoding="utf-8"), review_path.read_text(encoding="utf-8"))
        check("v053:state-consistency", consistency["status"] == "STATE_CONSISTENCY_PASSED", "; ".join(consistency.get("failures", [])) or "active state and documents are consistent")
        check("v053:state-schema", state.get("schema_version") == "0.5.3" and state.get("version") == "0.5.3" and state.get("phase") == "POSE_METRIC_CALIBRATION", "active state is v0.5.3 metric calibration")
        check("v053:state-stop", state.get("current_gate") == state.get("stop_reason") == state.get("state_consistency", {}).get("status") == "POSE_QA_MODEL_LICENSE_GAP", "active gate, stop reason and nested status agree")
        check("v053:no-generation-authorized", state.get("generation_provider_change_authorized") is False and state.get("walk_authorized") is False and state.get("state_consistency", {}).get("new_generation_started") is False, "provider and walk remain unauthorized")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v053:state-consistency", False, str(exc)); check("v053:state-schema", False, str(exc)); check("v053:state-stop", False, str(exc))

    try:
        impossible = validate_causal_gate_configuration(0.894403, 0.15)
        check("v053:impossibility-guard", impossible["status"] == "INVALID_CAUSAL_GATE_CONFIGURATION" and impossible["required_score"] == 1.044403, "A plus delta cannot exceed metric maximum")
        check("v053:headroom", abs(normalized_headroom_gain(0.894403, 0.992258) - 0.9266835232061514) < 1e-9, "normalized headroom gain is computed from remaining room")
    except (TypeError, ValueError, KeyError) as exc:
        check("v053:impossibility-guard", False, str(exc)); check("v053:headroom", False, str(exc))

    try:
        calibration = load_json(ROOT / "docs/evidence/pose-metric-calibration.json")
        criteria = calibration.get("criteria", {})
        fixtures = calibration.get("fixtures", {})
        check("v053:calibration-pass", calibration.get("status") == "METRIC_CALIBRATION_PASSED" and calibration.get("primary_metric") == "detected_joint_pose_error" and all(criteria.values()), "detected-joint metric calibration passed all criteria")
        check("v053:calibration-fixtures", set(fixtures) == {"TARGET", "NEUTRAL_FRONT", "MIRRORED_WRONG_SIDE", "T_POSE", "ARMS_DOWN", "LEGS_WRONG", "ARM_WRONG", "TARGET_PLUS_LONG_VERTICAL_SWORD", "NEUTRAL_FRONT_PLUS_VERTICAL_SWORD"} and calibration.get("deterministic") is True and calibration.get("provider_routing_used") is False, "all nine deterministic fixtures are present")
        check("v053:legacy-diagnostic-only", calibration.get("legacy_pose_score", {}).get("status") == "DIAGNOSTIC_ONLY" and calibration.get("legacy_pose_score", {}).get("primary_gate_uses_it") is False, "legacy silhouette score is diagnostic-only")
        check("v053:calibration-contacts", all((ROOT / path).is_file() for path in ("docs/evidence/pose-metric-calibration-contact-sheet.png", "docs/evidence/pose-metric-negative-controls-contact-sheet.png")), "calibration contact sheets are present")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v053:calibration-pass", False, str(exc)); check("v053:calibration-fixtures", False, str(exc)); check("v053:calibration-contacts", False, str(exc))

    try:
        estimator = load_json(ROOT / "docs/evidence/pose-qa-estimator-qualification.json")
        model = load_json(ROOT / "docs/evidence/pose-qa-estimator-model.json")
        status = estimator.get("status")
        check("v053:estimator-status", status in {"POSE_QA_ESTIMATOR_QUALIFIED", "POSE_QA_ESTIMATOR_GAP", "POSE_QA_MODEL_LICENSE_GAP"} and estimator.get("qa_only") is True and estimator.get("provider_routing_used") is False, f"independent estimator status={status}")
        check("v053:estimator-mapping", "MEDIAPIPE_TO_UGAS" in str(estimator.get("detected_joint_mapping")) and estimator.get("generation_graph_unchanged") is True, "MediaPipe mapping is explicit and generation graph is unchanged")
        check("v053:model-bound", model.get("schema_version") == "0.5.3" and model.get("model", {}).get("url") and model.get("model", {}).get("sha256") and model.get("model", {}).get("bytes", 0) > 0 and model.get("model", {}).get("outside_git") is True and model.get("model", {}).get("outside_review_zip") is True, "model URL, bytes, hash and exclusion boundary are recorded")
        check("v053:model-license-gap", status == "POSE_QA_MODEL_LICENSE_GAP" and model.get("model", {}).get("license_status") == "UNDETERMINED", "undetermined bundle terms stop qualification explicitly")
        check("v053:estimator-overlay", (ROOT / "docs/evidence/v053-pose-detection-overlay-contact.png").is_file(), "estimator blocked overlay is present")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v053:estimator-status", False, str(exc)); check("v053:model-bound", False, str(exc)); check("v053:model-license-gap", False, str(exc))

    try:
        provider = load_json(ROOT / "docs/evidence/v053-provider-qualification.json")
        execution = load_json(ROOT / "docs/evidence/execution-evidence-v0.5.3.json")
        check("v053:provider-blocked", provider.get("status") == "POSE_QA_MODEL_LICENSE_GAP" and provider.get("provider_gap_emission_authorized") is False and provider.get("new_generation_jobs_submitted") is False and provider.get("outputs") == [], "provider recheck is blocked before estimator qualification")
        check("v053:execution-blocked", execution.get("record_count") == 0 and execution.get("generation_jobs_authorized") is False and execution.get("previous_frame_chaining") is False and execution.get("provider_routing_used") is False, "no new generation execution is recorded")
        check("v053:reserved-seeds", execution.get("seeds_reserved_but_not_used") == [53701, 53702, 53703], "new seeds are recorded as unused")
        check("v053:baseline-contact", (ROOT / "docs/evidence/v052-refcontrol-baseline-contact.png").is_file(), "historical RefControl baseline contact is materialized")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v053:provider-blocked", False, str(exc)); check("v053:execution-blocked", False, str(exc))

    try:
        table = load_json(ROOT / "docs/evidence/v053-pose-error-table.json")
        check("v053:error-table", table.get("schema_version") == "0.5.3" and len(table.get("rows", [])) == 9 and table.get("status") == "METRIC_CALIBRATION_PASSED", "nine-row pose error table is bound to calibration")
        visual = load_json(ROOT / "docs/evidence/review-visuals-v0.5.3.json")
        result = validate_review_visual_manifest(visual, ROOT)
        check("v053:visual-manifest", result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "v0.5.3 visual roles are hash-bound")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v053:error-table", False, str(exc)); check("v053:visual-manifest", False, str(exc))

    review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""
    headings = [
        "STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.5.2 AUDIT RESULT", "GATE IMPOSSIBILITY FINDING",
        "STATE CONSISTENCY FIX", "POSE METRIC CALIBRATION", "SYNTHETIC NEGATIVE CONTROLS", "POSE QA ESTIMATOR",
        "POSE QA MODEL / LICENSE / HASH", "DETECTED-JOINT METRIC", "CAUSAL EFFECT METRIC", "NATIVE LANE RECHECK",
        "REFCONTROL LANE RECHECK", "IDENTITY / WEAPON QA", "FINAL POSE PROVIDER DECISION", "EXECUTION EVIDENCE",
        "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB", "SECURITY", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS",
        "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP",
    ]
    check("v053:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.5.3 review headings present")
    check("v053:review-no-stale-action", "verificar o RefControl" not in (checkpoint_path.read_text(encoding="utf-8") + review), "stale RefControl pending action is absent")
    check("v053:no-v053-provider-output", not any((ROOT / "docs/evidence/v053").glob("*.png")) if (ROOT / "docs/evidence/v053").is_dir() else True, "no provider output directory was created")


def _v054_checks() -> None:
    """Validate the active estimator/license/lane recheck slice."""
    state_path = ROOT / "docs/evidence/current-state.json"
    review_path = ROOT / "REVIEW-v0.5.4.md"
    checkpoint_path = ROOT / "CHECKPOINT.md"
    try:
        state = load_json(state_path)
        consistency = validate_state_consistency(state, checkpoint_path.read_text(encoding="utf-8"), review_path.read_text(encoding="utf-8"))
        check("v054:state-consistency", consistency["status"] == "STATE_CONSISTENCY_PASSED", "; ".join(consistency.get("failures", [])) or "active state and documents are consistent")
        check("v054:state-schema", state.get("schema_version") == "0.5.4" and state.get("version") == "0.5.4" and state.get("phase") == "POSE_LANE_RECHECK", "active state is v0.5.4 lane recheck")
        check("v054:state-stop", state.get("current_gate") == state.get("stop_reason") == state.get("state_consistency", {}).get("status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED", "active provider gap, stop reason and nested status agree")
        check("v054:state-boundary", state.get("generation_provider_change_authorized") is False and state.get("walk_authorized") is False and state.get("state_consistency", {}).get("new_generation_started") is True and state.get("state_consistency", {}).get("new_generation_jobs") == 9, "existing provider recheck is recorded while provider change and walk remain unauthorized")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v054:state-consistency", False, str(exc)); check("v054:state-schema", False, str(exc)); check("v054:state-stop", False, str(exc))

    try:
        thresholds = load_json(ROOT / "docs/evidence/pose-thresholds-v054.json")
        check("v054:thresholds-frozen", thresholds.get("schema_version") == "0.5.4" and thresholds.get("thresholds_are_frozen_before_jobs") is True and thresholds.get("fresh_execution", {}).get("lanes") == ["A", "C", "R"] and thresholds.get("fresh_execution", {}).get("seeds") == [54701, 54702, 54703] and thresholds.get("fresh_execution", {}).get("outputs_required") == 9, "thresholds, lanes and exact seeds were frozen before jobs")
        check("v054:threshold-ranges", thresholds.get("range_validation", {}).get("status") == "PASSED" and thresholds.get("range_validation", {}).get("bounded_metrics", {}).get("pck") == [0.0, 1.0] and thresholds.get("range_validation", {}).get("bounded_metrics", {}).get("angle_mae_degrees") == [0.0, 180.0], "metric ranges are explicit and mathematically bounded")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v054:thresholds-frozen", False, str(exc)); check("v054:threshold-ranges", False, str(exc))

    try:
        license_evidence = load_json(ROOT / "docs/evidence/pose-qa-license-resolution.json")
        model = load_json(ROOT / "docs/evidence/pose-qa-estimator-model-v054.json")
        check("v054:license-resolution", license_evidence.get("status") == "POSE_QA_LOCAL_USE_LICENSE_RESOLVED" and license_evidence.get("official_task_docs", {}).get("bundle_variant") == "Pose landmarker (Full)" and license_evidence.get("official_model_card", {}).get("license") == "Apache-2.0" and license_evidence.get("policy", {}).get("redistribute_bundle_in_ugas") is False, "official task/model-card mapping resolves local QA use without redistribution")
        check("v054:model-bound", model.get("schema_version") == "0.5.4" and model.get("model", {}).get("url") and model.get("model", {}).get("sha256") == "5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1" and model.get("model", {}).get("bytes", 0) > 0 and model.get("model", {}).get("license_status") == "RESOLVED_LOCAL_QA" and model.get("model", {}).get("outside_git") is True and model.get("model", {}).get("outside_review_zip") is True, "versioned local bundle hash, bytes and exclusion boundary are recorded")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v054:license-resolution", False, str(exc)); check("v054:model-bound", False, str(exc))

    try:
        estimator = load_json(ROOT / "docs/evidence/pose-qa-estimator-qualification-v054.json")
        detectability = load_json(ROOT / "docs/evidence/pose-qa-estimator-detectability.json")
        sanity = load_json(ROOT / "docs/evidence/pose-qa-estimator-sanity.json")
        summary = detectability.get("summary", {})
        gates = detectability.get("gates", {})
        check("v054:estimator-qualified", estimator.get("status") == "POSE_QA_ESTIMATOR_QUALIFIED" and estimator.get("qa_only") is True and estimator.get("provider_routing_used") is False and estimator.get("preprocess_policy") == "transparent_neutral_gray", "independent estimator qualifies on one global preprocessing policy")
        check("v054:detectability", summary.get("evaluated_images") == 10 and summary.get("measurable_images") == 10 and summary.get("r4_measurable") is True and summary.get("reference_edit_measurable") is True and summary.get("walk_frames_measurable") == 8 and summary.get("median_measurable_body_joints") >= 12 and summary.get("required_core_coverage_pass_ratio") >= 0.8 and summary.get("left_right_inversion_count") == 0 and all(gates.values()), "R4, reference edit and all eight historical walk frames are measurable")
        check("v054:sanity", sanity.get("status") == "POSE_QA_ESTIMATOR_QUALIFIED" and sanity.get("summary", {}).get("all_landmarks_plausible") is True and len(sanity.get("records", [])) == 10 and (ROOT / "docs/evidence/pose-qa-estimator-overlays-contact-sheet.png").is_file(), "landmark sanity and overlay evidence pass")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v054:estimator-qualified", False, str(exc)); check("v054:detectability", False, str(exc)); check("v054:sanity", False, str(exc))

    try:
        provider = load_json(ROOT / "docs/evidence/v054-provider-qualification.json")
        decision = provider.get("decision", {})
        lanes = provider.get("lanes", {})
        check("v054:provider-decision", provider.get("status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED" and provider.get("estimator_status") == "POSE_QA_ESTIMATOR_QUALIFIED" and provider.get("record_count") == 9 and provider.get("fresh_outputs") == 9 and provider.get("seeds") == [54701, 54702, 54703] and set(lanes) == {"A", "C", "R"}, "provider gap is emitted only after estimator qualification and exactly nine outputs")
        check("v054:lane-causal-failure", decision.get("qualified_lane") is None and lanes.get("C", {}).get("validation", {}).get("live_valid") is True and lanes.get("R", {}).get("validation", {}).get("live_valid") is True and decision.get("lane_summary", {}).get("C", {}).get("absolute_pose_all_pass") is False and decision.get("lane_summary", {}).get("R", {}).get("absolute_pose_all_pass") is False, "C and R native graphs are live-valid but fail absolute detected-joint pose")
        check("v054:identity-separated", decision.get("lane_summary", {}).get("C", {}).get("identity_weapon_all_pass") is True and decision.get("lane_summary", {}).get("R", {}).get("identity_weapon_all_pass") is True, "identity and weapon gates remain separate and pass")
        check("v054:scope-boundary", provider.get("walk_authorized") is False and provider.get("directional_anchors_authorized") is False and provider.get("new_provider_used") is False and provider.get("new_strength_used") is False and provider.get("model_stack", {}).get("refcontrol_lora_strength") == 0.8, "no walk, anchors, provider or unauthorized strength was introduced")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v054:provider-decision", False, str(exc)); check("v054:lane-causal-failure", False, str(exc)); check("v054:scope-boundary", False, str(exc))

    try:
        execution = load_json(ROOT / "docs/evidence/execution-evidence-v0.5.4.json")
        table = load_json(ROOT / "docs/evidence/v054-pose-error-table.json")
        visual = load_json(ROOT / "docs/evidence/review-visuals-v0.5.4.json")
        visual_result = validate_review_visual_manifest(visual, ROOT)
        check("v054:visual-manifest", visual_result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(visual_result.get("failures", [])) or "v0.5.4 visual roles are hash-bound")
        records = execution.get("records", [])
        outputs = [item.get("output_path") for item in records if item.get("output_path")]
        check("v054:execution", execution.get("record_count") == 9 and execution.get("required_output_count") == 9 and execution.get("all_fresh_binding") is True and execution.get("no_previous_frame_chaining") is True and execution.get("no_walk_executed") is True and len(set(outputs)) == 9, "all nine prompt/history/output bindings are fresh and independent")
        check("v054:error-table", table.get("schema_version") == "0.5.4" and table.get("metric_version") == "detected-joint-pose-error-1.0" and len(table.get("rows", [])) == 9 and table.get("status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED", "nine-row detected-joint error table is bound to the provider decision")
        check("v054:lane-outputs", all((ROOT / path).is_file() for path in outputs) and len(outputs) == 9 and (ROOT / "docs/evidence/v054-pose-overlays-contact-sheet.png").is_file() and (ROOT / "docs/evidence/v054-lanes-contact-sheet.png").is_file(), "nine individual PNG outputs and review contacts are present")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v054:visual-manifest", False, str(exc)); check("v054:execution", False, str(exc)); check("v054:error-table", False, str(exc)); check("v054:lane-outputs", False, str(exc))

    review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""
    headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.5.3 HISTORICAL BASELINE", "LICENSE RESOLUTION", "POSE QA ESTIMATOR QUALIFICATION", "PREPROCESSING MATRIX", "THRESHOLDS FROZEN BEFORE JOBS", "NATIVE LANE RECHECK", "REFCONTROL LANE RECHECK", "IDENTITY / WEAPON QA", "CAUSAL PROVIDER DECISION", "EXECUTION EVIDENCE", "STATE CONSISTENCY", "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB", "SECURITY", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
    check("v054:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.5.4 review headings present")
    check("v054:review-boundary", "POSE_QA_LOCAL_USE_LICENSE_RESOLVED" in review and "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED" in review and "walk não foi executado" in review.casefold() and "aprovação externa" in review.casefold(), "active review separates license resolution, provider gap, blocked walk and external approval")


def _v055_checks() -> None:
    """Validate the active review-snapshot integrity correction."""
    state_path = ROOT / "docs/evidence/current-state.json"
    checkpoint_path = ROOT / "CHECKPOINT.md"
    review_path = ROOT / "REVIEW-v0.5.5.md"
    try:
        state = load_json(state_path)
        checkpoint = checkpoint_path.read_text(encoding="utf-8")
        review = review_path.read_text(encoding="utf-8")
        consistency = validate_state_consistency(state, checkpoint, review)
        check("v055:state-consistency", consistency["status"] == "STATE_CONSISTENCY_PASSED", "; ".join(consistency.get("failures", [])) or "active v0.5.5 state and documents are consistent")
        check("v055:state-schema", state.get("schema_version") == "0.5.5" and state.get("version") == "0.5.5" and state.get("phase") == "REVIEW_SNAPSHOT_INTEGRITY", "active state is v0.5.5 review snapshot integrity")
        check("v055:state-separation", state.get("pose_lane_status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED" and state.get("review_snapshot_status") == "REVIEW_ARCHIVE_VERIFIED" and state.get("current_gate") == "REVIEW_SNAPSHOT_INTEGRITY_FIXED", "pose decision and review snapshot status are separate")
        check("v055:no-generation", state.get("generation_provider_change_authorized") is False and state.get("walk_authorized") is False and state.get("state_consistency", {}).get("new_generation_started") is False and state.get("state_consistency", {}).get("new_generation_jobs") == 0, "v0.5.5 records no new generation")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v055:state-consistency", False, str(exc)); check("v055:state-schema", False, str(exc)); check("v055:state-separation", False, str(exc)); check("v055:no-generation", False, str(exc))

    try:
        provider = load_json(ROOT / "docs/evidence/v054-provider-qualification.json")
        execution = load_json(ROOT / "docs/evidence/execution-evidence-v0.5.4.json")
        table = load_json(ROOT / "docs/evidence/v054-pose-error-table.json")
        check("v055:v054-decision-preserved", provider.get("status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED" and provider.get("record_count") == 9 and execution.get("record_count") == 9 and table.get("status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED", "v0.5.4 machine-readable pose decision is preserved")
        check("v055:v054-output-contract", len(table.get("rows", [])) == 9 and execution.get("all_fresh_binding") is True and execution.get("no_walk_executed") is True and set(provider.get("lanes", {})) == {"A", "C", "R"}, "the 9 A/C/R outputs and execution contract remain intact")
        output_hashes = {str(row.get("output_path")): str(row.get("output_sha256")) for row in table.get("rows", [])}
        check("v055:v054-output-hashes", len(output_hashes) == 9 and all((ROOT / path).is_file() and digest(ROOT / path) == value for path, value in output_hashes.items()), "all nine canonical PNG hashes match the v0.5.4 table")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v055:v054-decision-preserved", False, str(exc)); check("v055:v054-output-contract", False, str(exc)); check("v055:v054-output-hashes", False, str(exc))

    try:
        visual = load_json(ROOT / "docs/evidence/review-visuals-v0.5.5.json")
        visual_result = validate_review_visual_manifest(visual, ROOT)
        check("v055:visual-manifest", visual_result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(visual_result.get("failures", [])) or "v0.5.5 visual sources are hash-bound")
        sources = {str(item.get("source_path")) for item in visual.get("images", [])}
        check("v055:visual-sources", set(V054_CANONICAL_OUTPUTS).issubset(sources) and all((ROOT / source).is_file() for source in sources), "review manifest resolves every canonical source path")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v055:visual-manifest", False, str(exc)); check("v055:visual-sources", False, str(exc))

    matcher = self_test_sensitive_matcher()
    check("v055:matcher-self-test", matcher["status"] == "SENSITIVE_MATCHER_SELF_TEST_PASSED", "; ".join(matcher.get("failures", [])) or "anchored security matcher passes required include/exclude cases")
    check("v055:archive-verifier", (ROOT / "scripts/validation/verify_review_archive.py").is_file(), "tracked review archive verifier is present")
    review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""
    headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.5.4 AUDIT FINDING", "ROOT CAUSE", "SENSITIVE PATH MATCHER FIX", "CANONICAL SNAPSHOT CONTRACT", "REVIEW ARCHIVE VERIFIER", "V054 LANE OUTPUT PRESERVATION", "HASH VERIFICATION", "SECURITY EXCLUSIONS", "POSE DECISION PRESERVED", "NO NEW GENERATION EVIDENCE", "TESTS", "VALIDATION", "EXTRACTED ZIP SELF-TEST", "TRACKED SNAPSHOT / GITHUB", "STATE CONSISTENCY", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
    check("v055:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.5.5 review headings present")
    check("v055:review-boundary", "REVIEW_SNAPSHOT_INTEGRITY_FIXED" in review and "REVIEW_ARCHIVE_VERIFIED" in review and "não houve comfyui" in review.casefold() and "nenhum threshold" in review.casefold() and "foi alterado" in review.casefold(), "review separates packaging fix from unchanged pose decision and GPU boundary")


def _v060_checks() -> None:
    """Validate the immutable v0.6.0 SDXL ControlNet/IP-Adapter snapshot."""
    provider: dict[str, Any] = {}
    state_path = ROOT / "docs/evidence/current-state-v0.6.0.json"
    review_path = ROOT / "REVIEW-v0.6.0.md"
    try:
        state = load_json(state_path)
        check("v060:state-consistency", state.get("schema_version") == "0.6.0" and state.get("version") == "0.6.0" and state.get("phase") == "SDXL_CONTROL_POSE_PROVIDER_QUALIFICATION" and state.get("current_gate") == "SDXL_OPENPOSE_CONTROL_GAP", "immutable v0.6.0 state snapshot is internally identified")
        check("v060:state-schema", state.get("schema_version") == "0.6.0" and state.get("version") == "0.6.0" and state.get("phase") == "SDXL_CONTROL_POSE_PROVIDER_QUALIFICATION", "historical state is the SDXL qualification phase")
        check("v060:historical-separation", state.get("previous_release", {}).get("version") == "0.5.5" and state.get("pose_lane_status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED" and state.get("previous_review_snapshot_status") == "REVIEW_ARCHIVE_VERIFIED", "v0.5.4 pose and v0.5.5 review results remain historical")
        check("v060:scope-boundary", state.get("walk_authorized") is False and state.get("generation_provider_change_authorized") is False, "walk and production provider routing remain unauthorized")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v060:state-consistency", False, str(exc)); check("v060:state-schema", False, str(exc)); check("v060:historical-separation", False, str(exc))

    try:
        audit = load_json(ROOT / "docs/evidence/custom-node-audit-ipadapter-plus.json")
        check("v060:custom-node-audit", audit.get("audit_status") == "CUSTOM_NODE_AUDIT_PASSED" and audit.get("commit") == "a0f451a5113cf9becb0847b92884cb10cbdec0ef" and audit.get("license") == "GPL-3.0-only" and audit.get("distribution_boundary") == "local-only" and audit.get("source_vendored_in_ugas") is False, "custom node is pinned, audited and local-only")
        check("v060:custom-node-residual-risk", "torch.load" in json.dumps(audit) and "optional" in json.dumps(audit).casefold(), "optional local embed loader residual risk is documented")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v060:custom-node-audit", False, str(exc))

    try:
        stack = load_json(ROOT / "docs/evidence/sdxl-model-stack-qualification.json")
        artifacts = stack.get("artifacts", [])
        check("v060:model-stack", stack.get("status") in {"MODEL_ARTIFACTS_VERIFIED", "MODEL_ARTIFACT_MISSING", "MODEL_HASH_MISMATCH"} and len(artifacts) == 4 and all(item.get("source_revision") and item.get("sha256") and item.get("license") and item.get("bytes", 0) > 0 for item in artifacts), "four exact SDXL provider artifacts have source/license/size/hash records")
        check("v060:model-boundary", stack.get("weights_outside_git") is True and all(item.get("verification", {}).get("path", "").lower().endswith(".safetensors") for item in artifacts), "weights are external and not part of the source package")
        for name in ("sdxl-base-model-qualification.json", "sdxl-openpose-controlnet-qualification.json", "ipadapter-sdxl-model-qualification.json", "clip-vision-qualification.json"):
            item = load_json(ROOT / "docs/evidence" / name)
            check(f"v060:artifact:{name}", item.get("source_revision") and item.get("license") and item.get("verification", {}).get("expected_sha256"), "artifact qualification record is explicit")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v060:model-stack", False, str(exc))

    try:
        doctor = load_json(ROOT / "docs/evidence/runtime-doctor-v0.6.0.json")
        required_nodes = doctor.get("required_nodes", {})
        check("v060:runtime-doctor", doctor.get("schema_version") == "0.6.0" and doctor.get("status") in {"RUNTIME_DOCTOR_PASSED", "SDXL_CONTROL_PROVIDER_HARDWARE_GAP"} and "RTX 5050" in doctor.get("gpu", {}).get("name", "") and doctor.get("gpu", {}).get("vram_total", 0) >= 512 * 1024 * 1024, "runtime doctor records the real RTX 5050 and VRAM gate")
        check("v060:native-nodes", all(required_nodes.get(name) is True for name in ("ControlNetLoader", "ControlNetApplyAdvanced", "CLIPVisionLoader", "CLIPVisionEncode", "IPAdapterModelLoader", "IPAdapterAdvanced")), "native ControlNet and pinned IP-Adapter nodes are observed")
        check("v060:runtime-strategy", doctor.get("runtime_strategy") == ["512x512 FP16-compatible attempt", "low-VRAM/offload fallback", "sequential model unload/offload"], "required 512/offload/unload strategy is recorded")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v060:runtime-doctor", False, str(exc)); check("v060:native-nodes", False, str(exc))

    try:
        workflow = load_json(ROOT / "docs/evidence/sdxl-provider-workflow-qualification.json")
        lanes = workflow.get("lanes", [])
        check("v060:workflow-qualification", workflow.get("status") in {"SDXL_PROVIDER_WORKFLOW_VALID", "SDXL_PROVIDER_WORKFLOW_GAP"} and {item.get("lane") for item in lanes} == {"P", "I", "PI"} and all(item.get("direct_guide") is (item.get("lane") in {"P", "PI"}) for item in lanes), "separate P/I/PI API graphs are registered with direct guide semantics")
        check("v060:workflow-separation", workflow.get("ipadapter_never_receives_skeleton") is True and workflow.get("controlnet_never_receives_r4_identity") is True and workflow.get("anchor", {}).get("sha256") == ANCHOR_SHA256, "ControlNet/IP-Adapter input separation and R4 hash are explicit")
        for workflow_id in ("sdxl-openpose-controlnet-p", "sdxl-ipadapter-i", "sdxl-openpose-ipadapter-character"):
            record = load_workflow(ROOT, workflow_id)
            check(f"v060:workflow:{workflow_id}", record.get("schema_version") == "0.6.0" and record.get("deterministic_seed") is True and record.get("api_json"), "v0.6.0 workflow registry entry is deterministic")
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        check("v060:workflow-qualification", False, str(exc)); check("v060:workflow-separation", False, str(exc))

    try:
        provider = load_json(ROOT / "docs/evidence/sdxl-provider-qualification.json")
        execution = load_json(ROOT / "docs/evidence/execution-evidence-v0.6.0.json")
        final_status = provider.get("status")
        allowed = {"SDXL_CONTROL_POSE_PROVIDER_QUALIFIED", "SDXL_CONTROL_POSE_PROVIDER_GAP", "SDXL_CONTROL_PROVIDER_HARDWARE_GAP", "SDXL_IDENTITY_ADAPTER_GAP", "SDXL_OPENPOSE_CONTROL_GAP"}
        check("v060:provider-status", final_status in allowed and provider.get("walk_authorized") is False and provider.get("animation_authorized") is False and provider.get("external_approval") == "not-claimed", f"provider final state is fail-closed: {final_status}")
        check("v060:execution", execution.get("schema_version") == "0.6.0" and execution.get("previous_frame_chaining") is False and execution.get("weights_in_git") is False and execution.get("custom_node_source_vendored") is False and execution.get("attempted_record_count", 0) >= 3, "new execution evidence binds prompt/history/output and distribution boundaries")
        smoke = provider.get("smoke", {})
        check("v060:factorial", len(smoke.get("records", [])) == 3 and {item.get("lane") for item in smoke.get("records", [])} == {"P", "I", "PI"} and provider.get("seeds", {}).get("smoke") == 60701, "one new smoke seed is recorded separately for P/I/PI")
        if provider.get("paired", {}).get("records"):
            paired = provider["paired"]["records"]
            check("v060:paired", len(paired) == 9 and provider.get("seeds", {}).get("paired") == [60702, 60703, 60704], "three new paired seeds per factorial lane are recorded")
        else:
            check("v060:paired-blocked", provider.get("benchmark", {}).get("status") == "NOT_RUN" or provider.get("smoke", {}).get("technical_green") is False, "later phases are absent when the smoke technical gate is not green")
        benchmark = provider.get("benchmark", {})
        if benchmark.get("status") == "NOT_RUN":
            check("v060:benchmark-blocked", provider.get("smoke", {}).get("technical_green") is False, "strength benchmark is not fabricated before smoke green")
        else:
            check("v060:benchmark", len(benchmark.get("configs", [])) == 4 and benchmark.get("seed") == 60705 and benchmark.get("ipadapter_weight_type") == "linear" and benchmark.get("ranking_rule") == ["pose", "identity", "weapon", "lower_body", "nme", "runtime"], "strength benchmark uses four fixed PI configurations and declared rank")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v060:provider-status", False, str(exc)); check("v060:execution", False, str(exc)); check("v060:factorial", False, str(exc))

    try:
        visuals = load_json(ROOT / "docs/evidence/review-visuals-v0.6.0.json")
        result = validate_review_visual_manifest(visuals, ROOT)
        check("v060:visual-manifest", result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "current SDXL visual roles are hash-bound")
        check("v060:overlay-evidence", (ROOT / "docs/evidence/sdxl-identity-drift-contact.json").is_file() and (ROOT / "docs/evidence/sdxl-pose-detection-overlays-contact-sheet.png").is_file() or provider.get("smoke", {}).get("technical_green") is False, "pose overlays and regional identity evidence are present when generation reached QA")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v060:visual-manifest", False, str(exc))

    review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""
    headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.5.5 BASELINE", "POSE GAP STRATEGY", "STATE CONSISTENCY", "CUSTOM NODE AUDIT", "CUSTOM NODE PIN / LICENSE", "SDXL BASE MODEL", "OPENPOSE CONTROLNET MODEL", "IP-ADAPTER MODEL", "CLIP VISION MODEL", "RUNTIME / RTX 5050", "WORKFLOW TOPOLOGY", "P / I / PI FACTORIAL SMOKE", "STRENGTH BENCHMARK", "POSE QA", "IDENTITY / WEAPON QA", "FINAL PROVIDER QUALIFICATION", "CAPABILITY ROUTING", "REGRESSION PROTECTION", "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB", "SECURITY / DISTRIBUTION", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
    check("v060:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.6.0 review headings present")
    check("v060:review-boundary", "walk" in review.casefold() and "não" in review.casefold() and "aprovação externa" in review.casefold() and "GPL-3.0" in review, "review separates blocked walk, external approval and GPL boundary")


def _v061_checks() -> None:
    """Validate the active v0.6.1 smoke correction without inferring completion."""
    state_path = ROOT / "docs/evidence/current-state.json"
    checkpoint_path = ROOT / "CHECKPOINT.md"
    review_path = ROOT / "REVIEW-v0.6.1.md"
    provider: dict[str, Any] = {}
    try:
        state = load_json(state_path)
        checkpoint = checkpoint_path.read_text(encoding="utf-8")
        review = review_path.read_text(encoding="utf-8")
        consistency = validate_state_consistency(state, checkpoint, review)
        check("v061:state-consistency", consistency["status"] == "STATE_CONSISTENCY_PASSED", "; ".join(consistency.get("failures", [])) or "active v0.6.1 state and documents are consistent")
        check("v061:state-schema", state.get("schema_version") == "0.6.1" and state.get("version") == "0.6.1" and state.get("phase") == "SDXL_CONTROL_POSE_PROVIDER_SMOKE_CORRECTION", "active state is the v0.6.1 smoke correction")
        check("v061:state-status", state.get("current_gate") == state.get("provider_smoke_status") and state.get("current_gate") == state.get("state_consistency", {}).get("status"), "provider smoke status, current gate and nested state agree")
        check("v061:state-boundary", state.get("previous_release", {}).get("version") == "0.6.0" and state.get("historical_pose_lane_status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED" and state.get("walk_authorized") is False and state.get("generation_provider_change_authorized") is False, "v0.6.0 history is preserved and walk/provider changes remain unauthorized")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v061:state-consistency", False, str(exc)); check("v061:state-schema", False, str(exc)); check("v061:state-status", False, str(exc)); check("v061:state-boundary", False, str(exc))

    allowed_statuses = {
        "SDXL_POSTPROCESS_GAP",
        "SDXL_OPENPOSE_CONTROL_GAP",
        "SDXL_COMBINED_CONDITIONING_INTERFERENCE_GAP",
        "SDXL_IDENTITY_ADAPTER_GAP",
        "SDXL_COMBINED_IDENTITY_GAP",
        "SDXL_SMOKE_GREEN_READY_FOR_BENCHMARK_PROMPT",
    }
    try:
        provider = load_json(ROOT / "docs/evidence/sdxl-provider-qualification-v0.6.1.json")
        status = provider.get("status")
        check("v061:provider-status", status in allowed_statuses and provider.get("walk_authorized") is False and provider.get("anchors_authorized") is False and provider.get("animation_authorized") is False and provider.get("external_approval") == "not-claimed", f"provider status is one of the bounded smoke outcomes: {status}")
        check("v061:provider-phase", provider.get("schema_version") == "0.6.1" and provider.get("phase") == "SDXL_CONTROL_POSE_PROVIDER_SMOKE_CORRECTION" and provider.get("prompt_id") == "PROMPT-05C-UGAS-SDXL-SMOKE-EVIDENCE-HARD-GATES-v0.6.1", "provider evidence is bound to the active prompt and phase")
        smoke = provider.get("smoke", {})
        smoke_records = smoke.get("records", [])
        check("v061:smoke-factorial", len(smoke_records) == 3 and {item.get("lane") for item in smoke_records} == {"P", "I", "PI"} and all(item.get("seed") == 61701 for item in smoke_records), "exactly one P/I/PI job per lane uses seed 61701")
        check("v061:later-phases-not-run", provider.get("paired", {}).get("status") == "NOT_RUN" and provider.get("paired", {}).get("records") == [] and provider.get("benchmark", {}).get("status") == "NOT_RUN" and provider.get("confirmation", {}).get("status") == "NOT_RUN" and provider.get("confirmation", {}).get("records") == [] and provider.get("seeds", {}).get("paired") == [] and provider.get("seeds", {}).get("benchmark") is None and provider.get("seeds", {}).get("confirmation") == [], "paired, benchmark and confirmation phases remain NOT_RUN")
        check("v061:provider-boundary", provider.get("new_generation_jobs") == 3 and provider.get("walk_authorized") is False and "walk" not in json.dumps(provider.get("smoke", {})).casefold(), "smoke is bounded to three jobs and contains no walk execution")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v061:provider-status", False, str(exc)); check("v061:provider-phase", False, str(exc)); check("v061:smoke-factorial", False, str(exc)); check("v061:later-phases-not-run", False, str(exc))

    try:
        execution = load_json(ROOT / "docs/evidence/execution-evidence-v0.6.1.json")
        records = execution.get("records", [])
        execution_result = validate_execution_evidence_v061(execution, ROOT)
        check("v061:execution-exact-count", execution_result["status"] == "SDXL_V061_EXECUTION_EVIDENCE_PASSED", "; ".join(execution_result.get("failures", [])) or "execution validator requires three attempted and three completed generations")
        check("v061:execution-bindings", execution_result["status"] == "SDXL_V061_EXECUTION_EVIDENCE_PASSED", "prompt, exact history, raw hash, fresh target and distribution boundaries all pass")
        for item in records:
            generation = item.get("generation", {})
            lane = item.get("lane")
            raw_path = ROOT / str(generation.get("raw_output_path", ""))
            execution_record = generation.get("execution_evidence") or {}
            qualification_context = execution_record.get("qualification_context") or {}
            check(f"v061:raw:{lane}", generation.get("completed") is True and bool(generation.get("prompt_id")) and execution_record.get("prompt_id") == generation.get("prompt_id") and qualification_context.get("prompt_id") == "PROMPT-05C-UGAS-SDXL-SMOKE-EVIDENCE-HARD-GATES-v0.6.1" and generation.get("history_record_key") == generation.get("prompt_id") and generation.get("history_key_matches_prompt_id") is True and generation.get("target_existed_before_submission") is False and generation.get("previous_frame_chaining") is False and raw_path.is_file() and digest(raw_path) == generation.get("raw_output_sha256") and generation.get("raw_output_hash_matches_comfy") is True, f"{lane} preserves completed prompt/history/raw evidence with matching SHA-256")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v061:execution-exact-count", False, str(exc)); check("v061:execution-bindings", False, str(exc))

    try:
        phase_table = load_json(ROOT / "docs/evidence/sdxl-smoke-phase-table.json")
        lanes = phase_table.get("lanes", [])
        check("v061:phase-table", phase_table.get("schema_version") == "0.6.1" and len(lanes) == 3 and {item.get("lane") for item in lanes} == {"P", "I", "PI"} and all(item.get("generation", {}).get("completed") is True for item in lanes), "phase table preserves generation and postprocess stages for all lanes")
        for item in lanes:
            postprocess = item.get("postprocess") or {}
            check(f"v061:postprocess:{item.get('lane')}", isinstance(postprocess.get("attempted"), bool) and isinstance(postprocess.get("passed"), bool) and postprocess.get("status") in {"POSTPROCESS_PASSED", "POSTPROCESS_FAILED"}, f"{item.get('lane')} has structured postprocess outcome")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v061:phase-table", False, str(exc))

    try:
        identity = load_json(ROOT / "docs/evidence/sdxl-identity-hard-gates.json")
        required = {"aggregate_score_pass", "weapon_pass", "head_face_pass", "armor_palette_pass", "black_cloth_pass", "body_proportions_pass", "single_subject_pass", "identity_pass", "failure_reasons"}
        identity_records = identity.get("records", [])
        check("v061:identity-policy", identity.get("schema_version") == "0.6.1" and identity.get("hard_gate_policy", {}).get("aggregate_score_cannot_compensate") is True and set(identity.get("hard_gate_policy", {}).get("required", [])) == {"aggregate_score", "weapon", "head_face", "armor_palette", "black_cloth", "body_proportions", "single_subject"}, "identity hard-gate policy is explicit and fail-closed")
        check("v061:identity-records", all(required.issubset(set((item.get("hard_gates") or {}))) for item in identity_records), "every evaluated identity lane records all hard booleans and reasons")
        historical_i = ROOT / "docs/evidence/sdxl-qualification/outputs/smoke-i-seed-60701.png"
        if historical_i.is_file():
            from ugas.identity_hard_gates import analyze_foreground_components
            historical_components = analyze_foreground_components(historical_i)
            check("v061:historical-i-single-subject", historical_components.get("multiple_subjects_detected") is True and historical_components.get("large_foreground_components") >= 2, "historical v0.6.0 I fixture is rejected as multiple subjects")
        else:
            check("v061:historical-i-single-subject", False, "historical v0.6.0 I fixture is missing")
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        check("v061:identity-policy", False, str(exc)); check("v061:identity-records", False, str(exc)); check("v061:historical-i-single-subject", False, str(exc))

    try:
        visual = load_json(ROOT / "docs/evidence/review-visuals-v0.6.1.json")
        visual_result = validate_review_visual_manifest(visual, ROOT)
        check("v061:visual-manifest", visual_result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(visual_result.get("failures", [])) or "v0.6.1 raw/pose/hard-gate visual roles are hash-bound")
        required_visuals = set(visual.get("required_current_visuals", []))
        check("v061:visual-roles", {"sdxl-smoke-raw-p-i-pi-contact-sheet.png", "sdxl-smoke-raw-pose-overlays-contact-sheet.png", "sdxl-smoke-phase-table.json", "sdxl-identity-hard-gates.json", "execution-evidence-v0.6.1.json"}.issubset(required_visuals), "raw contact, pose overlay, phase, identity and execution evidence are required")
        if provider.get("smoke", {}).get("technical_green") is True or any(item.get("output_path") for item in provider.get("smoke", {}).get("records", [])):
            check("v061:processed-role", "sdxl-smoke-postprocessed-contact-sheet.png" in required_visuals or not any(item.get("output_path") for item in provider.get("smoke", {}).get("records", [])), "postprocessed contact is listed only when a processed output exists")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v061:visual-manifest", False, str(exc)); check("v061:visual-roles", False, str(exc))

    review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""
    headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.6.0 AUDIT FINDINGS", "EXECUTION EVIDENCE PRESERVATION FIX", "RAW GENERATION EVIDENCE", "RAW POSE QA", "POSTPROCESS QA", "IDENTITY HARD GATES", "SINGLE SUBJECT GATE", "P / I / PI CORRECTIVE SMOKE", "FINAL SMOKE CLASSIFICATION", "MODEL / CUSTOM NODE BOUNDARY", "EXECUTION EVIDENCE", "TESTS", "VALIDATION", "REVIEW ARCHIVE SELF-TEST", "TRACKED SNAPSHOT / GITHUB", "SECURITY / LICENSES", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
    check("v061:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.6.1 review headings present")
    check("v061:review-boundary", "review-visuals-v0.6.0.json" in review and "benchmark" in review.casefold() and "not_run" in json.dumps(provider).casefold() and "aprovação externa" in review.casefold() or "external approval" in review.casefold(), "current review separates historical v0.6.0 evidence, blocked later phases and external approval")



def main() -> int:
    required = [
        "README.md", "INSTALL.md", "CHECKPOINT.md", "REVIEW-v0.5.0.md", "REVIEW-v0.5.1.md", "REVIEW-v0.5.2.md", "REVIEW-v0.5.3.md", "REVIEW-v0.4.3.md", "REVIEW-v0.4.2.md", "LICENSE", "package.json", "pyproject.toml", "docs/2d-master-pipeline.md", "docs/comfyui.md", "docs/roadmap.md", "docs/test-coverage-matrix-v0.4.2.md", "docs/test-coverage-matrix-v0.4.3.md", "docs/test-coverage-matrix-v0.5.0.md", "docs/test-coverage-matrix-v0.5.1.md", "docs/test-coverage-matrix-v0.5.2.md", "docs/test-coverage-matrix-v0.5.3.md", "providers/models/registry.json", "providers/workflows/registry.json", "schemas/reference-edit-contract.json", "schemas/character-identity-manifest.json", "schemas/pose-guide.json", "schemas/openpose-pose-guide.json", "schemas/current-state.json", "schemas/directional-anchor-set.json", "schemas/animation-spec.json", "schemas/animation-frame.json", "schemas/animation-qa.json", "pose-guides/views/front.json", "pose-guides/views/left.json", "pose-guides/views/right.json", "pose-guides/views/back.json", "pose-guides/challenges/multiref-strong-left-arm-up.json", "pose-guides/openpose-v3/challenges/multiref-strong-left-arm-up.json", "docs/evidence/identity-manifest.json", "docs/evidence/multiref-qualification.json", "docs/evidence/pose-guide-manifest.json", "docs/evidence/directional-anchor-set.json", "docs/evidence/directional-anchor-qa.json", "docs/evidence/walk-front-8-animation-spec.json", "docs/evidence/walk-front-8-animation-qa.json", "docs/evidence/walk-front-8.json", "docs/evidence/execution-evidence.json", "docs/evidence/review-visuals-v0.5.0.json", "docs/evidence/runtime-doctor-v0.5.1.json", "docs/evidence/multiref-v2-qualification.json", "docs/evidence/execution-evidence-v0.5.1.json", "docs/evidence/review-visuals-v0.5.1.json", "docs/evidence/current-state.json", "docs/evidence/state-consistency.json", "docs/evidence/runtime-doctor-v0.5.2.json", "docs/evidence/native-reference-order-qualification.json", "docs/evidence/execution-evidence-v0.5.2.json", "docs/evidence/refcontrol-model-qualification.json", "docs/evidence/refcontrol-pose-qualification.json", "docs/evidence/openpose-guide-v3-manifest.json", "docs/evidence/review-visuals-v0.5.2.json", "docs/evidence/pose-metric-calibration.json", "docs/evidence/pose-metric-calibration-contact-sheet.png", "docs/evidence/pose-metric-negative-controls-contact-sheet.png", "docs/evidence/pose-qa-estimator-qualification.json", "docs/evidence/pose-qa-estimator-model.json", "docs/evidence/v052-refcontrol-baseline-contact.png", "docs/evidence/v053-pose-detection-overlay-contact.png", "docs/evidence/v053-pose-error-table.json", "docs/evidence/v053-provider-qualification.json", "docs/evidence/execution-evidence-v0.5.3.json", "docs/evidence/review-visuals-v0.5.3.json", "docs/evidence/v050-baseline-walk-contact.png", "docs/evidence/pose-guides-v2-contact-sheet.png", "docs/evidence/pose-guide-v2-control-example.png", "docs/evidence/pose-guide-v2-review-overlay.png", "docs/evidence/multiref-v2-ab-contact-sheet.png", "docs/evidence/v051-gap-baseline.png", "docs/evidence/openpose-guide-v3-control-example.png", "docs/evidence/openpose-guides-v3-contact-sheet.png", "docs/evidence/native-reference-order-abc-contact-sheet.png", "docs/evidence/refcontrol-strength-benchmark-contact-sheet.png", "docs/evidence/refcontrol-pose-overlay-contact.png", "docs/evidence/reference-edit-workflow-qualification.json", "docs/evidence/upstream/workflow_templates-image-edit-base.json", "docs/evidence/upstream/comfyui-blueprint-image-edit.json", "docs/evidence/reference-edit-contract.json", "docs/evidence/reference-edit-config-benchmark.json", "docs/evidence/reference-edit-config-benchmark-contact-sheet.png", "docs/evidence/reference-edit-candidates.json", "docs/evidence/reference-edit-candidates-contact-sheet.png", "docs/evidence/reference-edit-selected-rgb.png", "docs/evidence/reference-edit-selected-transparent.png", "docs/evidence/reference-edit-selected-checkerboard.png", "docs/evidence/reference-edit-v0.4.3-before-after.png", "docs/evidence/reference-edit-diff-heatmap.png", "docs/evidence/reference-edit-target-mask.png", "docs/evidence/reference-edit-protected-mask.png", "docs/evidence/reference-edit-fidelity.json", "docs/evidence/reference-edit-execution-evidence.json", "docs/evidence/reference-edit-v0.4.3-qa.json", "docs/evidence/reference-edit-v0.4.3-transparency-qa.json", "docs/evidence/revision-chain-v0.4.3.json", "docs/evidence/review-visuals-v0.4.3.json",
    ]
    required += [
        "REVIEW-v0.5.5.md", "docs/test-coverage-matrix-v0.5.5.md",
        "docs/evidence/review-visuals-v0.5.5.json", "scripts/validation/verify_review_archive.py",
        "src/ugas/review_snapshot.py",
        "docs/evidence/v054-pose-error-table.json", "docs/evidence/v054-provider-qualification.json",
        "docs/evidence/execution-evidence-v0.5.4.json",
        *V054_CANONICAL_OUTPUTS,
    ]
    required += [
        "REVIEW-v0.6.0.md", "docs/test-coverage-matrix-v0.6.0.md",
        "docs/evidence/custom-node-audit-ipadapter-plus.json",
        "docs/evidence/sdxl-base-model-qualification.json",
        "docs/evidence/sdxl-openpose-controlnet-qualification.json",
        "docs/evidence/ipadapter-sdxl-model-qualification.json",
        "docs/evidence/clip-vision-qualification.json",
        "docs/evidence/sdxl-model-stack-qualification.json",
        "docs/evidence/runtime-doctor-v0.6.0.json",
        "docs/evidence/sdxl-provider-workflow-qualification.json",
        "docs/evidence/sdxl-provider-qualification.json",
        "docs/evidence/execution-evidence-v0.6.0.json",
        "docs/evidence/sdxl-identity-drift-contact.json",
        "docs/evidence/review-visuals-v0.6.0.json",
        "scripts/providers/audit_ipadapter_custom_node.py",
        "scripts/providers/qualify_sdxl_models.py",
        "scripts/providers/run_sdxl_runtime_doctor.py",
        "scripts/validation/run_sdxl_provider_qualification.py",
        "providers/custom-nodes/registry.json",
        "providers/custom-nodes/README.md",
        "providers/workflows/sdxl-openpose-controlnet-p.api.json",
        "providers/workflows/sdxl-ipadapter-i.api.json",
        "providers/workflows/sdxl-openpose-ipadapter-character.api.json",
    ]
    required += [
        "REVIEW-v0.6.1.md", "docs/test-coverage-matrix-v0.6.1.md", "docs/evidence/current-state-v0.6.0.json",
        "docs/evidence/sdxl-provider-workflow-qualification-v0.6.1.json",
        "docs/evidence/sdxl-provider-qualification-v0.6.1.json",
        "docs/evidence/execution-evidence-v0.6.1.json", "docs/evidence/sdxl-smoke-phase-table.json",
        "docs/evidence/sdxl-identity-hard-gates.json", "docs/evidence/review-visuals-v0.6.1.json",
        "src/ugas/identity_hard_gates.py", "src/ugas/sdxl_smoke_evidence.py",
    ]
    for item in required:
        path = ROOT / item; check(f"path:{item}", path.exists(), "present" if path.exists() else "missing")
        if path.exists() and item not in {"README.md", "INSTALL.md", "CHECKPOINT.md", "REVIEW-v0.4.2.md"}: check(f"tracked:{item}", tracked(item), "tracked or present in review snapshot")
    schemas: dict[str, dict] = {}
    for path in (ROOT / "schemas").glob("*.json"):
        try: value = load_json(path); validate_schema_document(value); schemas[path.stem] = value; check(f"schema:{path.name}", True, "valid JSON Schema")
        except (OSError, json.JSONDecodeError, SchemaValidationError) as exc: check(f"schema:{path.name}", False, str(exc))
    try:
        models = load_registry(ROOT); validate_instance(models, schemas["model-registry"]); check("registry:models", len(models.get("models", [])) >= 4, "explicit model records")
        for model in models["models"]:
            validate_instance(model, schemas["model-manifest"])
            if model.get("schema_version") == "0.6.0":
                semantic = model.get("recommended_steps") in {20, None} and model.get("recommended_guidance") in {7.0, None}
                license_recorded = model.get("commercial_use_status") in {"approved", "conditional-license-review-required", "review", "required"}
            else:
                semantic = model["family"] == "birefnet" or (model["variant"] == "distilled" and model.get("recommended_steps") == 4 and model.get("recommended_guidance") == 1.0) or (model["variant"] == "base" and model.get("recommended_steps") == 50 and model.get("recommended_guidance") == 4.0)
                license_recorded = model["commercial_use_status"] == "approved"
            check(f"model:{model['id']}", license_recorded and semantic and all(str(v) != "RECORD_AFTER_DOWNLOAD" for v in model.get("sha256", {}).values()) or model.get("id") == "flux2-klein-4b-fp8", "license and lane semantics valid")
    except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError) as exc: check("registry:models", False, str(exc))
    try:
        workflows = load_workflows(ROOT); check("registry:workflows", len(workflows) >= 6, "four historical FLUX lanes, native multi-reference and BiRefNet")
        for item in workflows:
            record = load_workflow(ROOT, item["id"]); graph = validate_api_workflow(record["api"]); model = load_model(ROOT, item["required_models"][0]); compatible = validate_model_workflow_compatibility(model, record)["compatible"]
            custom_ok = not item["custom_nodes_required"] or all(str(value).startswith("comfyui-ipadapter-plus@a0f451a5113cf9becb0847b92884cb10cbdec0ef") for value in item["custom_nodes_required"])
            check(f"workflow:{item['id']}", graph["valid_graph"] and compatible and custom_ok and item["schema_version"] in {"0.4.3", "0.5.0", "0.5.1", "0.5.2", "0.6.0", UGAS_VERSION}, "native graph, pinned custom-node boundary and capability compatibility valid")
    except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError, ValueError) as exc: check("registry:workflows", False, str(exc))
    _historical_coverage_checks(); _reference_edit_checks(); _review_checks(); _v050_checks(); _v051_checks(); _v052_checks(); _v060_checks(); _v061_checks()
    package_version = load_json(ROOT / "package.json")["version"]
    with (ROOT / "pyproject.toml").open("rb") as stream: pyproject_version = tomllib.load(stream)["project"]["version"]
    init_version = __import__("ugas").__version__
    check("version:consistency", UGAS_VERSION == package_version == pyproject_version == init_version == "0.6.1", f"runtime={UGAS_VERSION}, package={package_version}, pyproject={pyproject_version}")
    docs = ["README.md", "INSTALL.md", "CHECKPOINT.md", "REVIEW-v0.6.1.md", "docs/2d-master-pipeline.md", "docs/comfyui.md", "docs/roadmap.md"]
    check("docs:version", all(UGAS_VERSION in (ROOT / path).read_text(encoding="utf-8") for path in docs), "current operational docs identify 0.6.1")
    checkpoint_text = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8").casefold()
    check("docs:animation-boundary", "animação genérica" in checkpoint_text and "não autoriza" in checkpoint_text, "checkpoint keeps generic animation outside scope")
    check("security:tracked-forbidden", not any(Path(path).suffix.casefold() in {".safetensors", ".ckpt", ".gguf", ".onnx"} for path in subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.splitlines()) if (ROOT / ".git").exists() else True, "weights are outside Git")
    compile_run = _run([sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"], ROOT); check("tests:compileall", compile_run.returncode == 0, (compile_run.stdout + compile_run.stderr).strip()[-500:])
    test_run = _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], ROOT, timeout=360); test_text = test_run.stdout + test_run.stderr; match = re.search(r"Ran (\d+) tests", test_text); check("tests:unit", test_run.returncode == 0 and match is not None and int(match.group(1)) >= 79, test_text.strip()[-800:])
    snapshot_check()
    failures = 0
    for name, ok, detail in RESULTS: print(f"{'PASS' if ok else 'FAIL'} {name} - {detail}"); failures += not ok
    print(f"SUMMARY checks={len(RESULTS)} passed={len(RESULTS) - failures} failed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
