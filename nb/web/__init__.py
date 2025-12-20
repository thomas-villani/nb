"""Web viewer package for nb.

Provides the template loading functionality for the web interface.
Static files (CSS, JS) are loaded lazily and cached.
"""

from pathlib import Path

_TEMPLATE_CACHE: str | None = None
_WEB_DIR = Path(__file__).parent


def get_template() -> str:
    """Load and assemble the web template with lazy caching.

    Combines the HTML template with CSS and JavaScript from separate files.
    The assembled template is cached after first load.

    Returns:
        Complete HTML template string ready for serving.
    """
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is not None:
        return _TEMPLATE_CACHE

    css = (_WEB_DIR / "static" / "styles.css").read_text(encoding="utf-8")
    js = (_WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")
    html = (_WEB_DIR / "templates" / "index.html").read_text(encoding="utf-8")

    # Replace placeholders with actual content
    _TEMPLATE_CACHE = html.replace("/* STYLES_PLACEHOLDER */", css).replace(
        "/* SCRIPTS_PLACEHOLDER */", js
    )
    return _TEMPLATE_CACHE


def clear_template_cache() -> None:
    """Clear the cached template (useful for development/testing)."""
    global _TEMPLATE_CACHE
    _TEMPLATE_CACHE = None
