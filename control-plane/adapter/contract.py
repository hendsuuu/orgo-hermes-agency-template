"""Provider-neutral AgencyTask model, status machine, and guardrails.

This module is the integration boundary described in
``docs/notion-to-custom-migration.md``. Intake, the control-plane service, and
every worker depend on these types and rules -- never on Notion property names.
When the backend moves to Postgres in phase 2, only ``notion_backend`` changes;
this file and the workers stay untouched.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

# --- Status machine ---------------------------------------------------------

# Canonical order, mirrored exactly by the Notion "Status" property.
STATUSES = (
    "inbox", "triage", "assigned", "in_progress",
    "blocked", "review", "done", "cancelled",
)
TERMINAL_STATUSES = frozenset({"done", "cancelled"})

# Human-readable labels used by the Notion backend. Kept here so the contract
# owns the mapping and the backend stays a thin translation layer.
STATUS_LABELS = {
    "inbox": "Inbox", "triage": "Triage", "assigned": "Assigned",
    "in_progress": "In Progress", "blocked": "Blocked", "review": "Review",
    "done": "Done", "cancelled": "Cancelled",
}
LABEL_TO_STATUS = {label: key for key, label in STATUS_LABELS.items()}

PRIORITIES = ("critical", "high", "normal", "low")
SOURCES = ("slack", "pm", "notion", "api", "migration")

# Transitions the Project Manager (the sole dispatcher) may perform.
PM_TRANSITIONS = {
    "inbox": {"triage", "assigned", "cancelled"},
    "triage": {"assigned", "blocked", "cancelled"},
    "assigned": {"triage", "assigned", "blocked", "cancelled"},
    "in_progress": {"blocked", "triage", "cancelled"},
    "blocked": {"triage", "assigned", "cancelled"},
    "review": {"assigned", "done", "cancelled"},
    "done": set(),
    "cancelled": set(),
}

# Transitions a worker may perform, and only on a task assigned to itself.
WORKER_TRANSITIONS = {
    "assigned": {"in_progress"},
    "in_progress": {"blocked", "review", "done"},
    "blocked": {"in_progress"},
}

# Fields a worker is allowed to write. Assignment, priority, and project are
# owned by the PM; the service rejects any worker attempt to touch them.
WORKER_WRITABLE_FIELDS = frozenset({
    "status", "description", "result_ref", "tokens_used", "lease", "updated_at",
})

_TASK_ID_RE = re.compile(r"^tsk_[a-z0-9_-]{8,}$")


class ContractError(ValueError):
    """Raised when a task payload or transition violates the contract."""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def derive_task_id(idempotency_key: str) -> str:
    """Deterministic task id from an idempotency key.

    The same Slack message (channel_id + ts) always maps to the same task id,
    so a replayed event finds the existing task instead of creating a
    duplicate.
    """
    digest = hashlib.sha1(idempotency_key.encode("utf-8")).hexdigest()[:16]
    return f"tsk_{digest}"


@dataclass
class Lease:
    owner: str
    acquired_at: str
    expires_at: str

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return parse_iso(self.expires_at) < now


@dataclass
class Task:
    task_id: str
    title: str
    project: str
    status: str
    priority: str
    source: str
    requested_by: str
    created_at: str
    suggested_assignee: Optional[str] = None
    assigned_agent: Optional[str] = None
    parent_task_id: Optional[str] = None
    slack: Optional[dict[str, Any]] = None
    description: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    approval_required: bool = False
    idempotency_key: Optional[str] = None
    result_ref: Optional[str] = None
    tokens_used: int = 0
    lease: Optional[Lease] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.lease is None:
            data["lease"] = None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        payload = dict(data)
        lease = payload.get("lease")
        if isinstance(lease, dict):
            payload["lease"] = Lease(**lease)
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        payload = {k: v for k, v in payload.items() if k in known}
        return cls(**payload)

    def validate(self) -> "Task":
        if not _TASK_ID_RE.match(self.task_id):
            raise ContractError(f"invalid task_id: {self.task_id!r}")
        if not (3 <= len(self.title) <= 200):
            raise ContractError("title length must be 3..200")
        if self.status not in STATUSES:
            raise ContractError(f"invalid status: {self.status!r}")
        if self.priority not in PRIORITIES:
            raise ContractError(f"invalid priority: {self.priority!r}")
        if self.source not in SOURCES:
            raise ContractError(f"invalid source: {self.source!r}")
        if not self.project:
            raise ContractError("project is required")
        if not self.requested_by:
            raise ContractError("requested_by is required")
        return self


def check_transition(actor_role: str, current: str, target: str) -> None:
    """Raise ContractError if the actor may not move current -> target.

    ``actor_role`` is either "pm" or "worker". Callers must separately verify
    that a worker actor owns the task it is transitioning.
    """
    if target not in STATUSES:
        raise ContractError(f"invalid target status: {target!r}")
    table = PM_TRANSITIONS if actor_role == "pm" else WORKER_TRANSITIONS
    allowed = table.get(current, set())
    if target not in allowed:
        raise ContractError(
            f"{actor_role} may not move task from {current!r} to {target!r}"
        )


def new_lease(owner: str, ttl_seconds: int) -> Lease:
    now = datetime.now(timezone.utc)
    expires = datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=timezone.utc)
    return Lease(
        owner=owner,
        acquired_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        expires_at=expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
