"""Local, read-only observability primitives for UGAS."""

from .events import TelemetryEvent
from .service import ObservabilityService

__all__ = ["ObservabilityService", "TelemetryEvent"]
