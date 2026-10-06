"""
src/tools/tabular_validator_cleaner.py
─────────────────────────────────────────────────────────────────────────────
Tool: tabular_validator_cleaner

Validates rows in a list-of-dicts (table) against caller-supplied rules:
  • required_columns  — which column names must be present in the table
  • required_fields   — which columns must be non-empty in every row

Returns two groups:
  • valid_rows   — rows that pass every check
  • invalid_rows — rows that fail, each annotated with a "validation_errors"
                   key listing what went wrong

Why generic?
  • No column names or rules are baked in here.
  • The LLM (or workflow step) supplies required_columns / required_fields
    based on the specific file it just loaded.

Return shape:
  {
    "ok":   bool,
    "data": {
        "valid_rows":    list[dict],
        "invalid_rows":  list[dict],   # each row has extra "validation_errors" key
        "total":         int,
        "valid_count":   int,
        "invalid_count": int,
    },
    "error": str | None
  }
─────────────────────────────────────────────────────────────────────────────
"""

from src.tools.registry import register_tool


# ── JSON schema ────────────────────────────────────────────────────────────────
_SCHEMA = {
    "name": "tabular_validator_cleaner",
    "description": (
        "Validate a table (list of row-dicts) against a set of rules. "
        "Checks that all required columns exist and that specified fields are "
        "non-empty in every row. Returns valid rows and invalid rows separately, "
        "with a human-readable error list attached to each invalid row."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "description": (
                    "The table to validate: a list of dicts where each dict "
                    "is one row and the keys are column names."
                ),
            },
            "required_columns": {
                "type": "array",
                "description": (
                    "Column names that MUST exist as keys in the row dicts. "
                    "If any are missing the tool returns ok=False immediately "
                    "because the entire dataset is unusable."
                ),
            },
            "required_fields": {
                "type": "array",
                "description": (
                    "Column names whose value must be non-empty in every row. "
                    "Rows with empty values in these columns go to invalid_rows."
                ),
            },
        },
        "required": ["rows", "required_columns", "required_fields"],
    },
}


@register_tool(schema=_SCHEMA)
def tabular_validator_cleaner(
    rows: list,
    required_columns: list,
    required_fields: list,
) -> dict:
    """
    Validate and split rows into valid vs invalid.

    Parameters
    ----------
    rows             : list[dict]  The table to validate.
    required_columns : list[str]   Columns that must exist as keys.
    required_fields  : list[str]   Columns that must be non-empty per row.

    Returns
    -------
    dict  {ok, data, error}
    """
    try:
        # ── Guard: rows must be a non-empty list ───────────────────────────────
        if not isinstance(rows, list) or len(rows) == 0:
            return {
                "ok":    False,
                "data":  None,
                "error": "No rows provided. The 'rows' parameter must be a non-empty list.",
            }

        # ── Check that all required columns actually exist in the dataset ──────
        # We look at the keys of the first row as the column set.
        # (All rows from file_data_loader share the same keys.)
        actual_columns = set(rows[0].keys())
        missing_columns = [c for c in required_columns if c not in actual_columns]
        if missing_columns:
            return {
                "ok":    False,
                "data":  None,
                "error": (
                    f"Required column(s) missing from the dataset: {missing_columns}. "
                    f"Available columns: {sorted(actual_columns)}"
                ),
            }

        # ── Validate each row ──────────────────────────────────────────────────
        valid_rows   = []
        invalid_rows = []

        for row in rows:
            errors = []

            # Check every required_field for a non-empty value
            for field in required_fields:
                value = row.get(field, "")
                if value is None or str(value).strip() == "":
                    errors.append(f"'{field}' is empty or missing")

            if errors:
                # Attach the list of errors to a copy of the row
                annotated = dict(row)
                annotated["validation_errors"] = errors
                invalid_rows.append(annotated)
            else:
                valid_rows.append(row)

        return {
            "ok": True,
            "data": {
                "valid_rows":    valid_rows,
                "invalid_rows":  invalid_rows,
                "total":         len(rows),
                "valid_count":   len(valid_rows),
                "invalid_count": len(invalid_rows),
            },
            "error": None,
        }

    except Exception as exc:
        return {
            "ok":    False,
            "data":  None,
            "error": f"Unexpected error in tabular_validator_cleaner: {exc}",
        }
