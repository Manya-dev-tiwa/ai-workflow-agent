"""
src/tools/file_data_loader.py
─────────────────────────────────────────────────────────────────────────────
Tool: file_data_loader

Loads a CSV or JSON file from disk and returns its contents as a list of
row-dicts (CSV) or a plain dict/list (JSON).

Why generic?
  • The file path comes in as a parameter — no hard-coded paths.
  • The caller decides which file to load; this tool just reads it safely.

Return shape:  {"ok": bool, "data": list[dict] | dict | list, "error": str | None}
─────────────────────────────────────────────────────────────────────────────
"""

import csv
import json
from pathlib import Path

from src.tools.registry import register_tool


# ── JSON schema for the LLM ────────────────────────────────────────────────────
_SCHEMA = {
    "name": "file_data_loader",
    "description": (
        "Load a CSV or JSON file from disk and return its contents. "
        "For CSV files, each row is returned as a dict keyed by column headers. "
        "For JSON files, the raw parsed value (dict or list) is returned. "
        "Use this tool whenever you need to read data from a file before processing it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": (
                    "Absolute or project-relative path to the file. "
                    "Supported extensions: .csv, .json"
                ),
            },
            "encoding": {
                "type": "string",
                "description": (
                    "Text encoding to use when reading the file. "
                    "Defaults to 'utf-8'. Use 'utf-8-sig' to strip BOM characters."
                ),
            },
        },
        "required": ["file_path"],
    },
}


@register_tool(schema=_SCHEMA)
def file_data_loader(file_path: str, encoding: str = "utf-8") -> dict:
    """
    Load a CSV or JSON file and return structured data.

    Parameters
    ----------
    file_path : str
        Path to the .csv or .json file to read.
    encoding  : str
        File encoding (default "utf-8").

    Returns
    -------
    dict
        {
          "ok":    True | False,
          "data":  list[dict] (CSV) | dict | list (JSON) | None on error,
          "error": None | str
        }
    """
    try:
        path = Path(file_path)

        # ── Does the file exist? ───────────────────────────────────────────────
        if not path.exists():
            from src.config import ROOT_DIR
            alt_path = ROOT_DIR / file_path
            if alt_path.exists():
                path = alt_path
            else:
                return {
                    "ok":    False,
                    "data":  None,
                    "error": f"File not found: '{file_path}'",
                }

        ext = path.suffix.lower()

        # ── CSV branch ─────────────────────────────────────────────────────────
        if ext == ".csv":
            rows = []
            with open(path, newline="", encoding=encoding) as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    # Strip whitespace from every cell value
                    rows.append({k: (v.strip() if v else v) for k, v in row.items()})

            # If the CSV was completely empty (no header row), tell the caller.
            if not rows:
                return {
                    "ok":    False,
                    "data":  None,
                    "error": f"CSV file '{file_path}' is empty or has no data rows.",
                }

            return {"ok": True, "data": rows, "error": None}

        # ── JSON branch ────────────────────────────────────────────────────────
        elif ext == ".json":
            if path.stat().st_size == 0:
                return {
                    "ok":    False,
                    "data":  None,
                    "error": f"JSON file '{file_path}' is empty.",
                }
            with open(path, encoding=encoding) as fh:
                payload = json.load(fh)
            return {"ok": True, "data": payload, "error": None}

        # ── Unsupported format ─────────────────────────────────────────────────
        else:
            return {
                "ok":    False,
                "data":  None,
                "error": (
                    f"Unsupported file type '{ext}'. "
                    "Only .csv and .json files are supported."
                ),
            }

    except UnicodeDecodeError as exc:
        # Give a helpful hint about encoding issues
        return {
            "ok":    False,
            "data":  None,
            "error": (
                f"Encoding error reading '{file_path}': {exc}. "
                "Try setting encoding='utf-8-sig' or 'latin-1'."
            ),
        }
    except Exception as exc:
        # Catch-all: never let a raw exception escape the tool boundary
        return {
            "ok":    False,
            "data":  None,
            "error": f"Unexpected error loading '{file_path}': {exc}",
        }
