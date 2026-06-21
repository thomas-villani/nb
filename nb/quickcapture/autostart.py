"""Run-at-login autostart for quick-capture (Windows).

Uses the per-user ``HKCU\\...\\Run`` registry key (no admin rights needed).
The launch command targets ``pythonw.exe -m nb.quickcapture`` so the tray app
starts at login without a console window.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Registry value name under the Run key.
VALUE_NAME = "nb-quickcapture"

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launcher() -> str:
    """Return the windowless Python launcher (pythonw.exe if available)."""
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")
    return str(windowless if windowless.exists() else exe)


def build_command(hotkey: str) -> str:
    """Build the autostart command line for the given hotkey."""
    return f'"{_launcher()}" -m nb.quickcapture --hotkey {hotkey}'


def enable(hotkey: str) -> str:
    """Register quick-capture to run at login. Returns the stored command."""
    import winreg

    command = build_command(hotkey)
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
    return command


def disable() -> bool:
    """Remove the autostart entry. Returns ``True`` if one was removed."""
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False


def current() -> str | None:
    """Return the registered autostart command, or ``None`` if not enabled."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return value
    except FileNotFoundError:
        return None
