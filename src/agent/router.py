"""
src/agent/router.py
-----------------------------------------------------------------------------
WorkflowRouter -- Intent classification and parameter extraction layer.

Responsibilities:
  • Takes a user request and the WorkflowRegistry (loaded from Excel).
  • Dynamically builds a catalog prompt from Excel (workflow_name, trigger, inputs).
    NOTHING is hard-coded in the prompt.
  • Calls LLMClient to select the best workflow_id and extract structured parameters.
  • Returns workflow_id = null (Python None) with a reason if no workflow matches.
  • Never crashes with an unhandled exception; missing keys or API errors return
    workflow_id = null with a descriptive error reason.
-----------------------------------------------------------------------------
"""

import logging
from typing import Any, Dict, Optional
from src.agent.registry import WorkflowRegistry
from src.llm.client import LLMClient

logger = logging.getLogger(__name__)


class WorkflowRouter:
    """
    LLM-powered router that matches user queries to business workflows cataloged in Excel.
    """

    def __init__(self, registry: WorkflowRegistry, llm_client: Optional[LLMClient] = None):
        """
        Initialize the router.
        
        Args:
            registry: The WorkflowRegistry instance containing loaded Excel workflows.
            llm_client: Optional LLMClient instance (useful for dependency injection or testing with FakeLLM).
        """
        self.registry = registry
        self.llm_client = llm_client if llm_client is not None else LLMClient()

    def build_system_prompt(self) -> str:
        """
        Dynamically builds the system prompt from the Excel workflow registry.
        Includes workflow_id, workflow_name, trigger description, and required inputs.
        """
        workflows = self.registry.get_all_workflows()

        catalog_lines = []
        for wf in workflows:
            wf_id = wf.get("workflow_id", "")
            wf_name = wf.get("workflow_name", "")
            trigger = wf.get("trigger", "")
            inputs = wf.get("inputs", "")
            catalog_lines.append(
                f"- Workflow ID: {wf_id}\n"
                f"  Name: {wf_name}\n"
                f"  Trigger: {trigger}\n"
                f"  Inputs: {inputs}"
            )

        catalog_text = "\n\n".join(catalog_lines)

        system_prompt = (
            "You are an intelligent intent router for an AI Workflow Agent.\n"
            "Your task is to analyze the user's request, match it against the workflow catalog below, "
            "and extract relevant execution parameters.\n\n"
            "=== WORKFLOW CATALOG (DYNAMICALLY LOADED FROM EXCEL) ===\n"
            f"{catalog_text}\n"
            "========================================================\n\n"
            "ROUTING RULES:\n"
            "1. Match the user request to the single best fitting Workflow ID (e.g., 'WF001', 'WF002', etc.) based on its Trigger and Inputs.\n"
            "2. Extract relevant parameters (such as order IDs like 'ORD-1001', percentage thresholds, filenames, SKUs, dates, priority) as a JSON object.\n"
            "3. Provide a concise 1-sentence reason explaining why this workflow was selected.\n"
            "4. IF THE USER REQUEST DOES NOT FIT ANY WORKFLOW (e.g. general conversation, weather questions, random chit-chat), "
            "set workflow_id to null and explain why in the reason field.\n\n"
            "OUTPUT FORMAT:\n"
            "You MUST respond ONLY with a valid JSON object matching this schema:\n"
            "{\n"
            '  "workflow_id": "WF00X" or null,\n'
            '  "parameters": {\n'
            '      "parameter_name": "value"\n'
            "  },\n"
            '  "reason": "Short 1-sentence explanation"\n'
            "}"
        )
        return system_prompt

    def route(self, user_request: str) -> Dict[str, Any]:
        """
        Routes a user request to a workflow ID and extracts parameters.

        Args:
            user_request: Free-form text query from the user.

        Returns:
            Dict containing:
                - "workflow_id": str (e.g., "WF001") or None if no match.
                - "parameters": dict of extracted parameters.
                - "reason": str explanation.
        """
        if not user_request or not user_request.strip():
            return {
                "workflow_id": None,
                "parameters": {},
                "reason": "Empty user request provided.",
            }

        system_prompt = self.build_system_prompt()
        user_prompt = f"User Request: {user_request.strip()}"

        # Call the LLM (or FakeLLM if injected)
        response = self.llm_client.generate_json(system_prompt, user_prompt)

        # Check if an error occurred (e.g., missing API key or LLM failure)
        if "error" in response and not response.get("workflow_id"):
            return {
                "workflow_id": None,
                "parameters": {},
                "reason": f"Routing failed due to LLM error: {response['error']}",
            }

        workflow_id = response.get("workflow_id")

        # Normalize JSON null / string "null" / string "none" to Python None
        if workflow_id is None or str(workflow_id).strip().lower() in ("null", "none", ""):
            workflow_id = None
        else:
            workflow_id = str(workflow_id).strip().upper()

        parameters = response.get("parameters", {})
        if not isinstance(parameters, dict):
            parameters = {}

        reason = response.get("reason", "No reason provided.")

        return {
            "workflow_id": workflow_id,
            "parameters": parameters,
            "reason": str(reason),
        }
