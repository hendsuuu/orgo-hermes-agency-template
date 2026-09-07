"""Dependency-free self-test for the contract and executor logic.

Run from the control-plane directory:  python -m adapter.selftest

Only imports stdlib-backed modules (contract, executor), so it verifies the
core transition rules and result parsing in CI without installing flask or
requests. Intake, service, and backend are exercised separately where those
dependencies are available.
"""

from adapter import contract as C
from adapter.contract import ContractError, derive_task_id
from adapter.executor import _parse_last_json


def main() -> None:
    # Legal worker / PM transitions.
    C.check_transition("worker", "assigned", "in_progress")
    C.check_transition("worker", "in_progress", "review")
    C.check_transition("worker", "in_progress", "done")
    C.check_transition("pm", "triage", "assigned")

    # Illegal transitions must raise.
    for bad in (("worker", "assigned", "done"),
                ("worker", "in_progress", "assigned"),
                ("pm", "done", "assigned")):
        try:
            C.check_transition(*bad)
        except ContractError:
            pass
        else:
            raise SystemExit(f"expected failure for {bad}")

    # Deterministic, well-formed task ids.
    key = "slack:123:456"
    assert derive_task_id(key) == derive_task_id(key)
    assert derive_task_id(key).startswith("tsk_")

    # Executor result parsing.
    assert _parse_last_json('noise\n{"result_ref":"x","tokens_used":9}')["tokens_used"] == 9
    assert _parse_last_json("no json") is None

    print("SELFTEST OK")


if __name__ == "__main__":
    main()
