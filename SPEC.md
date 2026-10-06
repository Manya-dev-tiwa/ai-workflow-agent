# Project: AI Agent Workflow Automation (Technical Assignment)

## Objective
data/workflows.xlsx has 10 business workflows. Convert them into an AI agent
that understands a user's request, identifies the right workflow, executes the
required steps, handles conditions/errors, and returns the final result.

## Excel structure
- Sheet "Workflows": Workflow_ID, Workflow_Name, Trigger, Inputs, Steps,
  Decision_Logic, Tools_Required, Expected_Output (WF001 to WF010)
- Sheet "Test_Questions": Workflow_ID, Test_Request, What_To_Check
Read the Excel file fully yourself. Do not guess its contents.

## The agent must
1. Understand the user's request
2. Select the correct workflow
3. Execute the required steps
4. Handle conditions and errors
5. Return the final result
The system must clearly show: which workflow was selected, what steps were
executed, and the final output.

## Architecture (expected flow)
User Request -> Agent -> Identify Workflow -> Workflow Steps -> Tools/APIs
-> Conditions/Decisions -> Final Result

## CRITICAL architecture rule
Do NOT build 10 separate hard-coded chatbots. Build a reusable, scalable
agent/workflow architecture where adding an 11th workflow needs minimal code
changes (ideally just a new row in the Excel file). Evaluation criteria:
reusability, scalability, maintainability, workflow selection, agent
reasoning, tool execution, error/condition handling.

## Technical requirements
- Python, LLM, agent/tool calling, Excel as the workflow source
- Simulate APIs/tools (mock data) where real APIs are unavailable
- Free to choose framework (LangGraph, LangChain, OpenAI Agents SDK, plain
  Python), but every technical decision must be explainable and justified
- Keep the code simple and readable: the developer must explain it in a video

## Submission (everything inside the GitHub repo)
Source code, Excel file, README, setup/installation instructions, all 10
implemented workflows, example inputs/requests, outputs/results, and a
.env.example if needed. A Loom video will demo the working app.

## Project rules
- Never hard-code API keys; use .env and commit only .env.example
- Use real tools (pandas, fuzzy matching) for data work; use the LLM for
  routing, parameter extraction and text generation
- Missing data or missing records must produce a clear message, never
  invented data
- Every workflow must pass its Test_Questions request