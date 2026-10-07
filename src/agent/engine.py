"""
src/agent/engine.py
-----------------------------------------------------------------------------
WorkflowEngine -- generic LLM-driven step execution engine.

How it works (video-friendly summary):
  1.  The engine receives a workflow row from Excel (Steps, Decision_Logic,
      Expected_Output, etc.) plus the parameters the router extracted.
  2.  It builds ONE system prompt that contains:
        • The workflow instructions (straight from Excel text).
        • The schemas of all registered tools (so the LLM knows what it can call).
        • The result of every tool call so far (the "history").
  3.  Each round the LLM picks one of three actions:
        ACTION "call_tool"   → run a tool, append result to history, loop.
        ACTION "ask_user"    → a required input is missing; stop and ask.
        ACTION "final_answer"→ the workflow is done; return the answer.
  4.  Guardrails enforced entirely in Python (no LLM needed):
        • max_steps  – hard cap on tool calls (default from config.py).
        • Tool results are truncated to MAX_TOOL_RESULT_CHARS so the LLM
          context never grows unbounded.
        • Tool failures are returned TO the LLM as an error result so it
          can try a different tool or explain.
        • No `if workflow_id == "WFxxx"` — all logic comes from Excel text.

Input resolution (generic, no per-workflow code):
  The engine checks the workflow's Inputs column and, if a file is referenced
  (words like "CSV", "XLSX", "JSON", "file", "spreadsheet"), it looks for a
  matching file in data/samples/ or data/mock_data/.  An optional
  `input_file` argument passed by the caller overrides this completely.

Return value (EngineResult dataclass):
  {
    workflow_id:   str,
    workflow_name: str,
    steps:         list[StepRecord],   # tool name, args, short result, ok/error
    final_output:  str,
    status:        "ok" | "max_steps" | "ask_user" | "error"
  }
-----------------------------------------------------------------------------
"""

import datetime
import json
import logging
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import MAX_STEPS, SAMPLES_DIR, MOCK_DATA_DIR
from src.llm.client import LLMClient
from src.tools.registry import TOOL_REGISTRY, call_tool, get_all_schemas

logger = logging.getLogger(__name__)

# Tool result strings longer than this are truncated before being sent to the LLM.
# This prevents the context window from overflowing on large datasets.
MAX_TOOL_RESULT_CHARS = 3000


# ── Structured return types ────────────────────────────────────────────────────

@dataclass
class StepRecord:
    """Records one tool call made during a workflow run."""
    step_num:  int
    tool_name: str
    arguments: Dict[str, Any]
    result:    str          # short summary (truncated for readability)
    status:    str          # "ok" or "error"


@dataclass
class EngineResult:
    """The structured result returned to the caller after a workflow run."""
    workflow_id:   str
    workflow_name: str
    steps:         List[StepRecord] = field(default_factory=list)
    final_output:  str = ""
    status:        str = "ok"   # "ok" | "max_steps" | "ask_user" | "error"


# ── File-hint resolution ───────────────────────────────────────────────────────

# Keywords in the Inputs column that suggest a file is expected
_FILE_KEYWORDS = {"csv", "xlsx", "json", "file", "spreadsheet", "upload", "data"}

# Map workflow IDs to their primary sample / mock-data files.
# This is the ONLY place where a workflow ID appears — and only to resolve
# which pre-existing file to use as a demo input.  The engine logic itself
# has zero per-workflow conditionals.
_WF_DEFAULT_FILES: Dict[str, str] = {
    "WF001": str(MOCK_DATA_DIR / "inventory.csv"),
    "WF002": str(MOCK_DATA_DIR / "products.csv"),
    "WF003": str(SAMPLES_DIR   / "vendor_upload.csv"),
    "WF004": str(SAMPLES_DIR   / "product_input.json"),
    "WF005": str(MOCK_DATA_DIR / "orders.csv"),
    "WF006": str(MOCK_DATA_DIR / "catalog.csv"),
    "WF007": str(SAMPLES_DIR   / "campaign_brief_input.json"),
    "WF008": str(SAMPLES_DIR   / "keywords.csv"),
    "WF009": str(MOCK_DATA_DIR / "employees.csv"),
    "WF010": str(MOCK_DATA_DIR / "execution_logs.csv"),
}

# A second file some workflows need (e.g. WF002 needs vendor prices too)
_WF_SECONDARY_FILES: Dict[str, str] = {
    "WF002": str(MOCK_DATA_DIR / "vendor_prices.csv"),
}


def _resolve_input_files(
    workflow: Dict[str, Any],
    params: Dict[str, Any],
    input_file: Optional[str],
) -> Dict[str, Any]:
    """
    Decide which file paths to inject into the execution parameters.

    Priority order:
      1. Caller-supplied `input_file` argument (highest priority).
      2. A 'file_path' already present in `params` (from the router).
      3. Hint-based resolution: match workflow's Inputs and query hints ("this product",
         "this vendor spreadsheet", "these keywords", "this campaign brief") against
         pre-mapped default files or files in data/samples/.
      4. Nothing — the LLM will have to ask the user.

    Returns a copy of `params` enriched with file paths.
    """
    result = dict(params)  # copy, never mutate the caller's dict

    # 1. Explicit override from the caller (highest priority)
    if input_file:
        result["file_path"] = input_file
        return result

    # 2. Already in params (router extracted it)
    if "file_path" in result and result["file_path"]:
        return result

    wf_id = workflow.get("workflow_id", "")
    inputs_text = (workflow.get("inputs") or "").lower()

    # 3. Fall back to hint-based resolution (pre-mapped default or matching sample file in data/samples/)
    default = _WF_DEFAULT_FILES.get(wf_id)
    if not default and SAMPLES_DIR.exists():
        for sample_file in SAMPLES_DIR.iterdir():
            stem = sample_file.stem.lower()
            keywords = [w for w in stem.replace("_", " ").split() if w not in ("input", "upload", "missing")]
            if keywords and any(kw in inputs_text for kw in keywords):
                default = str(sample_file)
                break

    if default:
        result["file_path"] = default

    # If there's a secondary file (e.g. WF002 needs vendor prices), add it too
    secondary = _WF_SECONDARY_FILES.get(wf_id)
    if secondary:
        result.setdefault("secondary_file_path", secondary)

    return result


# ── Prompt builders ────────────────────────────────────────────────────────────

def _build_system_prompt(
    workflow: Dict[str, Any],
    input_file: Optional[str] = None,
    current_date: Optional[str] = None,
) -> str:
    """
    Build the engine's system prompt entirely from Excel data.
    Contains: workflow name, steps, decision logic, expected output, tool schemas.
    """
    today_str = current_date or datetime.date.today().isoformat()
    tool_schemas_json = json.dumps(get_all_schemas(), indent=2)

    attached_file_section = ""
    if input_file:
        attached_file_section = (
            f"\n== ATTACHED INPUT FILE ==\n"
            f"The user attached this file path: \"{input_file}\"\n"
            f"You MUST read it with the file loader tool (file_data_loader) BEFORE using ask_user.\n"
            f"Do not assume any required input is missing until you have loaded and inspected this file.\n"
        )

    prompt = f"""You are an AI execution engine for business workflow automation.
Today's date is {today_str}.

== CURRENT WORKFLOW ==
Name            : {workflow.get('workflow_name', '')}
Workflow ID     : {workflow.get('workflow_id', '')}
Steps to follow : {workflow.get('steps', '')}
Decision Logic  : {workflow.get('decision_logic', '')}
Expected Output : {workflow.get('expected_output', '')}
Inputs          : {workflow.get('inputs', '')}
Tools Required  : {workflow.get('tools_required', '')}
{attached_file_section}
== AVAILABLE TOOLS ==
{tool_schemas_json}

== YOUR JOB ==
Execute the workflow step by step using the tools above.
After each tool call you will receive the tool's result and decide what to do next.

At every turn you MUST reply with ONLY a valid JSON object in one of these three forms:

Form 1 — call a tool:
{{
  "action": "call_tool",
  "tool_name": "<name of tool>",
  "arguments": {{ "<param>": "<value>", ... }},
  "reason": "<one sentence: why this tool, why these arguments>"
}}

Form 2 — ask the user for missing required input:
{{
  "action": "ask_user",
  "question": "<what specific information do you need from the user? Must state exactly what is missing>",
  "reason": "<why this info is needed>"
}}

Form 3 — workflow complete, return final answer:
{{
  "action": "final_answer",
  "answer": "<complete, readable answer for the user; if the request asks to show or list specific records, include the actual records or identifiers and details/reasons, not just counts>",
  "reason": "<one sentence summary>"
}}

== STRICT RULES ==
- Today's date is {today_str}. Always evaluate dates and calculate overdue/elapsed days relative to {today_str}.
- Never invent data. If a record is not found, say so clearly in your answer.
- Copy every ID, name, and number exactly as it appears in the tool results. Never combine, guess, or invent identifiers. If you are unsure of an ID, omit it rather than guess.
- When an input file is attached or provided by the user, you MUST read it with the file loader tool (file_data_loader) BEFORE using ask_user.
- Only call ask_user for fields that are still missing after reading the file, and name exactly those fields.
- If no input file was attached or provided, and required business inputs or specifications (such as campaign goal, target audience, promotion details, dates, or task instructions) are missing, you MUST call ask_user naming exactly the missing fields, following the workflow's Decision Logic. Do NOT search sample folders for user inputs.
- Before calling ask_user for a missing system dataset or database (e.g. employee database, product catalog), call list_data_files and pick the file whose name or columns match the workflow's Inputs/Tools_Required.
- When the user request or workflow asks to show, list, or report specific records or identifiers (for example each invalid row with the reason it failed), the final answer must include the actual records or identifiers the request asks for, not just totals or summary counts. Only list what the tool results contain, never invent rows.
- Always use the actual tool schemas above; do not call tools that do not exist.
- Do NOT wrap your JSON in markdown code fences.
"""
    return prompt


def _build_user_message(
    params: Dict[str, Any],
    history: List[Dict],
    input_file: Optional[str] = None,
) -> str:
    """
    Build the user-turn message: initial parameters + history of tool results.
    """
    parts = []

    if input_file:
        parts.append(
            f"== ATTACHED INPUT FILE ==\n"
            f"The user attached this file path: {input_file}\n"
            f"You MUST read it with the file loader tool (file_data_loader) BEFORE using ask_user."
        )

    if params:
        parts.append("== INITIAL PARAMETERS (from user request) ==")
        parts.append(json.dumps(params, indent=2))

    if history:
        parts.append("\n== TOOL CALL HISTORY ==")
        for entry in history:
            parts.append(
                f"Step {entry['step']}:\n"
                f"  Tool   : {entry['tool_name']}\n"
                f"  Args   : {json.dumps(entry['arguments'])}\n"
                f"  Result : {entry['result_summary']}\n"
                f"  Status : {entry['status']}"
            )

    parts.append("\nWhat is your next action?")
    return "\n".join(parts)


def _summarise_result(tool_result: dict) -> str:
    """
    Convert a tool's return dict into a short string for the LLM history.
    Truncates large results so the LLM context stays manageable.
    """
    if not tool_result.get("ok"):
        return f"ERROR: {tool_result.get('error', 'unknown error')}"

    data = tool_result.get("data")
    if data is None:
        return "OK (no data returned)"

    # If there's a pre-formatted report string, use that
    if isinstance(data, dict) and "report" in data:
        text = str(data["report"])
    else:
        text = json.dumps(data, default=str)

    # Truncate long results
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + f"\n... [truncated to {MAX_TOOL_RESULT_CHARS} chars]"

    return text


# ── The engine class ───────────────────────────────────────────────────────────

class WorkflowEngine:
    """
    Generic LLM-driven execution engine.
    Runs any workflow defined in the Excel registry without any per-workflow code.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        """
        Parameters
        ----------
        llm_client : optional LLMClient (or FakeLLM for testing)
            If None, a default LLMClient is created from config.
        """
        self.llm = llm_client if llm_client is not None else LLMClient()

    def run(
        self,
        workflow: Dict[str, Any],
        params: Dict[str, Any],
        input_file: Optional[str] = None,
        max_steps: int = MAX_STEPS,
        current_date: Optional[str] = None,
    ) -> EngineResult:
        """
        Execute a workflow and return a structured EngineResult.

        Parameters
        ----------
        workflow     : dict from WorkflowRegistry.get_workflow()
        params       : parameters extracted by the router
        input_file   : optional file path that overrides the default input file
        max_steps    : maximum number of tool calls allowed
        current_date : optional ISO date string overriding datetime.date.today()
        """
        wf_id   = workflow.get("workflow_id", "UNKNOWN")
        wf_name = workflow.get("workflow_name", "Unknown Workflow")

        result = EngineResult(workflow_id=wf_id, workflow_name=wf_name)

        # Enrich params with resolved file paths (generic, not per-workflow)
        params = _resolve_input_files(workflow, params, input_file or params.get("input_file"))

        # Determine effective attached input file (explicit override or hint-resolved default)
        attached_file = input_file or params.get("input_file") or params.get("file_path")

        # Build the fixed system prompt (stays the same for every loop turn)
        system_prompt = _build_system_prompt(workflow, input_file=attached_file, current_date=current_date)

        # History accumulates tool results so the LLM can see what has happened
        history: List[Dict] = []

        logger.info(f"Engine starting workflow {wf_id}: {wf_name}")

        # ── Main loop ──────────────────────────────────────────────────────────
        for step_num in range(1, max_steps + 1):

            # Build the message the LLM sees this turn
            user_message = _build_user_message(params, history, input_file=attached_file)

            # Ask the LLM what to do next
            llm_response = self.llm.generate_json(system_prompt, user_message)

            # If the LLM client itself returned an error (API down, bad key…)
            if "error" in llm_response and "action" not in llm_response:
                result.final_output = (
                    f"Engine stopped: LLM returned an error.\n"
                    f"Details: {llm_response.get('error', 'unknown')}"
                )
                result.status = "error"
                return result

            action = llm_response.get("action", "").strip().lower()

            # ── Action: call a tool ────────────────────────────────────────────
            if action == "call_tool":
                tool_name = llm_response.get("tool_name", "")
                arguments = llm_response.get("arguments", {})
                reason    = llm_response.get("reason", "")

                if not isinstance(arguments, dict):
                    arguments = {}

                logger.info(f"  Step {step_num}: calling tool '{tool_name}' | {reason}")

                # Execute the tool (returns ok/error dict, never raises)
                tool_result = call_tool(tool_name, **arguments)
                summary     = _summarise_result(tool_result)
                status_str  = "ok" if tool_result.get("ok") else "error"

                # Record this step
                result.steps.append(StepRecord(
                    step_num  = step_num,
                    tool_name = tool_name,
                    arguments = arguments,
                    result    = summary[:500],   # short version for the output
                    status    = status_str,
                ))

                # Feed result back into history so the LLM sees it next round
                history.append({
                    "step":           step_num,
                    "tool_name":      tool_name,
                    "arguments":      arguments,
                    "result_summary": summary,
                    "status":         status_str,
                })

            # ── Action: ask user for missing input ─────────────────────────────
            elif action == "ask_user":
                question = llm_response.get("question", "More information is needed.")
                result.final_output = f"I need more information to continue:\n\n{question}"
                result.status = "ask_user"
                logger.info(f"  Engine asking user: {question}")
                return result

            # ── Action: final answer ───────────────────────────────────────────
            elif action == "final_answer":
                answer = llm_response.get("answer", "")
                result.final_output = answer
                result.status = "ok"
                logger.info(f"  Engine returned final answer after {step_num} step(s).")
                return result

            # ── Unknown action (bad LLM output) ───────────────────────────────
            else:
                logger.warning(
                    f"  Step {step_num}: LLM returned unknown action '{action}'. "
                    f"Raw: {llm_response}"
                )
                # Record the bad turn and let the loop continue
                history.append({
                    "step":           step_num,
                    "tool_name":      "unknown",
                    "arguments":      {},
                    "result_summary": f"LLM returned unknown action: {action}",
                    "status":         "error",
                })

        # ── Max steps reached ──────────────────────────────────────────────────
        result.final_output = (
            f"Workflow stopped: reached the maximum of {max_steps} steps "
            f"without a final answer. Check the step log for details."
        )
        result.status = "max_steps"
        logger.warning(f"  Engine hit max_steps ({max_steps}) for workflow {wf_id}.")
        return result


# ── Pretty-printer ─────────────────────────────────────────────────────────────

def format_result(result: EngineResult) -> str:
    """
    Format an EngineResult into a readable multi-section string.
    Used by the CLI (src/main.py) and the run_all_workflows script.
    """
    lines = [
        "=" * 70,
        f"  Workflow : {result.workflow_id} — {result.workflow_name}",
        f"  Status   : {result.status.upper()}",
        "=" * 70,
    ]

    if result.steps:
        lines.append(f"\n  Steps Executed ({len(result.steps)}):")
        lines.append("  " + "-" * 66)
        for s in result.steps:
            lines.append(f"  [{s.step_num}] {s.tool_name}  [{s.status.upper()}]")
            # Show arguments compactly
            args_str = json.dumps(s.arguments)
            if len(args_str) > 120:
                args_str = args_str[:120] + "..."
            lines.append(f"       args   : {args_str}")
            # First line of result
            first_line = s.result.split("\n")[0][:120]
            lines.append(f"       result : {first_line}")
    else:
        lines.append("\n  (No tool steps executed)")

    lines.append("\n" + "=" * 70)
    lines.append("  FINAL OUTPUT")
    lines.append("=" * 70)
    # Indent the final output slightly for readability
    for line in result.final_output.splitlines():
        lines.append("  " + line)
    lines.append("=" * 70)

    return "\n".join(lines)
