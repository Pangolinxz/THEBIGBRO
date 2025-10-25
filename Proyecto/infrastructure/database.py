"""
Thread-safe Singleton that exposes a single database connection for the entire
LogiTrace process. It wraps Django's connection handler so every component that
needs raw SQL uses the same, reusable connection rather than instantiating new
ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List

from django.db import connections


@dataclass(frozen=True)
class DatabaseSettingsSnapshot:
    """Small helper to expose the DB settings that back the singleton."""

    engine: str
    name: str
    user: str
    host: str
    port: str


class DatabaseConnection:
    """
    Singleton facade around Django's default connection. Only one instance of
    this class will ever exist, guaranteeing that all low-level operations share
    a single connection object (and pool) regardless of where they are invoked.
    """

    _instance: "DatabaseConnection | None" = None
    _lock: Lock = Lock()

    def __new__(cls) -> "DatabaseConnection":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._connection_alias = "default"
                    cls._instance._connection_wrapper = None
        return cls._instance

    def _wrapper(self):
        """
        Lazily bootstraps or reuses the same Django database wrapper so the
        underlying driver connection is shared application-wide.
        """
        if (
            self._connection_wrapper is None
            or not self._connection_wrapper.is_usable()
        ):
            self._connection_wrapper = connections[self._connection_alias]
            self._connection_wrapper.ensure_connection()
        return self._connection_wrapper

    def execute(self, sql: str, params: List[Any] | None = None) -> List[Dict[str, Any]]:
        """
        Executes raw SQL using the singleton connection and returns a list of
        dicts (column -> value) when the statement yields rows.
        """
        wrapper = self._wrapper()
        params = params or []
        with wrapper.cursor() as cursor:
            cursor.execute(sql, params)
            if cursor.description:
                columns = [col[0] for col in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            else:
                rows = []
        return rows

    def close(self) -> None:
        """Explicitly closes the shared connection (mainly for tests or CLI tools)."""
        if self._connection_wrapper:
            self._connection_wrapper.close()
            self._connection_wrapper = None

    def metadata(self) -> DatabaseSettingsSnapshot:
        """Expose read-only connection settings for observability endpoints."""
        settings = connections.databases.get(self._connection_alias, {})
        return DatabaseSettingsSnapshot(
            engine=settings.get("ENGINE", ""),
            name=settings.get("NAME", ""),
            user=settings.get("USER", ""),
            host=settings.get("HOST", ""),
            port=str(settings.get("PORT", "")),
        )

    def is_alive(self) -> bool:
        """
        Run a very cheap heartbeat query to confirm the DB is reachable without
        forcing callers to handle driver-specific exceptions.
        """
        try:
            self.execute("SELECT 1")
            return True
        except Exception:
            self.close()
            return False


__all__ = ["DatabaseConnection", "DatabaseSettingsSnapshot"]
