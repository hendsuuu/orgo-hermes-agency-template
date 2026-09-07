"""Fail-closed human approval gate for state-changing Composio actions."""

from __future__ import annotations

from typing import Any, Iterable

_READ_ONLY_PREFIXES = (
    "GET_", "LIST_", "FIND_", "SEARCH_", "FETCH_", "RETRIEVE_",
    "LOOKUP_", "AUTOCOMPLETE_", "DESCRIBE_", "CHECK_",
)


def _tool_slugs(args: dict[str, Any]) -> list[str]:
    raw_tools = args.get("tools")
    if not isinstance(raw_tools, list) or not raw_tools:
        return ["UNKNOWN_COMPOSIO_ACTION"]
    result: list[str] = []
    for item in raw_tools:
        slug = item.get("tool_slug") if isinstance(item, dict) else None
        result.append(slug.strip().upper() if isinstance(slug, str) and slug.strip() else "UNKNOWN_COMPOSIO_ACTION")
    return result


def _is_read_only(slug: str) -> bool:
    action = slug.split("_", 1)[1] if "_" in slug else slug
    return action.startswith(_READ_ONLY_PREFIXES)


def _is_executor(tool_name: str) -> bool:
    return tool_name.startswith("mcp_") and tool_name.endswith("_COMPOSIO_MULTI_EXECUTE_TOOL")


def _is_connection_manager(tool_name: str) -> bool:
    return tool_name.startswith("mcp_") and tool_name.endswith("_COMPOSIO_MANAGE_CONNECTIONS")


def _ask(slugs: Iterable[str], operation: str) -> dict[str, str] | None:
    unique = list(dict.fromkeys(slugs))
    display = ", ".join(unique[:12])
    if len(unique) > 12:
        display += f" (+{len(unique) - 12} more)"
    try:
        from tools.approval import request_elicitation_consent
        answer = request_elicitation_consent(
            "Approve external Composio action?",
            f"Agent requests {operation}: {display}. This can change external data or access.",
            timeout_seconds=300,
            surface="composio-human-approval",
        )
    except Exception:
        answer = "decline"
    if answer == "accept":
        return None
    return {
        "action": "block",
        "message": "BLOCKED: no explicit Slack approval. Do not retry through another tool.",
    }


def _on_pre_tool_call(tool_name: str = "", args: Any = None, **_: Any):
    data = args if isinstance(args, dict) else {}
    if _is_executor(tool_name):
        slugs = _tool_slugs(data)
        return None if all(_is_read_only(slug) for slug in slugs) else _ask(slugs, "a non-read Composio action")
    if _is_connection_manager(tool_name) and data.get("reinitiate_all") is True:
        toolkits = data.get("toolkits")
        labels = [str(item).upper() for item in toolkits] if isinstance(toolkits, list) else ["CONNECTION"]
        return _ask(labels, "a Composio connection reset")
    return None


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
