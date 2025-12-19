"""Tests for nb.index.db module."""

from __future__ import annotations

from pathlib import Path

import pytest

from nb import config as config_module
from nb.config import Config, EmbeddingsConfig, NotebookConfig
from nb.index.db import (
    SCHEMA_VERSION,
    Database,
    apply_migrations,
    get_schema_version,
    init_db,
    rebuild_db,
    set_schema_version,
)


@pytest.fixture
def mock_config_for_rebuild(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Mock config to prevent rebuild_db from deleting real vector index.

    The rebuild_db function calls get_config() to find the vectors_path
    and delete it. Without this mock, tests would delete the user's
    real vector index!

    This patches the get_config function itself (not just _config variable)
    so that even if reset_config() is called during the test, subsequent
    calls to get_config() will still return the test config.
    """
    notes_root = tmp_path / "notes"
    notes_root.mkdir()
    nb_dir = notes_root / ".nb"
    nb_dir.mkdir()

    cfg = Config(
        notes_root=notes_root,
        editor="echo",
        notebooks=[NotebookConfig(name="daily", date_based=True)],
        embeddings=EmbeddingsConfig(),
    )

    config_module.reset_config()
    monkeypatch.setattr(config_module, "get_config", lambda: cfg)
    return cfg


class TestDatabase:
    """Tests for Database class."""

    def test_connect_creates_file(self, tmp_path: Path):
        db_path = tmp_path / "subdir" / "test.db"
        db = Database(db_path)

        try:
            conn = db.connect()
            assert conn is not None
            assert db_path.exists()
        finally:
            db.close()

    def test_connect_returns_same_connection(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")

        try:
            conn1 = db.connect()
            conn2 = db.connect()
            assert conn1 is conn2
        finally:
            db.close()

    def test_close(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")
        db.connect()
        db.close()

        # Connection should be cleared
        assert db._conn is None

    def test_execute(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")

        try:
            db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            db.execute("INSERT INTO test (name) VALUES (?)", ("test",))
            db.commit()

            result = db.fetchone("SELECT name FROM test")
            assert result["name"] == "test"
        finally:
            db.close()

    def test_executemany(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")

        try:
            db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            db.executemany(
                "INSERT INTO test (name) VALUES (?)", [("one",), ("two",), ("three",)]
            )
            db.commit()

            results = db.fetchall("SELECT name FROM test ORDER BY name")
            assert len(results) == 3
            assert results[0]["name"] == "one"
        finally:
            db.close()

    def test_fetchone_returns_none(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")

        try:
            db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")

            result = db.fetchone("SELECT * FROM test")
            assert result is None
        finally:
            db.close()

    def test_fetchall_empty(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")

        try:
            db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")

            results = db.fetchall("SELECT * FROM test")
            assert results == []
        finally:
            db.close()

    def test_transaction_commit(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")

        try:
            db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            db.commit()

            with db.transaction() as conn:
                conn.execute("INSERT INTO test (name) VALUES (?)", ("test",))

            # Should be committed
            result = db.fetchone("SELECT name FROM test")
            assert result["name"] == "test"
        finally:
            db.close()

    def test_transaction_rollback(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")

        try:
            db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            db.commit()

            with pytest.raises(ValueError):
                with db.transaction() as conn:
                    conn.execute("INSERT INTO test (name) VALUES (?)", ("test",))
                    raise ValueError("Trigger rollback")

            # Should be rolled back
            result = db.fetchone("SELECT name FROM test")
            assert result is None
        finally:
            db.close()


class TestSchemaVersion:
    """Tests for schema version functions."""

    def test_get_schema_version_uninitialized(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")

        try:
            version = get_schema_version(db)
            assert version == 0
        finally:
            db.close()

    def test_set_and_get_schema_version(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")

        try:
            # Initialize schema first
            init_db(db)

            set_schema_version(db, 3)

            version = get_schema_version(db)
            assert version == 3
        finally:
            db.close()


class TestMigrations:
    """Tests for migration functions."""

    def test_apply_migrations_from_zero(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")

        try:
            apply_migrations(db)

            # Should be at latest version
            version = get_schema_version(db)
            assert version == SCHEMA_VERSION

            # Core tables should exist
            tables = db.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
            table_names = [t["name"] for t in tables]

            assert "notes" in table_names
            assert "todos" in table_names
            assert "note_tags" in table_names
            assert "todo_tags" in table_names
        finally:
            db.close()

    def test_apply_migrations_idempotent(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")

        try:
            apply_migrations(db)
            version1 = get_schema_version(db)

            # Apply again
            apply_migrations(db)
            version2 = get_schema_version(db)

            assert version1 == version2
        finally:
            db.close()


class TestInitDb:
    """Tests for init_db function."""

    def test_creates_tables(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")

        try:
            init_db(db)

            # Verify notes table structure
            db.execute(
                "INSERT INTO notes (path, title, notebook, content_hash) "
                "VALUES (?, ?, ?, ?)",
                ("test.md", "Test Note", "projects", "abc123"),
            )
            db.commit()

            result = db.fetchone("SELECT * FROM notes WHERE path = ?", ("test.md",))
            assert result is not None
            assert result["title"] == "Test Note"
            assert result["notebook"] == "projects"
        finally:
            db.close()

    def test_creates_todos_table(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")

        try:
            init_db(db)

            # Verify todos table structure
            db.execute(
                "INSERT INTO todos (id, content, completed, source_type, source_path, line_number, created_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("id1", "Test todo", 0, "note", "test.md", 1, "2025-11-26"),
            )
            db.commit()

            result = db.fetchone("SELECT * FROM todos WHERE id = ?", ("id1",))
            assert result is not None
            assert result["content"] == "Test todo"
            assert result["completed"] == 0
        finally:
            db.close()


class TestRebuildDb:
    """Tests for rebuild_db function."""

    def test_clears_and_recreates(self, tmp_path: Path, mock_config_for_rebuild):
        """Test that rebuild_db clears data and recreates tables.

        Uses mock_config_for_rebuild to prevent deleting real vector index.
        """
        db = Database(tmp_path / "test.db")

        try:
            init_db(db)

            # Insert some data
            db.execute(
                "INSERT INTO notes (path, title, notebook, content_hash) "
                "VALUES (?, ?, ?, ?)",
                ("test.md", "Test Note", "projects", "abc123"),
            )
            db.commit()

            # Rebuild
            rebuild_db(db)

            # Data should be gone
            result = db.fetchone("SELECT * FROM notes")
            assert result is None

            # Tables should still exist
            tables = db.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
            table_names = [t["name"] for t in tables]
            assert "notes" in table_names
        finally:
            db.close()

    def test_schema_version_reset(self, tmp_path: Path, mock_config_for_rebuild):
        """Test that rebuild_db resets schema version.

        Uses mock_config_for_rebuild to prevent deleting real vector index.
        """
        db = Database(tmp_path / "test.db")

        try:
            init_db(db)

            rebuild_db(db)

            # Should be back to latest version
            version = get_schema_version(db)
            assert version == SCHEMA_VERSION
        finally:
            db.close()
