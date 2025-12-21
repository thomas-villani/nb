"""Centralized regex patterns for parsing markdown content.

This module consolidates all regex patterns used throughout nb for parsing
markdown elements like tags, attachments, and other syntax markers.
"""

from __future__ import annotations

import re

# Tag pattern: must start with a letter, can contain letters, numbers, hyphens, underscores
# Requires word boundary before # (start of line, whitespace, or parenthesis)
TAG_PATTERN = re.compile(r"(?:^|[\s(])#([a-zA-Z][a-zA-Z0-9_-]*)")

# Pattern for removing tags from content (doesn't include prefix to preserve spacing)
TAG_REMOVAL_PATTERN = re.compile(r"#[a-zA-Z][a-zA-Z0-9_-]*")

# Hex color patterns to exclude from tags (3, 4, 6, or 8 hex digits)
HEX_COLOR_PATTERN = re.compile(
    r"^[0-9a-fA-F]{3}$|^[0-9a-fA-F]{4}$|^[0-9a-fA-F]{6}$|^[0-9a-fA-F]{8}$"
)

# Simple attachment pattern for todo parsing: @attach: filepath
ATTACH_PATTERN_SIMPLE = re.compile(r"^\s*@attach:\s*(.+)$")

# Attachment pattern with optional title capture for note parsing:
# @attach: filepath "optional title"
ATTACH_PATTERN_WITH_TITLE = re.compile(
    r'^\s*@attach:\s*(.+?)(?:\s+"([^"]+)")?\s*$', re.MULTILINE
)
