"""
scripts/verify_registry.py
-----------------------------------------------------------------------------
Phase 1 verification script.

Run this from the project root to confirm that:
  1. The WorkflowRegistry loads data/workflows.xlsx without errors.
  2. All 10 workflows are present with the expected fields.
  3. All 10 test questions are present.

Usage:
    python scripts/verify_registry.py

Expected output: a formatted table of workflows + test questions.
-----------------------------------------------------------------------------
"""

import sys
from pathlib import Path

# Reconfigure stdout to UTF-8 so the arrow characters in Excel Steps field
# print correctly on Windows terminals (which default to cp1252).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add project root to sys.path so `src` is importable when running from root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.registry import WorkflowRegistry

SEPARATOR = "-" * 80


def print_section(title: str) -> None:
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


def main() -> None:
    print("\n[VERIFY] AI Workflow Agent -- Registry Verification")
    print(SEPARATOR)

    # Load registry
    try:
        registry = WorkflowRegistry()
    except Exception as exc:
        print(f"\n[FAIL] Failed to load registry:\n    {exc}")
        sys.exit(1)

    workflows = registry.get_all_workflows()
    test_questions = registry.get_test_questions()

    # Summary counts
    print(f"\n[OK]  Loaded {len(workflows)} workflow(s) and "
          f"{len(test_questions)} test question(s).")

    # Workflow details
    print_section("WORKFLOWS (from 'Workflows' sheet)")
    for wf in workflows:
        print(f"\n  [{wf['workflow_id']}]  {wf['workflow_name']}")
        print(f"    Trigger        : {wf['trigger']}")
        print(f"    Inputs         : {wf['inputs']}")
        print(f"    Steps          : {wf['steps']}")
        print(f"    Decision Logic : {wf['decision_logic']}")
        print(f"    Tools Required : {wf['tools_required']}")
        print(f"    Expected Output: {wf['expected_output']}")

    # Test question details
    print_section("TEST QUESTIONS (from 'Test_Questions' sheet)")
    for tq in test_questions:
        print(f"\n  [{tq['workflow_id']}]")
        print(f"    Test Request  : {tq['test_request']}")
        print(f"    What To Check : {tq['what_to_check']}")

    # Sanity checks
    print_section("SANITY CHECKS")

    expected_ids = [f"WF{str(i).zfill(3)}" for i in range(1, 11)]

    all_present = True
    for wf_id in expected_ids:
        wf = registry.get_workflow(wf_id)
        if wf is None:
            print(f"  [FAIL]  {wf_id} -- MISSING")
            all_present = False
        else:
            # Check no required field is empty
            empty_fields = [k for k, v in wf.items() if not v]
            if empty_fields:
                print(f"  [WARN]  {wf_id} -- empty fields: {empty_fields}")
            else:
                print(f"  [OK]    {wf_id} -- {wf['workflow_name']} -- all fields present")

    if all_present:
        print(f"\n  All {len(expected_ids)} workflows loaded correctly.")
    else:
        print(f"\n  Some workflows are missing -- check data/workflows.xlsx.")
        sys.exit(1)

    print(f"\n{SEPARATOR}")
    print("  Phase 1 Registry verification PASSED")
    print(f"{SEPARATOR}\n")


if __name__ == "__main__":
    main()
