"""FastAPI-based web viewer server package."""

from __future__ import annotations

from nb.web.server.app import create_app
from nb.web.server.settings import AppSettings

__all__ = ["AppSettings", "create_app"]
