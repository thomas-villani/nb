"""Tests for the notebook -> section -> note tree builder (nb.core.tree)."""

from __future__ import annotations

from nb.core.tree import ROOT_NOTEBOOK, build_note_tree


def _find(children, name, ntype):
    for c in children:
        if c["type"] == ntype and c["name"] == name:
            return c
    return None


def _notebook(tree, name):
    return _find(tree["notebooks"], name, "notebook")


def test_tree_notebook_order_and_empty(indexed_note, mock_cli_config):
    """Notebooks appear in config order, including configured-but-empty ones."""
    indexed_note("projects", "readme.md", "# Readme\n")

    tree = build_note_tree(mock_cli_config)
    names = [nb["name"] for nb in tree["notebooks"]]

    # Config order: daily, projects, work (daily/work are empty but present)
    assert names[:3] == ["daily", "projects", "work"]
    work = _notebook(tree, "work")
    assert work["count"] == 0
    assert work["children"] == []


def test_tree_sections_nesting(indexed_note, mock_cli_config):
    """Subfolders become nested folder nodes; top-level notes sit alongside."""
    indexed_note("projects", "readme.md", "# Readme\n")
    indexed_note("projects", "vizier/plan.md", "# Plan\n")
    indexed_note("projects", "vizier/docs/api.md", "# API\n")

    tree = build_note_tree(mock_cli_config)
    projects = _notebook(tree, "projects")

    # Folders sort before notes
    assert projects["children"][0]["type"] == "folder"
    vizier = _find(projects["children"], "vizier", "folder")
    assert vizier is not None
    assert vizier["path"] == "projects/vizier"
    assert vizier["count"] == 2  # plan.md + docs/api.md

    plan = _find(vizier["children"], "plan.md", "note")
    assert plan is not None
    assert plan["path"] == "projects/vizier/plan.md"
    assert plan["isLinked"] is False

    docs = _find(vizier["children"], "docs", "folder")
    assert docs is not None
    assert docs["path"] == "projects/vizier/docs"
    api = _find(docs["children"], "api.md", "note")
    assert api is not None
    assert api["path"] == "projects/vizier/docs/api.md"

    # readme.md is a top-level note in the notebook
    readme = _find(projects["children"], "readme.md", "note")
    assert readme is not None
    assert readme["path"] == "projects/readme.md"

    # Notebook count includes everything recursively
    assert projects["count"] == 3


def test_tree_date_based_notebook(indexed_note, mock_cli_config):
    """Date-based notebooks nest by year/week folders with dateMode set."""
    indexed_note("daily", "2026/May25-May31/2026-05-26.md", "# Tuesday\n")

    tree = build_note_tree(mock_cli_config)
    daily = _notebook(tree, "daily")
    assert daily["dateMode"] == "daily"

    year = _find(daily["children"], "2026", "folder")
    assert year is not None
    week = _find(year["children"], "May25-May31", "folder")
    assert week is not None
    note = _find(week["children"], "2026-05-26.md", "note")
    assert note is not None
    assert note["path"] == "daily/2026/May25-May31/2026-05-26.md"
    assert note["date"] == "2026-05-26"


def test_tree_paths_use_forward_slashes(indexed_note, mock_cli_config):
    """All note paths use forward slashes (round-trip through /api/note)."""
    indexed_note("projects", "a/b/c.md", "# C\n")

    tree = build_note_tree(mock_cli_config)

    def walk(children):
        for c in children:
            if c["type"] == "note":
                assert "\\" not in c["path"]
            elif c["type"] == "folder":
                assert "\\" not in c["path"]
                walk(c["children"])
            else:  # notebook node has no path, just children
                walk(c["children"])

    walk(tree["notebooks"])
