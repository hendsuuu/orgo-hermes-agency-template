"""Environment-driven settings for the control-plane service and the worker.

Secrets arrive from the Orgo vault into /root/.env and are re-exported by the
bootstrap scripts. Nothing here reads a file directly; it reads the process
environment so the same code runs under systemd, a shell, or a test harness.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


@dataclass
class ServiceSettings:
    """Control-plane (Project Manager computer) settings."""
    notion_api_key: str
    tasks_db_id: str
    notion_version: str
    host: str
    port: int
    control_plane_token: str
    pm_token: str
    lease_ttl_seconds: int
    reap_interval_seconds: int
    # Telegram intake
    telegram_bot_token: str
    telegram_group_chat_id: str
    allowed_user_ids: frozenset[str]
    pm_user_ids: frozenset[str]
    intake_poll_seconds: int
    offset_file: str

    @classmethod
    def from_env(cls) -> "ServiceSettings":
        missing = [k for k in ("NOTION_API_KEY", "NOTION_TASKS_DATABASE_ID",
                               "AGENCY_CONTROL_PLANE_TOKEN")
                   if not os.environ.get(k)]
        if missing:
            raise SystemExit(f"control-plane missing required env: {', '.join(missing)}")
        allowed = _csv(os.environ.get("TELEGRAM_ALLOWED_USER_IDS", ""))
        return cls(
            notion_api_key=os.environ["NOTION_API_KEY"],
            tasks_db_id=os.environ["NOTION_TASKS_DATABASE_ID"],
            notion_version=os.environ.get("NOTION_VERSION", "2022-06-28"),
            host=os.environ.get("AGENCY_SERVICE_HOST", "0.0.0.0"),
            port=_int("AGENCY_SERVICE_PORT", 8787),
            control_plane_token=os.environ["AGENCY_CONTROL_PLANE_TOKEN"],
            pm_token=os.environ.get("AGENCY_PM_TOKEN", ""),
            lease_ttl_seconds=_int("AGENCY_LEASE_TTL", 900),
            reap_interval_seconds=_int("AGENCY_REAP_INTERVAL", 120),
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_group_chat_id=os.environ.get("TELEGRAM_GROUP_CHAT_ID", ""),
            allowed_user_ids=allowed,
            pm_user_ids=_csv(os.environ.get("TELEGRAM_PM_USER_IDS", "")),
            intake_poll_seconds=_int("AGENCY_INTAKE_POLL", 3),
            offset_file=os.environ.get("AGENCY_TG_OFFSET_FILE",
                                       "/opt/agency-runtime/.tg-offset"),
        )


@dataclass
class WorkerSettings:
    """Worker computer settings. No Notion token ever appears here."""
    agent_id: str
    role: str
    control_plane_url: str
    control_plane_token: str
    poll_interval_seconds: int
    executor_cmd: str

    @classmethod
    def from_env(cls) -> "WorkerSettings":
        missing = [k for k in ("AGENCY_AGENT_ID", "AGENCY_CONTROL_PLANE_URL",
                               "AGENCY_CONTROL_PLANE_TOKEN")
                   if not os.environ.get(k)]
        if missing:
            raise SystemExit(f"worker missing required env: {', '.join(missing)}")
        return cls(
            agent_id=os.environ["AGENCY_AGENT_ID"],
            role=os.environ.get("AGENCY_ROLE", "worker"),
            control_plane_url=os.environ["AGENCY_CONTROL_PLANE_URL"].rstrip("/"),
            control_plane_token=os.environ["AGENCY_CONTROL_PLANE_TOKEN"],
            poll_interval_seconds=_int("AGENCY_POLL_INTERVAL", 60),
            executor_cmd=os.environ.get("AGENCY_EXECUTOR_CMD", ""),
        )


def _csv(value: str) -> frozenset[str]:
    return frozenset(part.strip() for part in value.split(",") if part.strip())
