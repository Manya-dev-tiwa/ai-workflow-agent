"""
src/main.py
-----------------------------------------------------------------------------
CLI entry point for the AI Workflow Agent.

Usage:
    python -m src.main "your request here"
    python -m src.main "Where is order ORD-1001?"
    python -m src.main "Which products need restocking?" --file data/mock_data/inventory.csv

What it does:
  1.  Loads the WorkflowRegistry from data/workflows.xlsx.
  2.  Runs the WorkflowRouter → selects the best workflow + extracts params.
  3.  Runs the WorkflowEngine → executes the workflow step by step.
  4.  Prints selected workflow, steps executed, and final output.
-----------------------------------------------------------------------------
"""

import sys
import argparse
import logging
from pathlib import Path

# Ensure UTF-8 output on Windows terminals (avoids cp1252 encode errors)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add project root to sys.path so `src.*` imports work when run as a module
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.registry import WorkflowRegistry
from src.agent.router   import WorkflowRouter
from src.agent.engine   import WorkflowEngine, format_result
from src.config         import LLM_PROVIDER


def _parse_args():
    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description="AI Workflow Agent — run a business workflow from natural language.",
    )
    parser.add_argument(
        "request",
        help='The user request in natural language, e.g. "Where is order ORD-1001?"',
    )
    parser.add_argument(
        "--file",
        default=None,
        dest="input_file",
        help="Optional: path to an input file that overrides the default sample file.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging to see every LLM call and tool execution.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()

    # ── Logging setup ─────────────────────────────────────────────────────────
    log_level = logging.DEBUG if args.debug else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s | %(name)s | %(message)s",
    )

    request = args.request.strip()
    if not request:
        print("ERROR: Please provide a non-empty request.")
        sys.exit(1)

    print(f"\n  Provider : {LLM_PROVIDER}")
    print(f"  Request  : {request}")
    if args.input_file:
        print(f"  File     : {args.input_file}")
    print()

    # ── Step 1: Load registry ─────────────────────────────────────────────────
    try:
        registry = WorkflowRegistry()
    except Exception as exc:
        print(f"ERROR: Could not load workflow registry.\n{exc}")
        sys.exit(1)

    # ── Step 2: Route ─────────────────────────────────────────────────────────
    print("Routing request...")
    router = WorkflowRouter(registry)
    route  = router.route(request)

    workflow_id = route.get("workflow_id")
    params      = route.get("parameters", {})
    reason      = route.get("reason", "")

    if workflow_id is None:
        print(f"\n  No matching workflow found.\n  Reason: {reason}")
        sys.exit(0)

    print(f"  -> Matched workflow : {workflow_id}")
    print(f"  -> Reason           : {reason}")
    print()

    # ── Step 3: Load the workflow definition ──────────────────────────────────
    workflow = registry.get_workflow(workflow_id)
    if workflow is None:
        print(f"ERROR: Workflow '{workflow_id}' not found in registry.")
        sys.exit(1)

    # ── Step 4: Run the engine ────────────────────────────────────────────────
    print(f"Running workflow {workflow_id}: {workflow.get('workflow_name', '')}...")
    engine = WorkflowEngine()
    result = engine.run(workflow, params, input_file=args.input_file)

    # ── Step 5: Print result ──────────────────────────────────────────────────
    print(format_result(result))

    # Exit with non-zero code on errors so scripts can detect failure
    if result.status == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
