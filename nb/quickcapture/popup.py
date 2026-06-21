"""The tiny capture popup (tkinter).

A borderless, centered, top-most window with a location dropdown, a
todo/plain toggle, and a single-line entry. Enter saves, Esc cancels.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from nb.quickcapture.capture import Location

# A muted dark palette so the popup is unobtrusive.
_BG = "#1e1e2e"
_FG = "#cdd6f4"
_HINT = "#7f849c"


class QuickCapturePopup:
    """A one-shot capture popup. Call :meth:`show` to display and block."""

    def __init__(
        self,
        root: tk.Tk,
        locations: list[Location],
        default_index: int = 0,
        default_as_todo: bool = True,
    ) -> None:
        self.locations = locations
        self.result: dict | None = None

        win = tk.Toplevel(root)
        self.win = win
        win.withdraw()
        win.overrideredirect(True)
        win.configure(bg=_BG, padx=14, pady=12)
        win.attributes("-topmost", True)

        labels = [loc.label for loc in locations]
        self.combo = ttk.Combobox(win, values=labels, state="readonly", width=20)
        self.combo.current(default_index if 0 <= default_index < len(labels) else 0)
        self.combo.grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.as_todo = tk.BooleanVar(value=default_as_todo)
        ttk.Checkbutton(win, text="as todo", variable=self.as_todo).grid(
            row=0, column=1, sticky="w"
        )

        self.entry = tk.Entry(
            win,
            width=46,
            font=("Segoe UI", 13),
            bg="#313244",
            fg=_FG,
            insertbackground=_FG,
            relief="flat",
        )
        self.entry.grid(
            row=1, column=0, columnspan=2, sticky="we", pady=(10, 0), ipady=5
        )

        tk.Label(
            win,
            text="Enter to save · Esc to cancel",
            bg=_BG,
            fg=_HINT,
            font=("Segoe UI", 8),
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        win.bind("<Return>", self._submit)
        win.bind("<Escape>", self._cancel)

        self._center()
        win.deiconify()
        win.lift()
        win.attributes("-topmost", True)
        self.entry.focus_force()
        try:
            win.grab_set()
        except tk.TclError:
            # grab can fail transiently right after deiconify; non-fatal.
            pass

    def _center(self) -> None:
        win = self.win
        win.update_idletasks()
        width = win.winfo_width()
        screen_w = win.winfo_screenwidth()
        screen_h = win.winfo_screenheight()
        x = (screen_w - width) // 2
        y = int(screen_h * 0.32)
        win.geometry(f"+{x}+{y}")

    def _submit(self, _event: object = None) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        location = self.locations[self.combo.current()]
        self.result = {
            "text": text,
            "notebook": location.notebook,
            "as_todo": bool(self.as_todo.get()),
        }
        self._close()

    def _cancel(self, _event: object = None) -> None:
        self.result = None
        self._close()

    def _close(self) -> None:
        try:
            self.win.grab_release()
        except tk.TclError:
            pass
        self.win.destroy()

    def show(self) -> dict | None:
        """Display the popup and block until it is closed.

        Returns the capture dict ``{text, notebook, as_todo}`` on save, or
        ``None`` if cancelled.
        """
        self.win.wait_window()
        return self.result
