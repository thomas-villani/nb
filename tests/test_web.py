"""Tests for the web viewer module."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from nb import config as config_module
from nb.cli import cli
from nb.config import Config, EmbeddingsConfig, NotebookConfig
from nb.web import TEMPLATE, NBHandler


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

    # Create notebook directories
    for nb in cfg.notebooks:
        if not nb.is_external:
            (notes_root / nb.name).mkdir(exist_ok=True)

    yield cfg

    config_module.reset_config()


@pytest.fixture
def mock_web_config(web_config: Config, monkeypatch: pytest.MonkeyPatch):
    """Mock get_config() for web tests."""
    config_module.reset_config()
    monkeypatch.setattr(config_module, "_config", web_config)
    return web_config


class MockRequest:
    """Mock HTTP request for testing."""

    def __init__(self, path: str):
        self.path = path

    def makefile(self, *args: Any, **kwargs: Any) -> io.BytesIO:
        return io.BytesIO()


class MockHandler(NBHandler):
    """Mock handler that captures responses."""

    def __init__(self, path: str):
        self.path = path
        self.response_code: int | None = None
        self.response_headers: dict[str, str] = {}
        self.response_body: bytes = b""
        self._headers_buffer: list[bytes] = []
        self._body: bytes = b""

        # Mock request/connection
        self.request = MockRequest(path)
        self.client_address = ("127.0.0.1", 12345)
        self.server = MagicMock()
        self.requestline = f"GET {path} HTTP/1.1"
        self.command = "GET"
        self.request_version = "HTTP/1.1"

        # Buffer for response
        self.wfile = io.BytesIO()
        self.rfile = io.BytesIO()

        # Mock headers
        self.headers = MagicMock()
        self.headers.get = lambda key, default=None: (
            str(len(self._body)) if key == "Content-Length" else default
        )

    def set_body(self, data: dict) -> None:
        """Set JSON body for POST requests."""
        self._body = json.dumps(data).encode()
        self.rfile = io.BytesIO(self._body)

    def send_response(self, code: int, message: str | None = None) -> None:
        self.response_code = code

    def send_header(self, keyword: str, value: str) -> None:
        self.response_headers[keyword] = value

    def end_headers(self) -> None:
        pass

    def log_message(self, format: str, *args: object) -> None:
        pass

    def get_response_json(self) -> Any:
        self.wfile.seek(0)
        return json.loads(self.wfile.read().decode())

    def get_response_html(self) -> str:
        self.wfile.seek(0)
        return self.wfile.read().decode()


class TestWebCommand:
    """Tests for the web CLI command."""

    def test_web_command_help(self, cli_runner: CliRunner):
        """Test that web command shows help."""
        result = cli_runner.invoke(cli, ["web", "--help"])

        assert result.exit_code == 0
        assert "Launch web viewer" in result.output
        assert "--port" in result.output
        assert "--no-open" in result.output

    def test_web_command_registered(self, cli_runner: CliRunner):
        """Test that web command is in the main help."""
        result = cli_runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "web" in result.output


class TestNBHandler:
    """Tests for the web request handler."""

    def test_serve_index_html(self, mock_web_config: Config):
        """Test serving the main HTML template."""
        handler = MockHandler("/")
        handler.do_GET()

        assert handler.response_code == 200
        assert handler.response_headers["Content-Type"] == "text/html"
        html = handler.get_response_html()
        assert "<!DOCTYPE html>" in html
        assert "<title>nb</title>" in html

    def test_serve_index_html_explicit(self, mock_web_config: Config):
        """Test serving /index.html."""
        handler = MockHandler("/index.html")
        handler.do_GET()

        assert handler.response_code == 200
        assert handler.response_headers["Content-Type"] == "text/html"

    def test_api_notebooks_empty(self, mock_web_config: Config):
        """Test /api/notebooks with no notes."""
        handler = MockHandler("/api/notebooks")
        handler.do_GET()

        assert handler.response_code == 200
        assert handler.response_headers["Content-Type"] == "application/json"
        data = handler.get_response_json()
        assert isinstance(data, list)
        # Should have 2 notebooks (daily and projects)
        assert len(data) == 2
        names = [nb["name"] for nb in data]
        assert "daily" in names
        assert "projects" in names
        # All should have 0 notes
        for nb in data:
            assert nb["count"] == 0

    def test_api_notebooks_with_notes(self, mock_web_config: Config):
        """Test /api/notebooks with some notes."""
        # Create a test note
        note_path = mock_web_config.notes_root / "projects" / "test-note.md"
        note_path.write_text("# Test Note\n\nSome content.", encoding="utf-8")

        handler = MockHandler("/api/notebooks")
        handler.do_GET()

        data = handler.get_response_json()
        projects = next(nb for nb in data if nb["name"] == "projects")
        assert projects["count"] == 1

    def test_api_notebook_notes(self, mock_web_config: Config):
        """Test /api/notebooks/<name> endpoint."""
        # Create test notes
        note_path = mock_web_config.notes_root / "projects" / "test-note.md"
        note_path.write_text(
            "---\ndate: 2025-11-28\n---\n\n# Test Note\n\nContent.", encoding="utf-8"
        )

        handler = MockHandler("/api/notebooks/projects")
        handler.do_GET()

        assert handler.response_code == 200
        data = handler.get_response_json()
        assert len(data) == 1
        assert data[0]["title"] == "Test Note"
        assert data[0]["date"] == "2025-11-28"
        assert "test-note.md" in data[0]["path"]

    def test_api_note_content(self, mock_web_config: Config):
        """Test /api/note?path= endpoint."""
        # Create a test note
        note_content = "---\ndate: 2025-11-28\n---\n\n# My Note\n\nHello world!"
        note_path = mock_web_config.notes_root / "projects" / "my-note.md"
        note_path.write_text(note_content, encoding="utf-8")

        handler = MockHandler("/api/note?path=projects/my-note.md")
        handler.do_GET()

        assert handler.response_code == 200
        data = handler.get_response_json()
        assert data["title"] == "My Note"
        assert data["path"] == "projects/my-note.md"
        assert "Hello world!" in data["content"]

    def test_api_note_missing_path(self, mock_web_config: Config):
        """Test /api/note without path parameter."""
        handler = MockHandler("/api/note")
        handler.do_GET()

        data = handler.get_response_json()
        assert data["error"] == "Missing path"

    def test_api_note_not_found(self, mock_web_config: Config):
        """Test /api/note with non-existent file."""
        handler = MockHandler("/api/note?path=does-not-exist.md")
        handler.do_GET()

        data = handler.get_response_json()
        assert data["error"] == "Not found"

    def test_api_search(self, mock_web_config: Config):
        """Test /api/search endpoint."""
        mock_result = MagicMock()
        mock_result.path = "projects/test.md"
        mock_result.title = "Test Note"
        mock_result.snippet = "Some snippet text"

        with patch("nb.index.search.get_search") as mock_search:
            mock_search.return_value.search.return_value = [mock_result]

            handler = MockHandler("/api/search?q=test")
            handler.do_GET()

            assert handler.response_code == 200
            data = handler.get_response_json()
            assert len(data) == 1
            assert data[0]["path"] == "projects/test.md"
            assert data[0]["title"] == "Test Note"
            assert data[0]["snippet"] == "Some snippet text"

    def test_api_search_empty_query(self, mock_web_config: Config):
        """Test /api/search with empty query."""
        handler = MockHandler("/api/search?q=")
        handler.do_GET()

        data = handler.get_response_json()
        assert data == []

    def test_api_todos(self, mock_web_config: Config):
        """Test /api/todos endpoint."""
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

            handler = MockHandler("/api/todos")
            handler.do_GET()

            assert handler.response_code == 200
            data = handler.get_response_json()
            assert len(data) == 1
            assert data[0]["id"] == "abc12345"
            assert data[0]["content"] == "Test todo item"
            assert data[0]["due"] == "2025-12-01"
            assert data[0]["priority"] == 1
            assert data[0]["status"] == "pending"

    def test_404_unknown_path(self, mock_web_config: Config):
        """Test 404 for unknown paths."""
        handler = MockHandler("/unknown/path")
        handler.do_GET()

        assert handler.response_code == 404


class TestNBHandlerPOST:
    """Tests for POST endpoints."""

    def test_create_note(self, mock_web_config: Config):
        """Test POST /api/note to create a new note."""
        handler = MockHandler("/api/note")
        handler.set_body(
            {
                "path": "projects/new-note.md",
                "content": "# New Note\n\nContent",
                "create": True,
            }
        )
        handler.do_POST()

        assert handler.response_code == 200
        data = handler.get_response_json()
        assert data["success"] is True

        # Verify file was created
        note_path = mock_web_config.notes_root / "projects" / "new-note.md"
        assert note_path.exists()
        assert "# New Note" in note_path.read_text()

    def test_create_note_already_exists(self, mock_web_config: Config):
        """Test POST /api/note fails when file exists and create=True."""
        # Create the file first
        note_path = mock_web_config.notes_root / "projects" / "existing.md"
        note_path.write_text("# Existing", encoding="utf-8")

        handler = MockHandler("/api/note")
        handler.set_body(
            {"path": "projects/existing.md", "content": "# New", "create": True}
        )
        handler.do_POST()

        data = handler.get_response_json()
        assert data["error"] == "File already exists"

    def test_update_note(self, mock_web_config: Config):
        """Test POST /api/note to update existing note."""
        # Create the file first
        note_path = mock_web_config.notes_root / "projects" / "update-me.md"
        note_path.write_text("# Old Content", encoding="utf-8")

        handler = MockHandler("/api/note")
        handler.set_body(
            {"path": "projects/update-me.md", "content": "# Updated Content"}
        )
        handler.do_POST()

        assert handler.response_code == 200
        assert "# Updated Content" in note_path.read_text()

    def test_add_todo(self, mock_web_config: Config):
        """Test POST /api/todos to create a new todo."""
        with patch("nb.core.todos.add_todo_to_inbox") as mock_add:
            handler = MockHandler("/api/todos")
            handler.set_body({"content": "New todo @due(friday)"})
            handler.do_POST()

            assert handler.response_code == 200
            mock_add.assert_called_once_with("New todo @due(friday)")

    def test_add_todo_empty_content(self, mock_web_config: Config):
        """Test POST /api/todos with empty content fails."""
        handler = MockHandler("/api/todos")
        handler.set_body({"content": ""})
        handler.do_POST()

        data = handler.get_response_json()
        assert data["error"] == "Content required"

    def test_toggle_todo(self, mock_web_config: Config):
        """Test POST /api/todos/<id>/toggle."""
        from datetime import date

        from nb.models import Todo, TodoSource, TodoStatus

        # Create a test note with a todo
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

            handler = MockHandler("/api/todos/abc12345/toggle")
            handler.do_POST()

            assert handler.response_code == 200

            # Verify the file was updated
            content = note_path.read_text()
            assert "[x]" in content  # Should be marked complete

    def test_toggle_todo_not_found(self, mock_web_config: Config):
        """Test POST /api/todos/<id>/toggle with invalid ID."""
        with patch("nb.index.todos_repo.get_todo_by_id") as mock_get:
            mock_get.return_value = None

            handler = MockHandler("/api/todos/invalid/toggle")
            handler.do_POST()

            assert handler.response_code == 404


class TestNotebookColors:
    """Tests for notebook colors."""

    def test_notebooks_include_color(self, mock_web_config: Config, monkeypatch):
        """Test /api/notebooks includes notebook colors."""

        # Add a color to one of the notebooks
        nb_config = mock_web_config.get_notebook("daily")
        monkeypatch.setattr(nb_config, "color", "blue")

        handler = MockHandler("/api/notebooks")
        handler.do_GET()

        data = handler.get_response_json()
        daily = next(nb for nb in data if nb["name"] == "daily")
        assert daily["color"] == "#58a6ff"  # blue hex


class TestTemplate:
    """Tests for the HTML template."""

    def test_template_contains_key_elements(self):
        """Test template has required HTML structure."""
        assert "<!DOCTYPE html>" in TEMPLATE
        assert "<title>nb</title>" in TEMPLATE
        assert "marked.min.js" in TEMPLATE
        assert "highlight.js" in TEMPLATE

    def test_template_has_navigation(self):
        """Test template has navigation elements."""
        assert 'class="sidebar"' in TEMPLATE
        assert 'id="notebooks"' in TEMPLATE
        assert 'id="notes"' in TEMPLATE
        assert 'id="content"' in TEMPLATE

    def test_template_has_search(self):
        """Test template has search functionality."""
        assert 'id="searchInput"' in TEMPLATE
        assert "doSearch" in TEMPLATE

    def test_template_has_todos_link(self):
        """Test template has todos link."""
        assert "loadTodos()" in TEMPLATE
        assert "Todos" in TEMPLATE
