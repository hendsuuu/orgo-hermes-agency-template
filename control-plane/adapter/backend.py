"""Task backend abstraction -- the seam between transport and storage.

Phase 1 uses ``NotionTaskBackend``. Phase 2 (see the migration doc) adds a
Postgres implementation of this same interface; nothing above this seam changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .contract import Task


class TaskBackend(ABC):
    """Serialized authority over task records.

    Only the control-plane service instantiates a backend. Workers never do --
    they go through the HTTP interface in ``service`` / ``client``.
    """

    @abstractmethod
    def get(self, task_id: str) -> Optional[Task]:
        ...

    @abstractmethod
    def find_by_task_id(self, task_id: str) -> Optional[Task]:
        """Idempotency lookup. task_id is derived deterministically from the
        idempotency key, so this doubles as the duplicate check."""
        ...

    @abstractmethod
    def query(
        self,
        statuses: Optional[list[str]] = None,
        assigned_agent: Optional[str] = None,
        limit: int = 50,
    ) -> list[Task]:
        ...

    @abstractmethod
    def create(self, task: Task) -> Task:
        ...

    @abstractmethod
    def update(self, task_id: str, fields: dict) -> Task:
        """Patch a subset of fields. ``fields`` uses contract names, not
        backend property names."""
        ...
