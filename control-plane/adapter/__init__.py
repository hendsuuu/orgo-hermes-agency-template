"""Agency control-plane runtime.

Phase-1 transport for the AgencyTask contract:

- ``service``  runs on the Project Manager / control-plane computer. It owns the
  Notion token, exposes the provider-neutral task interface over HTTP, runs the
  Telegram intake loop, and reaps expired leases.
- ``poller``   runs on every worker computer. It never sees the Notion token; it
  talks only to the control-plane HTTP interface, claims a lease on its own
  assigned tasks, invokes the local Hermes executor, and reports results back.

Everything here is deterministic, non-LLM transport. A language model is only
invoked by the executor when a claimed task is actually worked. Keeping the
transport tokenless is the core cost property of the fleet.
"""

__all__ = ["contract", "backend", "notion_backend", "service", "client",
           "intake", "executor", "poller", "reaper", "settings"]
