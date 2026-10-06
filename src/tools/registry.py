"""
src/tools/registry.py
─────────────────────────────────────────────────────────────────────────────
Tool Registry — the single source of truth for every non-LLM tool.

How it works
────────────
1.  Each tool function uses the @register_tool decorator.
2.  The decorator stores the function AND its JSON schema in TOOL_REGISTRY.
3.  An LLM-based engine (built in a later phase) can read TOOL_REGISTRY to
    know what tools exist, what parameters they take, and what they return.

Adding a new tool
──────────────────
• Write the function in its own file under src/tools/.
• Decorate it with @register_tool(schema={...}).
• Import that file in the block at the bottom of THIS file.
• That's it — no further registration needed anywhere.

JSON schema format (OpenAI function-calling compatible)
──────────────────────────────────────────────────────
{
    "name":        str,          # must match the function name
    "description": str,          # plain English; what the LLM will read
    "parameters": {
        "type": "object",
        "properties": {
            "<param>": {
                "type":        str,   # "string", "number", "boolean", "array"
                "description": str
            },
            ...
        },
        "required": [<list of mandatory param names>]
    }
}
─────────────────────────────────────────────────────────────────────────────
"""

from typing import Callable, Any

# ── Global registry ────────────────────────────────────────────────────────────
# Keys  : tool name (str)
# Values: dict with keys "function" and "schema"
TOOL_REGISTRY: dict[str, dict] = {}


def register_tool(schema: dict) -> Callable:
    """
    Decorator that registers a tool function in TOOL_REGISTRY.

    Usage:
        @register_tool(schema={
            "name": "my_tool",
            "description": "...",
            "parameters": {...}
        })
        def my_tool(...):
            ...

    The decorator returns the original function unchanged, so the tool can
    still be called directly in tests without going through the registry.
    """
    def decorator(fn: Callable) -> Callable:
        tool_name = schema["name"]

        # Sanity check: the schema name must match the function name so that
        # auto-dispatch (in the future engine) can call the right function.
        if tool_name != fn.__name__:
            raise ValueError(
                f"register_tool: schema name '{tool_name}' does not match "
                f"function name '{fn.__name__}'. They must be identical."
            )

        # Store both the callable and its schema together
        TOOL_REGISTRY[tool_name] = {
            "function": fn,
            "schema":   schema,
        }
        return fn  # return the original function untouched

    return decorator


def get_all_schemas() -> list[dict]:
    """
    Return the JSON schema for every registered tool.
    Useful for passing the full tool list to an LLM in a single call.
    """
    return [entry["schema"] for entry in TOOL_REGISTRY.values()]


def call_tool(name: str, **kwargs) -> dict:
    """
    Look up a tool by name and call it with the given keyword arguments.

    Returns the tool's structured result dict.
    Returns an error dict if the tool name is not found — never raises.
    """
    if name not in TOOL_REGISTRY:
        return {
            "ok":    False,
            "data":  None,
            "error": f"Unknown tool '{name}'. Known tools: {list(TOOL_REGISTRY.keys())}",
        }
    fn = TOOL_REGISTRY[name]["function"]
    return fn(**kwargs)


# ── Auto-import all tool modules ───────────────────────────────────────────────
# Each import below triggers the @register_tool decorator in that module,
# which populates TOOL_REGISTRY automatically.
# Order does not matter — the registry is a dict, not a list.

from src.tools import file_data_loader          # noqa: E402, F401
from src.tools import tabular_validator_cleaner  # noqa: E402, F401
from src.tools import data_calculator_aggregator # noqa: E402, F401
from src.tools import entity_lookup_tool         # noqa: E402, F401
from src.tools import text_similarity_matcher    # noqa: E402, F401
from src.tools import report_formatter           # noqa: E402, F401
