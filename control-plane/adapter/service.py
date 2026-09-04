"""Control-plane HTTP interface -- the adapter's task interface.

Workers never hold the Notion token; they call these endpoints instead. The
service enforces the non-negotiable operating model:

- Workers act only on tasks assigned to their own agent id.
- Workers may only perform worker-legal status transitions (contract.py).
- Only the PM path may create tasks or write assignment fields.

Auth: every request carries ``Authorization: Bearer <token>``. Worker endpoints
accept the shared control-plane token and require ``X-Agent-Id`` to match the
task's assignee. PM/admin endpoints require the PM token (falls back to the
control-plane token if a separate PM token is not configured -- a phase-3
hardening is to always separate them).
"""

from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import Flask, jsonify, request

from .backend import TaskBackend
from .contract import (
    Task, ContractError, check_transition, new_lease, utcnow_iso,
)
from .settings import ServiceSettings


def create_app(settings: ServiceSettings, backend: TaskBackend) -> Flask:
    app = Flask(__name__)
    pm_token = settings.pm_token or settings.control_plane_token

    def _bearer() -> str:
        header = request.headers.get("Authorization", "")
        return header[7:] if header.startswith("Bearer ") else ""

    def require_worker(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if _bearer() != settings.control_plane_token:
                return jsonify(error="unauthorized"), 401
            agent = request.headers.get("X-Agent-Id", "")
            if not agent:
                return jsonify(error="missing X-Agent-Id"), 400
            return fn(agent, *args, **kwargs)
        return wrapper

    def require_pm(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if _bearer() != pm_token:
                return jsonify(error="pm authorization required"), 401
            return fn(*args, **kwargs)
        return wrapper

    # --- health ------------------------------------------------------------

    @app.get("/health")
    def health():
        return jsonify(status="ok", ts=utcnow_iso())

    # --- worker endpoints --------------------------------------------------

    @app.get("/tasks/assigned")
    @require_worker
    def assigned(agent: str):
        """The calling worker's actionable queue: newly assigned work plus any
        of its own in-progress tasks (so it can resume after a restart)."""
        tasks = backend.query(statuses=["assigned", "in_progress"],
                              assigned_agent=agent, limit=25)
        return jsonify(tasks=[t.to_dict() for t in tasks])

    @app.post("/tasks/<task_id>/lease")
    @require_worker
    def lease(agent: str, task_id: str):
        task = backend.get(task_id)
        if task is None:
            return jsonify(error="not found"), 404
        if task.assigned_agent != agent:
            return jsonify(error="not your task"), 403
        if task.status == "assigned":
            lease_obj = new_lease(agent, settings.lease_ttl_seconds)
            updated = backend.update(task_id, {
                "status": "in_progress", "lease": lease_obj.__dict__,
            })
            return jsonify(task=updated.to_dict(), leased=True)
        if task.status == "in_progress" and task.lease and task.lease.owner == agent:
            lease_obj = new_lease(agent, settings.lease_ttl_seconds)
            updated = backend.update(task_id, {"lease": lease_obj.__dict__})
            return jsonify(task=updated.to_dict(), leased=True, renewed=True)
        return jsonify(error=f"not claimable in status {task.status}"), 409

    @app.post("/tasks/<task_id>/heartbeat")
    @require_worker
    def heartbeat(agent: str, task_id: str):
        task = backend.get(task_id)
        if task is None or task.assigned_agent != agent:
            return jsonify(error="not your task"), 403
        if not (task.lease and task.lease.owner == agent):
            return jsonify(error="no lease held"), 409
        lease_obj = new_lease(agent, settings.lease_ttl_seconds)
        backend.update(task_id, {"lease": lease_obj.__dict__})
        return jsonify(ok=True, expires_at=lease_obj.expires_at)

    @app.post("/tasks/<task_id>/status")
    @require_worker
    def worker_status(agent: str, task_id: str):
        body = request.get_json(force=True, silent=True) or {}
        target = body.get("status")
        task = backend.get(task_id)
        if task is None:
            return jsonify(error="not found"), 404
        if task.assigned_agent != agent:
            return jsonify(error="not your task"), 403
        try:
            check_transition("worker", task.status, target)
        except ContractError as exc:
            return jsonify(error=str(exc)), 422

        fields: dict = {"status": target}
        if "result_ref" in body:
            fields["result_ref"] = body["result_ref"]
        if "description" in body:
            fields["description"] = body["description"]
        if "tokens_used" in body:
            fields["tokens_used"] = int(body["tokens_used"])
        # Lease lifecycle: hold while working, release when leaving in_progress.
        if target == "in_progress":
            fields["lease"] = new_lease(agent, settings.lease_ttl_seconds).__dict__
        elif target in ("review", "done", "blocked"):
            fields["lease"] = None
        updated = backend.update(task_id, fields)
        return jsonify(task=updated.to_dict())

    # --- PM / admin endpoints ---------------------------------------------

    @app.post("/admin/tasks")
    @require_pm
    def admin_create():
        body = request.get_json(force=True, silent=True) or {}
        try:
            task = Task.from_dict(body).validate()
        except (ContractError, TypeError) as exc:
            return jsonify(error=str(exc)), 422
        created = backend.create(task)
        return jsonify(task=created.to_dict()), 201

    @app.post("/admin/tasks/<task_id>/assign")
    @require_pm
    def admin_assign(task_id: str):
        body = request.get_json(force=True, silent=True) or {}
        agent = body.get("assigned_agent")
        if not agent:
            return jsonify(error="assigned_agent required"), 422
        task = backend.get(task_id)
        if task is None:
            return jsonify(error="not found"), 404
        try:
            check_transition("pm", task.status, "assigned")
        except ContractError as exc:
            return jsonify(error=str(exc)), 422
        updated = backend.update(task_id, {
            "status": "assigned", "assigned_agent": agent, "lease": None,
        })
        return jsonify(task=updated.to_dict())

    @app.post("/admin/tasks/<task_id>/transition")
    @require_pm
    def admin_transition(task_id: str):
        body = request.get_json(force=True, silent=True) or {}
        target = body.get("status")
        task = backend.get(task_id)
        if task is None:
            return jsonify(error="not found"), 404
        try:
            check_transition("pm", task.status, target)
        except ContractError as exc:
            return jsonify(error=str(exc)), 422
        fields = {"status": target}
        for key in ("assigned_agent", "priority", "description", "parent_task_id"):
            if key in body:
                fields[key] = body[key]
        updated = backend.update(task_id, fields)
        return jsonify(task=updated.to_dict())

    @app.get("/admin/tasks")
    @require_pm
    def admin_list():
        statuses = request.args.get("status")
        status_list = statuses.split(",") if statuses else None
        tasks = backend.query(statuses=status_list, limit=100)
        return jsonify(tasks=[t.to_dict() for t in tasks])

    return app
