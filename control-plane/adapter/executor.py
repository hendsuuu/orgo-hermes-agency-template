"""Executor -- the only place a worker spends model tokens.

The poller is pure transport (no LLM). When it has claimed a task, it hands the
task to an Executor, which runs the local Hermes agent to actually do the work.

Hermes' exact headless invocation is deployment-specific, so the command is
configurable via ``AGENCY_EXECUTOR_CMD`` rather than hard-coded here. The command
receives the task through environment variables and a JSON file, and is expected
to print a final line of JSON: ``{"result_ref": "...", "tokens_used": N}``. If it
prints no such line, its stdout is saved to a local file and used as the result
reference. This keeps the transport honest about the one integration point that
depends on your Hermes build -- set ``AGENCY_EXECUTOR_CMD`` to wire it in.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .contract import Task, utcnow_iso


@dataclass
class ExecutionResult:
    ok: bool
    result_ref: str = ""
    tokens_used: int = 0
    note: str = ""


def build_task_brief(task: Task) -> str:
    """Compact, cost-aware brief. Pointers and acceptance criteria only -- never
    a context dump. The executor / Hermes retrieves details on demand."""
    lines = [f"Task {task.task_id}: {task.title}", f"Project: {task.project}"]
    if task.description:
        lines.append(f"Goal: {task.description}")
    if task.acceptance_criteria:
        lines.append("Acceptance criteria:")
        lines += [f"  - {c}" for c in task.acceptance_criteria]
    if task.approval_required:
        lines.append("NOTE: high-impact actions require inline Telegram approval.")
    return "\n".join(lines)


class Executor(Protocol):
    def run(self, task: Task) -> ExecutionResult: ...


class HermesCLIExecutor:
    """Runs the configured Hermes command for one task."""

    def __init__(self, command: str, agent_id: str, role: str,
                 workdir: str = "/opt/agency-runtime/results",
                 timeout: int = 1800) -> None:
        if not command:
            raise SystemExit(
                "AGENCY_EXECUTOR_CMD is not set. Point it at your Hermes headless "
                "task command before starting the worker poller."
            )
        self._command = command
        self._agent = agent_id
        self._role = role
        self._workdir = Path(workdir)
        self._timeout = timeout
        self._workdir.mkdir(parents=True, exist_ok=True)

    def run(self, task: Task) -> ExecutionResult:
        brief = build_task_brief(task)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            json.dump(task.to_dict(), tf)
            task_file = tf.name

        env = dict(os.environ)
        env.update({
            "AGENCY_TASK_ID": task.task_id,
            "AGENCY_TASK_FILE": task_file,
            "AGENCY_TASK_TITLE": task.title,
            "AGENCY_TASK_BRIEF": brief,
            "AGENCY_ACTING_AGENT": self._agent,
            "AGENCY_ACTING_ROLE": self._role,
        })
        try:
            proc = subprocess.run(
                self._command, shell=True, env=env, capture_output=True,
                text=True, timeout=self._timeout, input=brief,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(ok=False, note="executor timed out")
        finally:
            try:
                os.unlink(task_file)
            except OSError:
                pass

        if proc.returncode != 0:
            return ExecutionResult(
                ok=False,
                note=f"executor exit {proc.returncode}: {proc.stderr[-300:]}",
            )

        parsed = _parse_last_json(proc.stdout)
        if parsed is not None:
            return ExecutionResult(
                ok=True,
                result_ref=str(parsed.get("result_ref", "")),
                tokens_used=int(parsed.get("tokens_used", 0)),
                note=str(parsed.get("note", "")),
            )
        # No structured result: persist stdout and reference the file.
        out_path = self._workdir / f"{task.task_id}.txt"
        out_path.write_text(proc.stdout or "", encoding="utf-8")
        return ExecutionResult(
            ok=True, result_ref=f"file://{out_path}",
            note=f"stdout saved at {utcnow_iso()}",
        )


def _parse_last_json(text: str) -> dict | None:
    for line in reversed((text or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None
