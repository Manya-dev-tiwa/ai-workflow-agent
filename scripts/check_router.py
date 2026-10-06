"""
scripts/check_router.py
-----------------------------------------------------------------------------
Router Verification Script.

Sends all 10 Test_Requests from the Test_Questions sheet in data/workflows.xlsx
plus 3 non-matching requests to the real WorkflowRouter.

A 2-second pause is added between requests to stay within free-tier rate limits.

Outputs:
  • Test #, Request text, Expected vs Selected Workflow ID, Match status.
  • Extracted parameters and LLM reasoning.
  • Final summary accuracy table.
-----------------------------------------------------------------------------
"""

import sys
import json
import time
from pathlib import Path

# Ensure UTF-8 output encoding for Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agent.registry import WorkflowRegistry
from src.agent.router import WorkflowRouter
from src.config import LLM_PROVIDER


def main():
    print("=" * 80)
    print("               AI WORKFLOW AGENT -- ROUTER VERIFICATION SCRIPT          ")
    print("=" * 80)

    # 1. Load Registry from Excel
    try:
        registry = WorkflowRegistry()
        print(f"[+] Excel registry loaded successfully ({len(registry.get_all_workflows())} workflows).")
    except Exception as exc:
        print(f"[-] ERROR: Failed to load WorkflowRegistry: {exc}")
        sys.exit(1)

    # 2. Initialize Router
    print(f"[+] Initializing WorkflowRouter (Active Provider: '{LLM_PROVIDER}')...\n")
    router = WorkflowRouter(registry)

    # 3. Gather Test Questions from Excel
    excel_test_questions = registry.get_test_questions()

    # 4. Add 3 non-matching test cases (Expected workflow_id = None)
    non_matching_questions = [
        {
            "workflow_id": None,
            "test_request": "What is the weather today in New York?",
            "what_to_check": "Should match NO workflow (returns workflow_id = null)",
        },
        {
            "workflow_id": None,
            "test_request": "Can you write a short poem about artificial intelligence?",
            "what_to_check": "Should match NO workflow (returns workflow_id = null)",
        },
        {
            "workflow_id": None,
            "test_request": "How do I bake a chocolate cake at home?",
            "what_to_check": "Should match NO workflow (returns workflow_id = null)",
        },
    ]

    all_test_cases = excel_test_questions + non_matching_questions

    passed_count = 0
    total_count = len(all_test_cases)

    print("-" * 80)
    print(f"Running Router Verification on {total_count} test requests...")
    print("-" * 80)

    for idx, test_item in enumerate(all_test_cases, 1):
        expected_id = test_item.get("workflow_id")
        request_text = test_item.get("test_request", "")

        # Pause between requests to respect free-tier rate limits (2 req/s typical).
        # Skip the pause before the very first request.
        if idx > 1:
            time.sleep(2)

        # Route the request using LLMRouter
        result = router.route(request_text)
        selected_id = result.get("workflow_id")
        params = result.get("parameters", {})
        reason = result.get("reason", "")

        # Check match (handles None equality cleanly)
        is_match = selected_id == expected_id
        if is_match:
            passed_count += 1
            status_str = "MATCH    [OK]"
        else:
            status_str = "MISMATCH [X]"

        expected_display = str(expected_id) if expected_id is not None else "None (null)"
        selected_display = str(selected_id) if selected_id is not None else "None (null)"

        print(f"Test #{idx:02d}: {status_str}")
        print(f"  * Request    : \"{request_text}\"")
        print(f"  * Expected   : {expected_display}")
        print(f"  * Selected   : {selected_display}")
        print(f"  * Parameters : {json.dumps(params)}")
        print(f"  * LLM Reason : {reason}")
        print("-" * 80)

    print("\n" + "=" * 80)
    print("                           SUMMARY RESULTS                            ")
    print("=" * 80)
    print(f"  Total Requests Tested : {total_count}")
    print(f"  Successful Matches    : {passed_count}")
    print(f"  Mismatches            : {total_count - passed_count}")
    accuracy = (passed_count / total_count) * 100 if total_count > 0 else 0
    print(f"  Router Accuracy       : {accuracy:.1f}%")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
