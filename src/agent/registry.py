"""
src/agent/registry.py
-----------------------------------------------------------------------------
WorkflowRegistry -- the single source of truth for workflow metadata.

Responsibilities:
  * Read data/workflows.xlsx at startup.
  * Parse both sheets: "Workflows" and "Test_Questions".
  * Expose simple Python dicts / lists so the rest of the system
    never touches the Excel file directly.

Design rules (from PLAN.md):
  * No business logic here -- only reading and normalising.
  * Returns plain Python types (list[dict]) so it stays easy to test.
  * Raises clear errors if the file is missing or a sheet is absent.

Note on Windows file locking:
  On Windows, Excel locks .xlsx files while they are open.  We use the
  Win32 CreateFileW API with FILE_SHARE_READ | FILE_SHARE_WRITE to read
  the file into memory first, then parse from a BytesIO buffer.  This is
  transparent to the rest of the codebase.
-----------------------------------------------------------------------------
"""

import io
import sys
import pandas as pd
from pathlib import Path
from typing import Optional

# Import the resolved path from config so the file location is never
# duplicated across the codebase.
from src.config import WORKFLOWS_EXCEL


# ── Data class (plain dict) schema for reference ──────────────────────────────
#
# Workflow dict keys:
#   workflow_id, workflow_name, trigger, inputs, steps,
#   decision_logic, tools_required, expected_output
#
# Test question dict keys:
#   workflow_id, test_request, what_to_check


class WorkflowRegistry:
    """
    Loads and indexes all workflow definitions from the Excel file.

    Usage:
        registry = WorkflowRegistry()
        wf = registry.get_workflow("WF001")
        tests = registry.get_test_questions()
    """

    def __init__(self, excel_path: Path = WORKFLOWS_EXCEL):
        """
        Read the Excel file and build internal indexes.
        Called once at application startup.
        """
        self._excel_path = excel_path
        self._workflows: list[dict] = []        # ordered list of all workflows
        self._wf_by_id: dict[str, dict] = {}    # quick lookup by Workflow_ID
        self._test_questions: list[dict] = []   # all rows from Test_Questions sheet

        self._load()

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_all_workflows(self) -> list[dict]:
        """Return all workflow definitions (ordered as in Excel)."""
        return self._workflows

    def get_workflow(self, workflow_id: str) -> Optional[dict]:
        """
        Return a single workflow dict by ID (e.g. "WF001").
        Returns None — not an exception — if the ID is unknown, so the
        router can handle the missing-workflow case gracefully.
        """
        return self._wf_by_id.get(workflow_id.upper())

    def get_test_questions(self) -> list[dict]:
        """Return all test question rows."""
        return self._test_questions

    def get_test_question(self, workflow_id: str) -> Optional[dict]:
        """Return the test question for a specific workflow, or None."""
        for tq in self._test_questions:
            if tq["workflow_id"] == workflow_id.upper():
                return tq
        return None

    def workflow_ids(self) -> list[str]:
        """Return list of all known workflow IDs (e.g. ['WF001', ..., 'WF010'])."""
        return list(self._wf_by_id.keys())

    # ── Internal loading logic ─────────────────────────────────────────────────

    def _load(self) -> None:
        """
        Read both sheets from Excel.
        Uses _read_excel_bytes() to handle Windows file locking gracefully.
        Normalises column names to snake_case for consistent access throughout
        the codebase (no surprises from capitalisation differences).
        """
        if not self._excel_path.exists():
            raise FileNotFoundError(
                f"WorkflowRegistry: Excel file not found at '{self._excel_path}'.\n"
                "Make sure data/workflows.xlsx is present in the project root."
            )

        # Read file bytes using share-read (handles Windows Excel lock)
        excel_bytes = self._read_excel_bytes(self._excel_path)

        # -- Read "Workflows" sheet --------------------------------------------
        try:
            df_workflows = pd.read_excel(
                io.BytesIO(excel_bytes),
                sheet_name="Workflows",
                dtype=str,   # keep everything as strings -- no type coercion
                engine="openpyxl",  # explicit engine needed when reading from BytesIO
            )
        except Exception as exc:
            raise RuntimeError(
                f"WorkflowRegistry: Failed to read 'Workflows' sheet: {exc}"
            ) from exc

        # Normalise column names: lowercase + underscores
        df_workflows.columns = [
            col.strip().lower().replace(" ", "_") for col in df_workflows.columns
        ]

        for _, row in df_workflows.iterrows():
            wf = {
                "workflow_id":    self._clean(row.get("workflow_id")),
                "workflow_name":  self._clean(row.get("workflow_name")),
                "trigger":        self._clean(row.get("trigger")),
                "inputs":         self._clean(row.get("inputs")),
                "steps":          self._clean(row.get("steps")),
                "decision_logic": self._clean(row.get("decision_logic")),
                "tools_required": self._clean(row.get("tools_required")),
                "expected_output": self._clean(row.get("expected_output")),
            }
            self._workflows.append(wf)
            self._wf_by_id[wf["workflow_id"]] = wf

        # -- Read "Test_Questions" sheet ----------------------------------------
        try:
            df_tests = pd.read_excel(
                io.BytesIO(excel_bytes),
                sheet_name="Test_Questions",
                dtype=str,
                engine="openpyxl",  # explicit engine needed when reading from BytesIO
            )
        except Exception as exc:
            raise RuntimeError(
                f"WorkflowRegistry: Failed to read 'Test_Questions' sheet: {exc}"
            ) from exc

        df_tests.columns = [
            col.strip().lower().replace(" ", "_") for col in df_tests.columns
        ]

        for _, row in df_tests.iterrows():
            self._test_questions.append({
                "workflow_id":    self._clean(row.get("workflow_id")),
                "test_request":   self._clean(row.get("test_request")),
                "what_to_check":  self._clean(row.get("what_to_check")),
            })

    @staticmethod
    def _read_excel_bytes(path: Path) -> bytes:
        """
        Read a file into bytes even when another process (e.g. Excel) has it
        open with an exclusive lock.

        Strategy on Windows:
          Use PowerShell's Copy-Item with -Force which internally uses a
          share-compatible copy, writing to a temporary file, then read the
          temp file normally.

        Falls back to plain read_bytes() on non-Windows.
        """
        if sys.platform != "win32":
            return path.read_bytes()

        import subprocess
        import tempfile
        import os

        # Create a temp file next to the original (same drive, avoids permission
        # issues with cross-drive temp directories on some Windows setups)
        tmp_path = path.with_suffix(".~tmp.xlsx")
        try:
            # PowerShell Copy-Item opens the source with FILE_SHARE_READ | WRITE
            result = subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    f"Copy-Item -LiteralPath '{path}' -Destination '{tmp_path}' -Force"
                ],
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise OSError(
                    f"WorkflowRegistry: PowerShell copy failed for '{path}'.\n"
                    f"stderr: {result.stderr.decode(errors='replace')}\n"
                    "Close the file in Excel and try again."
                )
            return tmp_path.read_bytes()
        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass  # best-effort cleanup

    @staticmethod
    def _clean(value) -> str:
        """
        Convert a cell value to a clean string.
        pandas reads missing cells as float NaN -- convert those to empty string.
        """
        if pd.isna(value):
            return ""
        return str(value).strip()
