"""
src/tools/data_calculator_aggregator.py
─────────────────────────────────────────────────────────────────────────────
Tool: data_calculator_aggregator

Performs numeric calculations on a list-of-dicts table.

Supported operations (supplied via the `operation` parameter):
  • "compare_columns"  — compare two numeric columns row-by-row and flag rows
                         where the percentage difference exceeds a threshold
  • "below_threshold"  — flag rows where a numeric column is below a threshold
  • "aggregate"        — compute count, sum, average, min, max grouped by a
                         column; optionally filter to specific group values

Why generic?
  • Column names, thresholds, and aggregation keys all come through parameters.
  • No workflow IDs or business rules are baked in.

Return shape:
  {
    "ok":   bool,
    "data": <operation-specific dict>,
    "error": str | None
  }
─────────────────────────────────────────────────────────────────────────────
"""

import datetime
from src.tools.registry import register_tool


# ── JSON schema ────────────────────────────────────────────────────────────────
_SCHEMA = {
    "name": "data_calculator_aggregator",
    "description": (
        "Perform numeric or date calculations on a table (list of row-dicts). "
        "Supports operations: "
        "'compare_columns' (flag rows where two numeric columns differ by more than a percentage threshold), "
        "'below_threshold' (flag rows where a numeric column is below a value), "
        "'aggregate' (count/sum/average/min/max grouped by a column), "
        "'date_diff' / 'days_overdue' (compute days difference between a date column and today's real system date, or between two date columns. If comparing against today, uses the system date automatically)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "description": "The table to process: list of row-dicts.",
            },
            "operation": {
                "type": "string",
                "description": (
                    "Which calculation to run. "
                    "One of: 'compare_columns', 'below_threshold', 'aggregate', 'date_diff', 'days_overdue'."
                ),
            },
            "column_a": {
                "type": "string",
                "description": (
                    "For 'compare_columns': name of the first numeric column "
                    "(e.g. the internal / reference price). "
                    "For 'below_threshold': the column to compare against the threshold. "
                    "For 'date_diff'/'days_overdue': the date column to compare (e.g. 'Estimated_Delivery')."
                ),
            },
            "column_b": {
                "type": "string",
                "description": (
                    "For 'compare_columns': name of the second numeric column "
                    "(e.g. the vendor / comparison price). "
                    "For 'date_diff'/'days_overdue': optional second date column to compare against. "
                    "If omitted, compares against today's real system date."
                ),
            },
            "threshold": {
                "type": "number",
                "description": (
                    "For 'compare_columns': percentage difference threshold (e.g. 10 means 10%). "
                    "For 'below_threshold': the minimum acceptable numeric value. "
                    "For 'date_diff'/'days_overdue': minimum days threshold to flag (default 0, flagging past-due / overdue dates)."
                ),
            },
            "group_by_column": {
                "type": "string",
                "description": (
                    "For 'aggregate': the column whose distinct values define groups "
                    "(e.g. 'Workflow_ID', 'Status', 'Category')."
                ),
            },
            "value_column": {
                "type": "string",
                "description": (
                    "For 'aggregate': the numeric column to sum/average/min/max within each group."
                ),
            },
            "filter_values": {
                "type": "array",
                "description": (
                    "For 'aggregate': optional list of group-by values to include. "
                    "If empty or omitted, all groups are returned."
                ),
            },
            "id_column": {
                "type": "string",
                "description": (
                    "Optional column to include in flagged-row output as an identifier "
                    "(e.g. 'SKU', 'Order_ID', 'Run_ID'). Helps the caller understand which rows failed."
                ),
            },
            "date_column": {
                "type": "string",
                "description": (
                    "Optional alias for column_a when running 'date_diff' or 'days_overdue'."
                ),
            },
        },
        "required": ["rows", "operation"],
    },
}


def _to_float(value) -> float | None:
    """Try to convert a value to float; return None if it can't be converted."""
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


def _parse_date(value) -> datetime.date | None:
    """Try to parse a date from string/date/datetime; return None on failure."""
    if not value:
        return None
    # Guard isinstance() against cases where datetime.date is patched to a
    # MagicMock during unit tests — isinstance() raises TypeError in that case.
    try:
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
    except TypeError:
        pass
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(s[:10], fmt).date()
        except Exception:
            pass
    try:
        s_date = s.split("T")[0].split(" ")[0]
        return datetime.date.fromisoformat(s_date)
    except Exception:
        pass
    return None


@register_tool(schema=_SCHEMA)
def data_calculator_aggregator(
    rows: list,
    operation: str,
    column_a: str = "",
    column_b: str = "",
    threshold: float = 0.0,
    group_by_column: str = "",
    value_column: str = "",
    filter_values: list = None,
    id_column: str = "",
    date_column: str = "",
) -> dict:
    """
    Perform numeric calculations on a list-of-dicts table.

    Parameters
    ----------
    rows            : list[dict]  The table.
    operation       : str         One of 'compare_columns', 'below_threshold', 'aggregate'.
    column_a        : str         First column (for compare / below_threshold).
    column_b        : str         Second column (for compare).
    threshold       : float       Percentage or numeric threshold.
    group_by_column : str         Column to group by (for aggregate).
    value_column    : str         Numeric column to aggregate (for aggregate).
    filter_values   : list        Subset of group values to return (optional).
    id_column       : str         Optional column to include in flagged rows for readability.

    Returns
    -------
    dict  {ok, data, error}
    """
    try:
        if not isinstance(rows, list) or len(rows) == 0:
            return {
                "ok":    False,
                "data":  None,
                "error": "No rows provided.",
            }

        # ── Operation: compare_columns ─────────────────────────────────────────
        if operation == "compare_columns":
            # Validate required params
            if not column_a or not column_b:
                return {
                    "ok":    False,
                    "data":  None,
                    "error": "'compare_columns' requires 'column_a' and 'column_b'.",
                }

            flagged = []
            skipped = 0  # rows where conversion to float failed

            for row in rows:
                val_a = _to_float(row.get(column_a))
                val_b = _to_float(row.get(column_b))

                if val_a is None or val_b is None:
                    skipped += 1
                    continue

                # Avoid division by zero: if both values are 0 difference is 0
                if val_a == 0 and val_b == 0:
                    pct_diff = 0.0
                elif val_a == 0:
                    # Any non-zero val_b when val_a==0 is infinite difference
                    pct_diff = 100.0
                else:
                    pct_diff = abs(val_b - val_a) / abs(val_a) * 100

                if pct_diff > threshold:
                    entry = {
                        column_a:        val_a,
                        column_b:        val_b,
                        "pct_difference": round(pct_diff, 2),
                    }
                    if id_column and id_column in row:
                        entry[id_column] = row[id_column]
                    # Also carry any extra string columns for context
                    for k, v in row.items():
                        if k not in entry:
                            entry[k] = v
                    flagged.append(entry)

            return {
                "ok": True,
                "data": {
                    "flagged_rows":   flagged,
                    "flagged_count":  len(flagged),
                    "skipped_count":  skipped,
                    "threshold_pct":  threshold,
                },
                "error": None,
            }

        # ── Operation: below_threshold ─────────────────────────────────────────
        elif operation == "below_threshold":
            if not column_a:
                return {
                    "ok":    False,
                    "data":  None,
                    "error": "'below_threshold' requires 'column_a'.",
                }

            flagged = []
            skipped = 0

            for row in rows:
                val = _to_float(row.get(column_a))
                if val is None:
                    skipped += 1
                    continue
                if val < threshold:
                    entry = dict(row)
                    entry["_value"] = val
                    flagged.append(entry)

            return {
                "ok": True,
                "data": {
                    "flagged_rows":  flagged,
                    "flagged_count": len(flagged),
                    "skipped_count": skipped,
                    "threshold":     threshold,
                    "column":        column_a,
                },
                "error": None,
            }

        # ── Operation: aggregate ───────────────────────────────────────────────
        elif operation == "aggregate":
            if not group_by_column or not value_column:
                return {
                    "ok":    False,
                    "data":  None,
                    "error": "'aggregate' requires 'group_by_column' and 'value_column'.",
                }

            # Build per-group buckets  {group_value: [numeric values]}
            buckets: dict[str, list[float]] = {}
            counts:  dict[str, int]         = {}  # total rows per group (incl. non-numeric)

            for row in rows:
                group = str(row.get(group_by_column, "")).strip()
                counts[group] = counts.get(group, 0) + 1

                val = _to_float(row.get(value_column))
                if val is not None:
                    buckets.setdefault(group, []).append(val)

            # Optionally restrict to specific groups
            if filter_values:
                filter_set = {str(v) for v in filter_values}
                buckets = {k: v for k, v in buckets.items() if k in filter_set}
                counts  = {k: v for k, v in counts.items()  if k in filter_set}

            # Compute stats for each group
            results = {}
            for group, values in buckets.items():
                results[group] = {
                    "count":   counts.get(group, len(values)),
                    "sum":     round(sum(values), 4),
                    "average": round(sum(values) / len(values), 4),
                    "min":     min(values),
                    "max":     max(values),
                }

            # Groups that appeared in filter_values but had no numeric data
            if filter_values:
                for v in filter_values:
                    key = str(v)
                    if key not in results:
                        results[key] = {
                            "count":   counts.get(key, 0),
                            "sum":     None,
                            "average": None,
                            "min":     None,
                            "max":     None,
                            "note":    "No numeric data found for this group.",
                        }

            return {
                "ok": True,
                "data": {
                    "groups":          results,
                    "group_by_column": group_by_column,
                    "value_column":    value_column,
                },
                "error": None,
            }

        # ── Operation: date_diff / days_overdue ────────────────────────────────
        elif operation in ("date_diff", "days_diff", "date_difference", "days_overdue", "compare_dates"):
            target_col = column_a or date_column
            if not target_col:
                return {
                    "ok":    False,
                    "data":  None,
                    "error": f"'{operation}' requires 'column_a' (or 'date_column') specifying the date column.",
                }

            if threshold is None:
                threshold = 0.0

            # Compute from real system date clock
            system_today = datetime.date.today()
            flagged = []
            calculated = []
            skipped = 0

            for row in rows:
                val_a = row.get(target_col)
                d_a = _parse_date(val_a)
                if d_a is None:
                    skipped += 1
                    continue

                if column_b and column_b in row:
                    d_b = _parse_date(row.get(column_b))
                    if d_b is None:
                        skipped += 1
                        continue
                    days = (d_b - d_a).days
                else:
                    # Computed from the real system date (system_today - due_date)
                    # Positive value indicates the due date is in the past (overdue)
                    days = (system_today - d_a).days

                entry = dict(row)
                entry["days_diff"] = days
                entry["days_overdue"] = days
                calculated.append(entry)

                if days > threshold:
                    flagged.append(entry)

            return {
                "ok": True,
                "data": {
                    "reference_date": system_today.isoformat(),
                    "flagged_rows":   flagged,
                    "flagged_count":  len(flagged),
                    "calculated_rows": calculated,
                    "skipped_count":  skipped,
                    "threshold_days": threshold,
                    "column":         target_col,
                },
                "error": None,
            }

        # ── Unknown operation ──────────────────────────────────────────────────
        else:
            return {
                "ok":    False,
                "data":  None,
                "error": (
                    f"Unknown operation '{operation}'. "
                    "Supported: 'compare_columns', 'below_threshold', 'aggregate', 'date_diff', 'days_overdue'."
                ),
            }

    except Exception as exc:
        return {
            "ok":    False,
            "data":  None,
            "error": f"Unexpected error in data_calculator_aggregator: {exc}",
        }
