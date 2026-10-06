"""
src/tools/list_data_files.py
─────────────────────────────────────────────────────────────────────────────
Tool: list_data_files

Scans data/mock_data/ and data/samples/ and returns all available data files
along with their column names (reading only the CSV header row).
For JSON files, returns top-level keys if available.

Return shape: {"ok": bool, "data": list[dict], "error": str | None}
─────────────────────────────────────────────────────────────────────────────
"""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from src.config import MOCK_DATA_DIR, SAMPLES_DIR, ROOT_DIR
from src.tools.registry import register_tool

_SCHEMA = {
    "name": "list_data_files",
    "description": (
        "List all available data files in data/mock_data/ and data/samples/ along with their column names. "
        "Use this tool before calling ask_user for a missing dataset or file path to discover existing files "
        "whose name or columns match the workflow's Inputs/Tools_Required."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


@register_tool(schema=_SCHEMA)
def list_data_files(**kwargs) -> dict:
    """
    List every file in data/mock_data/ and data/samples/ with its column names
    (reading only the CSV header for CSV files).

    Returns
    -------
    dict
        {
          "ok":    True,
          "data":  [{"file_path": str, "columns": list[str]}, ...],
          "error": None
        }
    """
    try:
        results: List[Dict[str, Any]] = []
        directories = [MOCK_DATA_DIR, SAMPLES_DIR]

        for directory in directories:
            if not directory.exists():
                continue

            for file_path in sorted(directory.iterdir()):
                if not file_path.is_file():
                    continue

                try:
                    rel_path = file_path.relative_to(ROOT_DIR).as_posix()
                except ValueError:
                    rel_path = str(file_path).replace("\\", "/")

                columns: List[str] = []
                ext = file_path.suffix.lower()

                if ext == ".csv":
                    try:
                        with open(file_path, "r", newline="", encoding="utf-8-sig") as f:
                            reader = csv.reader(f)
                            header = next(reader, [])
                            columns = [c.strip() for c in header if c is not None and c.strip()]
                    except Exception:
                        columns = []
                elif ext == ".json":
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            payload = json.load(f)
                            if isinstance(payload, dict):
                                columns = list(payload.keys())
                            elif isinstance(payload, list) and payload and isinstance(payload[0], dict):
                                columns = list(payload[0].keys())
                    except Exception:
                        columns = []

                results.append({
                    "file_path": rel_path,
                    "columns":   columns,
                })

        return {
            "ok":    True,
            "data":  results,
            "error": None,
        }

    except Exception as exc:
        return {
            "ok":    False,
            "data":  None,
            "error": f"Unexpected error listing data files: {exc}",
        }
