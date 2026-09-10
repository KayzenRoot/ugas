"""Fail-closed, provider-neutral orchestration runtime for UGAS v0.24.1.

Forward-only correction of the v0.24.0 TEST_ONLY control plane.  This module
has no import edge to a provider client or to the legacy generation path.
"""

from __future__ import annotations

import copy
import ast
import hashlib
import inspect
import json
import ntpath
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

VERSION = "0.24.1"
SCHEMA_VERSION = VERSION
TEST_ONLY_MARKER = "TEST_ONLY"
SUPPORTED_ASSET_FAMILIES = (
    "equipment_outfits", "creatures_monsters", "items_props", "environment_tilesets",
    "maps_minimap", "ui_asset_family", "vfx_asset_family",
)
MAX_NODES = 64
MAX_DEPTH = 16
MAX_FANOUT = 16
MAX_RETRIES = 3
MAX_TIMEOUT_SECONDS = 3600
MAX_TELEMETRY_FIELDS = 24
MAX_TELEMETRY_STRING = 160

REQUEST_FIELDS = {
    "schema_version", "request_id", "project_id", "request_kind", "asset_family",
    "operation", "inputs", "dependency_refs", "outputs", "quality_profile",
    "budget_profile", "priority", "timeout_seconds", "retry_policy",
    "idempotency_key", "production_intent", "test_only", "request_hash",
}
REQUEST_REQUIRED = REQUEST_FIELDS - {"request_hash"}
DAG_FIELDS = {"schema_version", "dag_id", "project_id", "request_hash", "nodes", "dag_hash"}
NODE_FIELDS = {
    "node_id", "dependencies", "operation", "input_contract_hash", "dependency_hashes",
    "timeout_seconds", "retry_policy", "resource_class", "scheduling_key", "priority",
    "asset_family",
}
DEPENDENCY_REF_FIELDS = {
    "project_id", "family", "revision", "path", "authority_id", "content_hash",
    "semantic_hash", "read_only", "status", "approved_commit",
}
DEPENDENCY_REF_REQUIRED = {"project_id", "family", "revision", "path", "content_hash", "semantic_hash", "read_only"}


class OrchestrationContractError(RuntimeError):
    """A stable, fail-closed contract rejection."""

    def __init__(self, rejection_class: str, detail: str):
        self.rejection_class = rejection_class
        self.detail = detail
        super().__init__(f"{rejection_class}: {detail}")


class RetryableExecutionError(RuntimeError):
    error_class = "TRANSIENT_EXECUTION_ERROR"


class NonRetryableExecutionError(RuntimeError):
    error_class = "EXECUTION_CONTRACT_ERROR"


class NodeDeadlineExceeded(RetryableExecutionError):
    error_class = "NODE_DEADLINE_EXCEEDED"


class RequestDeadlineExceeded(RetryableExecutionError):
    error_class = "REQUEST_DEADLINE_EXCEEDED"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_value(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def _reject(rejection_class: str, detail: str) -> None:
    raise OrchestrationContractError(rejection_class, detail)


def strict_boolean_observation(observed: Any) -> bool:
    return type(observed) is bool and observed is True


def strict_gate(gate_id: str, observed: Any, detail: str = "", proof_source: str | None = None) -> dict[str, Any]:
    passed = strict_boolean_observation(observed)
    result = {"gate_id": gate_id, "observed": observed, "observed_type": type(observed).__name__, "status": "PASS" if passed else "FAIL", "detail": detail}
    if proof_source is not None:
        result["proof_source"] = proof_source
    return result


def _assert_no_unknown(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        _reject("ORCH_UNKNOWN_FIELD", f"{label} contains unknown fields: {unknown}")


def _assert_sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        _reject("ORCH_HASH_INVALID", f"{label} must be a lowercase SHA-256 hex digest")


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _validate_no_secret_like(value: Any) -> None:
    secret_words = ("token", "api_key", "apikey", "password", "authorization", "secret", "credential", "private_key")
    if any(any(word in key.casefold() for word in secret_words) for key in _walk_keys(value)):
        _reject("ORCH_SECRET_LIKE_DATA_REJECTED", "secret-like fields are not allowed in orchestration evidence")


def validate_safe_relative_path(value: str, *, root: Path | None = None) -> str:
    if not isinstance(value, str) or not value or ntpath.isabs(value) or value.startswith("/"):
        _reject("ORCH_ABSOLUTE_PATH_REJECTED", "absolute paths are forbidden")
    parts = Path(value.replace("\\", "/")).parts
    if ".." in parts:
        _reject("ORCH_PATH_TRAVERSAL_REJECTED", "path traversal is forbidden")
    if root is not None:
        candidate = (root / Path(*parts)).resolve()
        root_resolved = root.resolve()
        if candidate != root_resolved and root_resolved not in candidate.parents:
            _reject("ORCH_PATH_TRAVERSAL_REJECTED", "resolved path escapes root")
    return "/".join(parts)


def validate_dependency_ref(reference: Mapping[str, Any], *, expected_project_id: str | None = None) -> dict[str, Any]:
    if not isinstance(reference, Mapping):
        _reject("ORCH_DEPENDENCY_REF_INVALID", "dependency_ref must be an object")
    value = copy.deepcopy(dict(reference))
    _assert_no_unknown(value, DEPENDENCY_REF_FIELDS, "dependency_ref")
    missing = sorted(DEPENDENCY_REF_REQUIRED - set(value))
    if missing:
        _reject("ORCH_DEPENDENCY_REF_REQUIRED_FIELD_MISSING", f"dependency_ref is missing {missing}")
    if expected_project_id is not None and value.get("project_id") != expected_project_id:
        _reject("ORCH_CROSS_PROJECT_IDENTITY", "dependency reference crosses project identity")
    if not isinstance(value.get("project_id"), str) or not value["project_id"].strip():
        _reject("ORCH_DEPENDENCY_REF_INVALID", "dependency_ref.project_id is required")
    if value.get("family") not in SUPPORTED_ASSET_FAMILIES:
        _reject("ORCH_DEPENDENCY_REF_FAMILY_INVALID", "dependency_ref.family is not supported")
    if not isinstance(value.get("revision"), str) or not value["revision"].strip():
        _reject("ORCH_DEPENDENCY_REF_REVISION_INVALID", "dependency_ref.revision is required")
    validate_safe_relative_path(value.get("path", ""))
    _assert_sha(value.get("content_hash"), "dependency_ref.content_hash")
    _assert_sha(value.get("semantic_hash"), "dependency_ref.semantic_hash")
    if type(value.get("read_only")) is not bool or value["read_only"] is not True:
        _reject("ORCH_DEPENDENCY_REF_READ_ONLY_REQUIRED", "dependency_ref.read_only must be literal true")
    if "status" in value and value["status"] not in {"APPROVED", "APPROVED_FOUNDATION", "MERGED_CLOSED"}:
        _reject("ORCH_DEPENDENCY_REF_STATUS_REJECTED", "dependency authority is not approved")
    if "approved_commit" in value:
        _assert_sha(value["approved_commit"], "dependency_ref.approved_commit")
    return value


def _validate_project_identity(request: Mapping[str, Any], expected_project_id: str | None = None) -> None:
    project_id = request.get("project_id")
    if not isinstance(project_id, str) or not project_id or project_id.strip() != project_id:
        _reject("ORCH_PROJECT_ID_INVALID", "project_id must be a non-empty canonical string")
    if expected_project_id is not None and project_id != expected_project_id:
        _reject("ORCH_CROSS_PROJECT_IDENTITY", "request project identity does not match execution project")
    for reference in request.get("dependency_refs", []):
        validate_dependency_ref(reference, expected_project_id=project_id)


def validate_request(request: Mapping[str, Any], expected_project_id: str | None = None) -> dict[str, Any]:
    if not isinstance(request, Mapping):
        _reject("ORCH_REQUEST_INVALID", "request must be an object")
    value = copy.deepcopy(dict(request))
    _assert_no_unknown(value, REQUEST_FIELDS, "request")
    missing = sorted(REQUEST_REQUIRED - set(value))
    if missing:
        _reject("ORCH_REQUEST_REQUIRED_FIELD_MISSING", f"request is missing {missing}")
    if value.get("schema_version") != SCHEMA_VERSION:
        _reject("ORCH_REQUEST_SCHEMA_UNSUPPORTED", "unsupported request schema")
    if value.get("request_kind") != "ASSET_OPERATION":
        _reject("ORCH_REQUEST_KIND_INVALID", "only ASSET_OPERATION is supported")
    if value.get("asset_family") not in SUPPORTED_ASSET_FAMILIES:
        _reject("ORCH_UNKNOWN_ASSET_FAMILY", "asset family is not in the closed runtime registry")
    if value.get("operation") not in {"VALIDATE", "EXECUTE", "RESUME"}:
        _reject("ORCH_OPERATION_INVALID", "unsupported orchestration operation")
    for key in ("request_id", "idempotency_key"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            _reject("ORCH_REQUEST_ID_INVALID" if key == "request_id" else "ORCH_IDEMPOTENCY_KEY_INVALID", f"{key} is required")
    if not isinstance(value.get("inputs"), Mapping) or not isinstance(value.get("outputs"), Mapping):
        _reject("ORCH_IO_CONTRACT_INVALID", "inputs and outputs must be objects")
    if not isinstance(value.get("dependency_refs"), list):
        _reject("ORCH_DEPENDENCY_REFS_INVALID", "dependency_refs must be a list")
    if type(value.get("production_intent")) is not bool or value["production_intent"] is not False:
        _reject("ORCH_PRODUCTION_INTENT_REJECTED", "production_intent must be literal false")
    if type(value.get("test_only")) is not bool or value["test_only"] is not True:
        _reject("ORCH_TEST_ONLY_MARKER_REQUIRED", "test_only must be literal true")
    if not isinstance(value.get("priority"), int) or isinstance(value["priority"], bool) or not 0 <= value["priority"] <= 100:
        _reject("ORCH_PRIORITY_INVALID", "priority must be an integer from 0 through 100")
    if not isinstance(value.get("timeout_seconds"), int) or isinstance(value["timeout_seconds"], bool) or not 1 <= value["timeout_seconds"] <= MAX_TIMEOUT_SECONDS:
        _reject("ORCH_TIMEOUT_INVALID", "timeout_seconds must be bounded")
    retry = value.get("retry_policy")
    if not isinstance(retry, Mapping) or set(retry) - {"max_attempts", "retryable_errors"}:
        _reject("ORCH_RETRY_POLICY_INVALID", "retry_policy schema is invalid")
    if not isinstance(retry.get("max_attempts"), int) or isinstance(retry["max_attempts"], bool) or not 1 <= retry["max_attempts"] <= MAX_RETRIES:
        _reject("ORCH_RETRY_POLICY_INVALID", "retry_policy.max_attempts exceeds bounded limit")
    if not isinstance(retry.get("retryable_errors"), list) or not all(isinstance(item, str) for item in retry["retryable_errors"]):
        _reject("ORCH_RETRY_POLICY_INVALID", "retryable_errors must be a string list")
    _validate_project_identity(value, expected_project_id)
    _validate_no_secret_like(value)
    supplied_hash = value.pop("request_hash", None)
    computed_hash = sha256_value(value)
    if supplied_hash is not None and supplied_hash != computed_hash:
        _reject("ORCH_REQUEST_HASH_MISMATCH", "request hash does not match canonical request bytes")
    value["request_hash"] = computed_hash
    return value


def build_request(**kwargs: Any) -> dict[str, Any]:
    return validate_request({"schema_version": SCHEMA_VERSION, **kwargs})


def _node_contract_payload(node: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(node[key]) for key in NODE_FIELDS if key != "dependency_hashes" and key in node}


def node_contract_hash(node: Mapping[str, Any]) -> str:
    return sha256_value(_node_contract_payload(node))


def _validate_node(node: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(node, Mapping):
        _reject("ORCH_DAG_NODE_INVALID", "DAG node must be an object")
    value = copy.deepcopy(dict(node))
    _assert_no_unknown(value, NODE_FIELDS, "DAG node")
    missing = sorted(NODE_FIELDS - set(value))
    if missing:
        _reject("ORCH_DAG_NODE_REQUIRED_FIELD_MISSING", f"DAG node is missing {missing}")
    if not isinstance(value["node_id"], str) or not value["node_id"].strip():
        _reject("ORCH_DAG_NODE_ID_INVALID", "node_id is required")
    if not isinstance(value["dependencies"], list) or not all(isinstance(item, str) for item in value["dependencies"]):
        _reject("ORCH_DAG_DEPENDENCY_INVALID", "dependencies must be a string list")
    if len(value["dependencies"]) != len(set(value["dependencies"])):
        _reject("ORCH_DAG_DUPLICATE_DEPENDENCY", "node dependencies must be unique")
    if not isinstance(value["dependency_hashes"], Mapping) or set(value["dependency_hashes"]) != set(value["dependencies"]):
        _reject("ORCH_DAG_DEPENDENCY_HASHES_INVALID", "dependency hash keys must equal dependencies")
    _assert_sha(value["input_contract_hash"], "input_contract_hash")
    for dependency_hash in value["dependency_hashes"].values():
        _assert_sha(dependency_hash, "dependency_hash")
    if not isinstance(value["timeout_seconds"], int) or isinstance(value["timeout_seconds"], bool) or not 1 <= value["timeout_seconds"] <= MAX_TIMEOUT_SECONDS:
        _reject("ORCH_DAG_TIMEOUT_INVALID", "node timeout is not bounded")
    retry = value["retry_policy"]
    if not isinstance(retry, Mapping) or set(retry) - {"max_attempts", "retryable_errors"} or not isinstance(retry.get("retryable_errors"), list):
        _reject("ORCH_DAG_RETRY_POLICY_INVALID", "node retry policy is invalid")
    if not isinstance(retry.get("max_attempts"), int) or isinstance(retry["max_attempts"], bool) or not 1 <= retry["max_attempts"] <= MAX_RETRIES:
        _reject("ORCH_DAG_RETRY_POLICY_INVALID", "node retry count is unbounded")
    if "EXECUTION_CONTRACT_ERROR" in retry["retryable_errors"]:
        _reject("ORCH_NONRETRYABLE_ERROR_POLICY_REJECTED", "contract errors may not be retried")
    if not isinstance(value["resource_class"], str) or not value["resource_class"]:
        _reject("ORCH_DAG_RESOURCE_CLASS_INVALID", "resource_class is required")
    if not isinstance(value["scheduling_key"], str) or not value["scheduling_key"]:
        _reject("ORCH_DAG_SCHEDULING_KEY_INVALID", "scheduling_key is required")
    if not isinstance(value["priority"], int) or isinstance(value["priority"], bool) or not 0 <= value["priority"] <= 100:
        _reject("ORCH_DAG_PRIORITY_INVALID", "node priority is not bounded")
    if value["asset_family"] not in SUPPORTED_ASSET_FAMILIES:
        _reject("ORCH_UNKNOWN_ASSET_FAMILY", "node asset family is not supported")
    return value


def _depths(nodes: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    memo: dict[str, int] = {}
    visiting: set[str] = set()

    def depth(node_id: str) -> int:
        if node_id in memo:
            return memo[node_id]
        if node_id in visiting:
            _reject("ORCH_DAG_CYCLE", "DAG contains a cycle")
        visiting.add(node_id)
        memo[node_id] = 1 + max((depth(parent) for parent in nodes[node_id]["dependencies"]), default=0)
        visiting.remove(node_id)
        return memo[node_id]

    for node_id in nodes:
        depth(node_id)
    return memo


def validate_dag(dag: Mapping[str, Any], request: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(dag, Mapping):
        _reject("ORCH_DAG_INVALID", "DAG must be an object")
    value = copy.deepcopy(dict(dag))
    _assert_no_unknown(value, DAG_FIELDS, "DAG")
    if value.get("schema_version") != SCHEMA_VERSION:
        _reject("ORCH_DAG_SCHEMA_UNSUPPORTED", "unsupported DAG schema")
    raw_nodes = value.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes or len(raw_nodes) > MAX_NODES:
        _reject("ORCH_DAG_BOUNDS_EXCEEDED", "DAG node count is outside bounded range")
    nodes = [_validate_node(item) for item in raw_nodes]
    by_id = {item["node_id"]: item for item in nodes}
    if len(by_id) != len(nodes):
        _reject("ORCH_DAG_DUPLICATE_NODE_ID", "node identifiers must be unique")
    if request is not None:
        validated_request = validate_request(request)
        if value.get("project_id") != validated_request["project_id"]:
            _reject("ORCH_CROSS_PROJECT_IDENTITY", "DAG project does not match request project")
        if value.get("request_hash") != validated_request["request_hash"]:
            _reject("ORCH_DAG_REQUEST_HASH_MISMATCH", "DAG is not bound to request")
    for item in nodes:
        if item["node_id"] in item["dependencies"]:
            _reject("ORCH_DAG_SELF_DEPENDENCY", "node cannot depend on itself")
        for dependency in item["dependencies"]:
            if dependency not in by_id:
                _reject("ORCH_DAG_MISSING_DEPENDENCY", f"unknown dependency {dependency}")
            if item["dependency_hashes"].get(dependency) != node_contract_hash(by_id[dependency]):
                _reject("ORCH_DAG_STALE_DEPENDENCY_HASH", f"dependency hash is stale for {dependency}")
    depths = _depths(by_id)
    if max(depths.values()) > MAX_DEPTH:
        _reject("ORCH_DAG_DEPTH_EXCEEDED", "DAG depth exceeds bounded limit")
    fanout = {node_id: 0 for node_id in by_id}
    for item in nodes:
        for dependency in item["dependencies"]:
            fanout[dependency] += 1
    if max(fanout.values(), default=0) > MAX_FANOUT:
        _reject("ORCH_DAG_FANOUT_EXCEEDED", "DAG fanout exceeds bounded limit")
    value["nodes"] = nodes
    supplied_hash = value.pop("dag_hash", None)
    computed_hash = sha256_value(value)
    if supplied_hash is not None and supplied_hash != computed_hash:
        _reject("ORCH_DAG_HASH_MISMATCH", "DAG hash does not match canonical DAG bytes")
    value["dag_hash"] = computed_hash
    return value


def build_dag(request: Mapping[str, Any], nodes: list[Mapping[str, Any]], dag_id: str = "dag-1") -> dict[str, Any]:
    validated_request = validate_request(request)
    if not isinstance(nodes, list) or not nodes or len(nodes) > MAX_NODES:
        _reject("ORCH_DAG_BOUNDS_EXCEEDED", "DAG node count is outside bounded range")
    prepared = [copy.deepcopy(dict(raw)) for raw in nodes]
    for item in prepared:
        item.setdefault("dependency_hashes", {})
    by_id = {item.get("node_id"): item for item in prepared}
    if len(by_id) != len(prepared):
        _reject("ORCH_DAG_DUPLICATE_NODE_ID", "node identifiers must be unique")
    for item in prepared:
        for dependency in item["dependencies"]:
            if dependency not in by_id:
                _reject("ORCH_DAG_MISSING_DEPENDENCY", f"unknown dependency {dependency}")
            item["dependency_hashes"][dependency] = node_contract_hash(by_id[dependency])
        _validate_node(item)
    return validate_dag({"schema_version": SCHEMA_VERSION, "dag_id": dag_id, "project_id": validated_request["project_id"], "request_hash": validated_request["request_hash"], "nodes": prepared}, validated_request)


def deterministic_schedule(dag: Mapping[str, Any]) -> list[str]:
    value = validate_dag(dag)
    nodes = {item["node_id"]: item for item in value["nodes"]}
    remaining = {node_id: set(item["dependencies"]) for node_id, item in nodes.items()}
    schedule: list[str] = []
    while remaining:
        ready = sorted((node_id for node_id, deps in remaining.items() if not deps), key=lambda node_id: (-nodes[node_id]["priority"], node_id))
        if not ready:
            _reject("ORCH_DAG_CYCLE", "DAG could not produce dependency-first schedule")
        for node_id in ready:
            schedule.append(node_id)
            remaining.pop(node_id)
            for deps in remaining.values():
                deps.discard(node_id)
    return schedule


ALLOWED_TRANSITIONS = {
    "PLANNED": {"VALIDATED", "CANCELLED", "BLOCKED"},
    "VALIDATED": {"READY", "CANCELLED", "BLOCKED"},
    "READY": {"DISPATCHED", "CANCELLED", "BLOCKED"},
    "DISPATCHED": {"RUNNING", "CANCELLED", "FAILED", "BLOCKED"},
    "RUNNING": {"SUCCEEDED", "FAILED", "CANCELLED", "BLOCKED"},
    "SUCCEEDED": set(), "FAILED": set(), "CANCELLED": set(), "BLOCKED": set(),
}
TERMINAL_STATES = {"SUCCEEDED", "FAILED", "CANCELLED", "BLOCKED"}


def _event_hash(previous: str, event: Mapping[str, Any]) -> str:
    return sha256_value({"previous_event_hash": previous, "event": event})


@dataclass
class DeterministicClock:
    """Monotonic fake clock used by every deadline proof."""

    elapsed_seconds: float = 0.0

    def now(self) -> float:
        return float(self.elapsed_seconds)

    def advance(self, seconds: float) -> float:
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds < 0:
            _reject("ORCH_CLOCK_ADVANCE_INVALID", "clock advance must be a non-negative number")
        self.elapsed_seconds = round(self.elapsed_seconds + float(seconds), 9)
        return self.now()


FakeClock = DeterministicClock


@dataclass
class FakeExecutor:
    """A deterministic executor whose elapsed input is explicit and bounded."""

    durations: Mapping[str, float | list[float]] = field(default_factory=dict)
    elapsed_by_node: Mapping[str, float | list[float]] | None = None
    executions: int = 0
    provider_submit_calls: int = 0
    calls_by_node: dict[str, int] = field(default_factory=dict)

    def duration_for(self, node_id: str, attempt: int) -> float:
        source = self.elapsed_by_node if self.elapsed_by_node is not None else self.durations
        value: Any = source.get(node_id, 0.0)
        if isinstance(value, list):
            value = value[min(max(0, attempt - 1), len(value) - 1)] if value else 0.0
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            _reject("ORCH_FAKE_ELAPSED_INVALID", f"invalid fake elapsed duration for {node_id}")
        return float(value)

    def execute(self, request: Mapping[str, Any], node: Mapping[str, Any], *, attempt: int = 1) -> dict[str, Any]:
        self.executions += 1
        self.calls_by_node[node["node_id"]] = self.calls_by_node.get(node["node_id"], 0) + 1
        result_hash = sha256_value({"request_hash": request["request_hash"], "node_id": node["node_id"], "input_contract_hash": node["input_contract_hash"]})
        return {"status": "SUCCEEDED", "execution_id": f"fake-{result_hash[:16]}", "result_hash": result_hash, "provider": None, "synthetic": True, "test_only": True, "attempt": attempt}


@dataclass
class CircuitBreaker:
    failure_threshold: int = 2
    state: str = "CLOSED"
    failures: int = 0
    _probe_in_flight: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.failure_threshold, int) or isinstance(self.failure_threshold, bool) or self.failure_threshold < 1:
            _reject("ORCH_CIRCUIT_THRESHOLD_INVALID", "failure threshold must be positive")

    def allow(self) -> bool:
        if self.state == "OPEN":
            return False
        if self.state == "HALF_OPEN":
            if self._probe_in_flight:
                return False
            self._probe_in_flight = True
        return True

    def record_failure(self, *, retryable: bool = True) -> None:
        if not retryable:
            return
        if self.state == "HALF_OPEN":
            self._probe_in_flight = False
            self.state = "OPEN"
            self.failures = self.failure_threshold
            return
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.state = "OPEN"

    def half_open(self) -> None:
        if self.state == "OPEN":
            self.state = "HALF_OPEN"
            self._probe_in_flight = False

    def record_success(self) -> None:
        self.failures = 0
        self.state = "CLOSED"
        self._probe_in_flight = False


class CircuitRegistry:
    def __init__(self) -> None:
        self._breakers: dict[tuple[str, str, str, str], CircuitBreaker] = {}

    def for_identity(self, project_id: str, request_id: str, dag_hash: str = "", execution_policy_identity: str = "") -> CircuitBreaker:
        key = (project_id, request_id, dag_hash, execution_policy_identity)
        return self._breakers.setdefault(key, CircuitBreaker())


def validate_circuit_access(breaker: CircuitBreaker, attempted: Any) -> None:
    if breaker.state == "OPEN" and attempted is True:
        _reject("ORCH_CIRCUIT_BREAKER_BYPASS", "open circuit accepted a dispatch")
    if breaker.state == "HALF_OPEN" and attempted is True and breaker._probe_in_flight is False:
        _reject("ORCH_CIRCUIT_HALF_OPEN_PROBE_INVALID", "half-open probe was not admitted through breaker")


def validate_concurrency_limits(global_limit: Any, family_limits: Mapping[str, Any] | None = None) -> dict[str, int]:
    if not isinstance(global_limit, int) or isinstance(global_limit, bool) or not 1 <= global_limit <= MAX_NODES:
        _reject("ORCH_CONCURRENCY_BOUND_INVALID", "global concurrency must be an integer from 1 through MAX_NODES")
    normalized: dict[str, int] = {}
    for family, limit in (family_limits or {}).items():
        if family not in SUPPORTED_ASSET_FAMILIES:
            _reject("ORCH_FAMILY_UNKNOWN", f"unknown family limit {family}")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= global_limit:
            _reject("ORCH_FAMILY_LIMIT_INVALID", f"family limit for {family} must be between 1 and global limit")
        normalized[family] = limit
    return normalized


class DeterministicBatchScheduler:
    """Admission-only scheduler proving independent parallel capacity."""

    def __init__(self, dag: Mapping[str, Any], global_limit: int, family_limits: Mapping[str, int] | None = None):
        self.dag = validate_dag(dag)
        self.global_limit = global_limit
        self.family_limits = validate_concurrency_limits(global_limit, family_limits)
        self.nodes = {item["node_id"]: item for item in self.dag["nodes"]}

    def plan(self) -> dict[str, Any]:
        remaining = set(self.nodes)
        completed: set[str] = set()
        batches: list[list[str]] = []
        family_peaks: dict[str, int] = {}
        while remaining:
            ready = sorted((node_id for node_id in remaining if set(self.nodes[node_id]["dependencies"]).issubset(completed)), key=lambda node_id: (-self.nodes[node_id]["priority"], node_id))
            if not ready:
                _reject("ORCH_DAG_CYCLE", "scheduler cannot admit remaining nodes")
            batch: list[str] = []
            family_counts: dict[str, int] = {}
            for node_id in ready:
                family = self.nodes[node_id]["asset_family"]
                family_limit = self.family_limits.get(family, self.global_limit)
                if len(batch) >= self.global_limit or family_counts.get(family, 0) >= family_limit:
                    continue
                batch.append(node_id)
                family_counts[family] = family_counts.get(family, 0) + 1
            if not batch:
                _reject("ORCH_FAMILY_CONCURRENCY_EXCEEDED", "no ready node fits configured family limit")
            batches.append(batch)
            completed.update(batch)
            remaining.difference_update(batch)
            for family, count in family_counts.items():
                family_peaks[family] = max(family_peaks.get(family, 0), count)
        return {"batches": batches, "peak_global": max((len(batch) for batch in batches), default=0), "family_peaks": family_peaks, "dispatch_count": sum(len(batch) for batch in batches), "schedule_hash": sha256_value(batches)}


DeterministicAdmissionScheduler = DeterministicBatchScheduler


def validate_concurrency_observation(peak: Any, global_limit: int, family_limits: Mapping[str, int] | None = None, family_peaks: Mapping[str, Any] | None = None) -> None:
    validate_concurrency_limits(global_limit, family_limits)
    if not isinstance(peak, int) or isinstance(peak, bool) or peak < 0 or peak > global_limit:
        _reject("ORCH_GLOBAL_CONCURRENCY_EXCEEDED", "observed global peak exceeds concurrency limit")
    for family, family_peak in (family_peaks or {}).items():
        limit = (family_limits or {}).get(family, global_limit)
        if not isinstance(family_peak, int) or isinstance(family_peak, bool) or family_peak < 0 or family_peak > limit:
            _reject("ORCH_FAMILY_CONCURRENCY_EXCEEDED", f"observed peak exceeds family bound for {family}")


@dataclass
class OrchestrationRuntime:
    request: dict[str, Any]
    dag: dict[str, Any]
    max_concurrency: int = 4
    family_limits: dict[str, int] = field(default_factory=dict)
    executor: FakeExecutor = field(default_factory=FakeExecutor)
    clock: DeterministicClock = field(default_factory=DeterministicClock)
    execution_policy: Mapping[str, Any] = field(default_factory=dict)
    authority_binding_hash: str | None = None
    circuit_registry: CircuitRegistry | None = None
    states: dict[str, str] = field(init=False)
    results: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    attempts: dict[str, int] = field(default_factory=dict, init=False)
    events: list[dict[str, Any]] = field(default_factory=list, init=False)
    active: int = field(default=0, init=False)
    peak_concurrency: int = field(default=0, init=False)
    node_deadlines: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _last_event_hash: str = field(default="", init=False)
    _execution_policy_identity: str = field(default="", init=False)
    _breaker: CircuitBreaker = field(init=False)

    def __post_init__(self) -> None:
        self.request = validate_request(self.request)
        self.dag = validate_dag(self.dag, self.request)
        self.family_limits = validate_concurrency_limits(self.max_concurrency, self.family_limits)
        self.execution_policy = copy.deepcopy(dict(self.execution_policy))
        self._execution_policy_identity = sha256_value({"max_concurrency": self.max_concurrency, "family_limits": self.family_limits, "execution_policy": self.execution_policy, "authority_binding_hash": self.authority_binding_hash or ""})
        self.states = {node["node_id"]: "PLANNED" for node in self.dag["nodes"]}
        self.circuit_registry = self.circuit_registry or CircuitRegistry()
        self._breaker = self.circuit_registry.for_identity(self.request["project_id"], self.request["request_id"], self.dag["dag_hash"], self._execution_policy_identity)

    @property
    def scheduler_hash(self) -> str:
        return sha256_value(deterministic_schedule(self.dag))

    @property
    def execution_policy_identity(self) -> str:
        return self._execution_policy_identity

    @property
    def execution_identity(self) -> dict[str, str]:
        identity = {"project_id": self.request["project_id"], "idempotency_key": self.request["idempotency_key"], "request_hash": self.request["request_hash"], "dag_hash": self.dag["dag_hash"], "execution_policy_identity": self.execution_policy_identity, "authority_binding_hash": self.authority_binding_hash or ""}
        identity["identity_hash"] = sha256_value(identity)
        return identity

    def _node(self, node_id: str) -> dict[str, Any]:
        for node in self.dag["nodes"]:
            if node["node_id"] == node_id:
                return node
        _reject("ORCH_UNKNOWN_NODE", f"unknown node {node_id}")

    def transition(self, node_id: str, new_state: str, detail: str = "", **extra: Any) -> dict[str, Any]:
        if node_id not in self.states:
            _reject("ORCH_UNKNOWN_NODE", f"unknown node {node_id}")
        current = self.states[node_id]
        if new_state not in ALLOWED_TRANSITIONS.get(current, set()):
            _reject("ORCH_ILLEGAL_STATE_TRANSITION", f"{current} -> {new_state} is not allowed")
        self.states[node_id] = new_state
        event = {"sequence": len(self.events) + 1, "node_id": node_id, "from": current, "to": new_state, "detail": detail, "elapsed_seconds": self.clock.now(), "request_deadline_seconds": self.request["timeout_seconds"], **extra}
        event["event_hash"] = _event_hash(self._last_event_hash, event)
        self._last_event_hash = event["event_hash"]
        self.events.append(event)
        return copy.deepcopy(event)

    def dispatch(self, node_id: str) -> dict[str, Any]:
        state = self.states.get(node_id)
        if state is None:
            _reject("ORCH_UNKNOWN_NODE", f"unknown node {node_id}")
        if state in TERMINAL_STATES or state in {"DISPATCHED", "RUNNING"}:
            return {"duplicate": True, "state": state, "result": copy.deepcopy(self.results.get(node_id))}
        if state == "PLANNED":
            self.transition(node_id, "VALIDATED")
        if self.states[node_id] == "VALIDATED":
            self.transition(node_id, "READY")
        self.transition(node_id, "DISPATCHED")
        return {"duplicate": False, "state": "DISPATCHED"}

    def cancel(self, node_id: str) -> dict[str, Any]:
        if node_id not in self.states:
            _reject("ORCH_UNKNOWN_NODE", f"unknown node {node_id}")
        if self.states[node_id] in TERMINAL_STATES:
            return {"node_id": node_id, "state": self.states[node_id], "idempotent": True}
        self.transition(node_id, "CANCELLED", "explicit bounded cancellation")
        return {"node_id": node_id, "state": "CANCELLED", "idempotent": False}

    def retry(self, node_id: str) -> None:
        if self.states.get(node_id) in TERMINAL_STATES:
            _reject("ORCH_RETRY_AFTER_TERMINAL_REJECTED", "terminal execution cannot be retried")
        _reject("ORCH_RETRY_ONLY_THROUGH_BOUNDED_RUN", "retry is controlled by bounded execution loop")

    def _blocked_by_dependency(self, node: Mapping[str, Any]) -> bool:
        return any(self.states[dependency] in {"FAILED", "CANCELLED", "BLOCKED"} for dependency in node["dependencies"])

    def _admit(self, node: Mapping[str, Any]) -> None:
        if self.active >= self.max_concurrency:
            _reject("ORCH_GLOBAL_CONCURRENCY_EXCEEDED", "global concurrency bound exceeded")
        family_limit = self.family_limits.get(node["asset_family"], self.max_concurrency)
        running_family = sum(1 for node_id, state in self.states.items() if state == "RUNNING" and self._node(node_id)["asset_family"] == node["asset_family"])
        if running_family >= family_limit:
            _reject("ORCH_FAMILY_CONCURRENCY_EXCEEDED", "family concurrency bound exceeded")

    def _remaining_request(self) -> float:
        return round(self.request["timeout_seconds"] - self.clock.now(), 9)

    def _execute_one(self, node: dict[str, Any], fault: str | None = None) -> None:
        node_id = node["node_id"]
        self.dispatch(node_id)
        if not self._breaker.allow():
            self.transition(node_id, "BLOCKED", "circuit breaker OPEN blocked dispatch", circuit_state=self._breaker.state)
            return
        self._admit(node)
        self.transition(node_id, "RUNNING", circuit_state=self._breaker.state)
        self.active += 1
        self.peak_concurrency = max(self.peak_concurrency, self.active)
        node_started = self.clock.now()
        effective_node_deadline = min(float(self.request["timeout_seconds"]), node_started + float(node["timeout_seconds"]))
        max_attempts = node["retry_policy"]["max_attempts"]
        retryable = set(node["retry_policy"]["retryable_errors"])
        try:
            for attempt in range(1, max_attempts + 1):
                self.attempts[node_id] = attempt
                try:
                    request_remaining = self._remaining_request()
                    node_remaining = effective_node_deadline - self.clock.now()
                    if request_remaining <= 0:
                        raise RequestDeadlineExceeded("request deadline exhausted before node attempt")
                    if node_remaining <= 0:
                        raise NodeDeadlineExceeded("node deadline exhausted before node attempt")
                    duration = self.executor.duration_for(node_id, attempt)
                    if fault == "timeout":
                        duration = max(duration, min(request_remaining, node_remaining) + 1.0)
                    allowed = min(request_remaining, node_remaining)
                    if duration > allowed:
                        self.clock.advance(max(0.0, allowed))
                        if request_remaining <= node_remaining:
                            raise RequestDeadlineExceeded("fake elapsed duration exceeded request deadline")
                        raise NodeDeadlineExceeded("fake elapsed duration exceeded node deadline")
                    self.clock.advance(duration)
                    if fault == "retryable" and attempt == 1:
                        raise RetryableExecutionError("deterministic transient error")
                    if fault == "nonretryable":
                        raise NonRetryableExecutionError("deterministic contract error")
                    self.results[node_id] = self.executor.execute(self.request, node, attempt=attempt)
                    self.transition(node_id, "SUCCEEDED", attempt=attempt, duration_seconds=duration)
                    self._breaker.record_success()
                    self.node_deadlines[node_id] = {"started_seconds": node_started, "deadline_seconds": effective_node_deadline, "parent_deadline_seconds": float(self.request["timeout_seconds"]), "elapsed_seconds": self.clock.now() - node_started, "status": "SUCCEEDED"}
                    return
                except (RetryableExecutionError, NodeDeadlineExceeded, RequestDeadlineExceeded) as exc:
                    error_class = getattr(exc, "error_class", type(exc).__name__)
                    self.node_deadlines[node_id] = {"started_seconds": node_started, "deadline_seconds": effective_node_deadline, "parent_deadline_seconds": float(self.request["timeout_seconds"]), "elapsed_seconds": self.clock.now() - node_started, "status": "TIMEOUT" if isinstance(exc, (NodeDeadlineExceeded, RequestDeadlineExceeded)) else "RETRYABLE", "error_class": error_class}
                    can_retry = error_class in retryable and attempt < max_attempts and self._remaining_request() > 0 and self.clock.now() < effective_node_deadline
                    self._breaker.record_failure(retryable=True)
                    if can_retry and self._breaker.allow():
                        continue
                    self.transition(node_id, "FAILED", error_class, attempt=attempt, timeout_type=type(exc).__name__ if isinstance(exc, (NodeDeadlineExceeded, RequestDeadlineExceeded)) else None)
                    return
                except NonRetryableExecutionError as exc:
                    self.transition(node_id, "FAILED", type(exc).error_class, attempt=attempt)
                    return
        finally:
            self.active -= 1

    def run(self, faults: Mapping[str, str] | None = None, cancellations: Iterable[str] = (), stop_after_nodes: int | None = None) -> dict[str, Any]:
        fault_map = dict(faults or {})
        cancellation_set = set(cancellations)
        completed_this_run = 0
        for node_id in deterministic_schedule(self.dag):
            node = self._node(node_id)
            if stop_after_nodes is not None and completed_this_run >= stop_after_nodes:
                break
            if node_id in cancellation_set:
                self.cancel(node_id)
                continue
            if self._blocked_by_dependency(node):
                if self.states[node_id] == "PLANNED":
                    self.transition(node_id, "BLOCKED", "dependency terminal failure")
                continue
            if self.states[node_id] in TERMINAL_STATES:
                continue
            if self._remaining_request() <= 0:
                self.transition(node_id, "BLOCKED", "request deadline exhausted before dispatch", deadline_exhausted=True)
                continue
            self._execute_one(node, fault_map.get(node_id))
            if self.states[node_id] == "SUCCEEDED":
                completed_this_run += 1
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        status = "COMPLETE" if all(state in TERMINAL_STATES for state in self.states.values()) else "PARTIAL"
        return {"schema_version": SCHEMA_VERSION, "status": status, "project_id": self.request["project_id"], "request_id": self.request["request_id"], "request_hash": self.request["request_hash"], "dag_hash": self.dag["dag_hash"], "scheduler_hash": self.scheduler_hash, "execution_policy_identity": self.execution_policy_identity, "authority_binding_hash": self.authority_binding_hash or "", "execution_identity": copy.deepcopy(self.execution_identity), "max_concurrency": self.max_concurrency, "family_limits": copy.deepcopy(self.family_limits), "execution_policy": copy.deepcopy(self.execution_policy), "states": copy.deepcopy(self.states), "results": copy.deepcopy(self.results), "attempts": copy.deepcopy(self.attempts), "events": copy.deepcopy(self.events), "event_sequence": len(self.events), "event_hash": self._last_event_hash, "clock_elapsed_seconds": self.clock.now(), "request_deadline_seconds": self.request["timeout_seconds"], "node_deadlines": copy.deepcopy(self.node_deadlines), "peak_concurrency": self.peak_concurrency, "provider_submit_calls": self.executor.provider_submit_calls, "circuit": {"state": self._breaker.state, "failures": self._breaker.failures, "probe_in_flight": self._breaker._probe_in_flight}, "test_only": True}

    def checkpoint(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        completed = {node_id: result["result_hash"] for node_id, result in self.results.items() if self.states.get(node_id) == "SUCCEEDED"}
        snapshot["completed_result_hashes"] = completed
        snapshot["completed_hash"] = sha256_value(completed)
        snapshot["checkpoint_hash"] = sha256_value(snapshot)
        return snapshot


def _policy_identity(max_concurrency: int, family_limits: Mapping[str, int], execution_policy: Mapping[str, Any], authority_binding_hash: str) -> str:
    return sha256_value({"max_concurrency": max_concurrency, "family_limits": dict(family_limits), "execution_policy": dict(execution_policy), "authority_binding_hash": authority_binding_hash})


def _identity_for_values(request: Mapping[str, Any], dag: Mapping[str, Any], *, max_concurrency: int, family_limits: Mapping[str, int], execution_policy: Mapping[str, Any], authority_binding_hash: str) -> dict[str, str]:
    identity = {"project_id": request["project_id"], "idempotency_key": request["idempotency_key"], "request_hash": request["request_hash"], "dag_hash": dag["dag_hash"], "execution_policy_identity": _policy_identity(max_concurrency, family_limits, execution_policy, authority_binding_hash), "authority_binding_hash": authority_binding_hash}
    identity["identity_hash"] = sha256_value(identity)
    return identity


def validate_checkpoint(checkpoint: Mapping[str, Any], request: Mapping[str, Any], dag: Mapping[str, Any], completed_results: Mapping[str, Mapping[str, Any]] | None = None, *, execution_policy: Mapping[str, Any] | None = None, max_concurrency: int | None = None, family_limits: Mapping[str, int] | None = None, authority_binding_hash: str | None = None) -> dict[str, Any]:
    if not isinstance(checkpoint, Mapping):
        _reject("ORCH_CHECKPOINT_INVALID", "checkpoint must be an object")
    value = copy.deepcopy(dict(checkpoint))
    supplied_hash = value.pop("checkpoint_hash", None)
    if supplied_hash is None or supplied_hash != sha256_value(value):
        _reject("ORCH_CHECKPOINT_TAMPERED", "checkpoint hash is absent or invalid")
    request_value = validate_request(request)
    dag_value = validate_dag(dag, request_value)
    if value.get("schema_version") != SCHEMA_VERSION or value.get("project_id") != request_value["project_id"] or value.get("request_hash") != request_value["request_hash"]:
        _reject("ORCH_CHECKPOINT_IDENTITY_MISMATCH", "checkpoint request/project identity is stale")
    if value.get("dag_hash") != dag_value["dag_hash"]:
        _reject("ORCH_CHECKPOINT_STALE", "checkpoint DAG identity is stale")
    if value.get("scheduler_hash") != sha256_value(deterministic_schedule(dag_value)):
        _reject("ORCH_CHECKPOINT_SCHEDULER_MISMATCH", "checkpoint scheduler identity is stale")
    if value.get("test_only") is not True:
        _reject("ORCH_CHECKPOINT_INVALID", "checkpoint must remain TEST_ONLY")
    expected_nodes = {node["node_id"] for node in dag_value["nodes"]}
    states = value.get("states")
    if not isinstance(states, Mapping) or set(states) != expected_nodes:
        _reject("ORCH_CHECKPOINT_NODE_SET_MISMATCH", "checkpoint states must contain exactly the DAG nodes")
    if any(state not in ALLOWED_TRANSITIONS for state in states.values()):
        _reject("ORCH_CHECKPOINT_INVALID", "checkpoint contains an unknown state")
    results = value.get("results", {})
    if not isinstance(results, Mapping) or not set(results).issubset(expected_nodes):
        _reject("ORCH_CHECKPOINT_RESULT_NODE_MISMATCH", "checkpoint result nodes are not a DAG subset")
    succeeded = {node_id for node_id, state in states.items() if state == "SUCCEEDED"}
    if set(results) != succeeded:
        _reject("ORCH_CHECKPOINT_RESULT_STATE_MISMATCH", "only succeeded nodes may have results")
    for node_id, result in results.items():
        if not isinstance(result, Mapping) or result.get("status") != "SUCCEEDED":
            _reject("ORCH_CHECKPOINT_RESULT_STATE_MISMATCH", f"result is not successful for {node_id}")
        _assert_sha(result.get("result_hash"), f"result_hash:{node_id}")
    completed = value.get("completed_result_hashes", {})
    if not isinstance(completed, Mapping) or set(completed) != succeeded or value.get("completed_hash") != sha256_value(completed):
        _reject("ORCH_CHECKPOINT_RESULT_HASH_TAMPERED", "completed result identity is invalid")
    for node_id, result_hash in completed.items():
        _assert_sha(result_hash, f"completed_result_hash:{node_id}")
        if results[node_id].get("result_hash") != result_hash:
            _reject("ORCH_CHECKPOINT_RESULT_HASH_TAMPERED", f"completed result is not bound for {node_id}")
        if completed_results is not None and (node_id not in completed_results or completed_results[node_id].get("result_hash") != result_hash or completed_results[node_id].get("status") != "SUCCEEDED"):
            _reject("ORCH_CHECKPOINT_RESULT_HASH_TAMPERED", f"external completed result is not bound for {node_id}")
    events = value.get("events")
    if not isinstance(events, list) or value.get("event_sequence") != len(events):
        _reject("ORCH_CHECKPOINT_EVENT_SEQUENCE_INVALID", "event sequence is not monotonic")
    replay_states = {node_id: "PLANNED" for node_id in expected_nodes}
    previous = ""
    for expected_sequence, event in enumerate(events, 1):
        if not isinstance(event, Mapping) or event.get("node_id") not in expected_nodes:
            _reject("ORCH_CHECKPOINT_EVENT_NODE_UNKNOWN", "event references an unknown node")
        node_id = event["node_id"]
        if event.get("sequence") != expected_sequence or event.get("from") != replay_states[node_id] or event.get("to") not in ALLOWED_TRANSITIONS.get(replay_states[node_id], set()):
            _reject("ORCH_CHECKPOINT_EVENT_STATE_MISMATCH", "event state pair is invalid")
        unsigned = {key: event[key] for key in event if key != "event_hash"}
        if event.get("event_hash") != _event_hash(previous, unsigned):
            _reject("ORCH_CHECKPOINT_EVENT_CHAIN_INVALID", "event hash chain is invalid")
        replay_states[node_id] = event["to"]
        previous = event["event_hash"]
    if replay_states != dict(states):
        _reject("ORCH_CHECKPOINT_EVENT_STATE_MISMATCH", "event replay does not equal checkpoint states")
    expected_status = "COMPLETE" if all(state in TERMINAL_STATES for state in states.values()) else "PARTIAL"
    if value.get("status") != expected_status:
        _reject("ORCH_CHECKPOINT_STATUS_INVALID", "checkpoint status is inconsistent with node states")
    stored_identity = value.get("execution_identity")
    if not isinstance(stored_identity, Mapping):
        _reject("ORCH_CHECKPOINT_IDENTITY_MISMATCH", "checkpoint execution identity is missing")
    if stored_identity.get("project_id") != request_value["project_id"] or stored_identity.get("idempotency_key") != request_value["idempotency_key"] or stored_identity.get("request_hash") != request_value["request_hash"] or stored_identity.get("dag_hash") != dag_value["dag_hash"]:
        _reject("ORCH_CHECKPOINT_IDENTITY_MISMATCH", "checkpoint execution identity is stale")
    if max_concurrency is not None or family_limits is not None or execution_policy is not None or authority_binding_hash is not None:
        global_limit = max_concurrency if max_concurrency is not None else int(value.get("max_concurrency", 4))
        limits = validate_concurrency_limits(global_limit, family_limits if family_limits is not None else value.get("family_limits", {}))
        policy = execution_policy if execution_policy is not None else value.get("execution_policy", {})
        authority = authority_binding_hash if authority_binding_hash is not None else str(value.get("authority_binding_hash", ""))
        expected_identity = _identity_for_values(request_value, dag_value, max_concurrency=global_limit, family_limits=limits, execution_policy=policy, authority_binding_hash=authority)
        if dict(stored_identity) != expected_identity:
            _reject("ORCH_CHECKPOINT_EXECUTION_POLICY_MISMATCH", "checkpoint execution policy identity is stale")
    return {"status": "PASS", "checkpoint_status": expected_status, "request_hash": request_value["request_hash"], "dag_hash": dag_value["dag_hash"], "completed": len(completed), "event_sequence": len(events), "identity_hash": stored_identity.get("identity_hash")}


def atomic_write_checkpoint(path: Path, checkpoint: Mapping[str, Any]) -> Path:
    target = Path(path)
    if target.exists() and target.is_symlink():
        _reject("ORCH_SYMLINK_PATH_REJECTED", "checkpoint target may not be a symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(dict(checkpoint), ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def resume_from_checkpoint(request: Mapping[str, Any], dag: Mapping[str, Any], checkpoint: Mapping[str, Any], **kwargs: Any) -> OrchestrationRuntime:
    max_concurrency = kwargs.pop("max_concurrency", checkpoint.get("max_concurrency", 4))
    family_limits = kwargs.pop("family_limits", checkpoint.get("family_limits", {}))
    execution_policy = kwargs.pop("execution_policy", checkpoint.get("execution_policy", {}))
    authority_binding_hash = kwargs.pop("authority_binding_hash", checkpoint.get("authority_binding_hash", ""))
    validate_checkpoint(checkpoint, request, dag, execution_policy=execution_policy, max_concurrency=max_concurrency, family_limits=family_limits, authority_binding_hash=authority_binding_hash)
    runtime = OrchestrationRuntime(request, dag, max_concurrency=max_concurrency, family_limits=dict(family_limits), executor=kwargs.pop("executor", None) or FakeExecutor(), clock=DeterministicClock(float(checkpoint.get("clock_elapsed_seconds", 0.0))), execution_policy=execution_policy, authority_binding_hash=authority_binding_hash, circuit_registry=kwargs.pop("circuit_registry", None))
    runtime.states = copy.deepcopy(dict(checkpoint["states"]))
    runtime.results = copy.deepcopy(dict(checkpoint.get("results", {})))
    runtime.attempts = copy.deepcopy(dict(checkpoint.get("attempts", {})))
    runtime.events = copy.deepcopy(list(checkpoint.get("events", [])))
    runtime._last_event_hash = str(checkpoint.get("event_hash", ""))
    runtime.peak_concurrency = int(checkpoint.get("peak_concurrency", 0))
    runtime.node_deadlines = copy.deepcopy(dict(checkpoint.get("node_deadlines", {})))
    return runtime


def _resume_classmethod(cls: type[OrchestrationRuntime], request: Mapping[str, Any], dag: Mapping[str, Any], checkpoint: Mapping[str, Any], **kwargs: Any) -> OrchestrationRuntime:
    return resume_from_checkpoint(request, dag, checkpoint, **kwargs)


OrchestrationRuntime.resume_from_checkpoint = classmethod(_resume_classmethod)  # type: ignore[attr-defined]
OrchestrationRuntime.resume = OrchestrationRuntime.resume_from_checkpoint  # type: ignore[attr-defined]


def _semantic_hash(raw: bytes) -> str:
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return sha256_bytes(raw)
    return sha256_value(parsed)


def build_dependency_ref(repo_root: Path, *, project_id: str, family: str, revision: str, path: str, authority_id: str | None = None, status: str = "APPROVED_FOUNDATION", approved_commit: str | None = None) -> dict[str, Any]:
    safe_path = validate_safe_relative_path(path, root=Path(repo_root))
    target = (Path(repo_root) / Path(*safe_path.split("/"))).resolve()
    root = Path(repo_root).resolve()
    if not target.is_file() or root not in target.parents:
        _reject("ORCH_DEPENDENCY_AUTHORITY_MISSING", f"authority file is not present: {safe_path}")
    raw = target.read_bytes()
    value: dict[str, Any] = {"project_id": project_id, "family": family, "revision": revision, "path": safe_path, "content_hash": sha256_bytes(raw), "semantic_hash": _semantic_hash(raw), "read_only": True, "status": status}
    if authority_id is not None:
        value["authority_id"] = authority_id
    if approved_commit is not None:
        value["approved_commit"] = approved_commit
    return validate_dependency_ref(value, expected_project_id=project_id)


def _git_blob_at(repo_root: Path, commit: str, path: str) -> bytes:
    try:
        completed = subprocess.run(["git", "-C", str(repo_root), "show", f"{commit}:{path}"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        _reject("ORCH_DEPENDENCY_AUTHORITY_COMMIT_MISSING", f"approved authority commit could not be resolved: {exc}")
    return completed.stdout


def resolve_dependency_ref(reference: Mapping[str, Any], repo_root: Path, *, expected_project_id: str | None = None) -> dict[str, Any]:
    value = validate_dependency_ref(reference, expected_project_id=expected_project_id)
    root = Path(repo_root).resolve()
    safe_path = validate_safe_relative_path(value["path"], root=root)
    target = (root / Path(*safe_path.split("/"))).resolve()
    if not target.is_file() or root not in target.parents:
        _reject("ORCH_DEPENDENCY_AUTHORITY_MISSING", f"authority file is not present: {safe_path}")
    raw = target.read_bytes()
    observed_content_hash = sha256_bytes(raw)
    observed_semantic_hash = _semantic_hash(raw)
    if observed_content_hash != value["content_hash"] or observed_semantic_hash != value["semantic_hash"]:
        _reject("ORCH_DEPENDENCY_AUTHORITY_HASH_MISMATCH", f"authority bytes do not match {safe_path}")
    if "approved_commit" in value:
        approved_raw = _git_blob_at(root, value["approved_commit"], safe_path)
        if approved_raw != raw:
            _reject("ORCH_DEPENDENCY_AUTHORITY_BYTES_CHANGED", f"authority bytes differ from approved commit for {safe_path}")
    return {**value, "resolved_content_hash": observed_content_hash, "resolved_semantic_hash": observed_semantic_hash, "resolved_bytes": len(raw), "resolved_from": "repository"}


def resolve_dependency_refs(refs: Iterable[Mapping[str, Any]], repo_root: Path, *, expected_project_id: str | None = None) -> dict[str, Any]:
    resolved = [resolve_dependency_ref(reference, repo_root, expected_project_id=expected_project_id) for reference in refs]
    if not resolved:
        _reject("ORCH_DEPENDENCY_AUTHORITY_MISSING", "at least one approved authority is required")
    identity_payload = [{key: item[key] for key in ("project_id", "family", "revision", "path", "resolved_content_hash", "resolved_semantic_hash", "read_only", "status") if key in item} for item in resolved]
    return {"status": "PASS", "authorities": resolved, "authority_binding_hash": sha256_value(identity_payload), "resolved_authority_hashes": {item["family"]: item["resolved_content_hash"] for item in resolved}}


def validate_authority_binding(binding: Mapping[str, Any], refs: Iterable[Mapping[str, Any]], repo_root: Path, *, expected_project_id: str | None = None) -> dict[str, Any]:
    observed = resolve_dependency_refs(refs, repo_root, expected_project_id=expected_project_id)
    if binding.get("authority_binding_hash") != observed["authority_binding_hash"] or binding.get("resolved_authority_hashes") != observed["resolved_authority_hashes"]:
        _reject("ORCH_AUTHORITY_BINDING_MISMATCH", "authority binding does not match resolved repository bytes")
    return observed


class BoundedExecutionStore:
    """Request-bound store; it never promotes a failed execution to success."""

    def __init__(self, max_records: int = 256) -> None:
        if not isinstance(max_records, int) or isinstance(max_records, bool) or not 1 <= max_records <= 4096:
            _reject("ORCH_IDEMPOTENCY_STORE_BOUND_INVALID", "idempotency store capacity must be a bounded positive integer")
        self.max_records = max_records
        self._records: dict[tuple[str, str], dict[str, Any]] = {}

    def claim(self, identity: Mapping[str, str]) -> dict[str, Any]:
        key = (identity["project_id"], identity["idempotency_key"])
        existing = self._records.get(key)
        if existing is not None:
            if existing["identity_hash"] != identity["identity_hash"]:
                _reject("ORCH_IDEMPOTENCY_CONFLICT", "idempotency key is bound to a different request/DAG/policy identity")
            if existing["status"] == "SUCCEEDED":
                return {"decision": "REUSED", **copy.deepcopy(existing)}
            if existing["status"] == "RUNNING":
                return {"decision": "RUNNING_DUPLICATE", **copy.deepcopy(existing)}
        elif len(self._records) >= self.max_records:
            _reject("ORCH_IDEMPOTENCY_STORE_BOUNDS_EXCEEDED", "idempotency store capacity is exhausted")
        source_execution_id = f"exec-{identity['identity_hash'][:16]}"
        record = {"source_execution_id": source_execution_id, "identity_hash": identity["identity_hash"], "project_id": identity["project_id"], "idempotency_key": identity["idempotency_key"], "request_hash": identity["request_hash"], "dag_hash": identity["dag_hash"], "execution_policy_identity": identity["execution_policy_identity"], "authority_binding_hash": identity.get("authority_binding_hash", ""), "status": "RUNNING", "result_hashes": {}}
        self._records[key] = record
        return {"decision": "NEW", **copy.deepcopy(record)}

    def complete(self, identity: Mapping[str, str], snapshot: Mapping[str, Any]) -> dict[str, Any]:
        key = (identity["project_id"], identity["idempotency_key"])
        record = self._records.get(key)
        if record is None or record["identity_hash"] != identity["identity_hash"]:
            _reject("ORCH_IDEMPOTENCY_CONFLICT", "completion identity does not match claimed execution")
        status = "SUCCEEDED" if snapshot.get("status") == "COMPLETE" and all(state == "SUCCEEDED" for state in snapshot.get("states", {}).values()) else "FAILED"
        record.update({"status": status, "result_hashes": {node_id: result.get("result_hash") for node_id, result in snapshot.get("results", {}).items()}, "snapshot_hash": sha256_value(snapshot)})
        return copy.deepcopy(record)

    def get(self, identity: Mapping[str, str]) -> dict[str, Any] | None:
        value = self._records.get((identity["project_id"], identity["idempotency_key"]))
        return copy.deepcopy(value) if value is not None else None


IdempotencyStore = BoundedExecutionStore


class ExecutionCoordinator:
    def __init__(self, store: BoundedExecutionStore | None = None):
        self.store = store or BoundedExecutionStore()

    def execute(self, runtime: OrchestrationRuntime, *, faults: Mapping[str, str] | None = None, cancellations: Iterable[str] = (), stop_after_nodes: int | None = None) -> dict[str, Any]:
        identity = runtime.execution_identity
        claim = self.store.claim(identity)
        if claim["decision"] in {"REUSED", "RUNNING_DUPLICATE"}:
            return {"status": claim["decision"], "source_execution_id": claim["source_execution_id"], "identity": identity, "result_hashes": copy.deepcopy(claim.get("result_hashes", {})), "snapshot_hash": claim.get("snapshot_hash"), "executor_calls": 0}
        snapshot = runtime.run(faults=faults, cancellations=cancellations, stop_after_nodes=stop_after_nodes)
        record = self.store.complete(identity, snapshot)
        return {"status": "EXECUTED", "source_execution_id": record["source_execution_id"], "identity": identity, "result_hashes": record["result_hashes"], "snapshot": snapshot, "snapshot_hash": record.get("snapshot_hash"), "executor_calls": runtime.executor.executions}


def validate_idempotent_replay(executions_before: Any, executions_after: Any, duplicate: Any) -> None:
    if duplicate is True and executions_after != executions_before:
        _reject("ORCH_IDEMPOTENT_REPLAY_VIOLATION", "duplicate dispatch executed work twice")


def validate_no_dynamic_nodes(initial_node_ids: Iterable[str], observed_node_ids: Iterable[str]) -> None:
    if set(initial_node_ids) != set(observed_node_ids):
        _reject("ORCH_DYNAMIC_NODE_REJECTED", "execution introduced or removed a node")


def validate_terminal_immutability(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    if before.get("states") != after.get("states") or before.get("results") != after.get("results"):
        _reject("ORCH_TERMINAL_MUTATION_REJECTED", "terminal execution changed after terminal input")


def validate_output_identity(project_id: str, output: Mapping[str, Any]) -> None:
    if output.get("project_id") != project_id:
        _reject("ORCH_CROSS_PROJECT_OUTPUT", "output project identity does not match request project")
    validate_safe_relative_path(output.get("path", ""))


def validate_schedule_observation(dag: Mapping[str, Any], observed: Any) -> None:
    if observed != deterministic_schedule(dag):
        _reject("ORCH_SCHEDULER_NONDETERMINISTIC", "observed schedule differs from canonical schedule")


def validate_provider_submit_count(observed: Any) -> None:
    if type(observed) is not int or observed != 0:
        _reject("ORCH_REAL_PROVIDER_SUBMIT_REJECTED", "provider submission count must remain zero")


def validate_provider_spy_counts(observed: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(observed, Mapping):
        _reject("ORCH_PROVIDER_SPY_INVALID", "provider spy observations must be an object")
    normalized = {str(key): value for key, value in observed.items()}
    for target, count in normalized.items():
        if type(count) is not int or count != 0:
            _reject("ORCH_REAL_PROVIDER_SUBMIT_REJECTED", f"provider spy recorded a call: {target}")
    return {"status": "PASS", "targets": normalized, "all_zero": True}


def provider_spy_targets() -> tuple[str, ...]:
    return (
        "ugas.comfyui_client.ComfyUIClient.submit_workflow",
        "ugas.generation.ComfyUIClient.submit_workflow",
    )


def assert_provider_boundary(source: str | Path | None = None) -> dict[str, Any]:
    if source is None:
        source_text = inspect.getsource(OrchestrationRuntime)
        source_name = "ugas.orchestration_runtime_v0241.OrchestrationRuntime"
    elif isinstance(source, Path) or (isinstance(source, str) and "\n" not in source and Path(source).is_file()):
        source_path = Path(source)
        source_text = source_path.read_text(encoding="utf-8")
        source_name = source_path.as_posix()
    else:
        source_text = str(source)
        source_name = "provided-source"
    try:
        tree = ast.parse(source_text)
    except SyntaxError as exc:
        _reject("ORCH_PROVIDER_IMPORT_BOUNDARY_VIOLATION", f"source is not parseable: {exc}")
    forbidden_modules = {"ugas.comfyui_client", "ugas.generation", ".comfyui_client", ".generation", "comfyui_client", "generation"}
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits.extend(alias.name for alias in node.names if alias.name in forbidden_modules or alias.name.startswith("ugas.comfyui_client"))
        elif isinstance(node, ast.ImportFrom) and (node.module in forbidden_modules or (node.module or "").endswith(".comfyui_client") or (node.module or "").endswith(".generation")):
            hits.append(node.module or "")
    if hits:
        _reject("ORCH_PROVIDER_IMPORT_BOUNDARY_VIOLATION", f"provider imports detected in {source_name}: {hits}")
    return {"status": "PASS", "source": source_name, "forbidden_hits": [], "spy_targets": list(provider_spy_targets())}


def validate_production_boundary(record: Mapping[str, Any]) -> None:
    if record.get("production_routing") != "BLOCKED" or record.get("production_approved") is not False or record.get("new_generation") != 0:
        _reject("ORCH_PRODUCTION_BOUNDARY_REJECTED", "routing, approval and generation must remain blocked")


def validate_no_repo_local_uads(repo_root: Path) -> None:
    if (Path(repo_root) / ".uads").exists():
        _reject("ORCH_REPO_LOCAL_UADS_FOOTPRINT", "UADS runtime state must remain outside repository")


def sanitize_telemetry(event: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"event", "request_hash", "dag_hash", "node_id", "state", "sequence", "status", "resource_class", "duration_ms", "error_class", "elapsed_seconds", "deadline_seconds", "proof_source"}
    _validate_no_secret_like(event)
    _assert_no_unknown(event, allowed, "telemetry")
    value = copy.deepcopy(dict(event))
    for key, child in value.items():
        if isinstance(child, str) and (ntpath.isabs(child) or ("\\" in child and ":" in child)):
            _reject("ORCH_TELEMETRY_PATH_REJECTED", f"telemetry field {key} contains an absolute path")
        if isinstance(child, str) and len(child) > MAX_TELEMETRY_STRING:
            _reject("ORCH_TELEMETRY_BOUNDS_EXCEEDED", f"telemetry field {key} is too long")
    if len(value) > MAX_TELEMETRY_FIELDS:
        _reject("ORCH_TELEMETRY_BOUNDS_EXCEEDED", "telemetry event has too many fields")
    return value


def adapt_legacy_generation_request(legacy: Mapping[str, Any], project_id: str) -> dict[str, Any]:
    allowed = {"job_id", "asset_family", "inputs", "outputs", "profile", "seed"}
    _assert_no_unknown(legacy, allowed, "legacy generation request")
    return build_request(request_id=str(legacy.get("job_id", "legacy-request")), project_id=project_id, request_kind="ASSET_OPERATION", asset_family=legacy.get("asset_family"), operation="EXECUTE", inputs={"legacy": copy.deepcopy(legacy.get("inputs", {})), "profile": legacy.get("profile"), "seed": legacy.get("seed")}, dependency_refs=[], outputs=copy.deepcopy(legacy.get("outputs", {})), quality_profile="legacy-compatible", budget_profile="bounded-test-only", priority=0, timeout_seconds=60, retry_policy={"max_attempts": 1, "retryable_errors": []}, idempotency_key=f"legacy:{legacy.get('job_id', 'unknown')}", production_intent=False, test_only=True)


HARD_GATE_IDS = (
    "canonical_request", "request_hash", "dag_schema", "dag_acyclic", "dag_dependency_hashes",
    "scheduler_dependency_first", "scheduler_priority_lexical", "scheduler_deterministic",
    "bounded_global_concurrency", "bounded_family_concurrency", "family_limits_integer_bounded",
    "global_family_admission_observed", "no_dynamic_nodes", "state_transition_contract",
    "terminal_immutability", "idempotent_dispatch", "cross_runtime_idempotency",
    "failure_isolation", "bounded_cancellation", "bounded_retry", "retryable_error_class",
    "request_deadline_clock", "node_deadline_parent_bound", "timeout_rejection_typed",
    "retry_consumes_parent_deadline", "later_nodes_blocked_after_deadline", "partial_checkpoint_resume",
    "checkpoint_exact_node_set", "checkpoint_event_chain", "checkpoint_state_result_pair",
    "checkpoint_identity", "checkpoint_tamper_rejection", "resume_no_reexecution",
    "circuit_breaker_runtime", "circuit_open_dispatch_blocked", "circuit_half_open_single_probe",
    "circuit_nonretryable_not_transient", "authority_ref_schema", "authority_content_hash",
    "authority_revision_binding", "authority_read_only", "authority_payload_identity",
    "provider_source_boundary", "provider_client_spy_zero", "provider_legacy_spy_zero",
    "cache_identity", "cache_success_only", "result_provenance", "fake_executor_determinism",
    "telemetry_sanitized", "production_boundary", "legacy_adapter_narrow", "historical_closure_binding",
)


def evaluate_hard_gates(observations: Mapping[str, Any], proof_sources: Mapping[str, str] | None = None) -> dict[str, Any]:
    sources = proof_sources or {}
    gates = {gate_id: strict_gate(gate_id, observations.get(gate_id), "actual runtime/checker observation", sources.get(gate_id)) for gate_id in HARD_GATE_IDS}
    return {"schema_version": SCHEMA_VERSION, "gates": gates, "overall_pass": all(item["status"] == "PASS" for item in gates.values())}


__all__ = [
    "ALLOWED_TRANSITIONS", "BoundedExecutionStore", "CircuitBreaker", "CircuitRegistry", "DEPENDENCY_REF_FIELDS",
    "DeterministicAdmissionScheduler", "DeterministicBatchScheduler", "DeterministicClock", "ExecutionCoordinator",
    "FakeClock", "FakeExecutor", "HARD_GATE_IDS", "IdempotencyStore", "MAX_DEPTH", "MAX_FANOUT", "MAX_NODES",
    "NodeDeadlineExceeded", "NonRetryableExecutionError", "OrchestrationContractError", "OrchestrationRuntime",
    "RequestDeadlineExceeded", "RetryableExecutionError", "SUPPORTED_ASSET_FAMILIES", "VERSION",
    "adapt_legacy_generation_request", "assert_provider_boundary", "atomic_write_checkpoint", "build_dag",
    "build_dependency_ref", "build_request", "canonical_json", "deterministic_schedule", "evaluate_hard_gates",
    "node_contract_hash", "provider_spy_targets", "resolve_dependency_ref", "resolve_dependency_refs",
    "resume_from_checkpoint", "sanitize_telemetry", "sha256_bytes", "sha256_value", "strict_boolean_observation",
    "strict_gate", "validate_authority_binding", "validate_checkpoint", "validate_circuit_access",
    "validate_concurrency_limits", "validate_concurrency_observation", "validate_dependency_ref",
    "validate_dag", "validate_idempotent_replay", "validate_no_dynamic_nodes", "validate_no_repo_local_uads",
    "validate_output_identity", "validate_production_boundary", "validate_provider_spy_counts",
    "validate_provider_submit_count", "validate_request", "validate_safe_relative_path", "validate_schedule_observation",
    "validate_terminal_immutability",
]
