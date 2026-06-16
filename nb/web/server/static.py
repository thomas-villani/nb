"""Static asset serving for the web viewer.

Ports the old handler's ``serve_static`` so the vendored libraries (served under
``/static/vendor`` for the legacy UI) keep their exact content types and the
path-traversal guard (403 on escape, 404 on missing).
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import Response
from starlette.responses import FileResponse

# nb/web/server/static.py -> nb/web
_WEB_DIR = Path(__file__).parent.parent
STATIC_ROOT = (_WEB_DIR / "static").resolve()
DIST_ROOT = (_WEB_DIR / "dist").resolve()


def serve_static_file(rel: str) -> Response:
    """Serve a file from nb/web/static (vendored libraries, fonts, etc.).

    Guards against path traversal; only files under the static dir are served.

    Args:
        rel: Path relative to the static root (already URL-decoded).

    Returns:
        A FileResponse on success, or an empty Response with status 403
        (traversal) / 404 (missing), matching the old handler's behavior.
    """
    target = (STATIC_ROOT / rel).resolve()
    try:
        target.relative_to(STATIC_ROOT)
    except ValueError:
        return Response(status_code=403)
    if not target.is_file():
        return Response(status_code=404)

    ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    # Ensure correct types for assets mimetypes may miss on some platforms
    suffix = target.suffix.lower()
    if suffix == ".js":
        ctype = "application/javascript"
    elif suffix == ".css":
        ctype = "text/css"
    elif suffix == ".woff2":
        ctype = "font/woff2"

    return FileResponse(
        target, media_type=ctype, headers={"Cache-Control": "max-age=86400"}
    )
