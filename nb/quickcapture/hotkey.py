"""Global hotkey registration for quick-capture (Windows).

Uses the Win32 ``RegisterHotKey`` API via ``ctypes`` rather than a keyboard
hook. This is system-level (works regardless of focus), needs no admin
rights, and does not intercept every keystroke (which keyboard-hooking
libraries do, and which antivirus tools often flag).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from threading import Event

# Win32 modifier flags (see RegisterHotKey docs).
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001

_MODIFIERS: dict[str, int] = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "super": MOD_WIN,
    "cmd": MOD_WIN,
}

# Named virtual-key codes for non-character keys.
_NAMED_KEYS: dict[str, int] = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "insert": 0x2D,
    "ins": 0x2D,
    "delete": 0x2E,
    "del": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    **{f"f{n}": 0x70 + (n - 1) for n in range(1, 13)},
}


def parse_hotkey(spec: str) -> tuple[int, int]:
    """Parse a hotkey string like ``"ctrl+alt+n"`` into ``(modifiers, vk)``.

    Returns the combined modifier mask and the virtual-key code of the main
    key. ``MOD_NOREPEAT`` is *not* included here; the listener adds it.

    Raises:
        ValueError: If the spec is empty, has no main key, has more than one
            main key, or names an unknown key.
    """
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError("Empty hotkey specification.")

    modifiers = 0
    vk: int | None = None
    for part in parts:
        if part in _MODIFIERS:
            modifiers |= _MODIFIERS[part]
        elif len(part) == 1:
            if vk is not None:
                raise ValueError(f"Multiple main keys in hotkey: {spec!r}")
            vk = ord(part.upper())
        elif part in _NAMED_KEYS:
            if vk is not None:
                raise ValueError(f"Multiple main keys in hotkey: {spec!r}")
            vk = _NAMED_KEYS[part]
        else:
            raise ValueError(f"Unknown key in hotkey {spec!r}: {part!r}")

    if vk is None:
        raise ValueError(f"Hotkey {spec!r} has no main (non-modifier) key.")
    return modifiers, vk


def listen(
    modifiers: int,
    vk: int,
    on_press: Callable[[], None],
    stop: Event,
    hotkey_id: int = 1,
    on_ready: Callable[[], None] | None = None,
) -> None:
    """Register the hotkey and pump messages until ``stop`` is set.

    Intended to run on a dedicated thread. ``on_press`` is invoked (on this
    thread) each time the hotkey fires; keep it cheap and thread-safe — the
    quick-capture app just enqueues a request for the Tk thread. ``on_ready``,
    if given, is called once immediately after the hotkey is registered, so the
    caller can confirm startup succeeded.

    Raises:
        OSError: If the hotkey could not be registered (e.g. already taken).
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    if not user32.RegisterHotKey(None, hotkey_id, modifiers | MOD_NOREPEAT, vk):
        raise OSError(
            "Failed to register global hotkey (it may already be in use by "
            "another application)."
        )

    if on_ready is not None:
        on_ready()

    try:
        msg = wintypes.MSG()
        while not stop.is_set():
            # Non-blocking peek so we can honour `stop` promptly.
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY:
                    on_press()
            else:
                time.sleep(0.03)
    finally:
        user32.UnregisterHotKey(None, hotkey_id)
