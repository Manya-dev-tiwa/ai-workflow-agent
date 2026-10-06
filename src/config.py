"""
src/config.py
─────────────────────────────────────────────────────────────────────────────
Central configuration for the AI Workflow Agent.

Rules (from SPEC + PLAN):
  • API keys come from .env ONLY — never hard-coded here.
  • Provider selected by LLM_PROVIDER in .env ("openai" or "gemini").
  • Thresholds that can be read from a workflow's Decision_Logic column
    must be parsed there; only truly global defaults live here.
  • Any assumption is marked with # ASSUMPTION so it is easy to find.
─────────────────────────────────────────────────────────────────────────────
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env from the project root ───────────────────────────────────────────
# Path: AI-WORKFLOW-AGENT/.env  (two levels up from src/)
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# ── File paths ─────────────────────────────────────────────────────────────────
WORKFLOWS_EXCEL = ROOT_DIR / "data" / "workflows.xlsx"
MOCK_DATA_DIR   = ROOT_DIR / "data" / "mock_data"
SAMPLES_DIR     = ROOT_DIR / "data" / "samples"

# ── Provider selection ─────────────────────────────────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower().strip()

# ── OpenAI settings ────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

# ── Gemini settings ────────────────────────────────────────────────────────────
# Uses the new google-genai SDK (package: google-genai, import: from google import genai)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", "")).strip()
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()

# ── LLM timeout ────────────────────────────────────────────────────────────────
# How long (seconds) to wait for a single LLM response before giving up.
# Can be raised if the model is slow on large prompts.
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

# ── Engine guardrails ──────────────────────────────────────────────────────────
MAX_STEPS   = 10   # Maximum tool calls the engine will make per workflow run
MAX_RETRIES = 3    # Maximum LLM retries on transient errors or bad JSON

# ── WF010 default threshold ────────────────────────────────────────────────────
# ASSUMPTION: The Excel Decision_Logic for WF010 says "above defined threshold"
# but gives no numeric value.  We default to 30 seconds.  Change this if the
# business provides a concrete SLA.
DEFAULT_SLOW_STEP_THRESHOLD_SECONDS = 30


def validate_config() -> None:
    """
    Called at application start-up.
    Raises EnvironmentError if a required environment variable for the selected
    LLM provider is missing or invalid.
    This ensures failures are immediate and clear — never silent.
    """
    provider = LLM_PROVIDER
    if provider == "openai":
        if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("sk-..."):
            raise EnvironmentError(
                "MissingAPIKeyError: OPENAI_API_KEY is not configured in .env.\n"
                "Please add a valid OpenAI API key to your .env file."
            )
    elif provider == "gemini":
        if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("..."):
            raise EnvironmentError(
                "MissingAPIKeyError: GEMINI_API_KEY is not configured in .env.\n"
                "Please add a valid Gemini API key to your .env file."
            )
    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{provider}'. Must be 'openai' or 'gemini'."
        )
