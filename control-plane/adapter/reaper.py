"""Lease reaper.

An in-progress task whose lease has expired means its worker died, stalled, or
lost the network. The reaper moves such a task to ``blocked`` and clears the
lease, so the PM sees it and can reassign. Making it visible (rather than
silently re-queuing to a possibly-dead agent) is the phase-1 choice; automatic
retries and dead-lettering are phase-3 hardening in the migration doc.

Runs on the control-plane computer, which holds the backend.
"""

from __future__ import annotations

import threading

from .backend import TaskBackend
from .contract import utcnow_iso


class Reaper:
    def __init__(self, backend: TaskBackend, interval_seconds: int = 120) -> None:
        self._backend = backend
        self._interval = interval_seconds
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def sweep_once(self) -> int:
        reclaimed = 0
        for task in self._backend.query(statuses=["in_progress"], limit=100):
            if task.lease and task.lease.is_expired():
                note = f"{task.description}\n[lease expired {utcnow_iso()}; PM reassign]"
                self._backend.update(task.task_id, {
                    "status": "blocked", "lease": None, "description": note.strip(),
                })
                reclaimed += 1
                print(f"[reaper] reclaimed {task.task_id} (lease expired)")
        return reclaimed

    def run_forever(self) -> None:
        print(f"[reaper] sweeping every {self._interval}s")
        while not self._stop.is_set():
            try:
                self.sweep_once()
            except Exception as exc:  # never let the reaper die on one bad row
                print(f"[reaper] sweep error: {exc}")
            self._stop.wait(self._interval)
        print("[reaper] stopped")
