"""The quick-capture tray application.

Threading model (Windows):

* Main thread runs the hidden Tk root and its ``mainloop`` — tkinter is not
  thread-safe, so all UI work happens here.
* A daemon thread runs the Win32 hotkey message loop and, on each press,
  enqueues a request that the Tk thread drains via ``after`` polling.
* The system-tray icon (pystray, optional) runs detached on its own thread;
  its menu callbacks also just enqueue requests.
* The actual capture (file write + index upsert) runs on a short-lived
  worker thread so the UI stays responsive.
"""

from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING, Any

from nb.quickcapture.capture import capture_text, list_locations
from nb.quickcapture.hotkey import listen, parse_hotkey

if TYPE_CHECKING:
    import tkinter as tk


class QuickCaptureApp:
    """Always-on tray app: global hotkey → popup → capture."""

    def __init__(self, hotkey: str = "ctrl+alt+n") -> None:
        self.hotkey = hotkey
        self._modifiers, self._vk = parse_hotkey(hotkey)
        self._queue: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._popup_open = False
        self.root: tk.Tk | None = None
        self.icon: Any = None

    # ----------------------------------------------------------------- run #
    def run(self) -> None:
        import tkinter as tk

        root = tk.Tk()
        self.root = root
        root.withdraw()  # we only ever show transient popups

        hotkey_thread = threading.Thread(
            target=self._run_hotkey, name="nb-quickcapture-hotkey", daemon=True
        )
        hotkey_thread.start()

        self._start_tray()

        root.after(50, self._poll)
        try:
            root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            self.quit()

    def _run_hotkey(self) -> None:
        try:
            listen(
                self._modifiers, self._vk, lambda: self._queue.put("show"), self._stop
            )
        except OSError as exc:  # registration failed — surface and stop.
            self._queue.put(f"error:{exc}")

    # --------------------------------------------------------------- tray #
    def _start_tray(self) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError:
            # Tray is optional; the hotkey still works without it.
            return

        image = Image.new("RGB", (64, 64), "#1e1e2e")
        draw = ImageDraw.Draw(image)
        draw.rectangle((16, 14, 48, 50), outline="#89b4fa", width=4)
        draw.line((24, 32, 30, 38), fill="#a6e3a1", width=4)
        draw.line((30, 38, 42, 24), fill="#a6e3a1", width=4)

        menu = pystray.Menu(
            pystray.MenuItem("Capture now", lambda *_: self._queue.put("show")),
            pystray.MenuItem("Quit", lambda *_: self._queue.put("quit")),
        )
        self.icon = pystray.Icon("nb-quickcapture", image, "nb quick capture", menu)
        self.icon.run_detached()

    def _notify(self, title: str, message: str) -> None:
        if self.icon is not None:
            try:
                self.icon.notify(message, title)
                return
            except Exception:
                pass
        # Fall back to console output when no tray is available.
        print(f"{title}: {message}")

    # --------------------------------------------------------------- loop #
    def _poll(self) -> None:
        try:
            while True:
                msg = self._queue.get_nowait()
                if msg == "show":
                    self._show_popup()
                elif msg == "quit":
                    self.quit()
                    return
                elif msg.startswith("error:"):
                    self._notify("Quick-capture error", msg[len("error:") :])
                    self.quit()
                    return
        except queue.Empty:
            pass

        if self._stop.is_set():
            self._shutdown()
            return
        if self.root is not None:
            self.root.after(50, self._poll)

    def _show_popup(self) -> None:
        if self._popup_open or self.root is None:
            return
        from nb.quickcapture import state
        from nb.quickcapture.popup import QuickCapturePopup

        locations = list_locations()
        saved = state.load_state()
        default_index = next(
            (
                i
                for i, loc in enumerate(locations)
                if loc.notebook == saved.get("notebook")
            ),
            0,
        )
        default_as_todo = bool(saved.get("as_todo", True))

        self._popup_open = True
        try:
            result = QuickCapturePopup(
                self.root,
                locations,
                default_index=default_index,
                default_as_todo=default_as_todo,
            ).show()
        finally:
            self._popup_open = False

        if result:
            state.save_state(result["notebook"], result["as_todo"])
            self._do_capture(result)

    def _do_capture(self, result: dict) -> None:
        def work() -> None:
            try:
                summary = capture_text(
                    result["text"], result["notebook"], as_todo=result["as_todo"]
                )
                self._notify("Captured", summary)
            except Exception as exc:  # surface failures rather than swallowing.
                self._notify("Capture failed", str(exc))

        threading.Thread(target=work, name="nb-quickcapture-write", daemon=True).start()

    # --------------------------------------------------------------- exit #
    def quit(self) -> None:
        self._stop.set()

    def _shutdown(self) -> None:
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
        if self.root is not None:
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass
