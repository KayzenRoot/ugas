"""Fail-closed post-merge governance state for UGAS v0.21.3.

The tracked state records the historical closure baseline. Current ``main``
and closure approval are live GitHub facts and must be supplied by the
caller; they are never promoted to tracked-file invariants here.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping


CURRENT_VERSION = "0.21.3"
CURRENT_PHASE = "MAPS_MINIMAP"
CURRENT_GATE = "MAPS_MINIMAP_APPROVED_FOUNDATION_MERGED"
STOP_REASON = "MAPS_MINIMAP_CLOSED_UI_NEXT"
BASELINE_MAIN_SHA = "0c9b721b43d3cc12605ce009f6e0deb232b00045"
SEMANTIC_APPROVAL_HEAD = "812a2bed1f77df3d630425f23032c22fc72d5961"
FINAL_BOOKKEEPING_HEAD = "1ba088b40583a0ac6f287cbcc8ed8511031cd7e5"
MERGED_MAIN_SHA = "0c9b721b43d3cc12605ce009f6e0deb232b00045"
PRE_MERGE_APPROVAL_RECORD = "docs/evidence/github-governance-v0220/v0213-external-approval.json"
POST_MERGE_BINDING = "docs/evidence/github-governance-v0220/v0213-post-merge-binding.json"
CORRECTION_RECORD = "docs/evidence/github-governance-v0220/v0213-state-truth-correction-v1.json"
CLOSURE_BRANCH = "codex/v0.21.3-post-merge-closure-continuity"
CLOSURE_PR_NUMBER = 12
CLOSURE_ACTION = "resolve_post_merge_closure_gate_pr_12"
UI_ACTION = "start_ui_asset_family_v0220"
LIVE_SOURCE_MODE = "GITHUB_LIVE"

SUPPORTED_MAIN_CI_CONTEXTS = (
    "UGAS CI / unit-and-validation",
    "UGAS CI / docker-smoke",
)
REQUIRED_PR_REPROOF_CONTEXTS = (
    "UGAS CI / unit-and-validation",
    "UGAS CI / docker-smoke",
    "UGAS Review / evidence",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(char in "0123456789abcdef" for char in value.casefold())


def _context_names(contexts: Any) -> list[str]:
    if not isinstance(contexts, list):
        return []
    return [item.get("name") for item in contexts if isinstance(item, Mapping)]


def _strict_true(value: Any) -> bool:
    return type(value) is bool and value is True


def validate_pre_merge_reproof(binding: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the immutable PR #11 exact-head provenance block."""

    failures: list[str] = []
    proof = _mapping(binding.get("pre_merge_reproof"))
    contexts = proof.get("required_contexts")
    names = _context_names(contexts)
    if set(names) != set(REQUIRED_PR_REPROOF_CONTEXTS) or len(names) != len(set(names)):
        failures.append("context_set")
    if not isinstance(contexts, list) or any(
        not isinstance(item, Mapping)
        or item.get("status") != "completed"
        or item.get("conclusion") != "success"
        or item.get("head_sha") != FINAL_BOOKKEEPING_HEAD
        for item in contexts
    ):
        failures.append("contexts_not_success")
    artifact = _mapping(proof.get("artifact"))
    expected_artifact = {
        "id": 9999459003,
        "name": f"ugas-review-evidence-pr-11-{FINAL_BOOKKEEPING_HEAD}",
        "digest": "sha256:927eddebde4387d0f6a3d9007f9375f4b5ee0db8ca6e3a4c6830a936d804aa08",
        "status": "PASS",
    }
    for key, value in expected_artifact.items():
        if artifact.get(key) != value:
            failures.append(f"artifact:{key}")
    if proof.get("head_sha") != FINAL_BOOKKEEPING_HEAD or proof.get("pr_number") != 11:
        failures.append("identity")
    if proof.get("unit_tests") != {"passed": 559, "failed": 0}:
        failures.append("unit_tests")
    if proof.get("official_validation") != {"passed": 2552, "failed": 0}:
        failures.append("official_validation")
    return {"status": "PASS" if not failures else "FAIL", "failures": failures}


def validate_main_ci_provenance(
    binding: Mapping[str, Any],
    observed_context_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Validate exactly the two contexts that actually ran on merged main.

    ``observed_context_names`` is an optional live API snapshot. When it is
    supplied, the declared block must equal that snapshot exactly; the
    default still rejects extra PR-only contexts in the tracked binding.
    """

    failures: list[str] = []
    proof = _mapping(binding.get("post_merge_main_ci"))
    declared_supported = proof.get("supported_contexts")
    expected = list(observed_context_names) if observed_context_names is not None else list(SUPPORTED_MAIN_CI_CONTEXTS)
    if declared_supported != list(SUPPORTED_MAIN_CI_CONTEXTS):
        failures.append("supported_contexts")
    contexts = proof.get("contexts")
    names = _context_names(contexts)
    if set(names) != set(SUPPORTED_MAIN_CI_CONTEXTS) or set(names) != set(expected) or len(names) != len(set(names)):
        failures.append("context_set")
    if not isinstance(contexts, list) or any(
        not isinstance(item, Mapping)
        or item.get("status") != "completed"
        or item.get("conclusion") != "success"
        or item.get("head_sha") != MERGED_MAIN_SHA
        or not isinstance(item.get("check_run_id"), int)
        or not isinstance(item.get("workflow_run_id"), int)
        for item in contexts
    ):
        failures.append("contexts_not_success")
    if "UGAS Review / evidence" in names:
        failures.append("pr_only_review_context")
    if proof.get("commit_sha") != MERGED_MAIN_SHA:
        failures.append("commit_sha")
    if proof.get("unit_tests") != {"passed": 559, "failed": 0}:
        failures.append("unit_tests")
    if proof.get("official_validation") != {"passed": 2552, "failed": 0}:
        failures.append("official_validation")
    return {"status": "PASS" if not failures else "FAIL", "failures": failures}


def resolve_next_actions(state: Mapping[str, Any], live_closure: Mapping[str, Any] | None) -> dict[str, Any]:
    """Resolve the next action from live closure facts without mutating state.

    UI becomes eligible only when GitHub LIVE reports PR #12 externally
    approved and merged. Missing, malformed or false live facts fail closed
    to the closure-review action.
    """

    gate = _mapping(state.get("ui_start_gate"))
    if state.get("allowed_next_actions") != [CLOSURE_ACTION] or gate.get("status") != "BLOCKED":
        return {
            "status": "POST_MERGE_CLOSURE_GATE_REQUIRED",
            "allowed_next_actions": [CLOSURE_ACTION],
            "failures": ["tracked_closure_gate_invalid"],
        }
    live = _mapping(live_closure)
    condition = (
        live.get("pr_number") == CLOSURE_PR_NUMBER
        and live.get("pr_state") == "MERGED"
        and _strict_true(live.get("external_approval"))
        and _strict_true(live.get("merged"))
        and live.get("source_mode") == LIVE_SOURCE_MODE
    )
    if condition:
        return {"status": "UI_ASSET_FAMILY_UNBLOCKED", "allowed_next_actions": [UI_ACTION], "failures": []}
    return {
        "status": "POST_MERGE_CLOSURE_GATE_REQUIRED",
        "allowed_next_actions": [CLOSURE_ACTION],
        "failures": ["live_closure_condition_unresolved"],
    }


def validate_post_merge_state(
    state: Mapping[str, Any],
    binding: Mapping[str, Any],
    checkpoint_text: str = "",
    continuity_text: str = "",
    response_protocol_text: str = "",
) -> dict[str, Any]:
    failures: list[str] = []
    expected = {
        "schema_version": CURRENT_VERSION,
        "version": CURRENT_VERSION,
        "phase": CURRENT_PHASE,
        "current_gate": CURRENT_GATE,
        "stop_reason": STOP_REASON,
        "baseline_main_sha": BASELINE_MAIN_SHA,
        "next_candidate": "UI_ASSET_FAMILY",
        "maps_minimap_assets": "APPROVED_FOUNDATION",
        "maps_minimap_runtime_external_review": "APPROVED_FOUNDATION",
        "maps_minimap_lifecycle": "MERGED_CLOSED",
        "production_routing": "BLOCKED",
        "production_approved": False,
        "real_map_asset_coverage": "NONE",
        "real_minimap_asset_coverage": "NONE",
        "synthetic_map_fixture": "TEST_ONLY",
        "new_generation": 0,
        "next_capability_started": False,
    }
    failures.extend(f"{key}_invalid" for key, value in expected.items() if state.get(key) != value)
    if "main_sha" in state:
        failures.append("main_sha_forbidden")
    if state.get("allowed_next_actions") != [CLOSURE_ACTION]:
        failures.append("allowed_next_actions_invalid")

    ui_gate = _mapping(state.get("ui_start_gate"))
    expected_ui_gate = {
        "status": "BLOCKED",
        "activation_action": UI_ACTION,
        "condition": "GITHUB_LIVE_PR_12_EXTERNAL_APPROVAL_AND_MERGED",
        "authority": LIVE_SOURCE_MODE,
        "requires_pr_number": CLOSURE_PR_NUMBER,
    }
    failures.extend(f"ui_start_gate:{key}" for key, value in expected_ui_gate.items() if ui_gate.get(key) != value)

    bookkeeping = _mapping(state.get("bookkeeping_approval"))
    expected_bookkeeping = {
        "status": "APPROVED_FOUNDATION",
        "approved_head_sha": SEMANTIC_APPROVAL_HEAD,
        "merged_main_sha": MERGED_MAIN_SHA,
        "approval_record": PRE_MERGE_APPROVAL_RECORD,
        "post_bookkeeping_reproof_required": False,
        "merge_verified_via_protected_path": True,
    }
    failures.extend(f"bookkeeping:{key}" for key, value in expected_bookkeeping.items() if bookkeeping.get(key) != value)

    review = _mapping(state.get("review"))
    expected_review = {
        "repository": "KayzenRoot/ugas",
        "pr_number": 11,
        "pr_state": "MERGED",
        "feature_branch": "codex/v0.21.0-maps-minimap-runtime-foundation",
        "merged_main_sha": MERGED_MAIN_SHA,
        "approval_record": PRE_MERGE_APPROVAL_RECORD,
        "post_bookkeeping_reproof_required": False,
        "do_not_merge": False,
    }
    failures.extend(f"review:{key}" for key, value in expected_review.items() if review.get(key) != value)

    closure = _mapping(state.get("closure_review"))
    expected_closure = {
        "purpose": "GOVERNANCE_ONLY_POST_MERGE_CLOSURE",
        "repository": "KayzenRoot/ugas",
        "base_sha": BASELINE_MAIN_SHA,
        "branch": CLOSURE_BRANCH,
        "pr_number": CLOSURE_PR_NUMBER,
        "pr_state": "OPEN",
        "rejected_reviewed_head": "f494af8fbc74dbf6e2ffb63276b9480daf0c5fc1",
        "external_review_required": True,
        "do_not_merge": True,
        "merge_authorization": "NOT_AUTHORIZED_UNTIL_SOL_APPROVAL",
        "binding_record": POST_MERGE_BINDING,
        "correction_record": CORRECTION_RECORD,
    }
    failures.extend(f"closure_review:{key}" for key, value in expected_closure.items() if closure.get(key) != value)
    if closure.get("head_sha") not in {None, ""} and not _is_sha(closure.get("head_sha")):
        failures.append("closure_review:head_sha")

    pre_merge = validate_pre_merge_reproof(binding)
    failures.extend(f"pre_merge_reproof:{failure}" for failure in pre_merge["failures"])
    main_ci = validate_main_ci_provenance(binding)
    failures.extend(f"main_ci:{failure}" for failure in main_ci["failures"])

    expected_binding = {
        "schema_version": "0.22.1",
        "record_type": "post_merge_governance_binding",
        "merged_pr": 11,
        "merged": True,
        "final_bookkeeping_head": FINAL_BOOKKEEPING_HEAD,
        "merge_commit": MERGED_MAIN_SHA,
        "semantic_approval_head": SEMANTIC_APPROVAL_HEAD,
        "pre_merge_approval_record": PRE_MERGE_APPROVAL_RECORD,
        "production_routing": "BLOCKED",
        "production_approved": False,
        "real_map_asset_coverage": "NONE",
        "real_minimap_asset_coverage": "NONE",
        "synthetic_map_fixture": "TEST_ONLY",
        "new_generation": 0,
        "runtime_semantic_diff_final_head_to_merge": False,
        "closure_branch": CLOSURE_BRANCH,
        "closure_base_sha": BASELINE_MAIN_SHA,
    }
    failures.extend(f"binding:{key}" for key, value in expected_binding.items() if binding.get(key) != value)
    closure_binding = _mapping(binding.get("closure_pr"))
    if closure_binding.get("branch") != CLOSURE_BRANCH or closure_binding.get("base_sha") != BASELINE_MAIN_SHA:
        failures.append("binding:closure_pr_identity")
    if closure_binding.get("number") != CLOSURE_PR_NUMBER or closure_binding.get("state") != "OPEN":
        failures.append("binding:closure_pr_state")
    correction = _mapping(binding.get("correction"))
    if correction.get("record") != CORRECTION_RECORD or correction.get("rejected_head") != "f494af8fbc74dbf6e2ffb63276b9480daf0c5fc1":
        failures.append("binding:correction_identity")

    active = "\n".join((checkpoint_text, continuity_text, response_protocol_text))
    for literal in (
        CURRENT_VERSION,
        CURRENT_GATE,
        STOP_REASON,
        CLOSURE_ACTION,
        UI_ACTION,
        POST_MERGE_BINDING,
        CORRECTION_RECORD,
        "continue do chat anterior",
        "PROGRESSO E ETA",
        "baseline_main_sha",
        "GITHUB LIVE",
        "production_routing=BLOCKED",
        "new_generation=0",
    ):
        if literal.casefold() not in active.casefold():
            failures.append(f"active_documents_missing:{literal}")

    return {
        "status": CURRENT_GATE if not failures else "POST_MERGE_STATE_FAILED",
        "schema_version": CURRENT_VERSION,
        "failures": failures,
        "checked": {
            "version": state.get("version"),
            "phase": state.get("phase"),
            "current_gate": state.get("current_gate"),
            "baseline_main_sha": state.get("baseline_main_sha"),
            "closure_base_sha": binding.get("closure_base_sha"),
            "closure_pr_number": closure.get("pr_number"),
            "closure_pr_state": closure.get("pr_state"),
            "allowed_next_actions": state.get("allowed_next_actions"),
            "production_routing": state.get("production_routing"),
            "new_generation": state.get("new_generation"),
        },
    }


REQUIRED_PROGRESS_FIELDS = (
    "capability_current",
    "ugas_v1_overall",
    "completed_capabilities",
    "remaining_gates",
    "estimated_cycles",
    "eta_optimistic",
    "eta_realistic",
    "eta_conservative",
    "confidence",
    "critical_path",
    "status_delta",
)


def validate_progress_response(
    response: Mapping[str, Any],
    state: Mapping[str, Any],
    live_main_sha: str | None = None,
) -> dict[str, Any]:
    """Validate a response against live main and tracked semantic anchors."""

    failures = [f"missing:{key}" for key in REQUIRED_PROGRESS_FIELDS if key not in response]
    if "source_main_sha" in response:
        failures.append("source_main_sha_forbidden")
    if not _is_sha(live_main_sha):
        failures.append("live_main_sha_unavailable")
    elif response.get("source_live_main_sha") != live_main_sha:
        failures.append("source_live_main_sha_mismatch")
    if response.get("source_baseline_main_sha") != state.get("baseline_main_sha"):
        failures.append("source_baseline_main_sha_mismatch")
    if response.get("source_current_gate") != state.get("current_gate"):
        failures.append("source_current_gate_mismatch")
    if response.get("source_mode") != "LIVE_REPOSITORY_AND_GITHUB":
        failures.append("source_mode_must_be_live")
    return {"status": "PROGRESS_RESPONSE_PASSED" if not failures else "PROGRESS_RESPONSE_FAILED", "failures": failures}


__all__ = [
    "BASELINE_MAIN_SHA",
    "CLOSURE_ACTION",
    "CLOSURE_BRANCH",
    "CORRECTION_RECORD",
    "CURRENT_GATE",
    "CURRENT_PHASE",
    "CURRENT_VERSION",
    "FINAL_BOOKKEEPING_HEAD",
    "MERGED_MAIN_SHA",
    "POST_MERGE_BINDING",
    "PRE_MERGE_APPROVAL_RECORD",
    "REQUIRED_PR_REPROOF_CONTEXTS",
    "SEMANTIC_APPROVAL_HEAD",
    "STOP_REASON",
    "SUPPORTED_MAIN_CI_CONTEXTS",
    "UI_ACTION",
    "resolve_next_actions",
    "validate_main_ci_provenance",
    "validate_post_merge_state",
    "validate_pre_merge_reproof",
    "validate_progress_response",
]
