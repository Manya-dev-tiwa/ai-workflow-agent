"""
src/llm
-----------------------------------------------------------------------------
LLM integration layer for OpenAI and Google Gemini.
-----------------------------------------------------------------------------
"""

from src.llm.client import LLMClient, LLMError

__all__ = ["LLMClient", "LLMError"]
