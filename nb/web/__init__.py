"""Web viewer package for nb.

Provides the template loading functionality for the web interface.
Static files (CSS, JS) are loaded lazily and cached.
"""

from pathlib import Path

_TEMPLATE_CACHE: str | None = None
_WEB_DIR = Path(__file__).parent
_DEV_MODE = False


def set_dev_mode(enabled: bool) -> None:
    """Enable/disable dev mode.

    In dev mode the template is re-read from disk on every request so that
    edits to styles.css / app.js / index.html show up on browser reload
    without restarting the server.
    """
    global _DEV_MODE
    _DEV_MODE = enabled
    if enabled:
        clear_template_cache()


def _assemble_template() -> str:
    css = (_WEB_DIR / "static" / "styles.css").read_text(encoding="utf-8")
    js = (_WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")
    html = (_WEB_DIR / "templates" / "index.html").read_text(encoding="utf-8")
    return html.replace("/* STYLES_PLACEHOLDER */", css).replace(
        "/* SCRIPTS_PLACEHOLDER */", js
    )


def get_template() -> str:
    """Load and assemble the web template with lazy caching.

    Combines the HTML template with CSS and JavaScript from separate files.
    The assembled template is cached after first load, unless dev mode is on
    (see ``set_dev_mode``), in which case it is rebuilt from disk every call.

    Returns:
        Complete HTML template string ready for serving.
    """
    global _TEMPLATE_CACHE

    if _DEV_MODE:
        return _assemble_template()

    if _TEMPLATE_CACHE is not None:
        return _TEMPLATE_CACHE

    _TEMPLATE_CACHE = _assemble_template()
    return _TEMPLATE_CACHE


def clear_template_cache() -> None:
    """Clear the cached template (useful for development/testing)."""
    global _TEMPLATE_CACHE
    _TEMPLATE_CACHE = None
