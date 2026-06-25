"""Team identity resolution for multiplayer/shared notebooks.

Resolves "who am I" for todo attribution (`@owner(handle)`) and `nb todo --mine`.
Identity comes from the per-machine `team` config block, with blanks filled in
from the notes repo's git `user.name` / `user.email`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Identity:
    """A resolved team identity with its source for display."""

    name: str | None
    handle: str | None
    email: str | None
    source: str  # "config", "git", "config+git", or "none"


def slugify_handle(value: str) -> str:
    """Derive a short handle from a name or email local-part.

    "Thomas Villani" -> "thomas", "fede.rossi@acme.com" -> "fede.rossi".
    """
    # Use the email local-part if it looks like an email
    if "@" in value:
        value = value.split("@", 1)[0]
    value = value.strip().lower()
    # First whitespace-delimited token (e.g. first name)
    first = value.split()[0] if value.split() else value
    # Keep word chars, dots and hyphens
    return re.sub(r"[^a-z0-9._-]", "", first)


def _git_user(notes_root: Path) -> tuple[str | None, str | None]:
    """Read user.name / user.email from the notes repo's git config.

    Returns (name, email), either of which may be None.
    """
    try:
        from nb.core.git import get_repo

        repo = get_repo(notes_root)
        if repo is None:
            return None, None
        reader = repo.config_reader()
        name = None
        email = None
        try:
            name = str(reader.get_value("user", "name"))
        except Exception:
            name = None
        try:
            email = str(reader.get_value("user", "email"))
        except Exception:
            email = None
        return name, email
    except Exception:
        return None, None


def get_identity(notes_root: Path | None = None) -> Identity:
    """Resolve the current user's identity.

    Precedence: configured `team` fields win; any blank field falls back to the
    notes repo's git `user.name` / `user.email`. `handle` is derived from name or
    email if not explicitly set.
    """
    from nb.config import get_config

    config = get_config()
    if notes_root is None:
        notes_root = config.notes_root

    team = config.team
    cfg_name, cfg_handle, cfg_email = team.name, team.handle, team.email

    git_name = git_email = None
    if not (cfg_name and cfg_email):
        git_name, git_email = _git_user(notes_root)

    name = cfg_name or git_name
    email = cfg_email or git_email

    handle = cfg_handle
    if not handle:
        basis = name or email
        handle = slugify_handle(basis) if basis else None

    # Describe where the identity came from
    used_config = bool(cfg_name or cfg_handle or cfg_email)
    used_git = bool((git_name and not cfg_name) or (git_email and not cfg_email))
    if used_config and used_git:
        source = "config+git"
    elif used_config:
        source = "config"
    elif used_git:
        source = "git"
    else:
        source = "none"

    return Identity(name=name, handle=handle, email=email, source=source)
