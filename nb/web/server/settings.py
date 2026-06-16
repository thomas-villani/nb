"""Runtime settings for the web viewer.

Replaces the module-level globals (``_scope_notebook`` / ``_show_completed``) that
the old stdlib handler used. An ``AppSettings`` instance is stored on
``app.state.settings`` and injected into routes via a dependency.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppSettings:
    """Per-invocation options for the web viewer.

    Attributes:
        scope_notebook: When set, the viewer is limited to this single notebook
            (the sidebar tree, notebook list and initial view are filtered to it).
        show_completed: Include completed todos in the todo view.
    """

    scope_notebook: str | None = None
    show_completed: bool = False
