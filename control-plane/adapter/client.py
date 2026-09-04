"""Worker-side task client.

Depends only on the AgencyTask contract and the control-plane HTTP interface --
never on Notion. This is what keeps the phase-2 migration invisible to workers:
swap the backend behind the service and this client is unchanged.
"""

from __future__ import annotations

from typing import Optional

import requests

from .contract import Task


class TaskClientError(RuntimeError):
    pass


class TaskClient:
    def __init__(self, base_url: str, token: str, agent_id: str,
                 timeout: int = 30) -> None:
        self._base = base_url.rstrip("/")
        self._agent = agent_id
        self._timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {token}",
            "X-Agent-Id": agent_id,
            "Content-Type": "application/json",
        }

    def _call(self, method: str, path: str, json: Optional[dict] = None) -> dict:
        resp = requests.request(method, f"{self._base}{path}",
                                headers=self._headers, json=json,
                                timeout=self._timeout)
        if resp.status_code >= 400:
            raise TaskClientError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else {}

    def assigned(self) -> list[Task]:
        data = self._call("GET", "/tasks/assigned")
        return [Task.from_dict(t) for t in data.get("tasks", [])]

    def lease(self, task_id: str) -> Optional[Task]:
        """Claim a lease. Returns the leased Task, or None if it was not
        claimable (already taken / wrong status)."""
        try:
            data = self._call("POST", f"/tasks/{task_id}/lease")
        except TaskClientError as exc:
            if "409" in str(exc) or "403" in str(exc):
                return None
            raise
        return Task.from_dict(data["task"])

    def heartbeat(self, task_id: str) -> bool:
        try:
            self._call("POST", f"/tasks/{task_id}/heartbeat")
            return True
        except TaskClientError:
            return False

    def report(self, task_id: str, status: str, *,
               result_ref: Optional[str] = None,
               description: Optional[str] = None,
               tokens_used: int = 0) -> Task:
        body: dict = {"status": status, "tokens_used": tokens_used}
        if result_ref is not None:
            body["result_ref"] = result_ref
        if description is not None:
            body["description"] = description
        data = self._call("POST", f"/tasks/{task_id}/status", body)
        return Task.from_dict(data["task"])
