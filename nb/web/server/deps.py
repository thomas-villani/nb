"""FastAPI dependencies for the web viewer."""

from __future__ import annotations

from fastapi import Request

from nb.config import Config, get_config
from nb.web.server.settings import AppSettings


def get_settings(request: Request) -> AppSettings:
    """Return the per-invocation settings stored on the app."""
    return request.app.state.settings


def get_app_config() -> Config:
    """Return the active nb configuration.

    Reads the ``nb.config`` singleton on each call so tests that swap the config
    (via ``reset_config`` / patching ``_config``) are honored.
    """
    return get_config()
