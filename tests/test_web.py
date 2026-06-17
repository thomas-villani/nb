"""Tests for the web viewer (FastAPI backend)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from nb import config as config_module
from nb.cli import cli
from nb.cli import utils as cli_utils_module
from nb.config import Config, EmbeddingsConfig, NotebookConfig
from nb.index.db import reset_db
from nb.index.search import reset_search
from nb.web import get_template
from nb.web.server import AppSettings, create_app


@pytest.fixture
def cli_runner():
    """Create a Click CLI runner."""
    return CliRunner()


@pytest.fixture
def web_config(tmp_path: Path):
    """Set up isolated config for web tests."""
    notes_root = tmp_path / "notes"
    notes_root.mkdir()
    nb_dir = notes_root / ".nb"
    nb_dir.mkdir()

    cfg = Config(
        notes_root=notes_root,
        editor="echo",
        notebooks=[
            NotebookConfig(name="daily", date_based=True),
            NotebookConfig(name="projects", date_based=False),
        ],
        embeddings=EmbeddingsConfig(),
        date_format="%Y-%m-%d",
        time_format="%H:%M",
    )

    for nb in cfg.notebooks:
        if not nb.is_external:
            (notes_root / nb.name).mkdir(exist_ok=True)

    yield cfg

    config_module.reset_config()
    reset_db()


@pytest.fixture
def mock_web_config(web_config: Config, monkeypatch: pytest.MonkeyPatch):
    """Install ``web_config`` as the active nb configuration for the test.

    The web routers read the ``nb.config`` singleton on each request, so setting
    ``_config`` (and patching ``get_config`` for CLI modules that bind it early)
    is enough to isolate the test.
    """
    reset_search()
    config_module.reset_config()
    reset_db()

    monkeypatch.setattr(config_module, "_config", web_config)
    monkeypatch.setattr(config_module, "get_config", lambda: web_config)
    monkeypatch.setattr(cli_utils_module, "get_config", lambda: web_config)
    return web_config


@pytest.fixture(autouse=True)
def _no_background_reindex(monkeypatch: pytest.MonkeyPatch):
    """Stop POST /api/note from spawning a real reindex thread.

    The save handler reindexes in a daemon thread; left running it races with
    test teardown (config/db singletons get reset out from under it), making the
    suite flaky. Tests here don't assert on indexing, so no-op it.
    """
    monkeypatch.setattr(
        "nb.index.scanner.index_note_threadsafe",
        lambda *args, **kwargs: None,
    )


def make_client(settings: AppSettings | None = None) -> TestClient:
    """Build a TestClient over a fresh app with the given settings."""
    return TestClient(create_app(settings))


@pytest.fixture
def client(mock_web_config: Config) -> TestClient:
    """A TestClient with default settings (no scope, completed hidden)."""
    return make_client()


class TestWebCommand:
    """Tests for the web CLI command."""

    def test_web_command_help(self, cli_runner: CliRunner):
        result = cli_runner.invoke(cli, ["web", "--help"])
        assert result.exit_code == 0
        assert "Launch web viewer" in result.output
        assert "--port" in result.output
        assert "--no-open" in result.output

    def test_web_command_registered(self, cli_runner: CliRunner):
        result = cli_runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "web" in result.output


class TestGetEndpoints:
    """Tests for GET endpoints."""

    def test_serve_index_html(self, client: TestClient):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert "<!DOCTYPE html>" in resp.text
        assert "<title>nb</title>" in resp.text

    def test_serve_index_html_explicit(self, client: TestClient):
        resp = client.get("/index.html")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")

    def test_api_notebooks_empty(self, client: TestClient):
        resp = client.get("/api/notebooks")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        names = [nb["name"] for nb in data]
        assert "daily" in names
        assert "projects" in names
        for nb in data:
            assert nb["count"] == 0

    def test_api_notebooks_with_notes(
        self, client: TestClient, mock_web_config: Config
    ):
        note_path = mock_web_config.notes_root / "projects" / "test-note.md"
        note_path.write_text("# Test Note\n\nSome content.", encoding="utf-8")

        data = client.get("/api/notebooks").json()
        projects = next(nb for nb in data if nb["name"] == "projects")
        assert projects["count"] == 1

    def test_api_notebook_notes(self, client: TestClient, mock_web_config: Config):
        note_path = mock_web_config.notes_root / "projects" / "test-note.md"
        note_path.write_text(
            "---\ndate: 2025-11-28\n---\n\n# Test Note\n\nContent.", encoding="utf-8"
        )

        resp = client.get("/api/notebooks/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Test Note"
        assert data[0]["date"] == "2025-11-28"
        assert "test-note.md" in data[0]["path"]

    def test_api_notebook_notes_snippet(
        self, client: TestClient, mock_web_config: Config
    ):
        from nb.index.scanner import index_note

        note_path = mock_web_config.notes_root / "projects" / "snip.md"
        note_path.write_text(
            "---\ndate: 2025-11-28\n---\n\n# Title\n\nThe quick brown fox jumps.",
            encoding="utf-8",
        )
        index_note(note_path, mock_web_config.notes_root, index_vectors=False)

        data = client.get("/api/notebooks/projects").json()
        assert len(data) == 1
        assert "quick brown fox" in data[0]["snippet"]

    def test_api_notebooks_includes_recent_notes(
        self, client: TestClient, mock_web_config: Config
    ):
        from nb.index.scanner import index_note

        note_path = mock_web_config.notes_root / "projects" / "recent.md"
        note_path.write_text("# Recent Note\n\nBody.", encoding="utf-8")
        index_note(note_path, mock_web_config.notes_root, index_vectors=False)

        nbs = client.get("/api/notebooks").json()
        projects = next(nb for nb in nbs if nb["name"] == "projects")
        assert "recentNotes" in projects
        titles = [rn["title"] for rn in projects["recentNotes"]]
        assert "Recent Note" in titles

    def test_api_stream_all_notebooks(
        self, client: TestClient, mock_web_config: Config
    ):
        from nb.index.scanner import index_note

        for nbname, fname, title in [
            ("projects", "p1.md", "Proj One"),
            ("daily", "2025-11-28.md", "Day One"),
        ]:
            p = mock_web_config.notes_root / nbname / fname
            p.write_text(f"# {title}\n\nContent here.", encoding="utf-8")
            index_note(p, mock_web_config.notes_root, index_vectors=False)

        data = client.get("/api/stream").json()
        assert data["total"] >= 2
        nbs_in_stream = {n.get("notebook") for n in data["notes"]}
        assert {"projects", "daily"}.issubset(nbs_in_stream)

    def test_api_graph_notebook_filter(
        self, client: TestClient, mock_web_config: Config
    ):
        from nb.index.scanner import index_note

        for nbname, fname in [("projects", "p1.md"), ("daily", "2025-11-28.md")]:
            p = mock_web_config.notes_root / nbname / fname
            p.write_text("# T\n\nBody.", encoding="utf-8")
            index_note(p, mock_web_config.notes_root, index_vectors=False)

        data = client.get("/api/graph", params={"notebook": "projects"}).json()
        nb_nodes = {n["id"] for n in data["nodes"] if n["type"] == "notebook"}
        assert nb_nodes == {"notebook:projects"}
        note_nbs = {n["notebook"] for n in data["nodes"] if n["type"] == "note"}
        assert note_nbs == {"projects"}

    def test_api_todos_include_excluded_param(self, client: TestClient):
        # Both variants return a list; the param must be accepted.
        assert isinstance(client.get("/api/todos").json(), list)
        assert isinstance(
            client.get("/api/todos", params={"include_excluded": "true"}).json(), list
        )

    def test_api_note_content(self, client: TestClient, mock_web_config: Config):
        note_content = "---\ndate: 2025-11-28\n---\n\n# My Note\n\nHello world!"
        note_path = mock_web_config.notes_root / "projects" / "my-note.md"
        note_path.write_text(note_content, encoding="utf-8")

        resp = client.get("/api/note", params={"path": "projects/my-note.md"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "My Note"
        assert data["path"] == "projects/my-note.md"
        assert "Hello world!" in data["content"]

    def test_api_note_missing_path(self, client: TestClient):
        data = client.get("/api/note").json()
        assert data["error"] == "Missing path"

    def test_api_note_not_found(self, client: TestClient):
        data = client.get("/api/note", params={"path": "does-not-exist.md"}).json()
        assert data["error"] == "Not found"

    def test_api_note_path_traversal_blocked(self, client: TestClient):
        resp = client.get("/api/note", params={"path": "../../etc/passwd"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "Invalid path"

    def test_api_search(self, client: TestClient):
        mock_result = MagicMock()
        mock_result.path = "projects/test.md"
        mock_result.title = "Test Note"
        mock_result.snippet = "Some snippet text"

        with patch("nb.index.search.get_search") as mock_search:
            mock_search.return_value.search.return_value = [mock_result]
            resp = client.get("/api/search", params={"q": "test"})
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["path"] == "projects/test.md"
            assert data[0]["title"] == "Test Note"
            assert data[0]["snippet"] == "Some snippet text"

    def test_api_search_empty_query(self, client: TestClient):
        assert client.get("/api/search", params={"q": ""}).json() == []

    def test_api_todos(self, client: TestClient):
        from datetime import date

        from nb.models import Priority, Todo, TodoSource, TodoStatus

        mock_todo = Todo(
            id="abc12345",
            content="Test todo item",
            raw_content="- [ ] Test todo item @due(2025-12-01)",
            status=TodoStatus.PENDING,
            source=TodoSource(type="note", path=Path("projects/test.md")),
            line_number=1,
            created_date=date(2025, 11, 28),
            due_date=date(2025, 12, 1),
            priority=Priority.HIGH,
        )

        with patch("nb.index.todos_repo.get_sorted_todos") as mock_get_todos:
            mock_get_todos.return_value = [mock_todo]
            resp = client.get("/api/todos")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["id"] == "abc12345"
            assert data[0]["content"] == "Test todo item"
            assert data[0]["due"] == "2025-12-01"
            assert data[0]["priority"] == 1
            assert data[0]["status"] == "pending"
            assert data[0]["path"] == "projects/test.md"

    def test_api_startup_no_scope(self, client: TestClient):
        resp = client.get("/api/startup")
        assert resp.status_code == 200
        body = resp.json()
        assert body["scopeNotebook"] is None
        assert "inboxFile" in body

    def test_api_startup_with_scope(self, mock_web_config: Config):
        scoped = make_client(AppSettings(scope_notebook="projects"))
        resp = scoped.get("/api/startup")
        assert resp.status_code == 200
        body = resp.json()
        assert body["scopeNotebook"] == "projects"
        assert "inboxFile" in body

    def test_api_notebooks_scoped(self, mock_web_config: Config):
        root = mock_web_config.notes_root
        for notebook in ("projects", "work"):
            (root / notebook).mkdir(exist_ok=True)
            (root / notebook / "n1.md").write_text("# N1", encoding="utf-8")

        scoped = make_client(AppSettings(scope_notebook="projects"))
        names = {nb["name"] for nb in scoped.get("/api/notebooks").json()}
        assert names == {"projects"}

    def test_404_unknown_path(self, client: TestClient):
        assert client.get("/unknown/path").status_code == 404

    def test_serve_static_vendor_asset(self, client: TestClient):
        resp = client.get("/static/vendor/marked.min.js")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/javascript")
        assert len(resp.content) > 0

    def test_serve_static_path_traversal_blocked(self):
        # httpx normalizes ".." in the URL, so exercise the guard directly.
        from nb.web.server.static import serve_static_file

        assert serve_static_file("../webserver.py").status_code == 403

    def test_serve_static_missing_file(self, client: TestClient):
        resp = client.get("/static/vendor/does-not-exist.js")
        assert resp.status_code == 404


class TestPostEndpoints:
    """Tests for POST endpoints."""

    def test_create_note(self, client: TestClient, mock_web_config: Config):
        resp = client.post(
            "/api/note",
            json={
                "path": "projects/new-note.md",
                "content": "# New Note\n\nContent",
                "create": True,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        note_path = mock_web_config.notes_root / "projects" / "new-note.md"
        assert note_path.exists()
        assert "# New Note" in note_path.read_text()

    def test_create_note_already_exists(
        self, client: TestClient, mock_web_config: Config
    ):
        note_path = mock_web_config.notes_root / "projects" / "existing.md"
        note_path.write_text("# Existing", encoding="utf-8")

        resp = client.post(
            "/api/note",
            json={"path": "projects/existing.md", "content": "# New", "create": True},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "File already exists"

    def test_update_note(self, client: TestClient, mock_web_config: Config):
        note_path = mock_web_config.notes_root / "projects" / "update-me.md"
        note_path.write_text("# Old Content", encoding="utf-8")

        resp = client.post(
            "/api/note",
            json={"path": "projects/update-me.md", "content": "# Updated Content"},
        )
        assert resp.status_code == 200
        assert "# Updated Content" in note_path.read_text()

    def test_create_note_absolute_path_rejected(self, client: TestClient):
        # An absolute path outside notes_root must be rejected. The exact error
        # differs by platform (Windows treats "/etc/.." as drive-relative and
        # rejects it via the traversal guard), but it is always a 400.
        resp = client.post("/api/note", json={"path": "/etc/evil.md", "content": "x"})
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_add_todo(self, client: TestClient):
        with patch("nb.core.todos.add_todo_to_inbox") as mock_add:
            resp = client.post("/api/todos", json={"content": "New todo @due(friday)"})
            assert resp.status_code == 200
            mock_add.assert_called_once_with("New todo @due(friday)")

    def test_add_todo_empty_content(self, client: TestClient):
        resp = client.post("/api/todos", json={"content": ""})
        assert resp.status_code == 400
        assert resp.json()["error"] == "Content required"

    def test_toggle_todo(self, client: TestClient, mock_web_config: Config):
        from datetime import date

        from nb.models import Todo, TodoSource, TodoStatus

        note_path = mock_web_config.notes_root / "projects" / "test-todo.md"
        note_path.write_text("- [ ] Test todo\n", encoding="utf-8")

        mock_todo = Todo(
            id="abc12345",
            content="Test todo",
            raw_content="- [ ] Test todo",
            status=TodoStatus.PENDING,
            source=TodoSource(type="note", path=Path("projects/test-todo.md")),
            line_number=1,
            created_date=date(2025, 11, 28),
        )

        with (
            patch("nb.index.todos_repo.get_todo_by_id") as mock_get,
            patch("nb.index.todos_repo.update_todo_status"),
        ):
            mock_get.return_value = mock_todo
            resp = client.post("/api/todos/abc12345/toggle")
            assert resp.status_code == 200
            assert "[x]" in note_path.read_text()

    def test_toggle_todo_not_found(self, client: TestClient):
        with patch("nb.index.todos_repo.get_todo_by_id") as mock_get:
            mock_get.return_value = None
            resp = client.post("/api/todos/invalid/toggle")
            assert resp.status_code == 404


class TestNotebookColors:
    """Tests for notebook colors."""

    def test_notebooks_include_color(
        self, client: TestClient, mock_web_config: Config, monkeypatch
    ):
        nb_config = mock_web_config.get_notebook("daily")
        monkeypatch.setattr(nb_config, "color", "blue")

        data = client.get("/api/notebooks").json()
        daily = next(nb for nb in data if nb["name"] == "daily")
        assert daily["color"] == "#58a6ff"  # blue hex


class TestTemplate:
    """Tests for the (legacy) HTML template still served at /."""

    def test_template_contains_key_elements(self):
        template = get_template()
        assert "<!DOCTYPE html>" in template
        assert "<title>nb</title>" in template
        assert "/static/vendor/marked.min.js" in template
        assert "/static/vendor/highlight.min.js" in template
        assert "/static/vendor/toastui-editor-all.min.js" in template
        assert "cdn.jsdelivr.net" not in template
        assert "bootstrapcdn" not in template

    def test_template_has_navigation(self):
        template = get_template()
        assert 'class="sidebar"' in template
        assert 'id="tree"' in template
        assert 'id="content"' in template

    def test_template_has_search(self):
        template = get_template()
        assert 'id="searchInput"' in template
        assert "doSearch" in template

    def test_template_has_todos_link(self):
        template = get_template()
        assert "loadTodos()" in template
        assert "Todos" in template
