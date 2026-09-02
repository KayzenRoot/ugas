"""Bounded local SQLite event store with a memory fallback."""

from __future__ import annotations

from collections import deque
import json
from pathlib import Path
import sqlite3
import threading
from typing import Iterable

from .events import TelemetryEvent


class TelemetryStore:
    """Persist telemetry locally without making callers depend on SQLite."""

    def __init__(self, path: Path, *, max_events: int = 5000) -> None:
        self.path = Path(path)
        self.max_events = max(100, int(max_events))
        self.available = False
        self.reason: str | None = None
        self._lock = threading.RLock()
        self._fallback: deque[TelemetryEvent] = deque(maxlen=self.max_events)
        self._connection: sqlite3.Connection | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path, check_same_thread=False, timeout=1.5)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=NORMAL")
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS telemetry_events (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    timestamp TEXT NOT NULL,
                    category TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    source TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    job_id TEXT,
                    asset_id TEXT,
                    metadata_json TEXT NOT NULL
                )"""
            )
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON telemetry_events(timestamp)")
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_category ON telemetry_events(category)")
            self._connection.commit()
            self.available = True
        except Exception as exc:  # pragma: no cover - platform/filesystem dependent
            self.reason = f"{type(exc).__name__}: {exc}"[:500]
            self._fallback = deque(maxlen=self.max_events)
            self._close_connection()

    def _close_connection(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

    def insert(self, event: TelemetryEvent) -> bool:
        with self._lock:
            if not self.available or self._connection is None:
                self._fallback.append(event)
                return False
            try:
                self._connection.execute(
                    """INSERT OR IGNORE INTO telemetry_events
                    (event_id,timestamp,category,severity,source,action,status,message,job_id,asset_id,metadata_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (event.event_id, event.timestamp, event.category, event.severity, event.source,
                     event.action, event.status, event.message, event.job_id, event.asset_id,
                     json.dumps(event.metadata, ensure_ascii=True, separators=(",", ":"))),
                )
                self._connection.execute(
                    "DELETE FROM telemetry_events WHERE row_id IN "
                    "(SELECT row_id FROM telemetry_events ORDER BY row_id DESC LIMIT -1 OFFSET ?)",
                    (self.max_events,),
                )
                self._connection.commit()
                return True
            except Exception as exc:  # pragma: no cover - database failure dependent
                self.available = False
                self.reason = f"{type(exc).__name__}: {exc}"[:500]
                self._fallback.append(event)
                self._close_connection()
                return False

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> dict:
        try:
            metadata = json.loads(row["metadata_json"])
        except (TypeError, json.JSONDecodeError):
            metadata = {"store_error": "metadata could not be decoded"}
        return {
            "timestamp": row["timestamp"], "event_id": row["event_id"], "category": row["category"],
            "severity": row["severity"], "source": row["source"], "action": row["action"],
            "status": row["status"], "message": row["message"], "job_id": row["job_id"],
            "asset_id": row["asset_id"], "metadata": metadata,
        }

    def query(
        self,
        *,
        limit: int = 100,
        category: str | None = None,
        severity: str | None = None,
        search: str | None = None,
        after_row_id: int | None = None,
    ) -> list[dict]:
        limit = min(max(int(limit), 1), 500)
        with self._lock:
            if not self.available or self._connection is None:
                items = [event.to_dict() for event in self._fallback]
                if category:
                    items = [item for item in items if item["category"] == category]
                if severity:
                    items = [item for item in items if item["severity"] == severity]
                if search:
                    needle = search.casefold()
                    items = [item for item in items if needle in json.dumps(item, ensure_ascii=True).casefold()]
                return items[-limit:][::-1]
            clauses: list[str] = []
            values: list[object] = []
            if category:
                clauses.append("category = ?"); values.append(category)
            if severity:
                clauses.append("severity = ?"); values.append(severity)
            if search:
                clauses.append("(message LIKE ? OR action LIKE ? OR source LIKE ?)")
                needle = f"%{search}%"; values.extend((needle, needle, needle))
            if after_row_id is not None:
                clauses.append("row_id > ?"); values.append(int(after_row_id))
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            try:
                rows = self._connection.execute(
                    f"SELECT event_id,timestamp,category,severity,source,action,status,message,job_id,asset_id,metadata_json "
                    f"FROM telemetry_events {where} ORDER BY row_id DESC LIMIT ?", (*values, limit)
                ).fetchall()
                return [self._row_to_event(row) for row in rows]
            except Exception:
                return []

    def count(self) -> int:
        with self._lock:
            if not self.available or self._connection is None:
                return len(self._fallback)
            try:
                return int(self._connection.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()[0])
            except Exception:
                return 0

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.commit()
                except Exception:
                    pass
                self._close_connection()
