"""CLI tests for notebook commands."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from nb.cli import cli
from nb.config import Config


class TestNotebooksList:
    """Tests for 'nb notebooks' list command."""

    def test_notebooks_list(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test listing all notebooks."""
        result = cli_runner.invoke(cli, ["notebooks"])
        assert result.exit_code == 0
        assert "daily" in result.output
        assert "projects" in result.output
        assert "work" in result.output

    def test_notebooks_list_verbose(
        self, cli_runner: CliRunner, mock_cli_config: Config, indexed_note
    ):
        """Test verbose notebook listing with counts."""
        indexed_note("projects", "note1.md", "# Note 1\n")
        indexed_note("projects", "note2.md", "# Note 2\n")

        result = cli_runner.invoke(cli, ["notebooks", "-v"])
        assert result.exit_code == 0
        assert "Notebook" in result.output

    def test_notebooks_alias(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test 'nbs' alias."""
        result = cli_runner.invoke(cli, ["nbs"])
        assert result.exit_code == 0
        assert "daily" in result.output


class TestNotebooksCreate:
    """Tests for 'nb notebooks create' command."""

    def test_create_notebook(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test creating a new notebook."""
        result = cli_runner.invoke(cli, ["notebooks", "create", "ideas"])
        assert result.exit_code == 0
        assert "Created" in result.output
        assert "ideas" in result.output

        # Verify directory was created
        assert (mock_cli_config.notes_root / "ideas").exists()

    def test_create_date_based_notebook(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test creating a date-based notebook."""
        result = cli_runner.invoke(
            cli, ["notebooks", "create", "journal", "--date-based"]
        )
        assert result.exit_code == 0
        assert "daily" in result.output.lower()

    def test_create_todo_exclude_notebook(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test creating a notebook excluded from todos."""
        result = cli_runner.invoke(
            cli, ["notebooks", "create", "archive", "--todo-exclude"]
        )
        assert result.exit_code == 0
        assert "Excluded" in result.output or "archive" in result.output

    def test_create_external_notebook(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test creating a notebook from external path."""
        external_path = tmp_path / "external_notes"
        external_path.mkdir()
        (external_path / "readme.md").write_text("# External\n")

        result = cli_runner.invoke(
            cli, ["notebooks", "create", "external", "--from", str(external_path)]
        )
        assert result.exit_code == 0
        assert "external" in result.output.lower()

    def test_create_external_path_not_exists(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test creating notebook from non-existent path."""
        result = cli_runner.invoke(
            cli, ["notebooks", "create", "bad", "--from", "/nonexistent/path"]
        )
        assert result.exit_code == 1
        assert "not exist" in result.output.lower()

    def test_create_duplicate_notebook(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test creating a notebook that already exists."""
        result = cli_runner.invoke(cli, ["notebooks", "create", "projects"])
        assert result.exit_code == 1
        assert "already exists" in result.output.lower()


class TestNotebooksRemove:
    """Tests for 'nb notebooks remove' command."""

    def test_remove_notebook_with_force(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test removing a notebook with -f flag."""
        # Create a notebook first
        cli_runner.invoke(cli, ["notebooks", "create", "removeme"])

        result = cli_runner.invoke(cli, ["notebooks", "remove", "removeme", "-f"])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_remove_notebook_with_confirmation(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test removing a notebook with confirmation."""
        cli_runner.invoke(cli, ["notebooks", "create", "confirm"])

        # Cancel removal
        result = cli_runner.invoke(cli, ["notebooks", "remove", "confirm"], input="n\n")
        assert "Cancelled" in result.output

    def test_remove_nonexistent_notebook(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test removing a notebook that doesn't exist."""
        result = cli_runner.invoke(cli, ["notebooks", "remove", "nonexistent", "-f"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_remove_preserves_files(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test that removing a notebook preserves the files."""
        cli_runner.invoke(cli, ["notebooks", "create", "preserve"])
        note_path = mock_cli_config.notes_root / "preserve" / "note.md"
        note_path.write_text("# Preserved Note\n")

        cli_runner.invoke(cli, ["notebooks", "remove", "preserve", "-y"])

        # Files should still exist
        assert note_path.exists()


class TestNotebooksMerge:
    """Tests for 'nb notebooks merge' command."""

    def test_merge_basic(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test basic merge of one notebook into another."""
        # Create source notebook with notes
        cli_runner.invoke(cli, ["notebooks", "create", "source"])
        src_dir = mock_cli_config.notes_root / "source"
        (src_dir / "note1.md").write_text("# Note 1\n")
        (src_dir / "note2.md").write_text("# Note 2\n")

        result = cli_runner.invoke(cli, ["notebooks", "merge", "source", "projects"])
        assert result.exit_code == 0
        assert "Merged 2 note(s)" in result.output

        # Notes should be in target
        assert (mock_cli_config.notes_root / "projects" / "note1.md").exists()
        assert (mock_cli_config.notes_root / "projects" / "note2.md").exists()

        # Source should be empty / removed
        assert not (src_dir / "note1.md").exists()
        assert not (src_dir / "note2.md").exists()

    def test_merge_with_section(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test merge with --section places notes in a subfolder."""
        cli_runner.invoke(cli, ["notebooks", "create", "myproject"])
        proj_dir = mock_cli_config.notes_root / "myproject"
        (proj_dir / "readme.md").write_text("# Readme\n")
        (proj_dir / "todo.md").write_text("# Todo\n")

        result = cli_runner.invoke(
            cli, ["notebooks", "merge", "myproject", "projects", "--section", "myproject"]
        )
        assert result.exit_code == 0
        assert "Merged 2 note(s)" in result.output

        # Notes should be under section subfolder
        assert (mock_cli_config.notes_root / "projects" / "myproject" / "readme.md").exists()
        assert (mock_cli_config.notes_root / "projects" / "myproject" / "todo.md").exists()

    def test_merge_preserves_subdirectory_structure(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test that subdirectory structure is preserved after merge."""
        cli_runner.invoke(cli, ["notebooks", "create", "source"])
        src_dir = mock_cli_config.notes_root / "source"
        (src_dir / "sub1").mkdir()
        (src_dir / "sub2").mkdir()
        (src_dir / "root.md").write_text("# Root\n")
        (src_dir / "sub1" / "a.md").write_text("# A\n")
        (src_dir / "sub2" / "b.md").write_text("# B\n")

        result = cli_runner.invoke(
            cli, ["notebooks", "merge", "source", "projects", "-s", "archived"]
        )
        assert result.exit_code == 0

        assert (mock_cli_config.notes_root / "projects" / "archived" / "root.md").exists()
        assert (mock_cli_config.notes_root / "projects" / "archived" / "sub1" / "a.md").exists()
        assert (mock_cli_config.notes_root / "projects" / "archived" / "sub2" / "b.md").exists()

    def test_merge_moves_non_markdown_files(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test that non-markdown files (PDFs, CSVs, images) are also moved."""
        cli_runner.invoke(cli, ["notebooks", "create", "source"])
        src_dir = mock_cli_config.notes_root / "source"
        (src_dir / "readme.md").write_text("# Readme\n")
        (src_dir / "data.csv").write_bytes(b"a,b,c\n1,2,3\n")
        (src_dir / "assets").mkdir()
        (src_dir / "assets" / "logo.png").write_bytes(b"\x89PNG fake image")
        (src_dir / "assets" / "notes.md").write_text("# Asset Notes\n")

        result = cli_runner.invoke(
            cli, ["notebooks", "merge", "source", "projects", "-s", "src"]
        )
        assert result.exit_code == 0

        dest = mock_cli_config.notes_root / "projects" / "src"
        assert (dest / "readme.md").exists()
        assert (dest / "data.csv").exists()
        assert (dest / "data.csv").read_bytes() == b"a,b,c\n1,2,3\n"
        assert (dest / "assets" / "logo.png").exists()
        assert (dest / "assets" / "notes.md").exists()

        # Source should be fully cleaned up
        assert not src_dir.exists()

    def test_merge_dry_run(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test dry run shows planned moves without modifying files."""
        cli_runner.invoke(cli, ["notebooks", "create", "source"])
        src_dir = mock_cli_config.notes_root / "source"
        (src_dir / "note.md").write_text("# Note\n")

        result = cli_runner.invoke(
            cli, ["notebooks", "merge", "source", "projects", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "Would move" in result.output

        # Source file should still exist
        assert (src_dir / "note.md").exists()
        # Target should NOT have the file
        assert not (mock_cli_config.notes_root / "projects" / "note.md").exists()

    def test_merge_conflict_without_force(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test merge fails on conflict without --force."""
        cli_runner.invoke(cli, ["notebooks", "create", "source"])
        (mock_cli_config.notes_root / "source" / "clash.md").write_text("# Source\n")
        (mock_cli_config.notes_root / "projects" / "clash.md").write_text("# Target\n")

        result = cli_runner.invoke(cli, ["notebooks", "merge", "source", "projects"])
        assert result.exit_code == 1
        assert "conflict" in result.output.lower() or "force" in result.output.lower()

    def test_merge_conflict_with_force(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test merge succeeds with --force on conflict."""
        cli_runner.invoke(cli, ["notebooks", "create", "source"])
        (mock_cli_config.notes_root / "source" / "clash.md").write_text("# Source version\n")
        (mock_cli_config.notes_root / "projects" / "clash.md").write_text("# Target version\n")

        result = cli_runner.invoke(
            cli, ["notebooks", "merge", "source", "projects", "--force"]
        )
        assert result.exit_code == 0

        # Target should have source content
        content = (mock_cli_config.notes_root / "projects" / "clash.md").read_text()
        assert "Source version" in content

    def test_merge_removes_source_by_default(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test source notebook is removed from config by default."""
        cli_runner.invoke(cli, ["notebooks", "create", "removable"])
        (mock_cli_config.notes_root / "removable" / "note.md").write_text("# Note\n")

        result = cli_runner.invoke(
            cli, ["notebooks", "merge", "removable", "projects"]
        )
        assert result.exit_code == 0
        assert "Removed" in result.output

        # Notebook should be gone from listing
        list_result = cli_runner.invoke(cli, ["notebooks"])
        assert "removable" not in list_result.output

    def test_merge_keep_source(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test --keep-source preserves notebook in config."""
        cli_runner.invoke(cli, ["notebooks", "create", "keepable"])
        (mock_cli_config.notes_root / "keepable" / "note.md").write_text("# Note\n")

        result = cli_runner.invoke(
            cli, ["notebooks", "merge", "keepable", "projects", "--keep-source"]
        )
        assert result.exit_code == 0

        # Notebook should still be in listing
        list_result = cli_runner.invoke(cli, ["notebooks"])
        assert "keepable" in list_result.output

    def test_merge_same_notebook_error(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test merging a notebook into itself fails."""
        result = cli_runner.invoke(cli, ["notebooks", "merge", "projects", "projects"])
        assert result.exit_code == 1
        assert "itself" in result.output.lower()

    def test_merge_nonexistent_source(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test merging from a nonexistent notebook fails."""
        result = cli_runner.invoke(cli, ["notebooks", "merge", "nonexistent", "projects"])
        assert result.exit_code == 1
        assert "does not exist" in result.output.lower()
