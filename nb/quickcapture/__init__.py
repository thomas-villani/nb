"""Global quick-capture for nb (Windows).

A small always-on tray app that registers a global hotkey, pops a tiny input
window, and appends the captured line to a chosen note (default: today's daily
note) without opening a terminal.

The capture *logic* reuses the existing core functions
(:func:`nb.core.todos.add_todo_to_daily_note` /
:func:`nb.core.todos.add_todo_to_note`); this package only adds the Windows
front-end (global hotkey + popup + tray).
"""

from __future__ import annotations

__all__ = ["Location", "capture_text", "list_locations"]

from nb.quickcapture.capture import Location, capture_text, list_locations
