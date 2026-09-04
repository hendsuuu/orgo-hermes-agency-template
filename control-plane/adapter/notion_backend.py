"""Notion implementation of TaskBackend (phase 1 authority).

Only the control-plane service uses this class, so the Notion token stays on the
Project Manager / control-plane computer and never reaches a worker. Machine
fields that the adapter filters on (assigned agent, parent, lease) are stored as
rich-text / date mirror properties, so the fleet does not need per-agent Notion
page IDs to run. Human-facing relation properties can be maintained alongside for
planning views without affecting transport.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import requests

from .backend import TaskBackend
from .contract import (
    Lease, Task, STATUS_LABELS, LABEL_TO_STATUS, ContractError,
)

_API = "https://api.notion.com/v1"

# contract field -> (Notion property name, Notion type)
_PROPS: dict[str, tuple[str, str]] = {
    "task_id": ("Task ID", "rich_text"),
    "title": ("Title", "title"),
    "project": ("Project", "select"),
    "status": ("Status", "status"),
    "priority": ("Priority", "select"),
    "requested_by": ("Requested By", "rich_text"),
    "source": ("Source", "select"),
    "suggested_assignee": ("Suggested Assignee ID", "rich_text"),
    "assigned_agent": ("Assigned Agent ID", "rich_text"),
    "parent_task_id": ("Parent Task ID", "rich_text"),
    "description": ("Description", "rich_text"),
    "acceptance_criteria": ("Acceptance Criteria", "rich_text"),
    "approval_required": ("Approval Required", "checkbox"),
    "result_ref": ("Result Ref", "rich_text"),
    "tokens_used": ("Tokens Used", "number"),
    "idempotency_key": ("Idempotency Key", "rich_text"),
    "telegram_ref": ("Telegram Message", "rich_text"),
    "lease_owner": ("Lease Owner", "rich_text"),
    "lease_expires": ("Lease Expires", "date"),
}

_MAX_TEXT = 2000  # Notion per-rich-text content limit.


class NotionTaskBackend(TaskBackend):
    def __init__(self, api_key: str, tasks_db_id: str,
                 notion_version: str = "2022-06-28", timeout: int = 30) -> None:
        self._db = tasks_db_id
        self._timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": notion_version,
            "Content-Type": "application/json",
        }

    # --- HTTP with light 429 handling --------------------------------------

    def _request(self, method: str, path: str, json: Optional[dict] = None) -> dict:
        url = f"{_API}{path}"
        for attempt in range(5):
            resp = requests.request(method, url, headers=self._headers,
                                     json=json, timeout=self._timeout)
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", "1"))
                time.sleep(min(wait, 10))
                continue
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Notion {method} {path} -> {resp.status_code}: {resp.text[:400]}"
                )
            return resp.json()
        raise RuntimeError(f"Notion {method} {path} rate-limited after retries")

    # --- value encoders / decoders -----------------------------------------

    @staticmethod
    def _encode(value: Any, ptype: str) -> dict:
        if ptype == "title":
            return {"title": [{"text": {"content": str(value)[:_MAX_TEXT]}}] if value else []}
        if ptype == "rich_text":
            text = "" if value is None else str(value)
            return {"rich_text": [{"text": {"content": text[:_MAX_TEXT]}}] if text else []}
        if ptype == "select":
            return {"select": {"name": str(value)} if value else None}
        if ptype == "status":
            return {"status": {"name": STATUS_LABELS[value]}}
        if ptype == "checkbox":
            return {"checkbox": bool(value)}
        if ptype == "number":
            return {"number": value if value is not None else 0}
        if ptype == "date":
            return {"date": {"start": value} if value else None}
        raise ValueError(f"unknown property type {ptype}")

    @staticmethod
    def _decode(prop: dict) -> Any:
        ptype = prop.get("type")
        if ptype in ("title", "rich_text"):
            parts = prop.get(ptype, [])
            out = []
            for p in parts:
                if p.get("plain_text") is not None:
                    out.append(p["plain_text"])
                elif isinstance(p.get("text"), dict):
                    out.append(p["text"].get("content", ""))
            return "".join(out)
        if ptype == "select":
            sel = prop.get("select")
            return sel.get("name") if sel else None
        if ptype == "status":
            st = prop.get("status")
            return st.get("name") if st else None
        if ptype == "checkbox":
            return bool(prop.get("checkbox"))
        if ptype == "number":
            return prop.get("number") or 0
        if ptype == "date":
            d = prop.get("date")
            return d.get("start") if d else None
        return None

    def _task_to_props(self, task: Task, only: Optional[set[str]] = None) -> dict:
        """Build a Notion properties payload. ``only`` restricts to a subset of
        contract fields for partial updates."""
        props: dict[str, dict] = {}

        def put(field_key: str, value: Any) -> None:
            name, ptype = _PROPS[field_key]
            props[name] = self._encode(value, ptype)

        want = only if only is not None else set(_simple_fields())
        if only is None or "task_id" in only:
            put("task_id", task.task_id)
        if "title" in want:
            put("title", task.title)
        if "project" in want:
            put("project", task.project)
        if "status" in want:
            put("status", task.status)
        if "priority" in want:
            put("priority", task.priority)
        if "requested_by" in want:
            put("requested_by", task.requested_by)
        if "source" in want:
            put("source", task.source)
        if "suggested_assignee" in want:
            put("suggested_assignee", task.suggested_assignee or "")
        if "assigned_agent" in want:
            put("assigned_agent", task.assigned_agent or "")
        if "parent_task_id" in want:
            put("parent_task_id", task.parent_task_id or "")
        if "description" in want:
            put("description", task.description or "")
        if "acceptance_criteria" in want:
            put("acceptance_criteria", "\n".join(task.acceptance_criteria))
        if "approval_required" in want:
            put("approval_required", task.approval_required)
        if "result_ref" in want:
            put("result_ref", task.result_ref or "")
        if "tokens_used" in want:
            put("tokens_used", task.tokens_used)
        if only is None or "idempotency_key" in only:
            put("idempotency_key", task.idempotency_key or "")
        if only is None or "telegram" in only:
            ref = ""
            if task.telegram:
                ref = f"{task.telegram.get('chat_id','')}:{task.telegram.get('message_id','')}"
            props[_PROPS["telegram_ref"][0]] = self._encode(ref, "rich_text")
        if only is None or "lease" in only:
            if task.lease:
                put("lease_owner", task.lease.owner)
                put("lease_expires", task.lease.expires_at)
            else:
                put("lease_owner", "")
                put("lease_expires", None)
        return props

    def _page_to_task(self, page: dict) -> Task:
        p = page["properties"]

        def g(field_key: str) -> Any:
            name, _ = _PROPS[field_key]
            return self._decode(p[name]) if name in p else None

        status_label = g("status")
        status = LABEL_TO_STATUS.get(status_label, "inbox") if status_label else "inbox"
        ac = g("acceptance_criteria") or ""
        lease_owner = g("lease_owner")
        lease_expires = g("lease_expires")
        lease = None
        if lease_owner and lease_expires:
            lease = Lease(owner=lease_owner, acquired_at=page.get("created_time", ""),
                          expires_at=_as_zulu(lease_expires))
        telegram_ref = g("telegram_ref") or ""
        telegram = None
        if ":" in telegram_ref:
            chat_id, _, message_id = telegram_ref.partition(":")
            telegram = {"chat_id": chat_id, "message_id": message_id}
        return Task(
            task_id=g("task_id") or "",
            title=g("title") or "",
            project=g("project") or "unassigned",
            status=status,
            priority=g("priority") or "normal",
            source=g("source") or "notion",
            requested_by=g("requested_by") or "unknown",
            created_at=_as_zulu(page.get("created_time", "")),
            suggested_assignee=g("suggested_assignee") or None,
            assigned_agent=g("assigned_agent") or None,
            parent_task_id=g("parent_task_id") or None,
            telegram=telegram,
            description=g("description") or "",
            acceptance_criteria=[l for l in ac.split("\n") if l],
            approval_required=bool(g("approval_required")),
            idempotency_key=g("idempotency_key") or None,
            result_ref=g("result_ref") or None,
            tokens_used=int(g("tokens_used") or 0),
            lease=lease,
            updated_at=_as_zulu(page.get("last_edited_time", "")),
        )

    # --- TaskBackend interface ---------------------------------------------

    def create(self, task: Task) -> Task:
        task.validate()
        body = {"parent": {"database_id": self._db},
                "properties": self._task_to_props(task)}
        page = self._request("POST", "/pages", body)
        return self._page_to_task(page)

    def get(self, task_id: str) -> Optional[Task]:
        return self.find_by_task_id(task_id)

    def find_by_task_id(self, task_id: str) -> Optional[Task]:
        name, _ = _PROPS["task_id"]
        body = {"filter": {"property": name, "rich_text": {"equals": task_id}},
                "page_size": 1}
        data = self._request("POST", f"/databases/{self._db}/query", body)
        results = data.get("results", [])
        return self._page_to_task(results[0]) if results else None

    def query(self, statuses: Optional[list[str]] = None,
              assigned_agent: Optional[str] = None, limit: int = 50) -> list[Task]:
        and_filters: list[dict] = []
        if statuses:
            sname, _ = _PROPS["status"]
            or_filters = [{"property": sname, "status": {"equals": STATUS_LABELS[s]}}
                          for s in statuses]
            and_filters.append({"or": or_filters})
        if assigned_agent:
            aname, _ = _PROPS["assigned_agent"]
            and_filters.append({"property": aname, "rich_text": {"equals": assigned_agent}})
        body: dict[str, Any] = {"page_size": min(limit, 100)}
        if and_filters:
            body["filter"] = and_filters[0] if len(and_filters) == 1 else {"and": and_filters}
        data = self._request("POST", f"/databases/{self._db}/query", body)
        return [self._page_to_task(pg) for pg in data.get("results", [])]

    def _page_id_for(self, task_id: str) -> str:
        name, _ = _PROPS["task_id"]
        body = {"filter": {"property": name, "rich_text": {"equals": task_id}},
                "page_size": 1}
        data = self._request("POST", f"/databases/{self._db}/query", body)
        results = data.get("results", [])
        if not results:
            raise ContractError(f"task not found: {task_id}")
        return results[0]["id"]

    def update(self, task_id: str, fields: dict) -> Task:
        page_id = self._page_id_for(task_id)
        # Reuse the encoder by projecting ``fields`` onto a partial Task.
        stub = Task(
            task_id=task_id, title="x", project="x", status=fields.get("status", "inbox"),
            priority=fields.get("priority", "normal"), source="api",
            requested_by="system", created_at="1970-01-01T00:00:00Z",
        )
        lease = fields.get("lease")
        if isinstance(lease, dict):
            stub.lease = Lease(**lease)
        elif isinstance(lease, Lease):
            stub.lease = lease
        for key in ("assigned_agent", "suggested_assignee", "parent_task_id",
                    "description", "result_ref", "tokens_used"):
            if key in fields:
                setattr(stub, key, fields[key])
        if "acceptance_criteria" in fields:
            stub.acceptance_criteria = fields["acceptance_criteria"]
        if "approval_required" in fields:
            stub.approval_required = fields["approval_required"]

        only = set(fields.keys())
        props = self._task_to_props(stub, only=only)
        self._request("PATCH", f"/pages/{page_id}", {"properties": props})
        updated = self.find_by_task_id(task_id)
        assert updated is not None
        return updated


def _simple_fields() -> list[str]:
    return ["title", "project", "status", "priority", "requested_by", "source",
            "suggested_assignee", "assigned_agent", "parent_task_id",
            "description", "acceptance_criteria", "approval_required",
            "result_ref", "tokens_used", "lease"]


def _as_zulu(value: str) -> str:
    """Normalize a Notion ISO timestamp to the contract's ...Z form."""
    if not value:
        return ""
    v = value.replace("+00:00", "Z")
    if len(v) > 20 and "." in v:  # trim milliseconds Notion sometimes returns
        head, _, tail = v.partition(".")
        v = head + "Z" if tail else v
    return v
