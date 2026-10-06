"""
tests/test_router.py
-----------------------------------------------------------------------------
Unit tests for WorkflowRouter using a FakeLLM class (zero API calls).

Tests cover:
  1. Successful workflow routing and parameter extraction.
  2. The null case (request matching NO workflow in catalog).
  3. Invalid JSON handling (safe error recovery without crashing).
  4. Missing API key handling (graceful error return without stack trace).
  5. Dynamic catalog prompt generation from Excel registry.
-----------------------------------------------------------------------------
"""

import pytest
from typing import Any, Dict, Optional
from src.agent.registry import WorkflowRegistry
from src.agent.router import WorkflowRouter


class FakeLLM:
    """
    Mock LLM client for unit testing.
    Executes 0 network/API calls. Configurable to test various response scenarios.
    """

    def __init__(
        self,
        mode: str = "success",
        custom_response: Optional[Dict[str, Any]] = None,
        missing_key: bool = False,
    ):
        self.mode = mode
        self.custom_response = custom_response
        self.missing_key = missing_key
        self.provider = "fake"
        self.call_count = 0
        self.last_system_prompt = ""
        self.last_user_prompt = ""

    def validate_key(self):
        if self.missing_key:
            return False, "Missing API Key Error: OPENAI_API_KEY is not configured in .env."
        return True, ""

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_retries: int = 1,
    ) -> Dict[str, Any]:
        """Simulates LLM response generation based on test mode."""
        self.call_count += 1
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt

        # 1. Missing API Key scenario
        if self.missing_key:
            return {
                "error": "Missing API Key Error: OPENAI_API_KEY is not configured in .env.",
                "workflow_id": None,
                "parameters": {},
                "reason": "Missing API Key Error",
            }

        # 2. Custom explicit response override
        if self.custom_response is not None:
            return self.custom_response

        # 3. Invalid JSON error scenario
        if self.mode == "invalid_json":
            return {
                "error": "Invalid JSON Response Error: Failed to parse JSON after 2 attempt(s).",
                "workflow_id": None,
                "parameters": {},
                "reason": "Invalid JSON response.",
            }

        # 4. Null match scenario (no workflow fits)
        if self.mode == "null":
            return {
                "workflow_id": None,
                "parameters": {},
                "reason": "The user request does not match any business workflow in the catalog.",
            }

        # 5. Default success scenario (WF001 match)
        return {
            "workflow_id": "WF001",
            "parameters": {"threshold": 10},
            "reason": "User asked for products needing restocking.",
        }


@pytest.fixture
def registry():
    """Fixture to load the WorkflowRegistry from data/workflows.xlsx."""
    return WorkflowRegistry()


def test_router_successful_match(registry):
    """Test routing a request to WF005 with extracted parameters."""
    fake_llm = FakeLLM(
        custom_response={
            "workflow_id": "WF005",
            "parameters": {"order_id": "ORD-1001"},
            "reason": "User requested status for order ORD-1001.",
        }
    )
    router = WorkflowRouter(registry, llm_client=fake_llm)

    result = router.route("Where is order ORD-1001?")

    assert result["workflow_id"] == "WF005"
    assert result["parameters"] == {"order_id": "ORD-1001"}
    assert "ORD-1001" in result["reason"]
    assert fake_llm.call_count == 1


def test_router_null_case(registry):
    """Test that requests matching no workflow return workflow_id = None."""
    fake_llm = FakeLLM(mode="null")
    router = WorkflowRouter(registry, llm_client=fake_llm)

    result = router.route("What is the weather today in New York?")

    assert result["workflow_id"] is None
    assert isinstance(result["parameters"], dict)
    assert len(result["parameters"]) == 0
    assert "does not match" in result["reason"].lower()


def test_router_invalid_json_handling(registry):
    """Test that invalid JSON from LLM is handled safely without crashing."""
    fake_llm = FakeLLM(mode="invalid_json")
    router = WorkflowRouter(registry, llm_client=fake_llm)

    result = router.route("Which products need restocking?")

    assert result["workflow_id"] is None
    assert "error" in result["reason"].lower() or "invalid" in result["reason"].lower()


def test_router_missing_key_handling(registry):
    """Test that missing API keys return a clear error without a stack trace."""
    fake_llm = FakeLLM(missing_key=True)
    router = WorkflowRouter(registry, llm_client=fake_llm)

    result = router.route("Process vendor spreadsheet")

    assert result["workflow_id"] is None
    assert "missing api key" in result["reason"].lower()


def test_router_dynamic_prompt(registry):
    """Test that the prompt is built dynamically from Excel without hardcoded workflows."""
    fake_llm = FakeLLM()
    router = WorkflowRouter(registry, llm_client=fake_llm)

    prompt = router.build_system_prompt()

    # Verify workflows from Excel appear dynamically in the prompt
    assert "WF001" in prompt
    assert "WF005" in prompt
    assert "WF010" in prompt
    assert "WORKFLOW CATALOG (DYNAMICALLY LOADED FROM EXCEL)" in prompt
