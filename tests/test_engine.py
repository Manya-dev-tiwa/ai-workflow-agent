"""
tests/test_engine.py
-----------------------------------------------------------------------------
Unit tests for WorkflowEngine using a FakeLLM (zero API / network calls).

Test scenarios:
  1. Normal tool loop — LLM calls one tool then gives a final answer.
  2. Tool error         — tool fails, LLM receives the error and still finishes.
  3. Max-steps reached  — LLM keeps calling tools until the cap is hit.
  4. Ask-user           — LLM requests a missing required input and stops.
-----------------------------------------------------------------------------
"""

import pytest
from typing import Any, Dict, List, Optional

from src.agent.engine import WorkflowEngine, EngineResult, StepRecord


# ── FakeLLM ───────────────────────────────────────────────────────────────────

class FakeLLM:
    """
    Mock LLM client that returns pre-scripted JSON responses in sequence.
    Supports:
      - A list of responses consumed one at a time (round-robin if exhausted).
      - Inspection of every prompt sent (for assertions).
    """

    def __init__(self, responses: List[Dict[str, Any]]):
        """
        Parameters
        ----------
        responses : list of dicts
            Each dict is the parsed JSON the LLM would return for one turn.
            They are consumed in order; the last one is repeated if the list
            is exhausted.
        """
        self.responses  = responses
        self.call_count = 0
        self.provider   = "fake"
        self.prompts: List[str] = []   # stores every user prompt for inspection

    def validate_key(self):
        return True, ""

    def generate_json(self, system_prompt: str, user_prompt: str, max_retries: int = 1):
        self.prompts.append(user_prompt)
        idx = min(self.call_count, len(self.responses) - 1)
        response = self.responses[idx]
        self.call_count += 1
        return response


# ── Minimal workflow fixture ───────────────────────────────────────────────────

MINIMAL_WORKFLOW = {
    "workflow_id":     "WF001",
    "workflow_name":   "Test Workflow",
    "steps":           "Step 1: load data. Step 2: return answer.",
    "decision_logic":  "If stock < minimum, mark for restock.",
    "inputs":          "Product inventory CSV",
    "expected_output": "List of products needing restock.",
    "tools_required":  "file_data_loader",
}


# ── Test 1: Normal tool loop ──────────────────────────────────────────────────

def test_engine_normal_tool_loop():
    """
    LLM calls file_data_loader once, then returns a final_answer.
    Verifies: one step recorded, status = ok, final_output has the answer text.
    """
    fake_llm = FakeLLM(responses=[
        # Turn 1: call a real tool (file_data_loader with a known file)
        {
            "action":    "call_tool",
            "tool_name": "file_data_loader",
            "arguments": {"file_path": "data/mock_data/inventory.csv"},
            "reason":    "Need to read the inventory file.",
        },
        # Turn 2: give the final answer
        {
            "action": "final_answer",
            "answer": "Product A needs restocking (stock: 5, min: 10).",
            "reason": "Computed from inventory data.",
        },
    ])

    engine = WorkflowEngine(llm_client=fake_llm)
    result = engine.run(MINIMAL_WORKFLOW, params={})

    assert result.status == "ok"
    assert len(result.steps) == 1                     # one tool step
    assert result.steps[0].tool_name == "file_data_loader"
    assert result.steps[0].status   == "ok"
    assert "Product A" in result.final_output
    assert fake_llm.call_count == 2


# ── Test 2: Tool error ────────────────────────────────────────────────────────

def test_engine_tool_error_then_final_answer():
    """
    The first tool call fails (bad file path).
    The LLM receives the error and still returns a final_answer.
    Verifies: step recorded as 'error', engine still completes with status = ok.
    """
    fake_llm = FakeLLM(responses=[
        # Turn 1: call tool with a path that does not exist
        {
            "action":    "call_tool",
            "tool_name": "file_data_loader",
            "arguments": {"file_path": "data/nonexistent_file.csv"},
            "reason":    "Trying to load the file.",
        },
        # Turn 2: LLM acknowledges the error and responds
        {
            "action": "final_answer",
            "answer": "Could not load the file. Please check the file path.",
            "reason": "File not found error was returned by the tool.",
        },
    ])

    engine = WorkflowEngine(llm_client=fake_llm)
    result = engine.run(MINIMAL_WORKFLOW, params={})

    assert result.status == "ok"                       # engine finished normally
    assert len(result.steps) == 1
    assert result.steps[0].status == "error"           # tool step was an error
    assert "Could not load" in result.final_output


# ── Test 3: Max steps reached ─────────────────────────────────────────────────

def test_engine_max_steps_reached():
    """
    LLM keeps calling tools forever. The engine should stop after max_steps.
    Verifies: status = max_steps, correct number of steps recorded.
    """
    # Always returns "call a tool" — never a final_answer
    never_ending = {
        "action":    "call_tool",
        "tool_name": "file_data_loader",
        "arguments": {"file_path": "data/mock_data/inventory.csv"},
        "reason":    "Loading data again.",
    }
    fake_llm = FakeLLM(responses=[never_ending])

    engine = WorkflowEngine(llm_client=fake_llm)
    result = engine.run(MINIMAL_WORKFLOW, params={}, max_steps=3)

    assert result.status == "max_steps"
    assert len(result.steps) == 3                      # exactly max_steps steps
    assert "maximum" in result.final_output.lower()


# ── Test 4: Ask user for missing input ────────────────────────────────────────

def test_engine_ask_user_for_missing_input():
    """
    LLM cannot proceed without a required input and requests it from the user.
    Verifies: status = ask_user, final_output contains the question.
    """
    fake_llm = FakeLLM(responses=[
        {
            "action":   "ask_user",
            "question": "Which product name or SKU should I look up?",
            "reason":   "No product identifier was provided in the request.",
        },
    ])

    engine = WorkflowEngine(llm_client=fake_llm)
    result = engine.run(MINIMAL_WORKFLOW, params={})

    assert result.status == "ask_user"
    assert "product name" in result.final_output.lower()
    assert len(result.steps) == 0                      # no tool was called
    assert fake_llm.call_count == 1


# ── Test 5: Call list_data_files before asking user for missing dataset ────────

def test_engine_list_data_files_before_asking_user():
    """
    When a workflow requires a dataset/file that is not in params,
    the LLM calls list_data_files to find matching files instead of immediately
    asking the user for a file path.
    """
    workflow_needing_data = {
        "workflow_id":     "WF009",
        "workflow_name":   "Employee Task Assignment",
        "steps":           "Compare employee skills -> select employee",
        "decision_logic":  "Pick employee with required skills and capacity",
        "inputs":          "Task description; employee list; skills; workload",
        "expected_output": "Recommended employee and reasoning",
        "tools_required":  "Employee database",
    }

    fake_llm = FakeLLM(responses=[
        # Turn 1: Instead of calling ask_user for missing dataset, call list_data_files
        {
            "action":    "call_tool",
            "tool_name": "list_data_files",
            "arguments": {},
            "reason":    "Need to discover existing data files for employee list.",
        },
        # Turn 2: Pick data/mock_data/employees.csv from list_data_files result and load it
        {
            "action":    "call_tool",
            "tool_name": "file_data_loader",
            "arguments": {"file_path": "data/mock_data/employees.csv"},
            "reason":    "Load employees dataset found from list_data_files.",
        },
        # Turn 3: Final answer
        {
            "action": "final_answer",
            "answer": "Assigned urgent task to James Carter (Senior Developer with lowest workload).",
            "reason": "James Carter is available and has required capacity.",
        },
    ])

    engine = WorkflowEngine(llm_client=fake_llm)
    result = engine.run(workflow_needing_data, params={"task_description": "Urgent task", "priority": "urgent"})

    assert result.status == "ok"
    assert len(result.steps) == 2
    assert result.steps[0].tool_name == "list_data_files"
    assert result.steps[0].status == "ok"
    assert result.steps[1].tool_name == "file_data_loader"
    assert result.steps[1].status == "ok"
    assert "James Carter" in result.final_output
    assert fake_llm.call_count == 3


# ── Test 6: Input file provided -> file loader tool called before final answer ─

def test_engine_input_file_calls_loader_before_final_answer():
    """
    When an input_file is provided (e.g. JSON or CSV), the engine prompt
    informs the LLM of the attached file, and the LLM must call file_data_loader
    before returning a final answer or ask_user.
    """
    input_file_path = "data/samples/campaign_brief_input.json"

    fake_llm = FakeLLM(responses=[
        # Turn 1: LLM sees the attached file in the prompt and calls file_data_loader
        {
            "action":    "call_tool",
            "tool_name": "file_data_loader",
            "arguments": {"file_path": input_file_path},
            "reason":    "Need to load the attached campaign brief JSON file before proceeding.",
        },
        # Turn 2: LLM has the data from file_data_loader and returns the final answer
        {
            "action": "final_answer",
            "answer": "Created marketing campaign brief for the Autumn Home Office Collection.",
            "reason": "All required campaign parameters were loaded from the attached input file.",
        },
    ])

    engine = WorkflowEngine(llm_client=fake_llm)
    workflow = {
        "workflow_id":     "WF007",
        "workflow_name":   "Marketing Campaign Brief",
        "steps":           "Validate inputs -> create brief",
        "decision_logic":  "If inputs missing, ask user",
        "inputs":          "Campaign goal; product list; target audience; promotion; dates",
        "expected_output": "Marketing brief",
        "tools_required":  "file_data_loader",
    }

    result = engine.run(workflow, params={}, input_file=input_file_path)

    assert result.status == "ok"
    assert len(result.steps) == 1
    assert result.steps[0].tool_name == "file_data_loader"
    assert result.steps[0].arguments["file_path"] == input_file_path
    assert result.steps[0].status == "ok"
    assert "Autumn Home Office Collection" in result.final_output
    assert fake_llm.call_count == 2

    # Verify that the engine prompt informed the LLM about the attached input file
    assert len(fake_llm.prompts) >= 1
    first_prompt = fake_llm.prompts[0]
    assert input_file_path in first_prompt
    assert "file_data_loader" in first_prompt


# ── Test 7: Input file with missing fields -> loader called before ask_user ───

def test_engine_input_file_missing_fields_asks_user_after_loader():
    """
    When an input_file is read but some required fields are still missing,
    the loader is called first, and then ask_user is called specifically for the missing fields.
    """
    input_file_path = "data/samples/campaign_brief_missing.json"

    fake_llm = FakeLLM(responses=[
        # Turn 1: LLM calls file_data_loader
        {
            "action":    "call_tool",
            "tool_name": "file_data_loader",
            "arguments": {"file_path": input_file_path},
            "reason":    "Load attached file to inspect fields.",
        },
        # Turn 2: LLM notices campaign_goal and dates are missing
        {
            "action":   "ask_user",
            "question": "The campaign goal and dates are missing. Please provide them.",
            "reason":   "campaign_goal and dates were not found in the input file.",
        },
    ])

    engine = WorkflowEngine(llm_client=fake_llm)
    workflow = {
        "workflow_id":     "WF007",
        "workflow_name":   "Marketing Campaign Brief",
        "steps":           "Validate inputs -> create brief",
        "decision_logic":  "If campaign goal or dates missing, ask user",
        "inputs":          "Campaign goal; product list; target audience; promotion; dates",
        "expected_output": "Marketing brief",
        "tools_required":  "file_data_loader",
    }

    result = engine.run(workflow, params={}, input_file=input_file_path)

    assert result.status == "ask_user"
    assert len(result.steps) == 1
    assert result.steps[0].tool_name == "file_data_loader"
    assert "campaign goal" in result.final_output.lower()


# ── Test 8: Request asks to show invalid rows -> final answer includes actual records

def test_engine_prompt_instructs_actual_records_and_returns_invalid_rows():
    """
    When a request asks to show invalid rows / specific records,
    the system prompt instructs the LLM to return actual records/identifiers with reasons,
    not just counts/totals, without inventing rows.
    """
    fake_llm = FakeLLM(responses=[
        # Turn 1: load vendor upload file
        {
            "action":    "call_tool",
            "tool_name": "file_data_loader",
            "arguments": {"file_path": "data/samples/vendor_upload.csv"},
            "reason":    "Load vendor spreadsheet for validation.",
        },
        # Turn 2: validate required columns and fields
        {
            "action":    "call_tool",
            "tool_name": "tabular_validator_cleaner",
            "arguments": {
                "rows": [
                    {"SKU": "SKU-V01", "Product_Name": "Bluetooth Speaker", "Category": "Electronics", "Price": "39.99", "Stock_Quantity": "50"},
                    {"SKU": "SKU-V02", "Product_Name": "", "Category": "Accessories", "Price": "9.99", "Stock_Quantity": "100"},
                    {"SKU": "", "Product_Name": "Standing Desk", "Category": "Furniture", "Price": "349.99", "Stock_Quantity": "5"},
                ],
                "required_columns": ["SKU", "Product_Name"],
                "required_fields": ["SKU", "Product_Name"],
            },
            "reason":    "Validate required fields SKU and Product_Name.",
        },
        # Turn 3: final answer including the actual invalid records and reasons
        {
            "action": "final_answer",
            "answer": (
                "Validation complete: 1 valid row and 2 invalid rows found.\n"
                "Invalid rows:\n"
                "- SKU 'SKU-V02': missing required field Product_Name\n"
                "- Product 'Standing Desk' (missing SKU): missing required field SKU"
            ),
            "reason": "Provided summary and specific invalid records with reasons.",
        },
    ])

    engine = WorkflowEngine(llm_client=fake_llm)
    workflow = {
        "workflow_id":     "WF003",
        "workflow_name":   "Vendor File Processing",
        "steps":           "Read file -> detect columns -> validate required fields -> identify invalid rows",
        "decision_logic":  "Rows missing SKU or product name are invalid",
        "inputs":          "CSV/XLSX file containing vendor product data",
        "expected_output": "Cleaned file plus validation summary and invalid-row report",
        "tools_required":  "file_data_loader; tabular_validator_cleaner; report_formatter",
    }

    result = engine.run(workflow, params={"test_request": "Process this vendor spreadsheet and show invalid rows."})

    assert result.status == "ok"
    assert len(result.steps) == 2
    assert result.steps[0].tool_name == "file_data_loader"
    assert result.steps[1].tool_name == "tabular_validator_cleaner"
    assert "SKU-V02" in result.final_output
    assert "Standing Desk" in result.final_output
    assert "missing" in result.final_output.lower()

    # Verify that the system prompt informed the LLM to include actual records/identifiers
    assert len(fake_llm.prompts) >= 1
    # Check that system prompt rules require actual records/identifiers
    from src.agent.engine import _build_system_prompt
    sys_prompt = _build_system_prompt(workflow)
    assert "actual records or identifiers" in sys_prompt
    assert "never invent rows" in sys_prompt


# ── Test 9: Input file resolution — explicit file vs hint without file ───────

def test_input_file_resolution_explicit_and_hint():
    """
    Test input file resolution in engine:
    1. Explicit file priority: when input_file is given, it is used and attached in prompt.
    2. Hint without file: when no file is given, engine falls back to hint-based resolution
       (WF004 -> data/samples/product_input.json) and attaches it in system & user prompts.
    """
    workflow_wf004 = {
        "workflow_id":     "WF004",
        "workflow_name":   "Product Description Generator",
        "steps":           "Validate required attributes -> create product description",
        "decision_logic":  "Do not invent missing product attributes",
        "inputs":          "Product name; category; attributes; material; color; target audience",
        "expected_output": "Product description",
        "tools_required":  "file_data_loader; llm_content_generator",
    }

    # Case 1: Explicit file provided (top priority)
    fake_llm_explicit = FakeLLM(responses=[
        {
            "action":    "call_tool",
            "tool_name": "file_data_loader",
            "arguments": {"file_path": "data/samples/custom_product.json"},
            "reason":    "Load explicit input file.",
        },
        {
            "action": "final_answer",
            "answer": "Generated content from explicit file.",
            "reason": "Done.",
        },
    ])
    engine_explicit = WorkflowEngine(llm_client=fake_llm_explicit)
    result_explicit = engine_explicit.run(workflow_wf004, params={}, input_file="data/samples/custom_product.json")

    assert result_explicit.status == "ok"
    assert len(result_explicit.steps) == 1
    assert result_explicit.steps[0].arguments["file_path"] == "data/samples/custom_product.json"
    assert "data/samples/custom_product.json" in fake_llm_explicit.prompts[0]

    # Case 2: Hint without file provided (falls back to hint-resolved sample file)
    fake_llm_hint = FakeLLM(responses=[
        {
            "action":    "call_tool",
            "tool_name": "file_data_loader",
            "arguments": {"file_path": "data/samples/product_input.json"},
            "reason":    "Load hint-resolved product input file.",
        },
        {
            "action": "final_answer",
            "answer": "Generated content from hint-resolved file.",
            "reason": "Done.",
        },
    ])
    engine_hint = WorkflowEngine(llm_client=fake_llm_hint)
    result_hint = engine_hint.run(workflow_wf004, params={})

    assert result_hint.status == "ok"
    assert len(result_hint.steps) == 1
    assert "product_input.json" in fake_llm_hint.prompts[0]


def test_engine_system_prompt_injects_today_date():
    """Verify that today's date from the system clock is injected into the engine prompt."""
    import datetime
    from unittest.mock import patch
    from src.agent.engine import _build_system_prompt

    # Save the real datetime.date before patching to avoid recursion
    _real_date = datetime.date

    with patch("src.agent.engine.datetime.date") as mock_date:
        mock_date.today.return_value = _real_date(2026, 10, 6)
        mock_date.side_effect = lambda *a, **kw: _real_date(*a, **kw)

        prompt = _build_system_prompt(MINIMAL_WORKFLOW)
        assert "Today's date is 2026-10-06." in prompt
        assert "Always evaluate dates and calculate overdue/elapsed days relative to 2026-10-06." in prompt


# ── Test 11: System prompt contains ID-fidelity rule ─────────────────────────

def test_engine_system_prompt_contains_id_fidelity_rule():
    """
    Regression guard for the WF009 identifier mix-up bug:
    the system prompt must instruct the LLM to copy every ID, name, and number
    exactly as it appears in tool results — never to combine or guess identifiers.
    Generic rule; no workflow_id conditional anywhere.
    """
    from src.agent.engine import _build_system_prompt

    prompt = _build_system_prompt(MINIMAL_WORKFLOW)

    assert "Copy every ID, name, and number exactly as it appears in the tool results." in prompt
    assert "Never combine, guess, or invent identifiers." in prompt
    assert "omit it rather than guess" in prompt
