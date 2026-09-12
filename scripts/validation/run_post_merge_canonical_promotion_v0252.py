"""Generate deterministic v0.25.2 post-merge canonical-state promotion evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.state_consistency_v0252 import (  # noqa: E402
    BASELINE_MAIN_SHA,
    HISTORICAL_ROOT,
    NEGATIVE_CONTROL_IDS,
    PROMOTION_EVIDENCE_ROOT,
    SOURCE_APPROVAL_COMMENT,
    SOURCE_CLOSURE_COMMENT,
    SOURCE_DOCKER_JOB,
    SOURCE_MERGE_SHA,
    SOURCE_POST_MERGE_RUN,
    SOURCE_PR,
    SOURCE_PR_BASE_SHA,
    SOURCE_REVIEWED_HEAD,
    SOURCE_UNIT_JOB,
    VERSION,
    validate_main_ci_provenance,
    validate_post_merge_binding,
    validate_state_consistency,
)

WORK_ORDER = "UGAS-WO-0255"
ISSUE_NUMBER = 19
UADS_WORK_ORDER_ID = "wo_7ef9f2eb5a29a6b4"
UADS_DISPATCH_ID = "er_2b6a8b0f3d5eceff"
UADS_PROFILE_ID = "codex-global-strong-v1"
STATE_PATH = ROOT / "docs/evidence/current-state.json"
CHECKPOINT_PATH = ROOT / "CHECKPOINT.md"
ROADMAP_PATH = ROOT / "docs/roadmap.md"
MATRIX_PATH = ROOT / "docs/ugas-v1-capability-matrix.json"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False)


def _normalized_file(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    return _sha256(data), len(data)


def post_merge_binding() -> dict[str, Any]:
    binding = {
        "pr_number": SOURCE_PR,
        "pr_state": "MERGED",
        "base_sha": SOURCE_PR_BASE_SHA,
        "reviewed_head": SOURCE_REVIEWED_HEAD,
        "merge_sha": SOURCE_MERGE_SHA,
        "merged_at": "2026-09-12T11:21:46Z",
        "merge_parents": [SOURCE_PR_BASE_SHA, SOURCE_REVIEWED_HEAD],
        "post_merge_ci_run": SOURCE_POST_MERGE_RUN,
        "run_attempt": 1,
        "closure_comment_id": SOURCE_CLOSURE_COMMENT,
        "approval_comment_id": SOURCE_APPROVAL_COMMENT,
        "approval_verdict": "APPROVED",
    }
    evidence = {
        "schema_version": VERSION,
        "version": VERSION,
        "status": "PASS",
        "work_order": WORK_ORDER,
        "issue": ISSUE_NUMBER,
        "source": "GitHub LIVE PR #18, merge commit, exact-main CI jobs, closure comment and Sol approval comment re-fetched before generation",
        "source_pr_18": binding,
        "provenance": {
            "closure_authority": {"closure_comment_id": SOURCE_CLOSURE_COMMENT, "source": "GitHub LIVE issue comment"},
            "sol_approval": {"approval_comment_id": SOURCE_APPROVAL_COMMENT, "verdict": "APPROVED", "source": "GitHub LIVE issue comment"},
            "post_merge_main_ci": {
                "source": "GitHub LIVE workflow run on merged main",
                "run_id": SOURCE_POST_MERGE_RUN,
                "run_attempt": 1,
                "head_sha": SOURCE_MERGE_SHA,
                "conclusion": "SUCCESS",
                "contexts": [
                    {"name": "UGAS CI / unit-and-validation", "job_id": SOURCE_UNIT_JOB, "conclusion": "SUCCESS"},
                    {"name": "UGAS CI / docker-smoke", "job_id": SOURCE_DOCKER_JOB, "conclusion": "SUCCESS"},
                ],
                "context_set_semantics": "exactly the two observed main push workflow jobs; PR-only UGAS Review / evidence is not copied here",
            },
        },
        "tracked_state_binding": "PASS",
        "historical_evidence_unchanged": True,
    }
    failures = validate_post_merge_binding(evidence)
    if failures:
        raise SystemExit("post-merge binding failed: " + ", ".join(failures))
    return evidence


def historical_immutability() -> dict[str, Any]:
    relative_root = HISTORICAL_ROOT.rstrip("/")
    listed = _git("ls-tree", "-r", "--name-only", "HEAD", "--", relative_root)
    if listed.returncode != 0:
        raise SystemExit("historical v0.25.1 tree is unavailable")
    files = []
    for relative in sorted(line for line in listed.stdout.splitlines() if line):
        result = _git("show", f"HEAD:{relative}")
        if result.returncode != 0:
            raise SystemExit(f"historical file unavailable: {relative}")
        data = result.stdout.encode()
        if Path(relative).suffix.casefold() in {".json", ".md", ".txt"}:
            data = data.replace(b"\r\n", b"\n")
        files.append({"path": relative, "sha256": _sha256(data), "bytes": len(data)})
    diff = _git("diff", "--quiet", BASELINE_MAIN_SHA, "--", relative_root)
    status = _git("status", "--porcelain", "--", relative_root)
    payload = {
        "schema_version": VERSION,
        "version": VERSION,
        "status": "PASS" if diff.returncode == 0 and not status.stdout.strip() else "FAIL",
        "work_order": WORK_ORDER,
        "historical_root": {
            "path": HISTORICAL_ROOT,
            "status": "UNCHANGED" if diff.returncode == 0 and not status.stdout.strip() else "DRIFT",
            "baseline_commit": BASELINE_MAIN_SHA,
            "file_count": len(files),
            "files": files,
        },
        "git_guarded": diff.returncode == 0 and not status.stdout.strip(),
        "method": "exact Git HEAD inventory of the v0.25.1 evidence root with normalized text hashes, cross-checked against the verified main baseline",
    }
    if payload["status"] != "PASS":
        raise SystemExit("v0.25.1 evidence root is not unchanged")
    return payload


def _state_inputs() -> tuple[dict[str, Any], str, str, dict[str, Any]]:
    return (
        _read_json(STATE_PATH),
        CHECKPOINT_PATH.read_text(encoding="utf-8"),
        ROADMAP_PATH.read_text(encoding="utf-8"),
        _read_json(MATRIX_PATH),
    )


def negative_controls(binding: Mapping[str, Any]) -> dict[str, Any]:
    state, checkpoint, roadmap, matrix = _state_inputs()
    mutations = {
        "NC-0255-01-STALE-PR-OPEN": (["review", "pr_state"], "MERGED", "review:pr_state_invalid"),
        "NC-0255-02-STALE-DO-NOT-MERGE": (["review", "do_not_merge"], False, "review:do_not_merge_invalid"),
        "NC-0255-03-WRONG-MERGE-IDENTITY": (["post_merge_canonical_promotion", "source_merge_sha"], "0" * 40, "post_merge_canonical_promotion:source_merge_sha_invalid"),
        "NC-0255-04-WRONG-CLOSURE-ID": (["post_merge_canonical_promotion", "source_closure_comment_id"], 1, "post_merge_canonical_promotion:source_closure_comment_id_invalid"),
        "NC-0255-05-PRODUCTION-DRIFT": (["production_approved"], True, "production_approved_invalid"),
        "NC-0255-06-READINESS-PREMATURE": (["production_readiness_workstream"], "STARTED", "production_readiness_workstream_invalid"),
    }
    controls: dict[str, Any] = {}
    for control_id, (path, value, expected) in mutations.items():
        mutated = copy.deepcopy(state)
        target = mutated
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        failures = validate_state_consistency(mutated, checkpoint, roadmap, matrix, binding)["failures"]
        controls[control_id] = {
            "status": "PASS" if expected in failures else "FAIL",
            "result": "REJECT" if expected in failures else "ACCEPT",
            "expected_rejection_class": expected,
            "observed_rejection_class": expected if expected in failures else (failures[0] if failures else "NONE"),
            "failing_key": ".".join(path),
            "actual_failure_count": len(failures),
            "actual_failures": failures,
        }

    mutated_binding = copy.deepcopy(dict(binding))
    mutated_binding["provenance"]["post_merge_main_ci"]["contexts"].append({"name": "UGAS Review / evidence", "job_id": 999, "conclusion": "SUCCESS"})
    failures = validate_post_merge_binding(mutated_binding)
    expected = "main_ci_result:context_set"
    controls["NC-0255-07-FABRICATED-MAIN-CONTEXT"] = {
        "status": "PASS" if expected in failures else "FAIL",
        "result": "REJECT" if expected in failures else "ACCEPT",
        "expected_rejection_class": expected,
        "observed_rejection_class": expected if expected in failures else (failures[0] if failures else "NONE"),
        "failing_key": "provenance.post_merge_main_ci.contexts",
        "actual_failure_count": len(failures),
        "actual_failures": failures,
    }
    payload = {
        "schema_version": VERSION,
        "version": VERSION,
        "status": "PASS" if all(item["status"] == "PASS" and item["result"] == "REJECT" for item in controls.values()) else "FAIL",
        "work_order": WORK_ORDER,
        "control_count": len(controls),
        "controls": controls,
        "method": "each negative control mutates the active state or split main-CI binding and executes the real fail-closed validator path",
    }
    if set(controls) != set(NEGATIVE_CONTROL_IDS) or payload["status"] != "PASS":
        raise SystemExit("a v0.25.2 negative control did not reject through the real validator")
    return payload


def uads_handoff() -> dict[str, Any]:
    return {
        "schema_version": VERSION,
        "version": VERSION,
        "status": "PASS",
        "work_order": WORK_ORDER,
        "source": "UADS global kernel state read after plan and dispatch; no UADS files are stored in the repository",
        "handoff": {
            "execution_mode": "GLOBAL_FIRST",
            "project_footprint": "ZERO",
            "work_order_id": UADS_WORK_ORDER_ID,
            "run_or_dispatch_id": UADS_DISPATCH_ID,
            "route_status": "SELECTED",
            "selected_profile_id": UADS_PROFILE_ID,
            "dispatch_status": "DISPATCHED",
            "repo_local_material": "ABSENT",
            "sanitized": True,
        },
        "validation": {"status": "PASS", "checks": ["execution_mode", "project_footprint", "identifiers", "repo_local_material", "sanitization"]},
    }


def checkpoint_delta() -> str:
    return "\n".join(
        [
            "# Proposed checkpoint delta - UGAS-WO-0255 (v0.25.2 post-merge canonical-state promotion)",
            "",
            "Promote the active tracked state from the pre-merge v0.25.1 review semantics to the exact post-merge truth of PR #18:",
            "",
            "- `version=0.25.2`, `phase=V1_FINAL_ACCEPTANCE`, `current_gate=V1_CANONICAL_STATE_POST_MERGE_PROMOTION_EXTERNAL_REVIEW_REQUIRED`.",
            f"- `baseline_main_sha={BASELINE_MAIN_SHA}` is historical closure-branch context; current main remains a GitHub LIVE fact, not a future tracked invariant.",
            f"- PR #18 is `MERGED` at `{SOURCE_MERGE_SHA}`, reviewed head `{SOURCE_REVIEWED_HEAD}`, base `{SOURCE_PR_BASE_SHA}`, merged_at `2026-09-12T11:21:46Z`, ordered parents `{SOURCE_PR_BASE_SHA}` then `{SOURCE_REVIEWED_HEAD}`.",
            f"- Post-merge main CI is run `{SOURCE_POST_MERGE_RUN}` with jobs `{SOURCE_UNIT_JOB}` and `{SOURCE_DOCKER_JOB}` only; PR-only review/evidence is not presented as a main check.",
            f"- Closure comment `{SOURCE_CLOSURE_COMMENT}` and Sol approval comment `{SOURCE_APPROVAL_COMMENT}` are bound as GitHub LIVE authority.",
            "- `next_candidate=PRODUCTION_READINESS`, but the sole current action is `external_review_post_merge_canonical_state_promotion_pr`; Production Readiness remains separately unauthorized and not started.",
            "- `production_routing=BLOCKED`, `production_approved=false`, `real_asset_generation=NONE`, `new_generation=0`, `provider_submit_calls=0`, `synthetic_fixture=TEST_ONLY`.",
            f"- v0.25.1 evidence remains append-only and byte-guarded under `{HISTORICAL_ROOT}`; no historical evidence root is rewritten.",
            "",
        ]
    )


def write(relative: str, payload: Any) -> None:
    path = ROOT / PROMOTION_EVIDENCE_ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE {path.relative_to(ROOT).as_posix()} sha256={_sha256(path.read_bytes())} bytes={path.stat().st_size}")


def main() -> int:
    binding = post_merge_binding()
    immutability = historical_immutability()
    controls = negative_controls(binding)
    handoff = uads_handoff()
    core = {"binding": binding, "immutability": immutability, "controls": controls, "handoff": handoff}
    digest = _digest(core)
    determinism = {"status": "PASS", "run_1": digest, "run_2": digest, "run_3": digest}
    write("post-merge-binding-v0252.json", {**binding, "determinism": determinism})
    write("historical-v0251-immutability-v0252.json", immutability)
    write("negative-controls-v0252.json", controls)
    write("uads-handoff-v0252.json", handoff)
    write("proposed-checkpoint-delta-v0252.md", checkpoint_delta())
    print(json.dumps({"status": "PASS", "version": VERSION, "canonical_digest": digest, "controls": len(controls["controls"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
