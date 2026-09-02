"""Bounded local SQLite event store with a memory fallback."""

from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Iterable

from .events import TelemetryEvent


class TelemetryStore:
    """Persist telemetry locally without making callers depend on SQLite.

    Docker Desktop exposes the Windows bind mount through a Linux VM. SQLite
    must therefore have one writer at this boundary: native UGAS commands own
    the shared runtime database, while the container observes it read-only and
    keeps its own short-lived collector tail in memory.
    """

    @staticmethod
    def _initialize_connection(connection: sqlite3.Connection) -> None:
        connection.row_factory = sqlite3.Row
        # The runtime database is shared by native Windows commands and the
        # Docker dashboard through a bind mount. SQLite WAL relies on sidecar
        # locking semantics that are not reliable across Docker Desktop's
        # Windows/VM filesystem boundary; use the portable rollback journal
        # and an explicit bounded wait instead.
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute(
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
        connection.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON telemetry_events(timestamp)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_category ON telemetry_events(category)")
        connection.commit()

    def __init__(self, path: Path, *, max_events: int = 5000, read_only: bool | None = None) -> None:
        self.path = Path(path)
        self.max_events = max(100, int(max_events))
        self.read_only = bool(read_only) if read_only is not None else os.environ.get("UGAS_TELEMETRY_READ_ONLY") == "1" or os.environ.get("UGAS_CONTAINERIZED") == "1"
        self.available = False
        self.reason: str | None = None
        self._lock = threading.RLock()
        self._fallback: deque[TelemetryEvent] = deque(maxlen=self.max_events)
        # Keep the process-local tail visible even when another process holds
        # SQLite's short-lived write lock. Persisted rows remain authoritative
        # and are deduplicated by event_id when the connection is readable.
        self._recent_local: deque[TelemetryEvent] = deque(maxlen=self.max_events)
        self._connection: sqlite3.Connection | None = None
        self._writes_since_prune = 0
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.read_only:
                uri = f"file:{self.path.resolve().as_posix()}?mode=ro"
                self._connection = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=5.0, isolation_level=None)
                self._connection.row_factory = sqlite3.Row
                self._connection.execute("PRAGMA busy_timeout=5000")
                self._connection.execute("PRAGMA query_only=ON")
                self._connection.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
            else:
                self._connection = sqlite3.connect(self.path, check_same_thread=False, timeout=5.0)
                self._initialize_connection(self._connection)
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

    def _try_reopen(self) -> bool:
        if self.available and self._connection is not None:
            return True
        connection: sqlite3.Connection | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.read_only:
                uri = f"file:{self.path.resolve().as_posix()}?mode=ro"
                connection = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=5.0, isolation_level=None)
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA busy_timeout=5000")
                connection.execute("PRAGMA query_only=ON")
                connection.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
            else:
                connection = sqlite3.connect(self.path, check_same_thread=False, timeout=5.0)
                self._initialize_connection(connection)
            if self.read_only:
                self._connection = connection
                self.available = True
                self.reason = None
                return True
            pending = tuple(self._fallback)
            for event in pending:
                connection.execute(
                    """INSERT OR IGNORE INTO telemetry_events
                    (event_id,timestamp,category,severity,source,action,status,message,job_id,asset_id,metadata_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (event.event_id, event.timestamp, event.category, event.severity, event.source,
                     event.action, event.status, event.message, event.job_id, event.asset_id,
                     json.dumps(event.metadata, ensure_ascii=True, separators=(",", ":"))),
                )
            connection.commit()
            self._connection = connection
            self._fallback.clear()
            self.available = True
            self.reason = None
            return True
        except Exception as exc:
            if connection is not None:
                try: connection.close()
                except Exception: pass
            self.available = False
            self.reason = f"{type(exc).__name__}: {exc}"[:500]
            return False

    def insert(self, event: TelemetryEvent) -> bool:
        with self._lock:
            self._recent_local.append(event)
            if self.read_only:
                # The container must not write SQLite across the Docker
                # Desktop Windows/VM boundary. Its live events are still
                # exposed through the local tail, while host CLI events are
                # read from the shared database below.
                return False
            self._try_reopen()
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
                # Pruning on every event expands the write lock window and is
                # especially hostile to a native process sharing this DB with
                # Docker Desktop. Keep the bounded store semantics while
                # pruning in infrequent batches.
                self._writes_since_prune += 1
                if os.environ.get("UGAS_CONTAINERIZED") != "1" or self._writes_since_prune >= 250:
                    count = int(self._connection.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()[0])
                    if count > self.max_events:
                        self._connection.execute(
                            "DELETE FROM telemetry_events WHERE row_id IN "
                            "(SELECT row_id FROM telemetry_events ORDER BY row_id DESC LIMIT -1 OFFSET ?)",
                            (self.max_events,),
                        )
                    self._writes_since_prune = 0
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
            self._try_reopen()
            local_items = [event.to_dict() for event in reversed(self._recent_local)]
            if category:
                local_items = [item for item in local_items if item["category"] == category]
            if severity:
                local_items = [item for item in local_items if item["severity"] == severity]
            if search:
                needle = search.casefold()
                local_items = [item for item in local_items if needle in json.dumps(item, ensure_ascii=True).casefold()]
            if not self.available or self._connection is None:
                fallback_items = [event.to_dict() for event in reversed(self._fallback)]
                known = {item["event_id"] for item in local_items}
                local_items.extend(item for item in fallback_items if item["event_id"] not in known)
                return local_items[:limit]
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
                items = list(local_items)
                known = {item["event_id"] for item in items}
                items.extend(item for item in (self._row_to_event(row) for row in rows) if item["event_id"] not in known)
                return items[:limit]
            except Exception:
                return local_items[:limit]

    def count(self) -> int:
        with self._lock:
            self._try_reopen()
            if not self.available or self._connection is None:
                return len(self._fallback)
            try:
                return int(self._connection.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()[0])
            except Exception:
                return 0

    def close(self) -> None:
        with self._lock:
            # A short cross-process lock can move the last events into the
            # fallback deque. Give the shared database one bounded recovery
            # attempt before closing so host CLI events survive Docker
            # restart/rebuild proofs instead of disappearing with the process.
            if self._fallback:
                self._try_reopen()
            if self._connection is not None:
                try:
                    self._connection.commit()
                except Exception:
                    pass
                self._close_connection()
