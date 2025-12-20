"""Tests for template functionality."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from nb import config as config_module
from nb.config import Config, EmbeddingsConfig, NotebookConfig
from nb.core import notebooks as notebooks_module
from nb.core import templates as templates_module


class TestTemplateOperations:
    """Tests for template CRUD operations."""

    def test_list_templates_empty(self, temp_notes_root: Path) -> None:
        """Empty templates directory returns empty list."""
        from nb.core.templates import list_templates

        assert list_templates(temp_notes_root) == []

    def test_create_and_list_template(self, temp_notes_root: Path) -> None:
        """Create a template and verify it's listed."""
        from nb.core.templates import create_template, list_templates

        create_template("meeting", "# Meeting Notes\n", temp_notes_root)

        templates = list_templates(temp_notes_root)
        assert "meeting" in templates

    def test_create_template_creates_directory(self, temp_notes_root: Path) -> None:
        """Templates directory is created automatically."""
        from nb.core.templates import create_template, get_templates_dir

        templates_dir = get_templates_dir(temp_notes_root)
        assert not templates_dir.exists()

        create_template("test", "content", temp_notes_root)

        assert templates_dir.exists()
        assert templates_dir.is_dir()

    def test_create_duplicate_template_fails(self, temp_notes_root: Path) -> None:
        """Creating duplicate template raises FileExistsError."""
        from nb.core.templates import create_template

        create_template("test", "content", temp_notes_root)

        with pytest.raises(FileExistsError):
            create_template("test", "other content", temp_notes_root)

    def test_read_template(self, temp_notes_root: Path) -> None:
        """Read template content."""
        from nb.core.templates import create_template, read_template

        content = "# Test Template\n\n{{ date }}"
        create_template("test", content, temp_notes_root)

        assert read_template("test", temp_notes_root) == content

    def test_read_nonexistent_template(self, temp_notes_root: Path) -> None:
        """Reading nonexistent template returns None."""
        from nb.core.templates import read_template

        assert read_template("nonexistent", temp_notes_root) is None

    def test_template_exists(self, temp_notes_root: Path) -> None:
        """Check if template exists."""
        from nb.core.templates import create_template, template_exists

        assert not template_exists("test", temp_notes_root)

        create_template("test", "content", temp_notes_root)

        assert template_exists("test", temp_notes_root)

    def test_remove_template(self, temp_notes_root: Path) -> None:
        """Remove an existing template."""
        from nb.core.templates import create_template, remove_template, template_exists

        create_template("test", "content", temp_notes_root)
        assert template_exists("test", temp_notes_root)

        assert remove_template("test", temp_notes_root) is True
        assert not template_exists("test", temp_notes_root)

    def test_remove_nonexistent_template(self, temp_notes_root: Path) -> None:
        """Removing nonexistent template returns False."""
        from nb.core.templates import remove_template

        assert remove_template("nonexistent", temp_notes_root) is False

    def test_get_template_path(self, temp_notes_root: Path) -> None:
        """Get template path."""
        from nb.core.templates import get_template_path

        path = get_template_path("meeting", temp_notes_root)
        assert path == temp_notes_root / ".nb" / "templates" / "meeting.md"


class TestTemplateRendering:
    """Tests for template variable rendering."""

    def test_render_date_variable(self) -> None:
        """Render {{ date }} variable."""
        from nb.core.templates import render_template

        content = "Date: {{ date }}"
        result = render_template(content, dt=date(2025, 11, 29))

        assert result == "Date: 2025-11-29"

    def test_render_title_variable(self) -> None:
        """Render {{ title }} variable."""
        from nb.core.templates import render_template

        content = "# {{ title }}"
        result = render_template(content, title="My Note")

        assert result == "# My Note"

    def test_render_notebook_variable(self) -> None:
        """Render {{ notebook }} variable."""
        from nb.core.templates import render_template

        content = "Notebook: {{ notebook }}"
        result = render_template(content, notebook="projects")

        assert result == "Notebook: projects"

    def test_render_datetime_variable(self) -> None:
        """Render {{ datetime }} variable."""
        from nb.core.templates import render_template

        content = "Created: {{ datetime }}"
        result = render_template(content)

        # Should contain a datetime-like string (YYYY-MM-DDTHH:MM)
        assert "Created: " in result
        assert "T" in result.split("Created: ")[1]

    def test_render_multiple_variables(self) -> None:
        """Render multiple variables in same template."""
        from nb.core.templates import render_template

        content = "---\ndate: {{ date }}\n---\n\n# {{ title }}\n\nIn {{ notebook }}"
        result = render_template(
            content,
            title="Test Note",
            notebook="work",
            dt=date(2025, 11, 29),
        )

        assert "date: 2025-11-29" in result
        assert "# Test Note" in result
        assert "In work" in result

    def test_render_empty_variable(self) -> None:
        """Empty variables render as empty strings."""
        from nb.core.templates import render_template

        content = "Title: {{ title }}"
        result = render_template(content)  # No title provided

        assert result == "Title: "

    def test_render_default_date(self) -> None:
        """Date defaults to today if not provided."""
        from nb.core.templates import render_template

        content = "Date: {{ date }}"
        result = render_template(content)

        # Should contain today's date
        assert "Date: " in result
        assert date.today().isoformat() in result


class TestNoteCreationWithTemplate:
    """Tests for creating notes with templates."""

    def test_create_note_with_template(
        self, temp_notes_root: Path, mock_config: Config
    ) -> None:
        """Create note using a template."""
        from nb.core.notes import create_note
        from nb.core.templates import create_template

        # Create a template
        create_template(
            "test",
            "---\ndate: {{ date }}\n---\n\n# {{ title }}\n\nCustom template content!\n",
            temp_notes_root,
        )

        # Create note with template
        note_path = create_note(
            Path("projects/test-note"),
            title="My Test",
            template="test",
            notes_root=temp_notes_root,
        )

        content = note_path.read_text()
        assert "# My Test" in content
        assert "Custom template content!" in content

    def test_create_note_without_template(
        self, temp_notes_root: Path, mock_config: Config
    ) -> None:
        """Create note without template uses default."""
        from nb.core.notes import create_note

        note_path = create_note(
            Path("projects/test-note"),
            title="Default Note",
            notes_root=temp_notes_root,
        )

        content = note_path.read_text()
        assert "# Default Note" in content

    def test_create_note_with_missing_template_falls_back(
        self, temp_notes_root: Path, mock_config: Config
    ) -> None:
        """Create note with missing template falls back to default."""
        from nb.core.notes import create_note

        note_path = create_note(
            Path("projects/test-note"),
            title="Fallback Note",
            template="nonexistent",  # Template doesn't exist
            notes_root=temp_notes_root,
        )

        # Should still create note with default template
        content = note_path.read_text()
        assert "# Fallback Note" in content


class TestNotebookDefaultTemplate:
    """Tests for notebook default templates."""

    def test_notebook_with_default_template(
        self, temp_notes_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Notebook with default template uses it for new notes."""
        from nb.core.notebooks import ensure_notebook_note
        from nb.core.templates import create_template

        # Create template
        create_template(
            "daily-custom",
            "---\ndate: {{ date }}\n---\n\n# {{ title }}\n\nCustom daily template!\n",
            temp_notes_root,
        )

        # Create config with template
        cfg = Config(
            notes_root=temp_notes_root,
            editor="nano",
            notebooks=[
                NotebookConfig(name="daily", date_based=True, template="daily-custom"),
            ],
            embeddings=EmbeddingsConfig(),
        )
        # Patch get_config in all modules that import it at module level
        monkeypatch.setattr(config_module, "get_config", lambda: cfg)
        monkeypatch.setattr(notebooks_module, "get_config", lambda: cfg)
        monkeypatch.setattr(templates_module, "get_config", lambda: cfg)

        # Create daily directory
        (temp_notes_root / "daily").mkdir(exist_ok=True)

        # Create note - should use template
        note_path = ensure_notebook_note("daily", dt=date(2025, 11, 29))

        content = note_path.read_text()
        assert "Custom daily template!" in content

    def test_explicit_template_overrides_notebook_default(
        self, temp_notes_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit template parameter overrides notebook default."""
        from nb.core.notebooks import ensure_notebook_note
        from nb.core.templates import create_template

        # Create two templates
        create_template("default-tmpl", "Default template content", temp_notes_root)
        create_template("override-tmpl", "Override template content", temp_notes_root)

        # Config with default template
        cfg = Config(
            notes_root=temp_notes_root,
            editor="nano",
            notebooks=[
                NotebookConfig(name="daily", date_based=True, template="default-tmpl"),
            ],
            embeddings=EmbeddingsConfig(),
        )
        # Patch get_config in all modules that import it at module level
        monkeypatch.setattr(config_module, "get_config", lambda: cfg)
        monkeypatch.setattr(notebooks_module, "get_config", lambda: cfg)
        monkeypatch.setattr(templates_module, "get_config", lambda: cfg)

        (temp_notes_root / "daily").mkdir(exist_ok=True)

        # Create note with explicit template
        note_path = ensure_notebook_note(
            "daily", dt=date(2025, 11, 29), template="override-tmpl"
        )

        content = note_path.read_text()
        assert "Override template content" in content
        assert "Default template content" not in content

    def test_notebook_without_default_template_uses_builtin(
        self, temp_notes_root: Path, mock_config: Config
    ) -> None:
        """Notebook without default template uses built-in."""
        from nb.core.notebooks import ensure_notebook_note

        (temp_notes_root / "daily").mkdir(exist_ok=True)

        note_path = ensure_notebook_note("daily", dt=date(2025, 11, 29))

        content = note_path.read_text()
        # Built-in template format
        assert "date: 2025-11-29" in content
        assert "# Saturday, November 29, 2025" in content
