"""Web viewer for nb (FastAPI + uvicorn).

The request handling lives in :mod:`nb.web.server`. This module keeps the
``run_server`` entry point used by the ``nb web`` CLI command.
"""

from __future__ import annotations

import threading
import webbrowser


def run_server(
    port: int = 3000,
    open_browser: bool = True,
    show_completed: bool = False,
    notebook: str | None = None,
) -> None:
    """Start the web server.

    Args:
        port: TCP port to listen on.
        open_browser: Open the default browser at startup.
        show_completed: Include completed todos in the todo view.
        notebook: If set, scope the viewer to this single notebook (the sidebar
            tree, notebook list and initial view are limited to it).
    """
    import uvicorn

    from nb.web.server import AppSettings, create_app

    app = create_app(
        AppSettings(scope_notebook=notebook, show_completed=show_completed)
    )

    if open_browser:

        def open_delayed() -> None:
            import time

            time.sleep(0.5)
            webbrowser.open(f"http://localhost:{port}")

        threading.Thread(target=open_delayed, daemon=True).start()

    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    except KeyboardInterrupt:
        pass
    finally:
        print("\nStopped")
