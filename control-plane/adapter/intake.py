"""Telegram intake adapter.

Turns allowed human group messages into idempotent task records, enforcing the
intake contract (telegram/intake-contract.md):

- Bot-authored messages are never intake (no bot-to-bot loops).
- Only configured human users in the configured group are accepted.
- A single role tag -> one Inbox task with that role as suggested assignee.
- Several role tags -> one Inbox parent task for PM triage (not parallel tasks).
- A PM "/assign <agent-id> <title>" message -> an Assigned task.
- The duplicate key telegram:<chat_id>:<message_id> makes replays a no-op.

This runs on the control-plane computer, which is the only holder of the Notion
token. It is deterministic transport -- no model tokens are spent here.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Optional

import requests

from .backend import TaskBackend
from .contract import Task, derive_task_id, utcnow_iso
from .settings import ServiceSettings

_TG_API = "https://api.telegram.org"

# Telegram role alias -> role file name (mirrors telegram/routing.template.yaml).
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
        self._offset_path = Path(settings.offset_file)
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    # --- message classification (pure, testable) ---------------------------

    def classify(self, message: dict) -> Optional[Task]:
        """Return a Task to create, or None if the message is not intake."""
        frm = message.get("from") or {}
        chat = message.get("chat") or {}
        text = (message.get("text") or "").strip()
        chat_id = str(chat.get("id", ""))
        user_id = str(frm.get("id", ""))
        message_id = str(message.get("message_id", ""))

        if frm.get("is_bot"):
            return None
        if self._s.telegram_group_chat_id and chat_id != self._s.telegram_group_chat_id:
            return None
        if self._s.allowed_user_ids and user_id not in self._s.allowed_user_ids:
            return None
        if not text:
            return None

        key = f"telegram:{chat_id}:{message_id}"
        task_id = derive_task_id(key)
        if self._backend.find_by_task_id(task_id) is not None:
            return None  # idempotent: already ingested

        base = dict(
            task_id=task_id, project="inbox", priority="normal",
            source="telegram", requested_by=user_id, created_at=utcnow_iso(),
            idempotency_key=key, description=text,
            telegram={"chat_id": chat_id, "message_id": message_id},
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

    def _process_update(self, update: dict) -> None:
        message = update.get("message") or update.get("channel_post")
        if not message:
            return
        task = self.classify(message)
        if task is None:
            return
        try:
            created = self._backend.create(task.validate())
            print(f"[intake] created {created.task_id} ({created.status})")
        except Exception as exc:
            print(f"[intake] create failed for {task.task_id}: {exc}")

    # --- long-poll loop ----------------------------------------------------

    def run_forever(self) -> None:
        if not self._s.telegram_bot_token:
            print("[intake] TELEGRAM_BOT_TOKEN unset; intake disabled")
            return
        offset = self._load_offset()
        print(f"[intake] listening on group {self._s.telegram_group_chat_id or '(any)'}")
        base = f"{_TG_API}/bot{self._s.telegram_bot_token}"
        while not self._stop.is_set():
            try:
                resp = requests.get(
                    f"{base}/getUpdates",
                    params={"offset": offset, "timeout": 25,
                            "allowed_updates": '["message"]'},
                    timeout=40,
                )
                data = resp.json()
                if not data.get("ok"):
                    self._stop.wait(self._s.intake_poll_seconds)
                    continue
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    self._process_update(update)
                    self._save_offset(offset)
            except requests.RequestException as exc:
                print(f"[intake] telegram error: {exc}")
                self._stop.wait(self._s.intake_poll_seconds)
        print("[intake] stopped")

    def _load_offset(self) -> int:
        try:
            return int(self._offset_path.read_text().strip())
        except (OSError, ValueError):
            return 0

    def _save_offset(self, offset: int) -> None:
        try:
            self._offset_path.parent.mkdir(parents=True, exist_ok=True)
            self._offset_path.write_text(str(offset))
        except OSError:
            pass


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
