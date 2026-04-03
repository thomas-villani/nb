"""Interactive recording widget using Wijjit.

Provides a fullscreen TUI for recording sessions with:
- Elapsed/remaining time display
- Notes textarea for capturing thoughts during recording
- Extend and stop controls
- Auto-stop on timeout
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nb.recorder.audio import RecordingSession


def _format_time(seconds: int) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def run_recording_widget(
    session: RecordingSession,
    name: str,
    mode_str: str,
    timeout_seconds: int | None,
) -> str:
    """Run the interactive recording widget.

    Blocks until the user stops the recording or the timeout is reached.

    Args:
        session: Active recording session.
        name: Recording name for display.
        mode_str: Recording mode description (e.g., "mic + system").
        timeout_seconds: Auto-stop after this many seconds, or None for no limit.

    Returns:
        User-typed notes from the textarea.
    """
    from wijjit import Wijjit

    timeout_display = _format_time(timeout_seconds) if timeout_seconds else None

    app = Wijjit(
        initial_state={
            "elapsed": "0:00",
            "remaining": timeout_display or "",
            "timeout_seconds": timeout_seconds,
            "message": "Recording... type notes below, click Stop when done.",
            "user_notes": "",
        }
    )

    stop_timer = threading.Event()

    def timer_loop() -> None:
        while not stop_timer.is_set():
            if not session.is_recording or session._error:
                try:
                    app.quit()
                except Exception:
                    pass
                return

            elapsed = int(session.duration)
            app.state["elapsed"] = _format_time(elapsed)

            current_timeout = app.state.get("timeout_seconds")
            if current_timeout and current_timeout > 0:
                remaining = max(0, current_timeout - elapsed)
                app.state["remaining"] = _format_time(remaining)

                if remaining <= 0:
                    app.state["message"] = "Time's up! Stopping recording..."
                    try:
                        app.quit()
                    except Exception:
                        pass
                    return

            time.sleep(1)

    timer = threading.Thread(target=timer_loop, daemon=True)
    timer.start()

    @app.view("main", default=True)
    def main_view():
        def get_data():
            current_timeout = app.state.get("timeout_seconds")
            has_timeout = current_timeout is not None and current_timeout > 0
            return {
                "name": name,
                "mode": mode_str,
                "elapsed": app.state.get("elapsed", "0:00"),
                "remaining": app.state.get("remaining", ""),
                "has_timeout": has_timeout,
                "message": app.state.get("message", ""),
            }

        return {
            "template": """
{% frame border_style="single" title="Recording: {{ name }}" %}
  {% vstack spacing=1 %}

    {% hstack spacing=2 %}
      {% text bold=true color="red" %}● REC{% endtext %}
      {% text %}{{ elapsed }}{% endtext %}
      {% if has_timeout %}
        {% text dim=true %}/ {{ remaining }} remaining{% endtext %}
      {% endif %}
      {% text dim=true %}({{ mode }}){% endtext %}
    {% endhstack %}

    {% textarea id="user_notes" height=8 width=80 wrap=true placeholder="Type meeting notes here..." %}{% endtextarea %}

    {% hstack spacing=1 %}
      {% if has_timeout %}
        {% button action="extend_5" %}+5 min{% endbutton %}
        {% button action="extend_10" %}+10 min{% endbutton %}
      {% endif %}
      {% button action="stop" %}Stop Recording{% endbutton %}
    {% endhstack %}

    {% if message %}
      {% text dim=true %}{{ message }}{% endtext %}
    {% endif %}

  {% endvstack %}
{% endframe %}
            """,
            "data": get_data,
        }

    @app.on_action("stop")
    def on_stop(event):
        app.state["message"] = "Stopping recording..."
        app.quit()

    @app.on_action("extend_5")
    def on_extend_5(event):
        current = app.state.get("timeout_seconds") or 0
        app.state["timeout_seconds"] = current + 300
        app.state["message"] = "Extended by 5 minutes"

    @app.on_action("extend_10")
    def on_extend_10(event):
        current = app.state.get("timeout_seconds") or 0
        app.state["timeout_seconds"] = current + 600
        app.state["message"] = "Extended by 10 minutes"

    try:
        app.run()
    except KeyboardInterrupt:
        pass

    stop_timer.set()
    return app.state.get("user_notes", "")
