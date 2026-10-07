"""
tests/test_workflows.py
-----------------------------------------------------------------------------
End-to-end and definition validation tests for all 10 business workflows.

Ensures:
  1. Registry correctly loads all 11 workflows (WF001 through WF010).
  2. Every test question from Excel has a matching workflow definition.
  3. Every workflow definition specifies required fields, steps, tools, and output.
  4. Engine execution logic executes offline mock tools safely for each workflow.
-----------------------------------------------------------------------------
"""

import pytest
from pathlib import Path
from src.agent.registry import WorkflowRegistry
from src.agent.engine import WorkflowEngine, EngineResult
from tests.test_engine import FakeLLM, MINIMAL_WORKFLOW


@pytest.fixture
def registry():
    return WorkflowRegistry()


def test_all_10_workflows_loaded(registry):
    """Verify all 10 core workflows exist in the registry."""
    wf_ids = registry.workflow_ids()
    assert len(wf_ids) >= 10
    for i in range(1, 11):
        expected_id = f"WF{i:03d}"
        assert expected_id in wf_ids


def test_all_test_questions_mapped(registry):
    """Verify that all 11 test questions in Excel map to existing workflows."""
    test_questions = registry.get_test_questions()
    assert len(test_questions) == 11
    
    for tq in test_questions:
        wf_id = tq["workflow_id"]
        wf = registry.get_workflow(wf_id)
        assert wf is not None, f"Workflow {wf_id} missing for test request: {tq['test_request']}"
        assert wf["trigger"] is not None
        assert wf["steps"] is not None


@pytest.mark.parametrize("wf_id", [f"WF{i:03d}" for i in range(1, 11)])
def test_workflow_structure_validity(registry, wf_id):
    """Validate that every workflow has required non-empty metadata."""
    wf = registry.get_workflow(wf_id)
    assert wf["workflow_id"] == wf_id
    assert len(wf["workflow_name"]) > 0
    assert len(wf["trigger"]) > 0
    assert len(wf["inputs"]) > 0
    assert len(wf["steps"]) > 0
    assert len(wf["decision_logic"]) > 0
    assert len(wf["tools_required"]) > 0
    assert len(wf["expected_output"]) > 0


def test_engine_offline_execution_wf001(registry):
    """Test engine executing WF001 with offline FakeLLM client."""
    wf = registry.get_workflow("WF001")
    fake_llm = FakeLLM(responses=[
        {
            "action": "call_tool",
            "tool_name": "file_data_loader",
            "arguments": {"file_path": "data/mock_data/inventory.csv"},
            "reason": "Load inventory CSV file.",
        },
        {
            "action": "final_answer",
            "answer": "Found 2 products needing restock: P002 (Desk Lamp), P005 (Monitor Arm).",
            "reason": "Analyzed low stock items.",
        },
    ])

    engine = WorkflowEngine(llm_client=fake_llm)
    result = engine.run(wf, {"threshold": 10})

    assert result.status == "ok"
    assert result.workflow_id == "WF001"
    assert len(result.steps) == 1
    assert "Desk Lamp" in result.final_output

