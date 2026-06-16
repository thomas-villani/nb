"""FastAPI application factory for the web viewer."""

from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from nb.web.server.routers import (
    graph,
    history,
    notebooks,
    notes,
    search,
    todos,
)
from nb.web.server.settings import AppSettings
from nb.web.server.static import DIST_ROOT, serve_static_file


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Build the FastAPI app for the nb web viewer.

    Args:
        settings: Per-invocation options (notebook scope, completed todos). A
            fresh default is used when omitted.
    """
    app = FastAPI(title="nb web", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.settings = settings or AppSettings()

    # JSON API routers
    app.include_router(notebooks.router)
    app.include_router(notes.router)
    app.include_router(search.router)
    app.include_router(todos.router)
    app.include_router(graph.router)
    app.include_router(history.router)

    # Built SPA assets (base=/static/app/). Served for M4+; harmless until then.
    # Registered before the catch-all /static route so it takes precedence.
    if DIST_ROOT.is_dir():
        app.mount(
            "/static/app", StaticFiles(directory=DIST_ROOT, html=True), name="spa"
        )

    @app.get("/", response_class=HTMLResponse)
    @app.get("/index.html", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        # Legacy vanilla UI (app.js). Replaced by the SPA in a later milestone.
        from nb.web import get_template

        return HTMLResponse(get_template())

    @app.get("/static/{path:path}")
    def static_files(path: str) -> Response:
        # Vendored libraries / fonts for the legacy UI, served from nb/web/static.
        return serve_static_file(path)

    return app
