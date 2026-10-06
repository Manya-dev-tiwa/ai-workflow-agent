"""
src/tools/entity_lookup_tool.py
─────────────────────────────────────────────────────────────────────────────
Tool: entity_lookup_tool

Searches a list-of-dicts (table) for rows where a specific column matches a
given value.  Works for any table: orders, employees, products, etc.

Returns all matching rows (there may be more than one), the count, and a
clear message when nothing is found — so the caller never has to handle a
KeyError or None silently.

Why generic?
  • The table, lookup column, and search value all come through parameters.
  • No order IDs or employee names are baked in.

Return shape:
  {
    "ok":   bool,
    "data": {
        "matches":       list[dict],
        "match_count":   int,
        "lookup_column": str,
        "lookup_value":  str,
        "found":         bool,   # True even if match_count == 0 (ok, but empty)
    },
    "error": str | None
  }

  Note: ok=True + found=False means the lookup ran successfully but the
  entity was not in the dataset. ok=False means the tool itself failed.
─────────────────────────────────────────────────────────────────────────────
"""

from src.tools.registry import register_tool


# ── JSON schema ────────────────────────────────────────────────────────────────
_SCHEMA = {
    "name": "entity_lookup_tool",
    "description": (
        "Search a table (list of row-dicts) for rows where a specific column "
        "exactly matches a given value. Use this to look up an order by ID, "
        "find an employee by name, or retrieve any entity from a loaded dataset. "
        "Returns all matching rows and clearly signals when nothing is found."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "description": "The table to search: list of row-dicts.",
            },
            "lookup_column": {
                "type": "string",
                "description": (
                    "The column name to search in (e.g. 'Order_ID', 'SKU', 'Employee_Name')."
                ),
            },
            "lookup_value": {
                "type": "string",
                "description": (
                    "The value to search for. Comparison is case-insensitive and "
                    "strips surrounding whitespace."
                ),
            },
        },
        "required": ["rows", "lookup_column", "lookup_value"],
    },
}


@register_tool(schema=_SCHEMA)
def entity_lookup_tool(
    rows: list,
    lookup_column: str,
    lookup_value: str,
) -> dict:
    """
    Find all rows where `lookup_column` matches `lookup_value`.

    Parameters
    ----------
    rows          : list[dict]  The table to search.
    lookup_column : str         Column to match against.
    lookup_value  : str         Value to search for (case-insensitive, trimmed).

    Returns
    -------
    dict  {ok, data, error}
    """
    try:
        if not isinstance(rows, list) or len(rows) == 0:
            return {
                "ok":    False,
                "data":  None,
                "error": "No rows provided to search.",
            }

        if not lookup_column:
            return {
                "ok":    False,
                "data":  None,
                "error": "'lookup_column' must be a non-empty string.",
            }

        if not lookup_value:
            return {
                "ok":    False,
                "data":  None,
                "error": "'lookup_value' must be a non-empty string.",
            }

        # Check the column actually exists in the dataset
        sample_keys = set(rows[0].keys())
        if lookup_column not in sample_keys:
            return {
                "ok":    False,
                "data":  None,
                "error": (
                    f"Column '{lookup_column}' not found in the dataset. "
                    f"Available columns: {sorted(sample_keys)}"
                ),
            }

        # Normalise the search value for comparison
        target = str(lookup_value).strip().lower()

        matches = [
            row for row in rows
            if str(row.get(lookup_column, "")).strip().lower() == target
        ]

        found = len(matches) > 0

        # Build a clear human-readable note for when nothing is found
        note = None
        if not found:
            note = (
                f"No rows found where '{lookup_column}' = '{lookup_value}'. "
                "The entity may not exist in this dataset."
            )

        return {
            "ok": True,
            "data": {
                "matches":       matches,
                "match_count":   len(matches),
                "lookup_column": lookup_column,
                "lookup_value":  lookup_value,
                "found":         found,
                "note":          note,
            },
            "error": None,
        }

    except Exception as exc:
        return {
            "ok":    False,
            "data":  None,
            "error": f"Unexpected error in entity_lookup_tool: {exc}",
        }
