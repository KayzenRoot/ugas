"""Append-only sanitized provenance events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SECRET_KEYS = {"token", "api_key", "apikey", "password", "authorization", "secret"}


def sanitize(value):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.casefold() in SECRET_KEYS else sanitize(child) for key, child in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def append_event(path: Path, event: dict) -> None:
    value = sanitize(dict(event))
    value.setdefault("timestamp", datetime.now(timezone.utc).replace(microsecond=0).isoformat())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
