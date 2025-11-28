"""Editor integration utilities."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Editors that support +line syntax for opening at a specific line
LINE_NUMBER_EDITORS = {
    "vim",
    "nvim",
    "vi",
    "nano",
    "emacs",
    "code",
    "subl",
    "sublime_text",
    "atom",
    "micro",
    "helix",
    "hx",
    "kate",
    "gedit",
}

# Default editor fallback order
DEFAULT_EDITORS = ["micro", "notepad", "nano", "vim"]


def get_editor() -> str:
    """Get the editor command to use.

    Priority:
    1. $EDITOR environment variable
    2. $VISUAL environment variable
    3. First available from DEFAULT_EDITORS
    """
    # Check environment variables
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if editor:
        return editor

    # Try to find an available editor
    for editor in DEFAULT_EDITORS:
        if shutil.which(editor):
            return editor

    # Last resort fallback
    if sys.platform == "win32":
        return "notepad"
    return "vi"


def editor_supports_line_number(editor: str) -> bool:
    """Check if the editor supports +line syntax."""
    # Extract base command name (e.g., "code" from "/usr/bin/code")
    editor_name = Path(editor).stem.lower()
    return editor_name in LINE_NUMBER_EDITORS


def open_in_editor(
    path: Path, line: int | None = None, editor: str | None = None
) -> None:
    """Open a file in the configured editor.

    Args:
        path: Path to the file to open
        line: Optional line number to open at
        editor: Editor command (uses get_editor() if not specified)
    """
    if editor is None:
        editor = get_editor()

    # Build command
    cmd = [editor]

    # Add line number if supported
    if line is not None and editor_supports_line_number(editor):
        editor_name = Path(editor).stem.lower()
        if editor_name == "code":
            # VS Code uses --goto file:line syntax
            cmd.append("--goto")
            cmd.append(f"{path}:{line}")
        else:
            # Most editors use +line syntax
            cmd.append(f"+{line}")
            cmd.append(str(path))
    else:
        cmd.append(str(path))

    # Run the editor
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        raise RuntimeError(f"Editor not found: {editor}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Editor exited with error: {e.returncode}")


def open_file(path: Path) -> None:
    """Open a file with the system default application.

    Uses the appropriate command for each platform:
    - Windows: start
    - macOS: open
    - Linux: xdg-open
    """
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=True)
    else:
        subprocess.run(["xdg-open", str(path)], check=True)
