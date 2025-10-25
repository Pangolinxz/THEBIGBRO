"""Domain service helpers that leverage the Singleton DatabaseConnection."""

from __future__ import annotations

import time
from typing import Any, Dict

from django.utils import timezone

from infrastructure.database import DatabaseConnection


def database_health_summary() -> Dict[str, Any]:
    """
    Returns a JSON-serializable dict with connection metadata and the outcome
    of a simple heartbeat query. This is used by diagnostics endpoints.
    """
    db = DatabaseConnection()
    metadata = db.metadata()
    is_alive = db.is_alive()

    summary: Dict[str, Any] = {
        "engine": metadata.engine,
        "database": metadata.name,
        "host": metadata.host,
        "port": metadata.port,
        "checked_at": timezone.now().isoformat(),
        "status": "online" if is_alive else "offline",
    }

    if is_alive:
        summary["latency_ms"] = _probe_latency(db)
    else:
        summary["latency_ms"] = None

    return summary


def _probe_latency(db: DatabaseConnection) -> float:
    """Executes a trivial query and returns how long it took in ms."""
    start = time.perf_counter()
    db.execute("SELECT 1 AS alive")
    return round((time.perf_counter() - start) * 1000, 3)


__all__ = ["database_health_summary"]
