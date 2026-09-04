"""Command-line entry points.

  cd control-plane && python -m adapter.cli serve   # control-plane (PM computer)
  cd control-plane && python -m adapter.cli poll    # worker computer

``serve`` starts the HTTP task interface, the Telegram intake loop, and the lease
reaper in one process. ``poll`` runs the worker transport loop. The bootstrap
scripts pick the right command from the seeded role.
"""

from __future__ import annotations

import argparse
import os
import threading

from .intake import IntakeAdapter
from .notion_backend import NotionTaskBackend
from .poller import build_default_poller
from .reaper import Reaper
from .service import create_app
from .settings import ServiceSettings, WorkerSettings


def _serve() -> None:
    settings = ServiceSettings.from_env()
    backend = NotionTaskBackend(
        api_key=settings.notion_api_key,
        tasks_db_id=settings.tasks_db_id,
        notion_version=settings.notion_version,
    )

    intake = IntakeAdapter(settings, backend)
    reaper = Reaper(backend, interval_seconds=settings.reap_interval_seconds)
    threading.Thread(target=intake.run_forever, daemon=True).start()
    threading.Thread(target=reaper.run_forever, daemon=True).start()

    app = create_app(settings, backend)
    print(f"[service] listening on {settings.host}:{settings.port}")
    app.run(host=settings.host, port=settings.port, threaded=True)


def _poll() -> None:
    settings = WorkerSettings.from_env()
    lease_ttl = int(os.environ.get("AGENCY_LEASE_TTL", "900") or 900)
    poller = build_default_poller(settings, lease_ttl_hint=lease_ttl)
    poller.run_forever()


def main() -> None:
    parser = argparse.ArgumentParser(prog="agency-adapter")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="run the control-plane (PM computer)")
    sub.add_parser("poll", help="run the worker poller")
    args = parser.parse_args()
    if args.command == "serve":
        _serve()
    elif args.command == "poll":
        _poll()


if __name__ == "__main__":
    main()
