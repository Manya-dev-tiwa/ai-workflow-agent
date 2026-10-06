"""
scripts/test_llm.py
-----------------------------------------------------------------------------
Smoke test for the LLM client.

Sends ONE tiny prompt ("Reply with the word OK") through LLMClient and
prints the result or the exact error message.

Rules:
  • Never prints the API key.
  • Works with both providers (openai / gemini) — reads LLM_PROVIDER from .env.
  • Exit code 0 = success, exit code 1 = any error.

Usage:
    python scripts/test_llm.py
-----------------------------------------------------------------------------
"""

import sys
import json
from pathlib import Path

# Ensure the project root is on sys.path so `src.*` imports work
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import LLM_PROVIDER, LLM_TIMEOUT_SECONDS
from src.llm.client import LLMClient

# Use a tiny system + user prompt to minimise token cost and latency
SYSTEM_PROMPT = "You are a minimal test assistant. Always respond ONLY with a valid JSON object."
USER_PROMPT = 'Reply with exactly this JSON and nothing else: {"reply": "OK"}'


def main() -> int:
    print("=" * 60)
    print("  AI Workflow Agent - LLM Client Smoke Test")
    print("=" * 60)
    print(f"  Provider : {LLM_PROVIDER}")
    print(f"  Timeout  : {LLM_TIMEOUT_SECONDS}s")
    print("-" * 60)

    client = LLMClient()

    # Check key presence first (without printing the actual key)
    is_valid, key_err = client.validate_key()
    if not is_valid:
        print(f"[ERROR] {key_err}")
        print("  --> Add the correct API key to your .env file and try again.")
        return 1

    print(f"  Model    : {client.model}")
    print("  Sending test prompt: 'Reply with the word OK'")
    print("-" * 60)

    # Call through generate_json so we exercise the full pipeline
    result = client.generate_json(SYSTEM_PROMPT, USER_PROMPT)

    if "error" in result:
        # Structured error returned by the client — print it clearly
        print(f"[FAIL] LLM call failed:")
        print(f"       {result['error']}")
        return 1

    # Pretty-print the parsed JSON response
    print("[OK] LLM responded successfully:")
    print(f"     {json.dumps(result, indent=2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
