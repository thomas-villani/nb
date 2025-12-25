"""Background indexing daemon for nb.

Watches for filesystem changes and keeps the index up-to-date automatically.
CLI commands can skip indexing when daemon is running, making them near-instant.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from watchdog.events import FileSystemEvent

logger = logging.getLogger("nb.daemon")


class NoteChangeHandler:
    """Handle filesystem changes to markdown files."""

    def __init__(self, notes_root: Path, debounce_seconds: float = 2.0):
        self.notes_root = notes_root
        self.debounce_seconds = debounce_seconds
        self.pending_paths: set[Path] = set()
        self.last_change: float = 0.0
        self.stats = {"indexed": 0, "errors": 0, "removed": 0}

    def _should_handle(self, path: str) -> bool:
        """Check if this path should trigger indexing."""
        if not path.endswith(".md"):
            return False
        # Skip hidden files and .nb directory
        path_obj = Path(path)
        if any(part.startswith(".") for part in path_obj.parts):
            return False
        return True

    def on_modified(self, event: FileSystemEvent) -> None:
        src_path = str(event.src_path)
        if not event.is_directory and self._should_handle(src_path):
            self.pending_paths.add(Path(src_path))
            self.last_change = time.time()

    def on_created(self, event: FileSystemEvent) -> None:
        src_path = str(event.src_path)
        if not event.is_directory and self._should_handle(src_path):
            self.pending_paths.add(Path(src_path))
            self.last_change = time.time()

    def on_deleted(self, event: FileSystemEvent) -> None:
        src_path = str(event.src_path)
        if not event.is_directory and self._should_handle(src_path):
            # Mark for removal from index
            self.pending_paths.add(Path(src_path))
            self.last_change = time.time()

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file moves/renames."""
        if not event.is_directory:
            src_path = str(event.src_path)
            # Handle old path (deletion)
            if self._should_handle(src_path):
                self.pending_paths.add(Path(src_path))
                self.last_change = time.time()
            # Handle new path (creation)
            if hasattr(event, "dest_path"):
                dest_path = str(event.dest_path)
                if self._should_handle(dest_path):
                    self.pending_paths.add(Path(dest_path))
                    self.last_change = time.time()

    def process_pending(self) -> int:
        """Process batched changes. Returns number of files processed."""
        if not self.pending_paths:
            return 0
        if time.time() - self.last_change < self.debounce_seconds:
            return 0  # Wait for changes to settle

        paths = self.pending_paths.copy()
        self.pending_paths.clear()
        processed = 0

        for path in paths:
            try:
                if path.exists():
                    self._index_file(path)
                    logger.debug("Indexed: %s", path)
                else:
                    # File was deleted - remove from index
                    self._remove_from_index(path)
                    logger.debug("Removed: %s", path)
                    self.stats["removed"] += 1
                processed += 1
                self.stats["indexed"] += 1
            except Exception as e:
                logger.warning("Failed to index %s: %s", path, e)
                self.stats["errors"] += 1

        return processed

    def _index_file(self, path: Path) -> None:
        """Index a single file using thread-safe indexing."""
        from nb.index.scanner import index_note_threadsafe

        index_note_threadsafe(path, self.notes_root, index_vectors=False)

    def _remove_from_index(self, path: Path) -> None:
        """Remove a deleted file from the index."""
        from nb.index.db import get_db
        from nb.index.todos_repo import delete_todos_for_source
        from nb.utils.hashing import normalize_path

        db = get_db()
        try:
            rel_path = path.relative_to(self.notes_root)
            normalized = normalize_path(rel_path)
        except ValueError:
            # Path outside notes_root (linked file)
            normalized = normalize_path(path)

        db.execute("DELETE FROM notes WHERE path = ?", (normalized,))
        db.commit()
        delete_todos_for_source(path)


class LinkedFileHandler:
    """Handle changes to linked external files."""

    def __init__(self, alias: str, path: Path, debounce_seconds: float = 2.0):
        self.alias = alias
        self.path = path
        self.debounce_seconds = debounce_seconds
        self.pending_paths: set[Path] = set()
        self.last_change: float = 0.0
        self.stats = {"indexed": 0, "errors": 0}

    def _should_handle(self, event_path: str) -> bool:
        """Check if this path should trigger indexing."""
        if not event_path.endswith(".md"):
            return False
        path_obj = Path(event_path)
        if any(part.startswith(".") for part in path_obj.parts):
            return False
        return True

    def on_modified(self, event: FileSystemEvent) -> None:
        src_path = str(event.src_path)
        if not event.is_directory and self._should_handle(src_path):
            self.pending_paths.add(Path(src_path))
            self.last_change = time.time()

    def on_created(self, event: FileSystemEvent) -> None:
        src_path = str(event.src_path)
        if not event.is_directory and self._should_handle(src_path):
            self.pending_paths.add(Path(src_path))
            self.last_change = time.time()

    def on_deleted(self, event: FileSystemEvent) -> None:
        src_path = str(event.src_path)
        if not event.is_directory and self._should_handle(src_path):
            self.pending_paths.add(Path(src_path))
            self.last_change = time.time()

    def process_pending(self) -> int:
        """Check if reindex is needed. Returns number of files processed."""
        if not self.pending_paths:
            return 0
        if time.time() - self.last_change < self.debounce_seconds:
            return 0

        paths = self.pending_paths.copy()
        self.pending_paths.clear()
        processed = 0

        for path in paths:
            try:
                if path.exists():
                    from nb.index.scanner import index_linked_file

                    index_linked_file(path, alias=self.alias)
                    logger.debug("Indexed linked file: %s", path)
                    self.stats["indexed"] += 1
                    processed += 1
            except Exception as e:
                logger.warning("Failed to index linked file %s: %s", path, e)
                self.stats["errors"] += 1

        return processed


class WatchdogAdapter:
    """Adapter to connect our handlers to watchdog's FileSystemEventHandler."""

    def __init__(self, handler: NoteChangeHandler | LinkedFileHandler):
        self.handler = handler

    def dispatch(self, event: FileSystemEvent) -> None:
        """Dispatch event to the appropriate handler method."""
        if event.event_type == "modified":
            self.handler.on_modified(event)
        elif event.event_type == "created":
            self.handler.on_created(event)
        elif event.event_type == "deleted":
            self.handler.on_deleted(event)
        elif event.event_type == "moved" and hasattr(self.handler, "on_moved"):
            self.handler.on_moved(event)


class DaemonState:
    """Persistent state for the daemon."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.start_time: float = time.time()
        self.files_indexed: int = 0
        self.files_removed: int = 0
        self.errors: int = 0
        self.last_activity: float = time.time()

    def write(self) -> None:
        """Write current state to file."""
        data = {
            "pid": os.getpid(),
            "start_time": self.start_time,
            "files_indexed": self.files_indexed,
            "files_removed": self.files_removed,
            "errors": self.errors,
            "last_update": time.time(),
            "last_activity": self.last_activity,
        }
        try:
            self.state_file.write_text(json.dumps(data))
        except OSError as e:
            logger.warning("Failed to write state file: %s", e)

    @classmethod
    def read(cls, state_file: Path) -> dict | None:
        """Read state from file."""
        if not state_file.exists():
            return None
        try:
            return json.loads(state_file.read_text())
        except (json.JSONDecodeError, OSError):
            return None


def _read_file_with_retry(path: Path, max_attempts: int = 3, delay: float = 0.2) -> str:
    """Read a file with retry logic for Windows file locking."""
    last_error: PermissionError | None = None
    for attempt in range(max_attempts):
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError as e:
            last_error = e
            if attempt < max_attempts - 1:
                time.sleep(delay)
    # If we get here, all attempts failed
    raise last_error  # type: ignore[misc]


def run_daemon(notes_root: Path, nb_dir: Path, foreground: bool = False) -> None:
    """Run the indexing daemon."""
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        logger.error("watchdog package not installed. Run: uv pip install watchdog")
        sys.exit(1)

    pid_file = nb_dir / "daemon.pid"
    state_file = nb_dir / "daemon.state"
    log_file = nb_dir / "daemon.log"

    # Setup logging
    handlers: list[logging.Handler] = [logging.FileHandler(log_file)]
    if foreground:
        handlers.append(logging.StreamHandler())

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )

    # Write PID file
    pid_file.write_text(str(os.getpid()))

    # Initialize state
    state = DaemonState(state_file)

    # Setup signal handlers for graceful shutdown
    running = True

    def handle_shutdown(signum, frame):
        nonlocal running
        logger.info("Received shutdown signal")
        running = False

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, handle_shutdown)

    # Lazy import config to avoid initialization issues
    from nb.config import get_config

    config = get_config()

    # Setup watchers
    observer = Observer()
    our_handlers: list[NoteChangeHandler | LinkedFileHandler] = []

    # Create a wrapper class that inherits from FileSystemEventHandler
    class WatchdogHandler(FileSystemEventHandler):
        def __init__(self, adapter: WatchdogAdapter):
            super().__init__()
            self.adapter = adapter

        def on_any_event(self, event):
            self.adapter.dispatch(event)

    # Watch notes_root
    main_handler = NoteChangeHandler(notes_root)
    watchdog_handler = WatchdogHandler(WatchdogAdapter(main_handler))
    observer.schedule(watchdog_handler, str(notes_root), recursive=True)
    our_handlers.append(main_handler)
    logger.info("Watching: %s", notes_root)

    # Watch external notebooks
    for nb in config.external_notebooks():
        if nb.path and nb.path.exists():
            ext_handler = NoteChangeHandler(nb.path)
            ext_watchdog = WatchdogHandler(WatchdogAdapter(ext_handler))
            observer.schedule(ext_watchdog, str(nb.path), recursive=True)
            our_handlers.append(ext_handler)
            logger.info("Watching external notebook: %s @ %s", nb.name, nb.path)

    # Watch linked todo files
    from nb.core.links import list_linked_files, list_linked_notes

    for linked_todo in list_linked_files():
        if linked_todo.path.exists():
            if linked_todo.path.is_file():
                # Watch parent directory for single file
                lf_handler = LinkedFileHandler(linked_todo.alias, linked_todo.path)
                lf_watchdog = WatchdogHandler(WatchdogAdapter(lf_handler))
                observer.schedule(
                    lf_watchdog, str(linked_todo.path.parent), recursive=False
                )
                our_handlers.append(lf_handler)
            else:
                lf_handler = LinkedFileHandler(linked_todo.alias, linked_todo.path)
                lf_watchdog = WatchdogHandler(WatchdogAdapter(lf_handler))
                observer.schedule(lf_watchdog, str(linked_todo.path), recursive=True)
                our_handlers.append(lf_handler)
            logger.info(
                "Watching linked todos: %s @ %s", linked_todo.alias, linked_todo.path
            )

    # Watch linked note directories
    for linked_note in list_linked_notes():
        if linked_note.path.exists():
            ln_handler = NoteChangeHandler(linked_note.path)
            ln_watchdog = WatchdogHandler(WatchdogAdapter(ln_handler))
            observer.schedule(
                ln_watchdog, str(linked_note.path), recursive=linked_note.recursive
            )
            our_handlers.append(ln_handler)
            logger.info(
                "Watching linked notes: %s @ %s", linked_note.alias, linked_note.path
            )

    observer.start()
    logger.info("Daemon started (PID: %d)", os.getpid())

    try:
        while running:
            # Process pending changes from all handlers
            total_processed = 0
            for handler in our_handlers:
                processed = handler.process_pending()
                if processed > 0:
                    total_processed += processed
                    state.files_indexed += processed
                    state.last_activity = time.time()
                    if hasattr(handler, "stats"):
                        state.errors = sum(
                            h.stats.get("errors", 0) for h in our_handlers
                        )
                        state.files_removed = sum(
                            h.stats.get("removed", 0)
                            for h in our_handlers
                            if isinstance(h, NoteChangeHandler)
                        )

            # Update state file periodically
            state.write()

            time.sleep(1)
    except Exception as e:
        logger.error("Daemon error: %s", e)
        raise
    finally:
        observer.stop()
        observer.join()
        pid_file.unlink(missing_ok=True)
        state_file.unlink(missing_ok=True)
        logger.info("Daemon stopped")


def is_daemon_running(nb_dir: Path) -> tuple[bool, dict | None]:
    """Check if daemon is running. Returns (running, state)."""
    pid_file = nb_dir / "daemon.pid"
    state_file = nb_dir / "daemon.state"

    if not pid_file.exists():
        return False, None

    try:
        pid = int(pid_file.read_text().strip())

        # Check if process exists
        if sys.platform == "win32":
            # Use tasklist on Windows
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
            )
            if str(pid) not in result.stdout:
                raise ProcessLookupError()
        else:
            os.kill(pid, 0)

        state = DaemonState.read(state_file)
        return True, state
    except (ProcessLookupError, ValueError, PermissionError, FileNotFoundError):
        # Process doesn't exist, clean up stale files
        pid_file.unlink(missing_ok=True)
        state_file.unlink(missing_ok=True)
        return False, None


def stop_daemon(nb_dir: Path, timeout: float = 5.0) -> bool:
    """Stop the daemon. Returns True if stopped."""
    pid_file = nb_dir / "daemon.pid"

    if not pid_file.exists():
        return False

    try:
        pid = int(pid_file.read_text().strip())

        if sys.platform == "win32":
            # Windows: Try graceful termination first
            subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True)

            # Wait for process to exit
            wait_iterations = int(timeout * 10)
            for _ in range(wait_iterations):
                time.sleep(0.1)
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True,
                    text=True,
                )
                if str(pid) not in result.stdout:
                    return True

            # Force kill if still running
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            return True
        else:
            # Unix: Send SIGTERM
            os.kill(pid, signal.SIGTERM)

            # Wait for process to exit
            wait_iterations = int(timeout * 10)
            for _ in range(wait_iterations):
                time.sleep(0.1)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    return True

            # Force kill if still running
            os.kill(pid, signal.SIGKILL)
            return True

    except (ProcessLookupError, ValueError, PermissionError, FileNotFoundError):
        pid_file.unlink(missing_ok=True)
        return False


def get_daemon_log(nb_dir: Path, lines: int = 50) -> list[str]:
    """Get the last N lines from the daemon log."""
    log_file = nb_dir / "daemon.log"
    if not log_file.exists():
        return []

    try:
        content = log_file.read_text(encoding="utf-8")
        all_lines = content.splitlines()
        return all_lines[-lines:]
    except OSError:
        return []


def main() -> None:
    """Entry point for nb-daemon command."""
    # Determine config file path
    if len(sys.argv) >= 2:
        # Config path provided as argument
        config_path = Path(sys.argv[1]).expanduser().resolve()
        if not config_path.exists():
            print(f"Config file not found: {config_path}", file=sys.stderr)
            sys.exit(1)
    else:
        # Try default location
        config_path = Path.home() / "notes" / ".nb" / "config.yaml"
        if not config_path.exists():
            print("No config found at ~/notes/.nb/config.yaml", file=sys.stderr)
            print("Usage: nb-daemon [config_file]", file=sys.stderr)
            print(
                "\nEither run 'nb' first to create config, or provide path to config.yaml",
                file=sys.stderr,
            )
            sys.exit(1)

    # Load config and run daemon
    try:
        from nb.config.io import load_config

        config = load_config(config_path)
        run_daemon(config.notes_root, config.nb_dir, foreground=False)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)


# Entry point for running as a module (python -m nb.daemon)
if __name__ == "__main__":
    main()
