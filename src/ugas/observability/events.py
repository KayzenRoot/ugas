"""Structured, privacy-aware telemetry events.

The observability layer is deliberately independent from production asset
logic.  Event construction is bounded and sanitizes command/error metadata so
that a telemetry failure can never become a pipeline failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
import threading
import uuid
from typing import Any, Mapping

CATEGORIES = frozenset({
    "system", "process", "command", "job", "stage", "file", "asset", "qa",
    "provider", "error", "governance",
})
SEVERITIES = frozenset({"debug", "info", "warning", "error", "critical"})
MAX_MESSAGE_LENGTH = 1200
MAX_METADATA_LENGTH = 12000
_clock_lock = threading.Lock()
_last_timestamp_us = 0

_SECRET_KEY = re.compile(
    r"(?:token|password|passwd|secret|authorization|api[_-]?key|access[_-]?key|credential|cookie|env)\b",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(token|password|passwd|secret|authorization|api[_-]?key|access[_-]?key|credential|cookie)\s*(?:=|:)\s*[^\s,;]+"
)


def utc_timestamp() -> str:
    """Return a UTC RFC3339 timestamp that is monotonic within this process."""

    global _last_timestamp_us
    now_us = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
    with _clock_lock:
        if now_us <= _last_timestamp_us:
            now_us = _last_timestamp_us + 1
        _last_timestamp_us = now_us
    value = datetime.fromtimestamp(now_us / 1_000_000, timezone.utc)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def sanitize_text(value: object, *, limit: int = MAX_MESSAGE_LENGTH) -> str:
    text = str(value or "")
    text = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    return text[:limit] + ("..." if len(text) > limit else "")


def sanitize_metadata(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Make JSON metadata safe, bounded and free from common secret keys."""

    def clean(item: Any, depth: int = 0) -> Any:
        if depth > 4:
            return "[TRUNCATED]"
        if isinstance(item, Mapping):
            result: dict[str, Any] = {}
            for key, child in item.items():
                name = str(key)
                result[name] = "[REDACTED]" if _SECRET_KEY.search(name) else clean(child, depth + 1)
            return result
        if isinstance(item, (list, tuple)):
            return [clean(child, depth + 1) for child in list(item)[:100]]
        if isinstance(item, (str, int, float, bool)) or item is None:
            return sanitize_text(item, limit=2000) if isinstance(item, str) else item
        return sanitize_text(item, limit=500)

    cleaned = clean(value or {})
    try:
        encoded = json.dumps(cleaned, ensure_ascii=True, separators=(",", ":"))
    except (TypeError, ValueError):
        cleaned = {"observability_metadata_error": "metadata was not JSON serializable"}
        encoded = json.dumps(cleaned)
    if len(encoded) > MAX_METADATA_LENGTH:
        return {"observability_metadata_truncated": True, "summary": encoded[:MAX_METADATA_LENGTH]}
    return cleaned


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    timestamp: str
    event_id: str
    category: str
    severity: str
    source: str
    action: str
    status: str
    message: str
    job_id: str | None = None
    asset_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        category: str,
        severity: str = "info",
        source: str,
        action: str,
        status: str,
        message: str,
        job_id: str | None = None,
        asset_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "TelemetryEvent":
        category = str(category).lower()
        severity = str(severity).lower()
        if category not in CATEGORIES:
            raise ValueError(f"unsupported telemetry category: {category}")
        if severity not in SEVERITIES:
            raise ValueError(f"unsupported telemetry severity: {severity}")
        return cls(
            timestamp=utc_timestamp(),
            event_id=f"evt-{uuid.uuid4().hex}",
            category=category,
            severity=severity,
            source=sanitize_text(source, limit=200),
            action=sanitize_text(action, limit=200),
            status=sanitize_text(status, limit=120),
            message=sanitize_text(message),
            job_id=sanitize_text(job_id, limit=200) if job_id else None,
            asset_id=sanitize_text(asset_id, limit=200) if asset_id else None,
            metadata=sanitize_metadata(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "category": self.category,
            "severity": self.severity,
            "source": self.source,
            "action": self.action,
            "status": self.status,
            "message": self.message,
            "job_id": self.job_id,
            "asset_id": self.asset_id,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=True, separators=(",", ":"))
