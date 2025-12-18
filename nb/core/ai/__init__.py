"""AI-powered features for nb.

This module contains AI functionality built on top of the LLM client.
"""

from __future__ import annotations

from nb.core.ai.ask import AnswerResult, ask_notes

__all__ = [
    "AnswerResult",
    "ask_notes",
]
