"""Worker poller -- the tokenless transport loop on each worker computer.

Cycle: ask the control-plane for tasks assigned to me, claim a lease, run the
executor (the only token spend), report the result, repeat. A worker processes
one task at a time and never self-assigns; it acts only on tasks the PM already
routed to its agent id.

A background heartbeat renews the lease while a long task runs, so the reaper
does not reclaim work that is still in progress.
"""

from __future__ import annotations

import signal
import threading
import time

from .client import TaskClient, TaskClientError
from .contract import Task
from .executor import Executor, HermesCLIExecutor
from .settings import WorkerSettings


class _Heartbeat:
    """Renews a lease on an interval until stopped."""

    def __init__(self, client: TaskClient, task_id: str, interval: float) -> None:
        self._client = client
        self._task_id = task_id
        self._interval = max(interval, 15)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._client.heartbeat(self._task_id)
            except TaskClientError:
                pass

    def __enter__(self) -> "_Heartbeat":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()


class WorkerPoller:
    def __init__(self, settings: WorkerSettings, executor: Executor,
                 lease_ttl_hint: int = 900) -> None:
        self._s = settings
        self._client = TaskClient(settings.control_plane_url,
                                  settings.control_plane_token, settings.agent_id)
        self._executor = executor
        self._hb_interval = max(lease_ttl_hint / 3, 30)
        self._stop = threading.Event()

    def stop(self, *_) -> None:
        self._stop.set()

    def _handle(self, task: Task) -> None:
        # Claim work that is freshly assigned; resume our own in-progress task.
        if task.status == "assigned":
            leased = self._client.lease(task.task_id)
            if leased is None:
                return  # taken or not claimable; move on
            task = leased
        elif not (task.status == "in_progress"
                  and task.lease and task.lease.owner == self._s.agent_id):
            return

        with _Heartbeat(self._client, task.task_id, self._hb_interval):
            result = self._executor.run(task)

        if result.ok:
            self._client.report(task.task_id, "review",
                                result_ref=result.result_ref,
                                tokens_used=result.tokens_used)
        else:
            self._client.report(task.task_id, "blocked",
                                description=f"execution failed: {result.note}",
                                tokens_used=result.tokens_used)

    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        print(f"[poller] {self._s.agent_id} ({self._s.role}) polling "
              f"{self._s.control_plane_url} every {self._s.poll_interval_seconds}s")
        while not self._stop.is_set():
            try:
                for task in self._client.assigned():
                    if self._stop.is_set():
                        break
                    self._handle(task)
            except TaskClientError as exc:
                print(f"[poller] control-plane error: {exc}")
            except Exception as exc:  # keep the loop alive on unexpected errors
                print(f"[poller] unexpected error: {exc}")
            self._stop.wait(self._s.poll_interval_seconds)
        print("[poller] stopped")


def build_default_poller(settings: WorkerSettings, lease_ttl_hint: int = 900) -> WorkerPoller:
    executor = HermesCLIExecutor(
        command=settings.executor_cmd,
        agent_id=settings.agent_id,
        role=settings.role,
    )
    return WorkerPoller(settings, executor, lease_ttl_hint=lease_ttl_hint)
