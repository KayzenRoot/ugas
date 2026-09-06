"""Fail-closed active-state contract for the v0.20.3 governance correction."""

from __future__ import annotations

from typing import Any, Mapping


CURRENT_VERSION = "0.20.3"
CURRENT_PHASE = "ENVIRONMENT_TILESETS"
CURRENT_GATE = "ENVIRONMENT_TILESETS_QA_GOVERNANCE_INTEGRITY_TECHNICALLY_QUALIFIED"
NEXT_ACTION = "external_review_environment_tilesets_v0203"
BASELINE_HEAD = "93293d21f301e6d64232a992eb92533db9741118"
FEATURE_BRANCH = "codex/v0.20.0-environment-tilesets-runtime-foundation"
REJECTED_V0202_HEAD = "6022cf3c6158ebb762519a04e79ed42378438ccc"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str = "", review_text: str = "", roadmap_text: str = "") -> dict[str, Any]:
    failures: list[str] = []
    expected = {
        "schema_version": CURRENT_VERSION,
        "version": CURRENT_VERSION,
        "phase": CURRENT_PHASE,
        "current_gate": CURRENT_GATE,
        "creatures_monsters": "APPROVED_FOUNDATION",
        "items_props": "APPROVED_FOUNDATION",
        "environment_tilesets_runtime": "TECHNICALLY_QUALIFIED_FOUNDATION",
        "environment_tilesets_runtime_external_review": "REQUIRED",
        "real_environment_asset_coverage": "NONE",
        "synthetic_environment_fixture": "TEST_ONLY",
        "production_routing": "BLOCKED",
        "production_approved": False,
        "new_generation": 0,
        "always_on_dashboard_policy": "ENABLED",
        "runtime_mode": "DOCKER_ALWAYS_ON_LOCAL",
    }
    failures.extend(f"{key}_invalid" for key, value in expected.items() if state.get(key) != value)
    if state.get("allowed_next_actions") != [NEXT_ACTION]:
        failures.append("allowed_next_actions_invalid")
    forbidden = state.get("forbidden_actions", [])
    required_forbidden = {"direct_main_push", "force_push_or_history_rewrite", "enable_production_routing", "new_generation", "maps_minimap_assets", "ui_asset_family", "vfx_asset_family", "orchestration_runtime_hardening"}
    if not isinstance(forbidden, list) or not required_forbidden.issubset(forbidden):
        failures.append("forbidden_boundaries_incomplete")
    previous = _mapping(state.get("previous_release"))
    if previous.get("version") != "0.19.1" or previous.get("merge_commit") != BASELINE_HEAD:
        failures.append("previous_release_must_bind_v0191_merge")
    history = _mapping(state.get("correction_history"))
    if _mapping(history.get("v0.19.1")).get("status") != "APPROVED_FOUNDATION":
        failures.append("v0191_approval_history_invalid")
    for version, head in (("v0.20.0", "ae335ba198bb7f23210873e30948e8a19bc71cbd"), ("v0.20.1", "0353e6785017c08db6e55c9448d9fa60e5908802"), ("v0.20.2", REJECTED_V0202_HEAD)):
        record = _mapping(history.get(version))
        if record.get("status") != "CORRECTION_REQUIRED" or record.get("rejected_reviewed_head") != head or record.get("historical_evidence_unchanged") is not True:
            failures.append(f"{version}_rejection_history_invalid")
    external = _mapping(state.get("external_visual_review"))
    if external.get("items_props_runtime") != "APPROVED_FOUNDATION" or external.get("environment_tilesets_runtime") != "REQUIRED":
        failures.append("external_review_boundary_invalid")
    review = _mapping(state.get("review"))
    review_expected = {"repository": "KayzenRoot/ugas", "baseline_head": BASELINE_HEAD, "branch_base_commit": BASELINE_HEAD, "feature_branch": FEATURE_BRANCH, "execution_mode": "GITHUB_PR_FIRST", "merge_policy": "NO_SELF_MERGE_UNTIL_EXTERNAL_REVIEW", "no_self_merge_until_external_approval": True, "merge_authorization": "NOT_AUTHORIZED", "external_review_required": True, "do_not_merge": True}
    failures.extend(f"review:{key}" for key, value in review_expected.items() if review.get(key) != value)
    if review.get("pr_state") not in {"OPEN", "NOT_CREATED"} or not isinstance(review.get("pr_number"), int) or review["pr_number"] < 0:
        failures.append("review:pr_binding")
    nested = _mapping(state.get("state_consistency"))
    nested_expected = {"status": CURRENT_GATE, "version": CURRENT_VERSION, "phase": CURRENT_PHASE, "current_gate": CURRENT_GATE, "feature_branch": FEATURE_BRANCH, "branch_base_commit": BASELINE_HEAD, "production_routing": "BLOCKED", "production_approved": False, "new_generation": 0, "allowed_next_actions": [NEXT_ACTION], "next_capability_started": False}
    failures.extend(f"state_consistency:{key}" for key, value in nested_expected.items() if nested.get(key) != value)
    active = "\n".join((checkpoint_text, review_text, roadmap_text))
    literals = ("0.20.3", "0.20.2", "0.20.1", "0.20.0", "0.19.1", CURRENT_PHASE, CURRENT_GATE, NEXT_ACTION, "items_props=APPROVED_FOUNDATION", "environment_tilesets_runtime_external_review=REQUIRED", "real_environment_asset_coverage=NONE", "synthetic_environment_fixture=TEST_ONLY", "production_approved=false", "production_routing=BLOCKED", "new_generation=0", "external_review_environment_tilesets_v0203", "v0202_external_review=CORRECTION_REQUIRED")
    for literal in literals:
        if literal.casefold() not in active.casefold():
            failures.append(f"active_documents_missing:{literal}")
    return {"status": CURRENT_GATE if not failures else "STATE_CONSISTENCY_FAILED", "schema_version": CURRENT_VERSION, "failures": failures, "checked": {"version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "feature_branch": review.get("feature_branch"), "branch_base_commit": review.get("branch_base_commit"), "next_action": state.get("allowed_next_actions"), "production_routing": state.get("production_routing"), "new_generation": state.get("new_generation"), "pr_number": review.get("pr_number"), "pr_state": review.get("pr_state")}}


__all__ = ["BASELINE_HEAD", "CURRENT_GATE", "CURRENT_PHASE", "CURRENT_VERSION", "FEATURE_BRANCH", "NEXT_ACTION", "REJECTED_V0202_HEAD", "validate_state_consistency"]
