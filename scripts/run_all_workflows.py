"""
scripts/run_all_workflows.py
-----------------------------------------------------------------------------
End-to-end runner for all 10 Test_Requests.

For each workflow:
  1. Routes the Test_Request from the Test_Questions sheet.
  2. Runs the engine end-to-end.
  3. Saves the result to examples/outputs/WFxxx.md.
  4. Waits 2 seconds between requests to respect free-tier rate limits.

Usage:
    python scripts/run_all_workflows.py

Output files: examples/outputs/WFxxx.md (one file per workflow).
-----------------------------------------------------------------------------
"""

import sys
import time
import json
from pathlib import Path

# Make sure `src.*` imports work from any working directory
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agent.registry import WorkflowRegistry
from src.agent.router   import WorkflowRouter
from src.agent.engine   import WorkflowEngine, format_result, EngineResult
from src.config         import LLM_PROVIDER

# Where to write the per-workflow result files
OUTPUT_DIR = ROOT_DIR / "examples" / "outputs"


def save_markdown(wf_id: str, request: str, result: EngineResult) -> Path:
    """
    Write the EngineResult for one workflow to a Markdown file.
    Returns the path of the written file.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{wf_id}.md"

    steps_md = ""
    if result.steps:
        rows = ["| # | Tool | Status | First line of result |", "|---|------|--------|----------------------|"]
        for s in result.steps:
            first_line = s.result.split("\n")[0][:80].replace("|", "\\|")
            rows.append(f"| {s.step_num} | `{s.tool_name}` | {s.status.upper()} | {first_line} |")
        steps_md = "\n".join(rows)
    else:
        steps_md = "_No tool steps executed._"

    content = f"""# {wf_id} — {result.workflow_name}

**Status:** `{result.status.upper()}`  
**Provider:** `{LLM_PROVIDER}`

## Test Request

> {request}

## Steps Executed

{steps_md}

## Final Output

```
{result.final_output}
```
"""
    out_path.write_text(content, encoding="utf-8")
    return out_path


def main():
    print("=" * 70)
    print("  AI Workflow Agent — End-to-End Workflow Runner")
    print("=" * 70)
    print(f"  Provider : {LLM_PROVIDER}")
    print(f"  Output   : {OUTPUT_DIR}")
    print()

    # ── Load registry ─────────────────────────────────────────────────────────
    try:
        registry = WorkflowRegistry()
    except Exception as exc:
        print(f"ERROR loading registry: {exc}")
        sys.exit(1)

    test_questions = registry.get_test_questions()
    target_ids = set(sys.argv[1:]) if len(sys.argv) > 1 else None
    if target_ids:
        test_questions = [tq for tq in test_questions if tq.get("workflow_id") in target_ids]
    print(f"  Loaded {len(test_questions)} test questions from Excel.\n")

    router = WorkflowRouter(registry)
    engine = WorkflowEngine()

    passed = 0
    failed = 0

    for idx, tq in enumerate(test_questions, 1):
        expected_id  = tq.get("workflow_id", "")
        request_text = tq.get("test_request", "")

        print(f"[{idx:02d}/{len(test_questions)}] {expected_id}: \"{request_text}\"")

        # ── Route ─────────────────────────────────────────────────────────────
        route = router.route(request_text)
        selected_id = route.get("workflow_id")
        params      = route.get("parameters", {})
        reason      = route.get("reason", "")

        if selected_id is None:
            print(f"       -> Router: no match. Reason: {reason}")
            # Save a placeholder result
            result = EngineResult(
                workflow_id   = expected_id,
                workflow_name = "Unmatched",
                final_output  = f"Router returned no match. Reason: {reason}",
                status        = "error",
            )
            save_markdown(expected_id, request_text, result)
            failed += 1
        else:
            match_str = "OK" if selected_id == expected_id else f"MISMATCH (expected {expected_id})"
            print(f"       -> Router: {selected_id} [{match_str}]  params: {json.dumps(params)}")

            # ── Get the workflow definition ────────────────────────────────────
            workflow = registry.get_workflow(selected_id)
            if workflow is None:
                print(f"       -> ERROR: workflow '{selected_id}' not found in registry.")
                failed += 1
            else:
                # ── Run the engine ─────────────────────────────────────────────
                try:
                    result = engine.run(workflow, params)
                    out_path = save_markdown(expected_id, request_text, result)
                    print(f"       -> Engine: {result.status.upper()} | {len(result.steps)} steps | saved to {out_path.name}")
                    passed += 1
                except Exception as exc:
                    print(f"       -> Engine CRASHED: {exc}")
                    failed += 1

        print()

        # 2-second pause between requests to avoid hitting rate limits
        if idx < len(test_questions):
            time.sleep(2)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("=" * 70)
    print(f"  DONE — {passed} passed / {failed} failed / {len(test_questions)} total")
    print(f"  Results saved to: {OUTPUT_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
