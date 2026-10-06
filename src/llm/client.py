"""
src/llm/client.py
-----------------------------------------------------------------------------
LLMClient -- Unified interface for calling LLM APIs (OpenAI or Google Gemini).

Responsibilities:
  • Provider selection based on LLM_PROVIDER in .env ("openai" or "gemini").
  • Centralised execution: ONE place in the codebase that executes LLM calls.
  • JSON-mode helper (`generate_json`): safely parses output and retries up to
    once on invalid JSON, and up to 3 times on transient API errors (429, 500,
    503, 504) with exponential back-off.
  • Timeout configurable via LLM_TIMEOUT_SECONDS in .env (default 60 s).
  • Safe missing-key handling: returns a structured error object instead of
    crashing with a raw stack trace.

Gemini provider now uses the new google-genai SDK
  (package: google-genai, import: from google import genai).
  The old google-generativeai package has been removed.
-----------------------------------------------------------------------------
"""

import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

from src.config import (
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

# ── Error codes that are worth retrying automatically ─────────────────────────
# 429 = rate-limit, 500/503 = server error, 504 = gateway timeout
_RETRYABLE_HTTP_CODES = {429, 500, 503, 504}

# Maximum number of automatic API-error retries (distinct from JSON-parse retries)
_MAX_API_RETRIES = 3

# Back-off in seconds between API retries: 2 s, 4 s, 8 s
_BACKOFF_SECONDS = [2, 4, 8]


class LLMError(Exception):
    """Custom exception raised for operational errors in the LLM client."""
    pass


class LLMClient:
    """
    Unified LLM client supporting OpenAI and Google Gemini (new google-genai SDK).
    Provides:
      - Structured JSON generation
      - Automatic retries on transient API errors with back-off
      - Configurable timeout (LLM_TIMEOUT_SECONDS in .env)
      - Missing API key protection
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,  # None = use LLM_TIMEOUT_SECONDS from config
    ):
        """
        Initialize the LLM client.
        If provider/model/api_key/timeout are not specified, values come from config.py.
        """
        self.provider = (provider or LLM_PROVIDER).lower().strip()
        # Use the passed timeout, or fall back to the value from .env
        self.timeout = float(timeout) if timeout is not None else float(LLM_TIMEOUT_SECONDS)

        if self.provider == "gemini":
            self.model = model or GEMINI_MODEL
            self.api_key = api_key if api_key is not None else GEMINI_API_KEY
        else:
            self.provider = "openai"  # default fallback
            self.model = model or OPENAI_MODEL
            self.api_key = api_key if api_key is not None else OPENAI_API_KEY

    # ── Key validation ────────────────────────────────────────────────────────

    def validate_key(self) -> Tuple[bool, str]:
        """
        Validate whether a valid API key is present for the active provider.
        Returns (is_valid, error_message).
        """
        key = (self.api_key or "").strip()
        if not key or key.startswith("sk-...") or key.startswith("..."):
            key_name = "OPENAI_API_KEY" if self.provider == "openai" else "GEMINI_API_KEY"
            msg = (
                f"Missing API Key Error: {key_name} is not configured in .env "
                f"for provider '{self.provider}'."
            )
            return False, msg
        return True, ""

    # ── Public raw call (with retry on transient errors) ─────────────────────

    def raw_complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Execute a raw LLM request and return the raw text output.

        Retries up to _MAX_API_RETRIES times on retryable HTTP errors
        (429, 500, 503, 504) with exponential back-off.
        Raises LLMError if the key is missing or all retries are exhausted.
        """
        is_valid, err_msg = self.validate_key()
        if not is_valid:
            raise LLMError(err_msg)

        last_exc: Optional[Exception] = None

        for attempt in range(_MAX_API_RETRIES):
            try:
                if self.provider == "openai":
                    return self._call_openai(system_prompt, user_prompt)
                elif self.provider == "gemini":
                    return self._call_gemini(system_prompt, user_prompt)
                else:
                    raise LLMError(
                        f"Unsupported LLM_PROVIDER '{self.provider}'. "
                        "Use 'openai' or 'gemini'."
                    )

            except LLMError as exc:
                last_exc = exc
                err_str = str(exc)

                # Only retry if the error message contains a retryable status code
                should_retry = any(str(code) in err_str for code in _RETRYABLE_HTTP_CODES)

                if should_retry and attempt < _MAX_API_RETRIES - 1:
                    wait = _BACKOFF_SECONDS[attempt]
                    logger.warning(
                        f"Transient API error on attempt {attempt + 1}/{_MAX_API_RETRIES}: "
                        f"{exc}. Retrying in {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    # Non-retryable error or last attempt — give up immediately
                    raise

        # Should not reach here, but raise the last exception just in case
        raise last_exc  # type: ignore[misc]

    # ── Provider-specific implementations ─────────────────────────────────────

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        """Call OpenAI API with JSON mode enabled."""
        try:
            from openai import OpenAI, OpenAIError
        except ImportError:
            raise LLMError(
                "OpenAI Python package is not installed. Run `pip install openai`."
            )

        try:
            client = OpenAI(api_key=self.api_key, timeout=self.timeout)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            return content or ""
        except OpenAIError as exc:
            raise LLMError(f"OpenAI API Call Error: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Unexpected OpenAI Error: {exc}") from exc

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call Google Gemini API using the NEW google-genai SDK.
        (package: google-genai  |  import: from google import genai)

        JSON mode is requested via response_mime_type="application/json".
        System and user prompts are joined because the genai SDK uses a
        single `contents` argument.
        """
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError:
            raise LLMError(
                "google-genai package is not installed. "
                "Run `pip install google-genai`."
            )

        try:
            # Create a client with the API key
            client = genai.Client(api_key=self.api_key)

            # Combine system + user prompt into one string.
            # We use the chat interface (send_message) instead of
            # models.generate_content to avoid the AFC recommendation warning
            # emitted by the SDK when AFC is used outside of Chat.
            full_prompt = (
                f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\n"
                f"USER REQUEST:\n{user_prompt}"
            )

            # Open a single-turn chat session with JSON mode enabled
            chat = client.chats.create(
                model=self.model,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            response = chat.send_message(full_prompt)
            return response.text or ""

        except Exception as exc:
            # Preserve the original error string (including HTTP status codes)
            # so the retry logic in raw_complete can inspect it.
            raise LLMError(f"Google Gemini API Call Error: {exc}") from exc

    # ── JSON generation with parse-retry ─────────────────────────────────────

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_retries: int = 1,   # retries on bad JSON (API retries handled separately)
    ) -> Dict[str, Any]:
        """
        Generate a parsed JSON dict from the LLM.

        Steps:
          1. Validate API key — return error dict immediately if missing.
          2. Call raw_complete (which has its own API-error retry loop).
          3. Strip markdown fences and parse JSON.
          4. Retry ONCE with a correction prompt if JSON is invalid.
          5. On total failure return a safe structured error dict (never crash).
        """
        # 1. Missing-key safety check
        is_valid, err_msg = self.validate_key()
        if not is_valid:
            logger.error(err_msg)
            return {
                "error": err_msg,
                "workflow_id": None,
                "parameters": {},
                "reason": err_msg,
            }

        current_prompt = user_prompt
        last_parse_error = ""

        # Attempt: initial call (attempt 0) + up to max_retries for bad JSON
        for attempt in range(max_retries + 1):
            try:
                raw_text = self.raw_complete(system_prompt, current_prompt)

                # Strip markdown code fences (```json ... ```) if present
                cleaned = raw_text.strip()
                if cleaned.startswith("```"):
                    lines = cleaned.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    cleaned = "\n".join(lines).strip()

                parsed = json.loads(cleaned)

                if isinstance(parsed, dict):
                    return parsed
                elif isinstance(parsed, list):
                    return {"data": parsed}
                else:
                    raise ValueError(
                        f"Expected JSON object, got {type(parsed).__name__}."
                    )

            except (json.JSONDecodeError, ValueError) as parse_err:
                last_parse_error = str(parse_err)
                logger.warning(
                    f"JSON parse failed (attempt {attempt + 1}/{max_retries + 1}): "
                    f"{parse_err}"
                )
                if attempt < max_retries:
                    # Ask the model to fix the JSON on the next attempt
                    current_prompt = (
                        f"{user_prompt}\n\n"
                        f"CRITICAL FIX REQUIRED: Your previous output failed JSON "
                        f"parsing with error: '{parse_err}'.\n"
                        f"Respond ONLY with a valid JSON object. "
                        f"No prose, no markdown fences."
                    )

            except LLMError as llm_err:
                # API failure (all retries in raw_complete already exhausted)
                logger.error(f"LLM call failed: {llm_err}")
                return {
                    "error": str(llm_err),
                    "workflow_id": None,
                    "parameters": {},
                    "reason": str(llm_err),
                }

        # All JSON-parse retries exhausted
        err_msg = (
            f"Invalid JSON Response Error: Failed to parse JSON after "
            f"{max_retries + 1} attempt(s). Last error: {last_parse_error}"
        )
        return {
            "error": err_msg,
            "workflow_id": None,
            "parameters": {},
            "reason": err_msg,
        }
