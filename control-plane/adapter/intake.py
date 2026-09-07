"""Slack intake adapter.

Turns allowed human channel messages into idempotent task records, enforcing
the intake contract (slack/intake-contract.md):

- Bot-authored messages are never intake (no bot-to-bot loops).
- Only configured human users in the configured channel are accepted.
- A single role tag -> one Inbox task with that role as suggested assignee.
- Several role tags -> one Inbox parent task for PM triage (not parallel tasks).
- A PM "/assign <agent-id> <title>" message -> an Assigned task.
- The duplicate key slack:<channel_id>:<ts> makes replays a no-op.

This runs on the control-plane computer, which is the only holder of the Notion
token. It is deterministic transport -- no model tokens are spent here.

Connects to Slack over Socket Mode (an outbound WebSocket opened with
SLACK_APP_TOKEN), so no public inbound endpoint or signing secret is needed.
Unlike Telegram's long-poll offset, Slack does not replay events to a
disconnected Socket Mode client: a message sent while this process is down is
missed, not caught up on reconnect.
"""

from __future__ import annotations

import re
import threading
from typing import Optional

from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from .backend import TaskBackend
from .contract import Task, derive_task_id, utcnow_iso
from .settings import ServiceSettings

# Slack role alias -> role file name (mirrors slack/routing.template.yaml).
ROLE_ALIASES = {
    "ceo": "ceo",
    "pm": "project-manager", "project-manager": "project-manager",
    "developer": "developer", "dev": "developer",
    "marketing": "marketing",
    "content": "content-creator", "content-creator": "content-creator",
    "finance": "accountant", "accountant": "accountant",
    "researcher": "researcher", "research": "researcher",
    "ops": "ops-provisioner", "ops-provisioner": "ops-provisioner",
}

_TAG_RE = re.compile(r"@([a-z][a-z0-9\-]{1,30})", re.IGNORECASE)
_ASSIGN_RE = re.compile(r"^/assign\s+(\S+)\s+(.+)$", re.IGNORECASE | re.DOTALL)


class IntakeAdapter:
    def __init__(self, settings: ServiceSettings, backend: TaskBackend) -> None:
        self._s = settings
        self._backend = backend
        self._stop = threading.Event()
        self._client: Optional[SocketModeClient] = None

    def stop(self) -> None:
        self._stop.set()
        if self._client is not None:
            self._client.close()

    # --- message classification (pure, testable) ---------------------------

    def classify(self, event: dict) -> Optional[Task]:
        """Return a Task to create, or None if the event is not intake."""
        text = (event.get("text") or "").strip()
        channel_id = str(event.get("channel", ""))
        user_id = str(event.get("user", ""))
        ts = str(event.get("ts", ""))
        thread_ts = event.get("thread_ts")

        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return None
        if self._s.slack_channel_id and channel_id != self._s.slack_channel_id:
            return None
        if self._s.allowed_user_ids and user_id not in self._s.allowed_user_ids:
            return None
        if not text:
            return None

        key = f"slack:{channel_id}:{ts}"
        task_id = derive_task_id(key)
        if self._backend.find_by_task_id(task_id) is not None:
            return None  # idempotent: already ingested

        base = dict(
            task_id=task_id, project="inbox", priority="normal",
            source="slack", requested_by=user_id, created_at=utcnow_iso(),
            idempotency_key=key, description=text,
            slack={"channel_id": channel_id, "ts": ts, "thread_ts": thread_ts},
        )

        # PM explicit assignment.
        assign = _ASSIGN_RE.match(text)
        if assign and user_id in self._s.pm_user_ids:
            agent_id, title = assign.group(1), assign.group(2).strip()
            return Task(title=_clip(title), status="assigned",
                        assigned_agent=agent_id, **base)

        # Role tags.
        roles = _extract_roles(text)
        if len(roles) == 1:
            return Task(title=_clip(text), status="inbox",
                        suggested_assignee=roles[0], **base)
        # Zero or several tags: a single Inbox task for PM triage.
        return Task(title=_clip(text), status="inbox", **base)

    def _process_event(self, event: dict) -> None:
        if event.get("type") != "message":
            return
        task = self.classify(event)
        if task is None:
            return
        try:
            created = self._backend.create(task.validate())
            print(f"[intake] created {created.task_id} ({created.status})")
        except Exception as exc:
            print(f"[intake] create failed for {task.task_id}: {exc}")

    # --- Socket Mode loop ----------------------------------------------------

    def _on_socket_request(self, client: SocketModeClient,
                            request: SocketModeRequest) -> None:
        # Slack requires every envelope to be acked within 3 seconds.
        client.send_socket_mode_response(
            SocketModeResponse(envelope_id=request.envelope_id)
        )
        if request.type != "events_api":
            return
        event = request.payload.get("event") or {}
        self._process_event(event)

    def run_forever(self) -> None:
        if not self._s.slack_bot_token or not self._s.slack_app_token:
            print("[intake] SLACK_BOT_TOKEN/SLACK_APP_TOKEN unset; intake disabled")
            return
        print(f"[intake] listening on channel {self._s.slack_channel_id or '(any)'}")
        web_client = WebClient(token=self._s.slack_bot_token)
        client = SocketModeClient(app_token=self._s.slack_app_token, web_client=web_client)
        client.socket_mode_request_listeners.append(self._on_socket_request)
        self._client = client
        while not self._stop.is_set():
            try:
                client.connect()
                self._stop.wait()
            except Exception as exc:
                print(f"[intake] slack error: {exc}")
                self._stop.wait(self._s.intake_poll_seconds)
        client.close()
        print("[intake] stopped")


def _extract_roles(text: str) -> list[str]:
    seen: list[str] = []
    for match in _TAG_RE.findall(text):
        role = ROLE_ALIASES.get(match.lower())
        if role and role not in seen:
            seen.append(role)
    return seen


def _clip(text: str, limit: int = 180) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
