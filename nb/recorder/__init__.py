"""Meeting recorder module for nb.

This module provides audio recording and transcription capabilities.
It requires optional dependencies - install with: uv sync --extra recorder
"""

from __future__ import annotations

# Lazy import flag - dependencies are optional
_RECORDER_AVAILABLE: bool | None = None


def is_available() -> bool:
    """Check if recorder dependencies are installed."""
    global _RECORDER_AVAILABLE
    if _RECORDER_AVAILABLE is None:
        try:
            import numpy  # noqa: F401
            import sounddevice  # noqa: F401
            import soundfile  # noqa: F401

            _RECORDER_AVAILABLE = True
        except ImportError:
            _RECORDER_AVAILABLE = False
    return _RECORDER_AVAILABLE


def require_recorder() -> None:
    """Raise an error if recorder dependencies are not installed."""
    if not is_available():
        raise ImportError(
            "Recording features require additional dependencies.\n"
            "Install with: uv sync --extra recorder"
        )


__all__ = ["is_available", "require_recorder"]
