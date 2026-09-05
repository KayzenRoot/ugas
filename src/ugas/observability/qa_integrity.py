"""Cached, fail-closed validation of the active observability evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping

from ..schema_validation import validate_instance, validate_schema_document
from ..state_consistency_v0180 import validate_state_consistency

# The active state/review moved to v0.18.0. The v0.12.2 index remains the
# immutable baseline evidence used to bind the local observer.
ACTIVE_VERSION = "0.18.0"
ACTIVE_REVIEW = "REVIEW-v0.18.0.md"
ACTIVE_INDEX = "review-index-v0.12.2.json"
ACTIVE_EVIDENCE_DIR = "observability-v0122"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


TEXT_SUFFIXES = {".json", ".md", ".txt", ".py", ".toml", ".js", ".html", ".css"}


def _digest(path: Path) -> str:
    data = path.read_bytes()
    if path.name.casefold() == "license" or path.suffix.casefold() in TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_qa_semantics(tests: Mapping[str, Any], validation: Mapping[str, Any]) -> list[str]:
    """Return explicit QA-NC failures for malformed or contradictory counts."""
    failures: list[str] = []
    if not (tests.get("status") == "passed" and tests.get("failed") == 0 and tests.get("passed") == tests.get("count") and isinstance(tests.get("count"), int) and tests.get("count", 0) > 0):
        failures.append("tests_must_be_passed_failed_zero_passed_equals_count")
    if not (validation.get("status") == "passed" and validation.get("failed") == 0 and validation.get("passed") == validation.get("checks") and isinstance(validation.get("checks"), int) and validation.get("checks", 0) > 0):
        failures.append("validation_must_be_passed_failed_zero_passed_equals_checks")
    return failures


def _head(repo_root: Path) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, timeout=0.8, check=False, shell=False).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "UNKNOWN"


def validate_review_index(repo_root: Path, path: Path, *, schema_path: Path | None = None) -> dict[str, Any]:
    legacy = path.name == "review-index-v0.12.1.json"
    baseline_v0122 = path.name == "review-index-v0.12.2.json"
    version = "0.12.1" if legacy else ("0.12.2" if baseline_v0122 else ACTIVE_VERSION)
    evidence_dir = "observability-v0121" if legacy else ACTIVE_EVIDENCE_DIR
    default_schema = repo_root / "schemas" / ("review-index-v0.12.1.json" if legacy else "review-index-v0122.json")
    failures: list[str] = []
    try:
        value = _load(path)
        schema = _load(schema_path or default_schema)
        validate_schema_document(schema)
        validate_instance(value, schema)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return {"status": "GAP", "failures": [f"review-index:{type(exc).__name__}: {exc}"], "checked_at": _now(), "head": _head(repo_root)}
    if value.get("version") != version:
        failures.append("review-index-version-invalid")
    if value.get("production_routing") != "BLOCKED":
        failures.append("review-index-production-routing-invalid")
    external = value.get("external_visual_review", {})
    if external.get("attack_front_v2_approval") != "APPROVED_PILOT" or external.get("observability_dashboard_approval") != "REQUIRED":
        failures.append("review-index-external-review-boundary-invalid")
    if value.get("scope_boundary") != {"local_only": True, "read_only": True, "telemetry_upload": False, "new_generation": 0, "new_asset_family": False, "animation_pixels_changed": False, "comfyui_migrated": False}:
        failures.append("review-index-scope-boundary-invalid")
    artifacts = value.get("artifact_set", {}).get("artifacts", [])
    listed = {item.get("path") for item in artifacts}
    required_evidence = ("security-xss.json", "qa-negative-controls-v0121.json", "pipeline-live-stage-v0121.json", "orphan-reconciliation-v0121.json", "system-gpu-process-v0121.json", "stale-last-known-v0121.json", "file-activity-v0121.json", "preview-security-v0121.json", "external-review-v0112-binding-correction-v0121.json", "animation-regression-v0112-v0121.json", "test-results-v0121.json", "validation-results-v0121.json") if legacy else (
        "qa-cache-invalidation-v0122.json", "qa-negative-controls-v0122.json", "stale-last-known-integration-v0122.json",
        "generation-telemetry-contract-v0122.json", "docker-preflight-v0122.json", "docker-compose-config-v0122.json",
        "docker-build-v0122.json", "docker-runtime-v0122.json", "docker-gpu-v0122.json", "docker-cross-process-telemetry-v0122.json",
        "docker-file-watch-v0122.json", "docker-persistence-v0122.json", "docker-autostart-v0122.json", "docker-security-v0122.json",
        "test-results-v0122.json", "validation-results-v0122.json",
    )
    failures.extend(
        f"required-evidence-missing:{name}"
        for name in required_evidence
        if not (repo_root / "docs/evidence" / evidence_dir / name).is_file()
        or f"docs/evidence/{evidence_dir}/{name}" not in listed
    )
    screenshots = ("dashboard-overview.png", "dashboard-system-gpu-processes.png", "dashboard-live-pipeline-stage.png", "dashboard-qa-events.png", "dashboard-mobile.png") if legacy else ("dashboard-docker-overview-v0122.png", "dashboard-docker-live-activity-v0122.png")
    failures.extend(
        f"required-screenshot-missing:{name}"
        for name in screenshots
        if not (repo_root / "docs/evidence" / evidence_dir / name).is_file()
        or f"docs/evidence/{evidence_dir}/{name}" not in listed
    )
    if value.get("review_index") in listed:
        failures.append("review-index-self-referential")
    if value.get("artifact_set", {}).get("artifact_set_sha256") != hashlib.sha256(_canonical(artifacts).encode("utf-8")).hexdigest():
        failures.append("review-index-artifact-set-hash-invalid")
    for item in artifacts:
        relative = item.get("path", "")
        local = repo_root / relative
        if not relative or not local.is_file():
            failures.append(f"artifact-missing:{relative}")
        elif _digest(local) != item.get("sha256"):
            failures.append(f"artifact-hash-mismatch:{relative}")
    tests = value.get("tests", {})
    validation = value.get("validation", {})
    failures.extend(validate_qa_semantics(tests, validation))
    build_head = value.get("publication", {}).get("index_build_git_head")
    final_head = _head(repo_root)
    if build_head and final_head != "UNKNOWN":
        try:
            ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", build_head, final_head], cwd=repo_root, timeout=0.8, check=False, shell=False)
            if ancestor.returncode != 0:
                failures.append("review-index-build-head-not-ancestor")
        except (OSError, subprocess.TimeoutExpired):
            failures.append("review-index-ancestor-check-unavailable")
    return {"status": "PASS" if not failures else "GAP", "failures": failures, "checked_at": _now(), "head": final_head, "index_build_head": build_head, "artifact_count": len(artifacts), "visual_count": value.get("artifact_set", {}).get("visual_count")}


class ActiveEvidenceCache:
    """Cache canonical validation only for the same repository observation."""

    # Docker Desktop's Windows bind mount can make Git's complete worktree
    # walk take several seconds.  The old 1.5s limit incorrectly converted a
    # healthy repository into GIT_STATUS_UNAVAILABLE and kept the live panel
    # in a false fail-closed state.  This remains bounded and runs only on the
    # collector path; HTTP/SSE handlers read the latest completed result.
    _GIT_COMMAND_TIMEOUT_SECONDS = 20.0

    def __init__(self, repo_root: Path, *, state_path: Path | None = None, state_schema_path: Path | None = None,
                 checkpoint_path: Path | None = None, review_path: Path | None = None,
                 review_index_path: Path | None = None, review_index_schema_path: Path | None = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.state_path = state_path or self.repo_root / "docs/evidence/current-state.json"
        self.state_schema_path = state_schema_path or self.repo_root / "schemas/current-state-v0180.json"
        self.checkpoint_path = checkpoint_path or self.repo_root / "CHECKPOINT.md"
        self.review_path = review_path or self.repo_root / ACTIVE_REVIEW
        self.roadmap_path = self.repo_root / "docs/roadmap.md"
        self.review_index_path = review_index_path or self.repo_root / "docs/evidence" / ACTIVE_INDEX
        self._default_review_index = review_index_path is None
        self.review_index_schema_path = review_index_schema_path or self.repo_root / "schemas/review-index-v0122.json"
        self._fingerprint: tuple[tuple[str, str], ...] | None = None
        self._value: dict[str, Any] | None = None
        self._repository_observation: dict[str, Any] | None = None
        self._generation = 0

    def _files(self) -> tuple[Path, ...]:
        return (self.state_path, self.state_schema_path, self.checkpoint_path, self.review_path, self.roadmap_path, self.review_index_path, self.review_index_schema_path)

    def _git(self, args: list[str]) -> tuple[bool, str]:
        try:
            command = ["git"]
            # The repository is a Windows worktree exposed to a Linux
            # container. Normalize CRLF before asking Git for porcelain status
            # so line-ending filters do not become a false dirty-worktree gap.
            if os.environ.get("UGAS_CONTAINERIZED") == "1":
                command.extend(["-c", "core.autocrlf=true"])
            command.extend(args)
            result = subprocess.run(command, cwd=self.repo_root, capture_output=True, text=True, timeout=self._GIT_COMMAND_TIMEOUT_SECONDS, check=False, shell=False)
            return result.returncode == 0, result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return False, ""

    def _repository_state(self) -> dict[str, Any]:
        head_ok, head = self._git(["rev-parse", "HEAD"])
        status_ok, status = self._git(["status", "--porcelain=v1", "--untracked-files=all"])
        try:
            index = _load(self.review_index_path)
            artifact_set = str(index.get("artifact_set", {}).get("artifact_set_sha256") or "UNKNOWN")
            indexed_head = str(index.get("publication", {}).get("index_build_git_head") or "UNKNOWN")
        except (OSError, json.JSONDecodeError, TypeError, AttributeError):
            artifact_set, indexed_head = "UNKNOWN", "UNKNOWN"
        return {
            "current_head": head if head_ok and head else "UNKNOWN",
            "worktree_status": status if status_ok else "GIT_STATUS_UNAVAILABLE",
            "worktree_clean": bool(status_ok and not status),
            "git_status_available": status_ok,
            "artifact_set_sha256": artifact_set,
            "index_build_head": indexed_head,
        }

    def _key(self) -> tuple[tuple[str, str], ...]:
        repository = self._repository_state()
        self._repository_observation = repository
        values: list[tuple[str, str]] = [
            ("git_head", repository["current_head"]),
            ("worktree_status", hashlib.sha256(repository["worktree_status"].encode("utf-8", "replace")).hexdigest()),
            ("artifact_set_sha256", repository["artifact_set_sha256"]),
            ("index_build_head", repository["index_build_head"]),
        ]
        for path in self._files():
            try:
                stat = path.stat()
                values.append((str(path), f"{stat.st_mtime_ns}:{stat.st_size}"))
            except OSError:
                values.append((str(path), "0:0"))
        return tuple(values)

    def validate(self) -> dict[str, Any]:
        fingerprint = self._key()
        if fingerprint == self._fingerprint and self._value is not None:
            return self._value
        repository = self._repository_observation or self._repository_state()
        failures: list[str] = []
        state: dict[str, Any] | None = None
        try:
            state = _load(self.state_path)
            schema = _load(self.state_schema_path)
            validate_schema_document(schema)
            validate_instance(state, schema)
            consistency = validate_state_consistency(
                state,
                self.checkpoint_path.read_text(encoding="utf-8"),
                self.review_path.read_text(encoding="utf-8"),
                self.roadmap_path.read_text(encoding="utf-8"),
            )
            if consistency.get("failures"):
                failures.extend(f"state:{item}" for item in consistency["failures"])
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            failures.append(f"state:{type(exc).__name__}: {exc}")
        index_result = validate_review_index(self.repo_root, self.review_index_path, schema_path=self.review_index_schema_path)
        failures.extend(f"index:{item}" for item in index_result.get("failures", []))
        if not repository["git_status_available"]:
            failures.append("repository:GIT_STATUS_UNAVAILABLE")
        elif not repository["worktree_clean"]:
            failures.append("repository:WORKTREE_DIRTY_UNBOUND")
        tests: dict[str, Any] = {}
        validation: dict[str, Any] = {}
        try:
            index = _load(self.review_index_path)
            tests = index.get("tests", {})
            validation = index.get("validation", {})
        except (OSError, json.JSONDecodeError):
            pass
        if state and state.get("production_approved") is not False:
            failures.append("governance:production_approved_must_remain_false")
        if state and state.get("production_routing") != "BLOCKED":
            failures.append("governance:production_routing_must_remain_blocked")
        self._generation += 1
        fingerprint_sha256 = hashlib.sha256(_canonical(fingerprint).encode("utf-8")).hexdigest()
        state_failure = any(item.startswith("state:") for item in failures)
        # A present but tampered/invalid index is the direct NC05 cause and
        # must remain visible even when the surrounding worktree is dirty.
        # A missing index, by contrast, is still reported as a dirty-worktree
        # gap during the pre-index bootstrap phase.
        index_failure = index_result.get("status") != "PASS" and self.review_index_path.is_file()
        # A dirty active worktree is itself the binding gap. Preserve that
        # canonical reason for the live cache; custom fixture paths (notably
        # QA-NC-05) still surface the direct tampered-index reason.
        index_reason = index_failure and (not self._default_review_index or repository["worktree_clean"])
        reason = "STATE_EVIDENCE_INVALID" if state_failure else ("REVIEW_INDEX_INVALID" if index_reason else ("GIT_STATUS_UNAVAILABLE" if not repository["git_status_available"] else ("WORKTREE_DIRTY_UNBOUND" if not repository["worktree_clean"] else ("GOVERNANCE_GAP" if failures else None))))
        result = {
            "status": "PASS" if not failures and index_result.get("status") == "PASS" else "GAP",
            "checked_at": _now(),
            "cache_checked_at": _now(),
            "cache_generation": self._generation,
            "cache_fingerprint": fingerprint_sha256,
            "stale": bool(failures),
            "reason": reason,
            "current_head": repository["current_head"],
            "validated_head": repository["current_head"],
            "worktree_clean": repository["worktree_clean"],
            "git_status_available": repository["git_status_available"],
            "worktree_status": repository["worktree_status"],
            "index_build_head": repository["index_build_head"],
            "artifact_set_sha256": repository["artifact_set_sha256"],
            "failures": failures,
            "current_state": {"version": state.get("version"), "gate": state.get("current_gate"), "production_routing": state.get("production_routing"), "production_approved": state.get("production_approved"), "external_visual_review": state.get("external_visual_review")} if state else None,
            "tests": tests,
            "validation": validation,
            "review_index": index_result,
        }
        self._fingerprint = fingerprint
        self._value = result
        return result
