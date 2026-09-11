"""Fail-closed active-state validator for the UGAS V1 canonical-state reconciliation (v0.25.1)."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

VERSION = "0.25.1"
PHASE = "V1_FINAL_ACCEPTANCE"
BASELINE_MAIN_SHA = "02fa44f2173aca46b4484209abccf218fe688a63"
BRANCH = "codex/ugas-wo-0253-v1-canonical-state-reconciliation"
PR_TITLE = "UGAS WO-0253 V1 canonical-state reconciliation"
PREVIOUS_RELEASE_VERSION = "0.25.0"
CURRENT_GATE = "V1_TECHNICAL_BASELINE_MERGED_CLOSED"
STOP_REASON = "V1_TECHNICAL_BASELINE_CLOSED_PRODUCTION_READINESS_NOT_STARTED"
ACCEPTANCE_VERDICT = "V1_TECHNICAL_BASELINE_ACCEPTED"
NEXT_CANDIDATE = "PRODUCTION_READINESS"
NEXT_ACTION = "define_and_review_production_readiness_work_order"
MERGE_AUTHORIZATION = "GOVERNED_MERGE_ONLY_AFTER_EXACT_HEAD_BOOKKEEPING_REVIEW"
V1_SEMANTIC_HEAD = "66db255fdb2483da4bae08e418c904f24d215ebb"
V1_BOOKKEEPING_HEAD = "5046b3ed8c626540fa8258d25afc9a2abbf0a182"
V1_MERGE_MAIN_SHA = BASELINE_MAIN_SHA
V1_POST_MERGE_CI_RUN = 34610394648
V1_UNIT_JOB = 103299136405
V1_DOCKER_JOB = 103299136059
V1_CLOSURE_COMMENT_ID = 5636295417
V1_AUDIT_COMMENT_ID = 5637818972
V1_AUDIT_VERDICT = "APPROVED"
V1_PR_NUMBER = 16
V1_STATE_SNAPSHOT = "docs/evidence/canonical-state-reconciliation-v0251/v0250-state-snapshot.json"
CLOSURE_EVIDENCE_ROOT = "docs/evidence/canonical-state-reconciliation-v0251/"
V1_EVIDENCE_ROOT = "docs/evidence/v1-final-acceptance/"
FINAL_ACCEPTANCE_SUMMARY = "docs/evidence/v1-final-acceptance/final-acceptance-summary.json"
FROZEN_ACCEPTANCE_ROOT = "docs/evidence/v1-final-acceptance/"
ORCHESTRATION_EVIDENCE_ROOT = "docs/evidence/orchestration-runtime-v0247/"
HARD_GATE_COUNT = 30
CAPABILITY_COUNT = 16
RETAINED_MATRIX_VERSION = "0.25.0"
RETAINED_MATRIX_NEXT_CANDIDATE = "V1_FINAL_ACCEPTANCE"
ORCHESTRATION_LIFECYCLE = "MERGED_CLOSED"
OBSERVABILITY_STATUS = "APPROVED_PILOT"
OBSERVABILITY_ROW_STATUS = "APPROVED_PILOT; EXTERNAL_VISUAL_APPROVAL_BOUND"
OBSERVABILITY_APPROVAL_RECORD = "docs/evidence/github-governance-v0124/dashboard-external-visual-approval.json"
OBSERVABILITY_APPROVAL_ARTIFACT_ID = "9867524286"
OBSERVABILITY_APPROVAL_ARTIFACT_DIGEST = "sha256:6ffe21738ed7960aabb5cd874cc44c4030a3b5fee0463f58c004805637a4d6d2"
OBSERVABILITY_APPROVED_HEAD = "2f8d04f03a6f4de0ead7683899f945cd60d5000f"
APPROVED_SEMANTIC_HEAD = "66db255fdb2483da4bae08e418c904f24d215ebb"
APPROVAL_RECORD = "docs/evidence/v1-final-acceptance/sol-external-approval-v0251.json"
APPROVAL_REVIEW_ID_NUMERIC = 5177113418
POST_BOOKKEEPING_REPROOF_REQUIRED = True
CURRENT_EXACT_HEAD_AUTHORITY = "GITHUB_LIVE_ONLY"
REQUIRED_CONTEXTS = ("UGAS CI / unit-and-validation", "UGAS CI / docker-smoke", "UGAS Review / evidence")
UNSAFE_FORBIDDEN_ACTIONS = (
    "start_production_readiness",
    "enable_production_routing",
    "real_asset_generation",
    "merge_v1_final_acceptance_pr",
    "self_merge_v1_final_acceptance_pr",
    "self_merge_canonical_state_reconciliation_pr",
    "merge_canonical_state_reconciliation_pr",
    "start_ugas_v2",
)
REQUIRED_FORBIDDEN_ACTIONS = (
    "direct_main_push",
    "force_push_or_history_rewrite",
    "merge_without_sol_approval",
    "self_merge_v1_final_acceptance_pr",
    "merge_v1_final_acceptance_pr",
    "self_merge_canonical_state_reconciliation_pr",
    "merge_canonical_state_reconciliation_pr",
    "enable_production_routing",
    "start_production_readiness",
    "real_asset_generation",
    "provider_network",
    "start_ugas_v2",
)
CLOSURE_EVIDENCE_FILES = (
    "closure-binding-v0251.json",
    "immutability-proof-v0251.json",
    "negative-controls-v0251.json",
    "uads-handoff-v0251.json",
)
IMMUTABILITY_FROZEN_ROOTS = (FROZEN_ACCEPTANCE_ROOT, ORCHESTRATION_EVIDENCE_ROOT)
NEGATIVE_CONTROL_IDS = (
    "NEG-0253-01-STALE-PENDING-MERGE",
    "NEG-0253-02-MERGE-SHA-DRIFT",
    "NEG-0253-03-RUN-ID-DRIFT",
    "NEG-0253-04-UNIT-JOB-DRIFT",
    "NEG-0253-05-DOCKER-JOB-DRIFT",
    "NEG-0253-06-CLOSURE-COMMENT-DRIFT",
    "NEG-0253-07-AUDIT-VERDICT-DRIFT",
    "NEG-0253-08-PRODUCTION-APPROVED-DRIFT",
    "NEG-0253-09-PRODUCTION-ROUTING-DRIFT",
    "NEG-0253-10-NEW-GENERATION-DRIFT",
    "NEG-0253-11-PROVIDER-SUBMIT-DRIFT",
    "NEG-0253-12-REAL-ASSET-DRIFT",
    "NEG-0253-13-HARD-GATE-COUNT-DRIFT",
    "NEG-0253-14-NEXT-CANDIDATE-DRIFT",
    "NEG-0253-15-STALE-CURRENT-HEAD-CLAIM",
    "NEG-0253-16-MISLABELLED-HEAD-SOURCE",
    "NEG-0253-17-EXACT-HEAD-AUTHORITY-DRIFT",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str, roadmap_text: str, matrix: Mapping[str, Any], audit: Mapping[str, Any] | None = None) -> dict[str, Any]:
    failures: list[str] = []
    expected = {
        "schema_version": VERSION,
        "version": VERSION,
        "phase": PHASE,
        "baseline_main_sha": BASELINE_MAIN_SHA,
        "current_gate": CURRENT_GATE,
        "stop_reason": STOP_REASON,
        "acceptance_verdict": ACCEPTANCE_VERDICT,
        "next_candidate": NEXT_CANDIDATE,
        "allowed_next_actions": [NEXT_ACTION],
        "orchestration_runtime": "APPROVED_FOUNDATION",
        "orchestration_lifecycle": ORCHESTRATION_LIFECYCLE,
        "production_routing": "BLOCKED",
        "production_approved": False,
        "real_asset_generation": "NONE",
        "new_generation": 0,
        "provider_submit_calls": 0,
        "next_capability_started": False,
        "production_readiness_workstream": "NOT_STARTED_REQUIRED_SEPARATELY",
        "vfx_asset_family": "APPROVED_FOUNDATION",
        "vfx_asset_family_lifecycle": "MERGED_CLOSED",
        "ui_asset_family": "APPROVED_FOUNDATION",
        "ui_asset_family_lifecycle": "MERGED_CLOSED",
        "maps_minimap_assets": "APPROVED_FOUNDATION",
        "maps_minimap_lifecycle": "MERGED_CLOSED",
        "synthetic_fixture": "TEST_ONLY",
    }
    for key, expected_value in expected.items():
        if state.get(key) != expected_value:
            failures.append(f"{key}_invalid")
    if "main_sha" in state:
        failures.append("main_sha_forbidden")
    closure = _mapping(state.get("v1_closure"))
    for key, expected_value in {
        "semantic_head": V1_SEMANTIC_HEAD,
        "bookkeeping_head": V1_BOOKKEEPING_HEAD,
        "merge_main_sha": V1_MERGE_MAIN_SHA,
        "post_merge_ci_run": V1_POST_MERGE_CI_RUN,
        "unit_job": V1_UNIT_JOB,
        "docker_job": V1_DOCKER_JOB,
        "closure_comment_id": V1_CLOSURE_COMMENT_ID,
        "audit_comment_id": V1_AUDIT_COMMENT_ID,
        "audit_verdict": V1_AUDIT_VERDICT,
        "tracked_state_binding": "PASS",
    }.items():
        if closure.get(key) != expected_value:
            failures.append(f"v1_closure:{key}")
    previous_release = _mapping(state.get("previous_release"))
    if previous_release.get("version") != PREVIOUS_RELEASE_VERSION or previous_release.get("status") != ORCHESTRATION_LIFECYCLE or previous_release.get("merge_commit") != V1_MERGE_MAIN_SHA or previous_release.get("evidence") != V1_EVIDENCE_ROOT:
        failures.append("previous_release_invalid")
    history = _mapping(state.get("correction_history"))
    previous = _mapping(history.get(f"v{PREVIOUS_RELEASE_VERSION}"))
    if previous.get("status") != ORCHESTRATION_LIFECYCLE or previous.get("semantic_head") != V1_SEMANTIC_HEAD or previous.get("bookkeeping_head") != V1_BOOKKEEPING_HEAD or previous.get("merge_commit") != V1_MERGE_MAIN_SHA or previous.get("post_merge_ci_run") != V1_POST_MERGE_CI_RUN or previous.get("unit_job") != V1_UNIT_JOB or previous.get("docker_job") != V1_DOCKER_JOB or previous.get("closure_comment_id") != V1_CLOSURE_COMMENT_ID or previous.get("audit_comment_id") != V1_AUDIT_COMMENT_ID or previous.get("audit_verdict") != V1_AUDIT_VERDICT or previous.get("historical_evidence_unchanged") is not True:
        failures.append(f"correction_history:{PREVIOUS_RELEASE_VERSION}_closure_invalid")
    if _mapping(history.get("v0.24.7")).get("status") != "MERGED_CLOSED" or _mapping(history.get("v0.24.7")).get("merge_commit") != "6c6d53dab5a95226bf9578a6099d755d51327d8e" or _mapping(history.get("v0.24.7")).get("post_merge_ci_run") != 34523428088 or _mapping(history.get("v0.24.7")).get("closure_comment_id") != 5625161567:
        failures.append("correction_history:v0247_missing")
    if _mapping(history.get("v0.24.6")).get("status") != "CORRECTION_REQUIRED" or _mapping(history.get("v0.24.6")).get("historical_evidence_unchanged") is not True:
        failures.append("correction_history:v0246_missing")
    if _mapping(history.get("v0.23.4")).get("status") != "MERGED_CLOSED" or _mapping(history.get("v0.23.4")).get("merge_commit") != "dee98f8cd89ebd83a36ead7a22a184700d6e916f":
        failures.append("correction_history:v0234_missing")
    orchestration_closure = _mapping(state.get("orchestration_closure"))
    for key, expected_value in {
        "semantic_head": "6b1af57ec5f488d71bafafa17a892467adf1d1c1",
        "bookkeeping_head": "984a517d823aa426778c3bf2469eed72457eb028",
        "merge_main_sha": "6c6d53dab5a95226bf9578a6099d755d51327d8e",
        "post_merge_ci_run": 34523428088,
        "unit_job": 103026362729,
        "docker_job": 103026362968,
        "closure_comment_id": 5625161567,
        "tracked_state_binding": "PASS",
    }.items():
        if orchestration_closure.get(key) != expected_value:
            failures.append(f"orchestration_closure:{key}")
    observability = _mapping(state.get("observability"))
    for key, expected_value in {
        "status": OBSERVABILITY_STATUS,
        "external_visual_review": "PASS",
        "approval_record": OBSERVABILITY_APPROVAL_RECORD,
        "approval_artifact_id": OBSERVABILITY_APPROVAL_ARTIFACT_ID,
        "approval_artifact_digest": OBSERVABILITY_APPROVAL_ARTIFACT_DIGEST,
        "approved_reviewed_head": OBSERVABILITY_APPROVED_HEAD,
        "visuals_bound": 2,
        "self_approval": False,
        "historical_sources_rewritten": False,
        "production_approved": False,
    }.items():
        if observability.get(key) != expected_value:
            failures.append(f"observability:{key}")
    review = _mapping(state.get("review"))
    for key, expected_value in {
        "repository": "KayzenRoot/ugas",
        "base_sha": BASELINE_MAIN_SHA,
        "feature_branch": BRANCH,
        "pr_title": PR_TITLE,
        "pr_state": "OPEN",
        "pr_number_source": "GitHub LIVE PR metadata",
        "external_review_required": True,
        "merge_authorization": MERGE_AUTHORIZATION,
        "do_not_merge": True,
        "approved_semantic_head": APPROVED_SEMANTIC_HEAD,
        "approval_record": APPROVAL_RECORD,
        "approval_review_id_numeric": APPROVAL_REVIEW_ID_NUMERIC,
        "post_bookkeeping_reproof_required": POST_BOOKKEEPING_REPROOF_REQUIRED,
    }.items():
        if review.get(key) != expected_value:
            failures.append(f"review:{key}")
    pr_number = review.get("pr_number")
    if type(pr_number) is not int or pr_number < 0:
        failures.append("review:pr_number")
    if "head_sha" in review:
        failures.append("head_sha_invalid")
    if "head_sha_source" in review:
        failures.append("head_sha_source_invalid")
    if review.get("current_exact_head_authority") != CURRENT_EXACT_HEAD_AUTHORITY:
        failures.append("current_exact_head_authority_invalid")
    if set(REQUIRED_CONTEXTS) - set(review.get("required_contexts", [])):
        failures.append("review:required_contexts")
    acceptance = _mapping(state.get("v1_final_acceptance"))
    if acceptance.get("evidence_root") != V1_EVIDENCE_ROOT or acceptance.get("capability_count") != CAPABILITY_COUNT or acceptance.get("capabilities_audited") != CAPABILITY_COUNT or acceptance.get("observability_visual_review") != "PASS" or acceptance.get("production_scope") != "EXCLUDED":
        failures.append("v1_final_acceptance:binding_invalid")
    evidence_value = _mapping(state.get("evidence"))
    if evidence_value.get("root") != V1_EVIDENCE_ROOT or evidence_value.get("final_acceptance_summary") != FINAL_ACCEPTANCE_SUMMARY:
        failures.append("evidence_root_invalid")
    capabilities = matrix.get("capabilities") if isinstance(matrix.get("capabilities"), list) else []
    by_id = {item.get("id"): item for item in capabilities if isinstance(item, Mapping)}
    if len(capabilities) != CAPABILITY_COUNT:
        failures.append("matrix:capability_count_invalid")
    if matrix.get("version") != RETAINED_MATRIX_VERSION or matrix.get("next_candidate") != RETAINED_MATRIX_NEXT_CANDIDATE or matrix.get("production_routing") != "BLOCKED" or matrix.get("new_generation") != 0:
        failures.append("matrix:retained_acceptance_matrix_invalid")
    if by_id.get("orchestration_runtime_hardening", {}).get("status") != "APPROVED_FOUNDATION; MERGED_CLOSED":
        failures.append("matrix:orchestration_not_merged_closed")
    if by_id.get("vfx_asset_family", {}).get("status") != "APPROVED_FOUNDATION; MERGED_CLOSED" or by_id.get("ui_asset_family", {}).get("status") != "APPROVED_FOUNDATION; MERGED_CLOSED":
        failures.append("matrix:closed_family_regressed")
    observability_row = str(by_id.get("local_always_on_observability", {}).get("status", ""))
    if observability_row != OBSERVABILITY_ROW_STATUS:
        failures.append("matrix:observability_status_invalid")
    if "pending" in observability_row.casefold() or "required" in observability_row.casefold():
        failures.append("matrix:observability_pending_claim_retained")
    allowed = state.get("allowed_next_actions", [])
    forbidden = state.get("forbidden_actions", [])
    if not isinstance(forbidden, list):
        failures.append("forbidden_actions_invalid")
        forbidden = []
    if any(action in forbidden for action in allowed):
        failures.append("allowed_action_forbidden_contradiction")
    for action in REQUIRED_FORBIDDEN_ACTIONS:
        if action not in forbidden:
            failures.append(f"forbidden_action_missing:{action}")
    if any(action in allowed for action in UNSAFE_FORBIDDEN_ACTIONS):
        failures.append("unsafe_next_action")
    consistency_block = _mapping(state.get("state_consistency"))
    if consistency_block.get("status") != CURRENT_GATE or consistency_block.get("version") != VERSION or consistency_block.get("current_gate") != CURRENT_GATE or consistency_block.get("baseline_main_sha") != BASELINE_MAIN_SHA or consistency_block.get("feature_branch") != BRANCH or consistency_block.get("production_routing") != "BLOCKED" or consistency_block.get("production_approved") is not False or consistency_block.get("new_generation") != 0 or consistency_block.get("allowed_next_actions") != [NEXT_ACTION] or consistency_block.get("next_capability_started") is not False or consistency_block.get("orchestration_lifecycle") != ORCHESTRATION_LIFECYCLE:
        failures.append("state_consistency:binding_invalid")
    if audit is not None:
        audit_value = _mapping(audit)
        if audit_value.get("capability_count") != CAPABILITY_COUNT or audit_value.get("production_routing") != "BLOCKED" or audit_value.get("new_generation") != 0 or audit_value.get("status") != "PASS":
            failures.append("capability_audit_invalid")
        if _mapping(audit_value.get("observability")).get("visual_review_status") != "PASS":
            failures.append("capability_audit:observability_gate_invalid")
    documents = "\n".join((checkpoint_text, roadmap_text))
    for literal in (
        VERSION,
        PHASE,
        CURRENT_GATE,
        STOP_REASON,
        ACCEPTANCE_VERDICT,
        NEXT_CANDIDATE,
        NEXT_ACTION,
        ORCHESTRATION_LIFECYCLE,
        V1_SEMANTIC_HEAD,
        V1_BOOKKEEPING_HEAD,
        str(V1_POST_MERGE_CI_RUN),
        str(V1_UNIT_JOB),
        str(V1_DOCKER_JOB),
        str(V1_CLOSURE_COMMENT_ID),
        str(V1_AUDIT_COMMENT_ID),
        "production_routing=BLOCKED",
        "new_generation=0",
        "production_approved=false",
        "external review",
    ):
        if literal.casefold() not in documents.casefold():
            failures.append(f"documents_missing:{literal}")
    return {"status": CURRENT_GATE if not failures else "V1_CANONICAL_STATE_FAILED", "version": VERSION, "failures": failures, "checked": {"baseline_main_sha": state.get("baseline_main_sha"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "next_candidate": state.get("next_candidate"), "allowed_next_actions": state.get("allowed_next_actions"), "production_routing": state.get("production_routing"), "new_generation": state.get("new_generation"), "orchestration_lifecycle": state.get("orchestration_lifecycle"), "v1_closure_comment_id": closure.get("closure_comment_id"), "v1_audit_comment_id": closure.get("audit_comment_id"), "capability_count": len(capabilities)}}


def closure_binding_failures(evidence: Mapping[str, Any]) -> list[str]:
    """Fail closed when the append-only closure evidence does not bind the frozen identities."""
    failures: list[str] = []
    binding = _mapping(evidence.get("binding"))
    for key, expected_value in {
        "merge_main_sha": V1_MERGE_MAIN_SHA,
        "post_merge_ci_run": V1_POST_MERGE_CI_RUN,
        "unit_job": V1_UNIT_JOB,
        "docker_job": V1_DOCKER_JOB,
        "closure_comment_id": V1_CLOSURE_COMMENT_ID,
        "audit_comment_id": V1_AUDIT_COMMENT_ID,
        "audit_verdict": V1_AUDIT_VERDICT,
        "semantic_head": V1_SEMANTIC_HEAD,
        "bookkeeping_head": V1_BOOKKEEPING_HEAD,
    }.items():
        if binding.get(key) != expected_value:
            failures.append(f"binding:{key}")
    snapshot = _mapping(evidence.get("v0250_state_snapshot"))
    if snapshot.get("path") != V1_STATE_SNAPSHOT or snapshot.get("source_commit") != V1_MERGE_MAIN_SHA or not isinstance(snapshot.get("sha256"), str) or len(str(snapshot.get("sha256"))) != 64:
        failures.append("v0250_state_snapshot:invalid")
    if evidence.get("status") != "PASS" or evidence.get("version") != VERSION:
        failures.append("status_or_version_invalid")
    return failures


def definition_of_done_hard_gate_count(text: str) -> int | None:
    """Return the hard-gate count declared by the Definition of Done, or None when unparsable."""
    folded = " ".join(text.split())
    match = re.search(r"each of the (\d+) hard gates", folded)
    if match is None:
        match = re.search(r"(\d+) hard gates", folded)
    if match is None:
        return None
    return int(match.group(1))


def _frozen_root_content(repository_root: Path, root_relative: str) -> dict[str, bytes] | None:
    """Read LF-normalized frozen-root content, preferring committed Git objects.

    CI rebuilds runtime evidence inside the checkout, so inside a Git repository the
    committed ``HEAD`` content is authoritative; an isolated no-Git snapshot is read
    from its own tree. ``None`` means Git could not answer and the caller fails closed.
    """
    if (repository_root / ".git").exists():
        listed = subprocess.run(["git", "-C", str(repository_root), "ls-tree", "-r", "--name-only", "HEAD", "--", root_relative], capture_output=True, text=True, check=False)
        if listed.returncode != 0:
            return None
        content: dict[str, bytes] = {}
        for relative in listed.stdout.splitlines():
            blob = subprocess.run(["git", "-C", str(repository_root), "show", f"HEAD:{relative}"], capture_output=True, check=False)
            if blob.returncode != 0:
                return None
            data = blob.stdout
            if Path(relative).suffix.casefold() in {".json", ".md", ".txt"}:
                data = data.replace(b"\r\n", b"\n")
            content[relative] = data
        return content
    base = repository_root / root_relative
    content = {}
    if base.is_dir():
        for path in sorted(candidate for candidate in base.rglob("*") if candidate.is_file()):
            data = path.read_bytes()
            if path.suffix.casefold() in {".json", ".md", ".txt"}:
                data = data.replace(b"\r\n", b"\n")
            content[path.relative_to(repository_root).as_posix()] = data
    return content


def immutability_failures(evidence: Mapping[str, Any], repository_root: Path | None = None) -> list[str]:
    """Fail closed when the recorded frozen-root inventory is structurally unsound.

    When ``repository_root`` is provided the 38-file inventory is re-executed: every listed
    file must still exist with the same LF-normalized sha256 and byte size, and the frozen
    roots must not gain or lose files. Inside a Git checkout the committed HEAD content is
    authoritative (CI rebuilds runtime evidence in the working tree); an isolated no-Git
    snapshot is verified against its own tree.
    """
    failures: list[str] = []
    if evidence.get("status") != "PASS" or evidence.get("version") != VERSION:
        failures.append("status_or_version_invalid")
    roots = _mapping(evidence.get("frozen_roots"))
    for root_name in IMMUTABILITY_FROZEN_ROOTS:
        record = _mapping(roots.get(root_name))
        files = record.get("files") if isinstance(record.get("files"), list) else []
        if record.get("status") != "UNCHANGED":
            failures.append(f"{root_name}:status")
        if record.get("baseline_commit") != BASELINE_MAIN_SHA:
            failures.append(f"{root_name}:baseline_commit")
        if record.get("file_count") != len(files) or not files:
            failures.append(f"{root_name}:file_count")
        entries: dict[str, Mapping[str, Any]] = {}
        for entry in files:
            if not isinstance(entry, Mapping) or not isinstance(entry.get("path"), str) or not isinstance(entry.get("sha256"), str) or not isinstance(entry.get("bytes"), int):
                failures.append(f"{root_name}:entry")
                break
            entries[entry["path"]] = entry
        if repository_root is not None:
            content = _frozen_root_content(repository_root, root_name.rstrip("/"))
            if content is None:
                failures.append(f"{root_name}:git")
                continue
            if set(content) != set(entries):
                failures.append(f"{root_name}:inventory")
            for relative, entry in entries.items():
                data = content.get(relative)
                if data is None:
                    failures.append(f"{root_name}:{relative}:missing")
                    continue
                if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
                    failures.append(f"{root_name}:{relative}:sha256")
                if len(data) != entry.get("bytes"):
                    failures.append(f"{root_name}:{relative}:bytes")
    if evidence.get("git_guarded") is not True:
        failures.append("git_guarded")
    return failures

def negative_control_failures(evidence: Mapping[str, Any]) -> list[str]:
    """Fail closed when a mandated negative control did not observe a real rejection class."""
    failures: list[str] = []
    if evidence.get("status") != "PASS" or evidence.get("version") != VERSION:
        failures.append("status_or_version_invalid")
    controls = evidence.get("controls") if isinstance(evidence.get("controls"), dict) else {}
    if len(controls) != len(NEGATIVE_CONTROL_IDS):
        failures.append("control_count")
    for control_id in NEGATIVE_CONTROL_IDS:
        record = _mapping(controls.get(control_id))
        if record.get("status") != "PASS" or record.get("result") != "REJECT":
            failures.append(f"{control_id}:status")
            continue
        expected = record.get("expected_rejection_class")
        observed = record.get("observed_rejection_class")
        if not isinstance(expected, str) or not expected or expected != observed:
            failures.append(f"{control_id}:rejection_class")
        if not record.get("failing_key"):
            failures.append(f"{control_id}:failing_key")
    return failures


__all__ = ["ACCEPTANCE_VERDICT", "APPROVAL_RECORD", "APPROVAL_REVIEW_ID_NUMERIC", "APPROVED_SEMANTIC_HEAD", "BASELINE_MAIN_SHA", "BRANCH", "CAPABILITY_COUNT", "CLOSURE_EVIDENCE_FILES", "CLOSURE_EVIDENCE_ROOT", "CURRENT_EXACT_HEAD_AUTHORITY", "CURRENT_GATE", "FINAL_ACCEPTANCE_SUMMARY", "FROZEN_ACCEPTANCE_ROOT", "HARD_GATE_COUNT", "IMMUTABILITY_FROZEN_ROOTS", "MERGE_AUTHORIZATION", "NEGATIVE_CONTROL_IDS", "NEXT_ACTION", "NEXT_CANDIDATE", "OBSERVABILITY_APPROVAL_ARTIFACT_DIGEST", "OBSERVABILITY_APPROVAL_ARTIFACT_ID", "OBSERVABILITY_APPROVAL_RECORD", "OBSERVABILITY_APPROVED_HEAD", "OBSERVABILITY_ROW_STATUS", "OBSERVABILITY_STATUS", "ORCHESTRATION_EVIDENCE_ROOT", "ORCHESTRATION_LIFECYCLE", "PHASE", "POST_BOOKKEEPING_REPROOF_REQUIRED", "PREVIOUS_RELEASE_VERSION", "PR_TITLE", "REQUIRED_CONTEXTS", "REQUIRED_FORBIDDEN_ACTIONS", "RETAINED_MATRIX_NEXT_CANDIDATE", "RETAINED_MATRIX_VERSION", "STOP_REASON", "UNSAFE_FORBIDDEN_ACTIONS", "V1_AUDIT_COMMENT_ID", "V1_AUDIT_VERDICT", "V1_BOOKKEEPING_HEAD", "V1_CLOSURE_COMMENT_ID", "V1_DOCKER_JOB", "V1_EVIDENCE_ROOT", "V1_MERGE_MAIN_SHA", "V1_POST_MERGE_CI_RUN", "V1_PR_NUMBER", "V1_SEMANTIC_HEAD", "V1_STATE_SNAPSHOT", "V1_UNIT_JOB", "VERSION", "closure_binding_failures", "definition_of_done_hard_gate_count", "immutability_failures", "negative_control_failures", "validate_state_consistency"]
