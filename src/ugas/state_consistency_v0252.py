"""Fail-closed canonical-state promotion validator for UGAS v0.25.2."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

VERSION = "0.25.2"
PHASE = "V1_FINAL_ACCEPTANCE"
BASELINE_MAIN_SHA = "38606625d5b59b09c407f9cc903bd748d91e6b35"
BRANCH = "codex/ugas-wo-0255-v1-post-merge-canonical-state-promotion"
PR_TITLE = "UGAS WO-0255 V1 post-merge canonical-state promotion"
CURRENT_GATE = "V1_CANONICAL_STATE_POST_MERGE_PROMOTION_EXTERNAL_REVIEW_REQUIRED"
STOP_REASON = "V1_CANONICAL_STATE_PROMOTION_READY_FOR_EXTERNAL_REVIEW"
ACCEPTANCE_VERDICT = "V1_CANONICAL_STATE_PROMOTION_TECHNICALLY_QUALIFIED"
NEXT_CANDIDATE = "PRODUCTION_READINESS"
NEXT_ACTION = "external_review_post_merge_canonical_state_promotion_pr"
MERGE_AUTHORIZATION = "GOVERNED_MERGE_ONLY_AFTER_EXACT_HEAD_EXTERNAL_REVIEW"
PR_NUMBER = 20

SOURCE_PR = 18
SOURCE_PR_BASE_SHA = "02fa44f2173aca46b4484209abccf218fe688a63"
SOURCE_REVIEWED_HEAD = "5f4a56bf019cc10994ee2974430c3ffca3090a50"
SOURCE_MERGE_SHA = BASELINE_MAIN_SHA
SOURCE_MERGED_AT = "2026-09-12T11:21:46Z"
SOURCE_MERGE_PARENTS = (SOURCE_PR_BASE_SHA, SOURCE_REVIEWED_HEAD)
SOURCE_POST_MERGE_RUN = 34690855982
SOURCE_RUN_ATTEMPT = 1
SOURCE_UNIT_JOB = 103545700293
SOURCE_DOCKER_JOB = 103545700226
SOURCE_CLOSURE_COMMENT = 5645638986
SOURCE_APPROVAL_COMMENT = 5646607566
SOURCE_APPROVAL_VERDICT = "APPROVED"
SOURCE_MAIN_CONTEXTS = ("UGAS CI / unit-and-validation", "UGAS CI / docker-smoke")

PROMOTION_EVIDENCE_ROOT = "docs/evidence/post-merge-canonical-promotion-v0252/"
PROMOTION_BINDING = PROMOTION_EVIDENCE_ROOT + "post-merge-binding-v0252.json"
PROMOTION_IMMUTABILITY = PROMOTION_EVIDENCE_ROOT + "historical-v0251-immutability-v0252.json"
PROMOTION_NEGATIVE_CONTROLS = PROMOTION_EVIDENCE_ROOT + "negative-controls-v0252.json"
PROMOTION_UADS = PROMOTION_EVIDENCE_ROOT + "uads-handoff-v0252.json"
PROMOTION_DELTA = PROMOTION_EVIDENCE_ROOT + "proposed-checkpoint-delta-v0252.md"
HISTORICAL_ROOT = "docs/evidence/canonical-state-reconciliation-v0251/"
MATRIX_VERSION = "0.25.0"
HARD_GATE_COUNT = 30

REQUIRED_FORBIDDEN_ACTIONS = (
    "direct_main_push",
    "force_push_or_history_rewrite",
    "merge_without_sol_approval",
    "self_merge_post_merge_canonical_state_promotion_pr",
    "merge_post_merge_canonical_state_promotion_pr",
    "enable_production_routing",
    "start_production_readiness",
    "real_asset_generation",
    "provider_network",
    "start_ugas_v2",
)

NEGATIVE_CONTROL_IDS = (
    "NC-0255-01-STALE-PR-OPEN",
    "NC-0255-02-STALE-DO-NOT-MERGE",
    "NC-0255-03-WRONG-MERGE-IDENTITY",
    "NC-0255-04-WRONG-CLOSURE-ID",
    "NC-0255-05-PRODUCTION-DRIFT",
    "NC-0255-06-READINESS-PREMATURE",
    "NC-0255-07-FABRICATED-MAIN-CONTEXT",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _expected_source_binding() -> dict[str, Any]:
    return {
        "pr_number": SOURCE_PR,
        "pr_state": "MERGED",
        "base_sha": SOURCE_PR_BASE_SHA,
        "reviewed_head": SOURCE_REVIEWED_HEAD,
        "merge_sha": SOURCE_MERGE_SHA,
        "merged_at": SOURCE_MERGED_AT,
        "merge_parents": list(SOURCE_MERGE_PARENTS),
        "post_merge_ci_run": SOURCE_POST_MERGE_RUN,
        "run_attempt": SOURCE_RUN_ATTEMPT,
        "closure_comment_id": SOURCE_CLOSURE_COMMENT,
        "approval_comment_id": SOURCE_APPROVAL_COMMENT,
        "approval_verdict": SOURCE_APPROVAL_VERDICT,
    }


def validate_main_ci_provenance(main_ci: Mapping[str, Any]) -> list[str]:
    """Require the post-merge main result to contain exactly the observed 2/2 contexts."""
    failures: list[str] = []
    contexts = main_ci.get("contexts") if isinstance(main_ci.get("contexts"), list) else []
    names = [item.get("name") for item in contexts if isinstance(item, Mapping)]
    if set(names) != set(SOURCE_MAIN_CONTEXTS) or len(names) != len(SOURCE_MAIN_CONTEXTS):
        failures.append("main_ci_result:context_set")
    if any(name == "UGAS Review / evidence" for name in names):
        failures.append("main_ci_result:review_context_forbidden")
    if main_ci.get("run_id") != SOURCE_POST_MERGE_RUN or main_ci.get("head_sha") != SOURCE_MERGE_SHA or main_ci.get("conclusion") != "SUCCESS":
        failures.append("main_ci_result:identity")
    expected_jobs = {
        "UGAS CI / unit-and-validation": SOURCE_UNIT_JOB,
        "UGAS CI / docker-smoke": SOURCE_DOCKER_JOB,
    }
    for name, job_id in expected_jobs.items():
        matches = [item for item in contexts if isinstance(item, Mapping) and item.get("name") == name]
        if len(matches) != 1 or matches[0].get("job_id") != job_id or matches[0].get("conclusion") != "SUCCESS":
            failures.append(f"main_ci_result:{name}")
    return failures


def validate_post_merge_binding(binding_evidence: Mapping[str, Any]) -> list[str]:
    """Validate the real PR #18 closure identity and its split provenance blocks."""
    failures: list[str] = []
    if binding_evidence.get("status") != "PASS" or binding_evidence.get("version") != VERSION:
        failures.append("binding:status_or_version")
    binding = _mapping(binding_evidence.get("source_pr_18"))
    for key, expected in _expected_source_binding().items():
        if binding.get(key) != expected:
            failures.append(f"source_pr_18:{key}")
    if binding_evidence.get("tracked_state_binding") != "PASS":
        failures.append("binding:tracked_state_binding")
    provenance = _mapping(binding_evidence.get("provenance"))
    main_ci = _mapping(provenance.get("post_merge_main_ci"))
    failures.extend(validate_main_ci_provenance(main_ci))
    if _mapping(provenance.get("closure_authority")).get("closure_comment_id") != SOURCE_CLOSURE_COMMENT:
        failures.append("provenance:closure_authority")
    if _mapping(provenance.get("sol_approval")).get("approval_comment_id") != SOURCE_APPROVAL_COMMENT or _mapping(provenance.get("sol_approval")).get("verdict") != SOURCE_APPROVAL_VERDICT:
        failures.append("provenance:sol_approval")
    return failures


def _check_equal(failures: list[str], value: Any, expected: Any, key: str) -> None:
    if value != expected:
        failures.append(f"{key}_invalid")


def validate_state_consistency(
    state: Mapping[str, Any],
    checkpoint_text: str,
    roadmap_text: str,
    matrix: Mapping[str, Any],
    binding_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
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
        "production_routing": "BLOCKED",
        "production_approved": False,
        "real_asset_generation": "NONE",
        "new_generation": 0,
        "provider_submit_calls": 0,
        "next_capability_started": False,
        "production_readiness_workstream": "NOT_STARTED_REQUIRED_SEPARATELY",
        "synthetic_fixture": "TEST_ONLY",
    }
    for key, value in expected.items():
        _check_equal(failures, state.get(key), value, key)
    if "main_sha" in state:
        failures.append("main_sha_forbidden")

    closure = _mapping(state.get("post_merge_canonical_promotion"))
    for key, value in {
        "source_pr": SOURCE_PR,
        "source_pr_base_sha": SOURCE_PR_BASE_SHA,
        "source_reviewed_head": SOURCE_REVIEWED_HEAD,
        "source_merge_sha": SOURCE_MERGE_SHA,
        "source_merged_at": SOURCE_MERGED_AT,
        "source_post_merge_ci_run": SOURCE_POST_MERGE_RUN,
        "source_unit_job": SOURCE_UNIT_JOB,
        "source_docker_job": SOURCE_DOCKER_JOB,
        "source_closure_comment_id": SOURCE_CLOSURE_COMMENT,
        "source_approval_comment_id": SOURCE_APPROVAL_COMMENT,
        "source_approval_verdict": SOURCE_APPROVAL_VERDICT,
        "source_merge_parents": list(SOURCE_MERGE_PARENTS),
        "tracked_state_binding": "PASS",
    }.items():
        _check_equal(failures, closure.get(key), value, f"post_merge_canonical_promotion:{key}")
    if closure.get("source_pr") != SOURCE_PR:
        failures.append("post_merge_canonical_promotion:source_pr")

    review = _mapping(state.get("review"))
    for key, value in {
        "repository": "KayzenRoot/ugas",
        "base_sha": BASELINE_MAIN_SHA,
        "feature_branch": BRANCH,
        "pr_title": PR_TITLE,
        "pr_number_source": "GitHub LIVE PR metadata",
        "pr_state": "OPEN",
        "current_exact_head_authority": "GITHUB_LIVE_ONLY",
        "external_review_required": True,
        "merge_authorization": MERGE_AUTHORIZATION,
        "do_not_merge": True,
    }.items():
        _check_equal(failures, review.get(key), value, f"review:{key}")
    if type(review.get("pr_number")) is not int or review.get("pr_number") <= 0:
        failures.append("review:pr_number")
    if any(key in review for key in ("head_sha", "head_sha_source")):
        failures.append("review:self_referential_head_forbidden")

    forbidden = state.get("forbidden_actions")
    if not isinstance(forbidden, list):
        failures.append("forbidden_actions_invalid")
        forbidden = []
    for action in REQUIRED_FORBIDDEN_ACTIONS:
        if action not in forbidden:
            failures.append(f"forbidden_action_missing:{action}")
    allowed = state.get("allowed_next_actions")
    if isinstance(allowed, list) and any(action in forbidden for action in allowed):
        failures.append("allowed_action_forbidden_contradiction")
    if isinstance(allowed, list) and any("production" in str(action).casefold() for action in allowed):
        failures.append("premature_production_action")

    history = _mapping(state.get("correction_history"))
    previous = _mapping(history.get("v0.25.1"))
    if previous.get("status") != "MERGED_CLOSED" or previous.get("merge_commit") != SOURCE_MERGE_SHA or previous.get("historical_evidence_unchanged") is not True or previous.get("evidence") != HISTORICAL_ROOT:
        failures.append("correction_history:v0.25.1_invalid")
    if _mapping(state.get("previous_release")).get("version") != "0.25.1" or _mapping(state.get("previous_release")).get("status") != "MERGED_CLOSED":
        failures.append("previous_release_invalid")

    consistency = _mapping(state.get("state_consistency"))
    for key, value in {
        "status": CURRENT_GATE,
        "version": VERSION,
        "current_gate": CURRENT_GATE,
        "baseline_main_sha": BASELINE_MAIN_SHA,
        "feature_branch": BRANCH,
        "production_routing": "BLOCKED",
        "production_approved": False,
        "new_generation": 0,
        "allowed_next_actions": [NEXT_ACTION],
        "next_capability_started": False,
        "production_readiness_workstream": "NOT_STARTED_REQUIRED_SEPARATELY",
    }.items():
        _check_equal(failures, consistency.get(key), value, f"state_consistency:{key}")

    if matrix.get("version") != MATRIX_VERSION or matrix.get("production_routing") != "BLOCKED" or matrix.get("new_generation") != 0:
        failures.append("matrix:retained_acceptance_matrix_invalid")

    documents = "\n".join((checkpoint_text, roadmap_text))
    for literal in (VERSION, CURRENT_GATE, STOP_REASON, ACCEPTANCE_VERDICT, NEXT_CANDIDATE, NEXT_ACTION, SOURCE_MERGE_SHA, str(SOURCE_POST_MERGE_RUN), str(SOURCE_CLOSURE_COMMENT), str(SOURCE_APPROVAL_COMMENT), "production_routing=BLOCKED", "production_approved=false", "new_generation=0", "NOT_STARTED_REQUIRED_SEPARATELY"):
        if literal.casefold() not in documents.casefold():
            failures.append(f"documents_missing:{literal}")
    if binding_evidence is not None:
        failures.extend(validate_post_merge_binding(binding_evidence))
    return {
        "status": CURRENT_GATE if not failures else "V1_CANONICAL_STATE_PROMOTION_FAILED",
        "version": VERSION,
        "failures": failures,
        "checked": {
            "baseline_main_sha": state.get("baseline_main_sha"),
            "source_merge_sha": closure.get("source_merge_sha"),
            "current_gate": state.get("current_gate"),
            "next_candidate": state.get("next_candidate"),
            "allowed_next_actions": state.get("allowed_next_actions"),
            "production_routing": state.get("production_routing"),
            "production_approved": state.get("production_approved"),
            "new_generation": state.get("new_generation"),
        },
    }


def historical_immutability_failures(evidence: Mapping[str, Any], repository_root: Path | None = None) -> list[str]:
    failures: list[str] = []
    if evidence.get("status") != "PASS" or evidence.get("version") != VERSION:
        failures.append("status_or_version_invalid")
    record = _mapping(evidence.get("historical_root"))
    if record.get("path") != HISTORICAL_ROOT or record.get("status") != "UNCHANGED" or record.get("baseline_commit") != BASELINE_MAIN_SHA:
        failures.append("historical_root:binding")
    files = record.get("files") if isinstance(record.get("files"), list) else []
    if not files:
        failures.append("historical_root:files")
    if repository_root is not None:
        listed = subprocess.run(["git", "-C", str(repository_root), "ls-tree", "-r", "--name-only", "HEAD", "--", HISTORICAL_ROOT.rstrip("/")], capture_output=True, text=True, check=False)
        if listed.returncode != 0:
            failures.append("historical_root:git")
        else:
            recorded = {item.get("path"): item for item in files if isinstance(item, Mapping) and isinstance(item.get("path"), str)}
            actual = set(listed.stdout.splitlines())
            if actual != set(recorded):
                failures.append("historical_root:inventory")
            for relative, item in recorded.items():
                blob = subprocess.run(["git", "-C", str(repository_root), "show", f"HEAD:{relative}"], capture_output=True, check=False)
                data = blob.stdout.replace(b"\r\n", b"\n") if Path(relative).suffix.casefold() in {".json", ".md", ".txt"} else blob.stdout
                if blob.returncode != 0 or hashlib.sha256(data).hexdigest() != item.get("sha256") or len(data) != item.get("bytes"):
                    failures.append(f"historical_root:{relative}")
    return failures


def negative_control_failures(evidence: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if evidence.get("status") != "PASS" or evidence.get("version") != VERSION:
        failures.append("status_or_version_invalid")
    controls = evidence.get("controls") if isinstance(evidence.get("controls"), Mapping) else {}
    if set(controls) != set(NEGATIVE_CONTROL_IDS):
        failures.append("control_set")
    for control_id in NEGATIVE_CONTROL_IDS:
        record = _mapping(controls.get(control_id))
        if record.get("status") != "PASS" or record.get("result") != "REJECT":
            failures.append(f"{control_id}:status")
        if not isinstance(record.get("expected_rejection_class"), str) or record.get("expected_rejection_class") != record.get("observed_rejection_class"):
            failures.append(f"{control_id}:rejection_class")
        if not record.get("failing_key") or not record.get("actual_failure_count", 0) > 0:
            failures.append(f"{control_id}:actual_path")
    return failures


def definition_of_done_hard_gate_count(text: str) -> int | None:
    match = re.search(r"(?:each of the |)(\d+) hard gates", " ".join(text.split()))
    return int(match.group(1)) if match else None


__all__ = [
    "ACCEPTANCE_VERDICT", "BASELINE_MAIN_SHA", "BRANCH", "CURRENT_GATE", "HISTORICAL_ROOT",
    "NEXT_ACTION", "NEXT_CANDIDATE", "NEGATIVE_CONTROL_IDS", "PHASE", "PR_NUMBER", "PR_TITLE",
    "PROMOTION_BINDING", "PROMOTION_DELTA", "PROMOTION_EVIDENCE_ROOT", "PROMOTION_IMMUTABILITY",
    "PROMOTION_NEGATIVE_CONTROLS", "PROMOTION_UADS", "SOURCE_APPROVAL_COMMENT", "SOURCE_CLOSURE_COMMENT",
    "SOURCE_DOCKER_JOB", "SOURCE_MERGE_SHA", "SOURCE_POST_MERGE_RUN", "SOURCE_PR", "SOURCE_PR_BASE_SHA",
    "SOURCE_REVIEWED_HEAD", "SOURCE_UNIT_JOB", "STOP_REASON", "VERSION", "definition_of_done_hard_gate_count",
    "historical_immutability_failures", "negative_control_failures", "validate_main_ci_provenance",
    "validate_post_merge_binding", "validate_state_consistency",
]
