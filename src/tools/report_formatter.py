"""
src/tools/report_formatter.py
─────────────────────────────────────────────────────────────────────────────
Tool: report_formatter

Takes a list-of-dicts or a nested dict and formats it into a human-readable
text report.  Supported output formats:
  • "plain"     — simple key: value lines (good for single-entity lookups)
  • "table"     — aligned columns (good for tabular data)
  • "summary"   — bullet points summarising key stats fields
  • "markdown"  — GitHub-flavoured markdown table

Why generic?
  • No field names, units, or titles are baked in.
  • The caller supplies: title, data, format, and an optional list of
    columns to include (so irrelevant fields can be hidden).

Return shape:
  {
    "ok":    bool,
    "data":  {"report": str},   # the formatted text ready to display
    "error": str | None
  }
─────────────────────────────────────────────────────────────────────────────
"""

from src.tools.registry import register_tool


# ── JSON schema ────────────────────────────────────────────────────────────────
_SCHEMA = {
    "name": "report_formatter",
    "description": (
        "Format data into a human-readable text report. "
        "Accepts a list of row-dicts (table) or a single dict (entity). "
        "Supports output formats: 'plain', 'table', 'summary', 'markdown'. "
        "Use this as the final step before returning results to the user."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "data": {
                "type": "array",
                "description": (
                    "The data to format. Can be: "
                    "(a) a list of row-dicts for tabular output, "
                    "(b) a list containing one dict for a single-entity display, "
                    "(c) a flat dict with string keys and simple values for a summary."
                ),
            },
            "title": {
                "type": "string",
                "description": "Title/heading to print at the top of the report.",
            },
            "format": {
                "type": "string",
                "description": (
                    "Output format. One of: 'plain', 'table', 'summary', 'markdown'. "
                    "Default: 'plain'."
                ),
            },
            "columns": {
                "type": "array",
                "description": (
                    "Optional list of column names to include (in order). "
                    "If empty or omitted, all columns are shown."
                ),
            },
            "max_rows": {
                "type": "number",
                "description": (
                    "Optional maximum number of rows to include. "
                    "If omitted, all rows are shown."
                ),
            },
        },
        "required": ["data", "title"],
    },
}


def _plain(rows: list, columns: list) -> str:
    """
    Format each row as key: value pairs, separated by blank lines.
    Good for a small number of entities (e.g. one order, one product).
    """
    lines = []
    for row in rows:
        for col in columns:
            val = row.get(col, "")
            lines.append(f"  {col}: {val}")
        lines.append("")  # blank line between rows
    return "\n".join(lines).rstrip()


def _table(rows: list, columns: list) -> str:
    """
    Format rows as a fixed-width text table with aligned columns.
    """
    if not rows:
        return "(no rows)"

    # Determine column widths: max of header length and longest value
    widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            widths[col] = max(widths[col], len(str(row.get(col, ""))))

    def fmt_row(row_dict):
        return "  ".join(
            str(row_dict.get(col, "")).ljust(widths[col])
            for col in columns
        )

    header    = fmt_row({col: col for col in columns})
    separator = "  ".join("-" * widths[col] for col in columns)
    data_rows = [fmt_row(row) for row in rows]

    return "\n".join([header, separator] + data_rows)


def _summary(data: dict | list, columns: list) -> str:
    """
    Format as bullet-point summary.
    If data is a list, each item gets its own bullet block.
    If data is a dict, keys/values are shown as bullets.
    """
    lines = []
    items = data if isinstance(data, list) else [data]

    for item in items:
        if isinstance(item, dict):
            for col in (columns if columns else item.keys()):
                val = item.get(col, "")
                lines.append(f"  • {col}: {val}")
            lines.append("")
        else:
            lines.append(f"  • {item}")

    return "\n".join(lines).rstrip()


def _markdown(rows: list, columns: list) -> str:
    """
    Format rows as a GitHub-flavoured markdown table.
    """
    if not rows:
        return "(no rows)"

    header    = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    data_rows = [
        "| " + " | ".join(str(row.get(col, "")) for col in columns) + " |"
        for row in rows
    ]

    return "\n".join([header, separator] + data_rows)


@register_tool(schema=_SCHEMA)
def report_formatter(
    data,
    title: str,
    format: str = "plain",
    columns: list = None,
    max_rows: int = None,
) -> dict:
    """
    Format data into a human-readable report string.

    Parameters
    ----------
    data     : list[dict] | dict  Data to format.
    title    : str                Report title / heading.
    format   : str                'plain' | 'table' | 'summary' | 'markdown'.
    columns  : list[str]          Columns to include (all if empty).
    max_rows : int                Limit number of rows shown.

    Returns
    -------
    dict  {ok, data: {report: str}, error}
    """
    try:
        if data is None:
            return {
                "ok":    False,
                "data":  None,
                "error": "No data provided to format.",
            }

        # Normalise to list for uniform handling
        if isinstance(data, dict):
            rows = [data]
        elif isinstance(data, list):
            rows = data
        else:
            return {
                "ok":    False,
                "data":  None,
                "error": (
                    f"Unsupported data type '{type(data).__name__}'. "
                    "Expected list or dict."
                ),
            }

        if len(rows) == 0:
            report = f"{'─' * 60}\n{title}\n{'─' * 60}\n(no data)"
            return {"ok": True, "data": {"report": report}, "error": None}

        # Determine columns to display
        if columns:
            cols = columns
        elif rows and isinstance(rows[0], dict):
            # Use the key order of the first row
            cols = list(rows[0].keys())
        else:
            cols = []

        # Apply row limit
        if max_rows and isinstance(max_rows, (int, float)):
            rows = rows[: int(max_rows)]

        # Build the body based on format
        fmt = (format or "plain").lower().strip()

        if fmt == "plain":
            body = _plain(rows, cols)
        elif fmt == "table":
            body = _table(rows, cols)
        elif fmt == "summary":
            body = _summary(rows if len(rows) > 1 else data, cols)
        elif fmt == "markdown":
            body = _markdown(rows, cols)
        else:
            return {
                "ok":    False,
                "data":  None,
                "error": (
                    f"Unknown format '{format}'. "
                    "Supported: 'plain', 'table', 'summary', 'markdown'."
                ),
            }

        # Wrap with title header
        divider = "─" * 60
        report = f"{divider}\n{title}\n{divider}\n{body}"

        return {"ok": True, "data": {"report": report}, "error": None}

    except Exception as exc:
        return {
            "ok":    False,
            "data":  None,
            "error": f"Unexpected error in report_formatter: {exc}",
        }
