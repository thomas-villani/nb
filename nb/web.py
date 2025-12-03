"""Minimal web viewer for nb."""

from __future__ import annotations

import http.server
import json
import socketserver
import sqlite3
import threading
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from nb.config import get_config
from nb.core.links import list_linked_notes, scan_linked_note_files
from nb.core.notebooks import get_notebook_notes_with_linked, list_notebooks
from nb.core.notes import get_note, get_sections_for_path


def get_alias_for_path(note_path: Path) -> str | None:
    """Get the alias for a given note path, if one exists.

    Uses a fresh SQLite connection for thread safety with ThreadingTCPServer.
    """
    config = get_config()
    try:
        # Create a fresh connection for thread safety
        conn = sqlite3.connect(config.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT alias, path FROM note_aliases")
        rows = cursor.fetchall()
        conn.close()

        # Normalize the path for comparison
        normalized = note_path.resolve() if note_path.is_absolute() else note_path
        normalized_str = str(normalized).replace("\\", "/")

        for row in rows:
            alias_path = Path(row["path"])
            if not alias_path.is_absolute():
                alias_path = config.notes_root / alias_path
            if (
                alias_path.resolve() == normalized
                or str(alias_path).replace("\\", "/") == normalized_str
            ):
                return row["alias"]
    except Exception:
        # If database doesn't exist or table missing, just return None
        pass
    return None


# Color name to hex mapping for notebook colors
COLOR_MAP = {
    "blue": "#58a6ff",
    "green": "#3fb950",
    "cyan": "#39c5cf",
    "magenta": "#db61a2",
    "red": "#f85149",
    "yellow": "#d29922",
    "orange": "#db6d28",
    "purple": "#a371f7",
    "pink": "#ff7b72",
    "gray": "#7d8590",
    "grey": "#7d8590",
}


def get_color_hex(color: str | None) -> str | None:
    """Convert color name to hex, or return hex if already hex."""
    if not color:
        return None
    if color.startswith("#"):
        return color
    return COLOR_MAP.get(color.lower())


def _safe_note_path(notes_root: Path, rel: str) -> Path | None:
    """Validate and resolve a note path, ensuring it stays within notes_root.

    For internal notes (relative paths), ensures the resolved path doesn't
    escape notes_root via path traversal (e.g., "../../etc/passwd").

    For linked/external notes (absolute paths), returns the path as-is since
    they are intentionally outside notes_root.

    Args:
        notes_root: The notes root directory.
        rel: The relative or absolute path string from the request.

    Returns:
        Resolved Path if valid, None if path traversal detected.
    """
    path = Path(rel)

    # Absolute paths are allowed for linked/external notes
    if path.is_absolute():
        return path

    # For relative paths, resolve and check containment
    resolved = (notes_root / rel).resolve()
    try:
        resolved.relative_to(notes_root.resolve())
    except ValueError:
        # Path escapes notes_root - path traversal attempt
        return None
    return resolved


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>nb</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/highlight.js@11/lib/core.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/highlight.js@11/lib/languages/python.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/highlight.js@11/lib/languages/javascript.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/highlight.js@11/lib/languages/bash.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/highlight.js@11/lib/languages/sql.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/highlight.js@11/lib/languages/yaml.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/highlight.js@11/styles/github-dark.min.css">
    <style>
        :root {
            --bg: #0d1117;
            --surface: #161b22;
            --text: #e6edf3;
            --text-dim: #7d8590;
            --accent: #58a6ff;
            --border: #30363d;
            --red: #f85149;
            --orange: #d29922;
            --green: #3fb950;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }

        /* Layout */
        .app { display: flex; min-height: 100vh; }
        .sidebar {
            width: 260px;
            background: var(--surface);
            border-right: 1px solid var(--border);
            padding: 1rem;
            overflow-y: auto;
            position: fixed;
            height: 100vh;
        }
        .main {
            margin-left: 260px;
            flex: 1;
            padding: 2rem 3rem;
        }

        /* Sidebar */
        .brand { font-weight: 600; font-size: 1.25rem; margin-bottom: 1.5rem; }
        .nav-section { margin-bottom: 1.5rem; }
        .nav-section h3 {
            font-size: 0.75rem;
            text-transform: uppercase;
            color: var(--text-dim);
            margin-bottom: 0.5rem;
            letter-spacing: 0.05em;
        }
        .nav-link {
            display: block;
            padding: 0.35rem 0.5rem;
            color: var(--text-dim);
            text-decoration: none;
            border-radius: 4px;
            font-size: 0.9rem;
            cursor: pointer;
        }
        .nav-link:hover { background: var(--border); color: var(--text); }
        .nav-link.active { background: var(--accent); color: var(--bg); }
        .note-list { max-height: 50vh; overflow-y: auto; }

        /* Color indicator */
        .color-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 6px;
            vertical-align: middle;
        }

        /* Search */
        .search-box {
            width: 100%;
            padding: 0.5rem;
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 4px;
            color: var(--text);
            font-size: 0.9rem;
            margin-bottom: 1rem;
        }
        .search-box:focus { outline: none; border-color: var(--accent); }
        .search-results { margin-top: 1rem; }
        .search-result {
            padding: 0.75rem;
            background: var(--surface);
            border-radius: 6px;
            margin-bottom: 0.5rem;
            cursor: pointer;
            border: 1px solid var(--border);
        }
        .search-result:hover { border-color: var(--accent); }
        .search-result h4 { margin-bottom: 0.25rem; color: var(--accent); }
        .search-result .snippet { font-size: 0.85rem; color: var(--text-dim); }

        /* Content */
        #content h1 { border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1rem; }
        #content h1, #content h2, #content h3 { margin-top: 1.5em; color: var(--text); }
        #content a { color: var(--accent); }
        #content a.wiki-link { color: var(--green); text-decoration: none; border-bottom: 1px dashed var(--green); }
        #content a.wiki-link:hover { border-bottom-style: solid; }
        #content a.note-link { text-decoration: none; border-bottom: 1px dotted var(--accent); }
        #content a.note-link:hover { border-bottom-style: solid; }
        #content pre { background: var(--surface); padding: 1rem; border-radius: 6px; overflow-x: auto; }
        #content code { background: var(--surface); padding: 0.2em 0.4em; border-radius: 3px; font-size: 0.9em; }
        #content pre code { background: none; padding: 0; }
        #content ul, #content ol { padding-left: 1.5rem; }
        #content li { margin: 0.25rem 0; }
        #content blockquote { border-left: 3px solid var(--border); padding-left: 1rem; color: var(--text-dim); }
        #content table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
        #content th, #content td { border: 1px solid var(--border); padding: 0.5rem; text-align: left; }
        #content th { background: var(--surface); }
        #content img { max-width: 100%; }

        /* Frontmatter panel */
        .frontmatter-panel {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 1rem;
            margin-bottom: 1.5rem;
        }
        .frontmatter-panel h4 {
            font-size: 0.75rem;
            text-transform: uppercase;
            color: var(--text-dim);
            margin-bottom: 0.75rem;
            letter-spacing: 0.05em;
        }
        .frontmatter-panel dl {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 0.5rem;
            margin: 0;
        }
        .frontmatter-panel .fm-row {
            display: flex;
            gap: 0.5rem;
        }
        .frontmatter-panel dt {
            color: var(--text-dim);
            font-size: 0.85rem;
            min-width: 80px;
        }
        .frontmatter-panel dd {
            color: var(--text);
            font-size: 0.85rem;
            margin: 0;
        }

        /* Backlinks panel */
        .backlinks-panel {
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border);
        }
        .backlinks-panel h3 {
            font-size: 0.85rem;
            text-transform: uppercase;
            color: var(--text-dim);
            margin-bottom: 0.75rem;
            letter-spacing: 0.05em;
        }
        .backlinks-panel ul {
            list-style: none;
            padding: 0;
        }
        .backlinks-panel li {
            padding: 0.4rem 0;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .backlinks-panel li a {
            color: var(--accent);
            text-decoration: none;
        }
        .backlinks-panel li a:hover { text-decoration: underline; }
        .backlinks-panel .meta {
            font-size: 0.75rem;
            color: var(--text-dim);
        }

        /* Graph view */
        .graph-container {
            width: 100%;
            height: calc(100vh - 150px);
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            overflow: hidden;
        }
        .graph-container svg {
            width: 100%;
            height: 100%;
        }
        .graph-node {
            cursor: pointer;
        }
        .graph-node circle {
            stroke: var(--border);
            stroke-width: 1.5px;
        }
        .graph-node:hover circle {
            stroke: var(--accent);
            stroke-width: 2px;
        }
        .graph-node text {
            font-size: 10px;
            fill: var(--text);
            pointer-events: none;
        }
        .graph-link {
            stroke: var(--border);
            stroke-opacity: 0.6;
        }
        .graph-link:hover {
            stroke: var(--accent);
            stroke-opacity: 1;
        }
        .graph-controls {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
            flex-wrap: wrap;
            align-items: center;
        }
        .graph-controls label {
            color: var(--text-dim);
            font-size: 0.85rem;
        }
        .graph-controls input[type="range"] {
            width: 100px;
        }

        /* Notebook grid for home */
        .notebook-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 1rem; }
        .notebook-card {
            background: var(--surface);
            padding: 1.25rem;
            border-radius: 8px;
            border: 1px solid var(--border);
            cursor: pointer;
            transition: border-color 0.2s;
            position: relative;
        }
        .notebook-card:hover { border-color: var(--accent); }
        .notebook-card h3 { margin-bottom: 0.25rem; font-size: 1rem; display: flex; align-items: center; }
        .notebook-card .count { color: var(--text-dim); font-size: 0.85rem; }
        .notebook-card .color-bar {
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 4px;
            border-radius: 8px 0 0 8px;
        }

        /* Todos */
        .todo-item {
            padding: 0.75rem;
            background: var(--surface);
            border-radius: 6px;
            margin-bottom: 0.5rem;
            border-left: 3px solid var(--border);
            display: flex;
            align-items: flex-start;
            gap: 0.75rem;
        }
        .todo-item.overdue { border-left-color: var(--red); }
        .todo-item.due-today { border-left-color: var(--orange); }
        .todo-item.in-progress { border-left-color: var(--green); }
        .todo-item.completed { opacity: 0.6; }
        .todo-item .checkbox {
            width: 18px;
            height: 18px;
            border: 2px solid var(--border);
            border-radius: 3px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            margin-top: 2px;
        }
        .todo-item .checkbox:hover { border-color: var(--accent); }
        .todo-item.completed .checkbox { background: var(--green); border-color: var(--green); }
        .todo-item .checkbox svg { display: none; }
        .todo-item.completed .checkbox svg { display: block; }
        .todo-item .todo-body { flex: 1; }
        .todo-item .content { margin-bottom: 0.25rem; }
        .todo-item.completed .content { text-decoration: line-through; }
        .todo-item .meta { font-size: 0.8rem; color: var(--text-dim); }
        .priority-1 { color: var(--red); }
        .priority-2 { color: var(--orange); }
        .priority-3 { color: var(--text-dim); }

        /* Add todo form */
        .add-todo-form {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1.5rem;
        }
        .add-todo-form input {
            flex: 1;
            padding: 0.5rem 0.75rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 4px;
            color: var(--text);
            font-size: 0.9rem;
        }
        .add-todo-form input:focus { outline: none; border-color: var(--accent); }
        .add-todo-form button {
            padding: 0.5rem 1rem;
            background: var(--accent);
            border: none;
            border-radius: 4px;
            color: var(--bg);
            font-weight: 500;
            cursor: pointer;
        }
        .add-todo-form button:hover { opacity: 0.9; }

        /* Action buttons */
        .header-actions {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
        }
        .btn {
            padding: 0.4rem 0.75rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 4px;
            color: var(--text);
            font-size: 0.85rem;
            cursor: pointer;
        }
        .btn:hover { border-color: var(--accent); }
        .btn-primary { background: var(--accent); color: var(--bg); border-color: var(--accent); }

        /* Note editor */
        .note-editor {
            margin-top: 1rem;
        }
        .note-editor textarea {
            width: 100%;
            min-height: 400px;
            padding: 1rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text);
            font-family: monospace;
            font-size: 0.9rem;
            resize: vertical;
        }
        .note-editor textarea:focus { outline: none; border-color: var(--accent); }
        .editor-actions {
            display: flex;
            gap: 0.5rem;
            margin-top: 0.75rem;
        }

        /* Loading state */
        .loading { color: var(--text-dim); }

        /* Note table rows */
        .note-row { cursor: pointer; transition: background 0.15s; }
        .note-row:hover { background: var(--surface); }

        /* Mobile */
        @media (max-width: 768px) {
            .sidebar { width: 100%; height: auto; position: relative; border-right: none; border-bottom: 1px solid var(--border); }
            .main { margin-left: 0; padding: 1rem; }
            .app { flex-direction: column; }
            .note-list { max-height: 30vh; }
        }

        /* Kanban Board Styles */
        .kanban-board {
            display: flex;
            gap: 1rem;
            overflow-x: auto;
            padding-bottom: 1rem;
            min-height: 400px;
        }
        .kanban-column {
            min-width: 280px;
            max-width: 320px;
            background: var(--surface);
            border-radius: 8px;
            padding: 0.5rem;
            display: flex;
            flex-direction: column;
        }
        .kanban-column.drag-over {
            border: 2px dashed var(--accent);
            background: rgba(88, 166, 255, 0.1);
        }
        .kanban-header {
            font-weight: 600;
            padding: 0.5rem;
            border-bottom: 2px solid var(--accent);
            margin-bottom: 0.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .kanban-header .count {
            font-size: 0.8rem;
            color: var(--text-dim);
            background: var(--bg);
            padding: 0.1rem 0.4rem;
            border-radius: 10px;
        }
        .kanban-items {
            flex: 1;
            min-height: 100px;
            overflow-y: auto;
        }
        .kanban-card {
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 4px;
            padding: 0.75rem;
            margin-bottom: 0.5rem;
            cursor: grab;
            transition: border-color 0.15s, box-shadow 0.15s;
        }
        .kanban-card:hover {
            border-color: var(--accent);
        }
        .kanban-card.dragging {
            opacity: 0.5;
            cursor: grabbing;
        }
        .kanban-card-content {
            margin-bottom: 0.5rem;
            word-wrap: break-word;
        }
        .kanban-card-meta {
            font-size: 0.75rem;
            color: var(--text-dim);
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }
        .kanban-card-meta .priority-1 { color: #f85149; }
        .kanban-card-meta .priority-2 { color: #d29922; }
        .kanban-card-meta .priority-3 { color: #58a6ff; }
        .kanban-card-meta .due { color: var(--text-dim); }
        .kanban-card-meta .due.overdue { color: #f85149; }
        .kanban-card-meta .due.today { color: #d29922; }
        .kanban-card-meta .notebook { color: var(--accent); }
    </style>
</head>
<body>
    <div class="app">
        <nav class="sidebar">
            <div class="brand">nb</div>
            <input type="text" class="search-box" placeholder="Search notes..." id="searchInput">
            <div class="nav-section">
                <h3>Navigation</h3>
                <a class="nav-link" onclick="loadHome()">Home</a>
                <a class="nav-link" onclick="loadHistory()">History</a>
                <a class="nav-link" onclick="loadTodos()">Todos</a>
                <a class="nav-link" onclick="loadKanban()">Kanban</a>
                <a class="nav-link" onclick="loadGraph()">Graph</a>
            </div>
            <div class="nav-section">
                <h3>Notebooks</h3>
                <div id="notebooks"></div>
            </div>
            <div class="nav-section" id="notes-section" style="display:none">
                <h3>Notes</h3>
                <div id="notes" class="note-list"></div>
            </div>
        </nav>
        <main class="main">
            <div id="content"><p class="loading">Loading...</p></div>
        </main>
    </div>

    <script>
        // Wiki link extension for marked.js
        const wikiLinkExtension = {
            name: 'wikiLink',
            level: 'inline',
            start(src) { return src.indexOf('[['); },
            tokenizer(src) {
                const match = /^\\[\\[([^\\]|]+)(?:\\|([^\\]]+))?\\]\\]/.exec(src);
                if (match) {
                    return {
                        type: 'wikiLink',
                        raw: match[0],
                        target: match[1].trim(),
                        display: (match[2] || match[1]).trim()
                    };
                }
            },
            renderer(token) {
                const target = escapeHtml(token.target);
                const display = escapeHtml(token.display);
                return `<a href="javascript:void(0)" class="wiki-link" data-target="${target}" onclick="navigateToNote('${escapeJs(token.target)}')">${display}</a>`;
            }
        };

        // Custom renderer for markdown links to handle internal notes
        const renderer = new marked.Renderer();
        const originalLinkRenderer = renderer.link.bind(renderer);
        renderer.link = function(href, title, text) {
            // Handle both object form (newer marked) and positional args (older marked)
            if (typeof href === 'object') {
                const token = href;
                href = token.href;
                title = token.title;
                text = token.text;
            }

            const isExternal = /^(https?:|mailto:|ftp:|file:)/i.test(href);
            if (isExternal) {
                // External link - open in new tab
                const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
                return `<a href="${escapeHtml(href)}"${titleAttr} target="_blank" rel="noopener">${text}</a>`;
            } else {
                // Internal link - navigate to note
                const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
                return `<a href="javascript:void(0)" class="note-link" data-target="${escapeHtml(href)}"${titleAttr} onclick="navigateToNote('${escapeJs(href)}')">${text}</a>`;
            }
        };

        marked.use({ extensions: [wikiLinkExtension], renderer: renderer });
        marked.setOptions({
            highlight: function(code, lang) {
                if (lang && hljs.getLanguage(lang)) {
                    return hljs.highlight(code, { language: lang }).value;
                }
                return code;
            },
            gfm: true,
            breaks: true
        });

        let currentNotebook = null;
        let currentNotePath = null;
        let searchTimeout = null;
        let notebooksCache = [];
        let notebookFilter = '';
        let notebookFilterTimeout = null;
        let cachedNotebookNotes = []; // Cache notes for current notebook

        // Load preferences from localStorage with defaults
        function loadPreferences() {
            try {
                const prefs = JSON.parse(localStorage.getItem('nb-web-prefs') || '{}');
                return {
                    homeSortBy: prefs.homeSortBy || 'alpha',
                    notebookSortBy: prefs.notebookSortBy || 'mtime-desc',
                    historySortBy: prefs.historySortBy || 'viewed',
                    todoSortBy: prefs.todoSortBy || 'section',
                };
            } catch (e) {
                return {
                    homeSortBy: 'alpha',
                    notebookSortBy: 'mtime-desc',
                    historySortBy: 'viewed',
                    todoSortBy: 'section',
                };
            }
        }

        function savePreferences() {
            try {
                localStorage.setItem('nb-web-prefs', JSON.stringify({
                    homeSortBy,
                    notebookSortBy,
                    historySortBy,
                    todoSortBy,
                }));
            } catch (e) {
                // Ignore localStorage errors
            }
        }

        // Initialize preferences from localStorage
        const prefs = loadPreferences();
        let homeSortBy = prefs.homeSortBy;
        let notebookSortBy = prefs.notebookSortBy;
        let historySortBy = prefs.historySortBy;
        let todoSortBy = prefs.todoSortBy;

        function sortNotebooks(notebooks, sortBy) {
            return [...notebooks].sort((a, b) => {
                if (sortBy === 'alpha') return (a.name || '').localeCompare(b.name || '');
                if (sortBy === 'modified') return (b.lastModified || 0) - (a.lastModified || 0);
                if (sortBy === 'viewed') {
                    // Parse ISO date strings for comparison
                    const aViewed = a.lastViewed ? new Date(a.lastViewed).getTime() : 0;
                    const bViewed = b.lastViewed ? new Date(b.lastViewed).getTime() : 0;
                    return bViewed - aViewed;
                }
                return 0;
            });
        }

        function sortNotes(notes, sortBy) {
            return [...notes].sort((a, b) => {
                if (sortBy === 'date-desc') return (b.date || '').localeCompare(a.date || '');
                if (sortBy === 'date-asc') return (a.date || '9999').localeCompare(b.date || '9999');
                if (sortBy === 'mtime-desc') return (b.mtime || 0) - (a.mtime || 0);
                if (sortBy === 'mtime-asc') return (a.mtime || 0) - (b.mtime || 0);
                if (sortBy === 'viewed-desc') {
                    const aViewed = a.lastViewed ? new Date(a.lastViewed).getTime() : 0;
                    const bViewed = b.lastViewed ? new Date(b.lastViewed).getTime() : 0;
                    return bViewed - aViewed;
                }
                if (sortBy === 'viewed-asc') {
                    const aViewed = a.lastViewed ? new Date(a.lastViewed).getTime() : Infinity;
                    const bViewed = b.lastViewed ? new Date(b.lastViewed).getTime() : Infinity;
                    return aViewed - bViewed;
                }
                if (sortBy === 'title-asc') return (a.title || '').localeCompare(b.title || '');
                if (sortBy === 'title-desc') return (b.title || '').localeCompare(a.title || '');
                if (sortBy === 'filename') return (a.filename || '').localeCompare(b.filename || '');
                if (sortBy === 'section') {
                    // Sort by section path first, then by mtime within each section
                    const aSection = (a.sections || []).join('/');
                    const bSection = (b.sections || []).join('/');
                    const sectionCmp = aSection.localeCompare(bSection);
                    if (sectionCmp !== 0) return sectionCmp;
                    return (b.mtime || 0) - (a.mtime || 0);
                }
                return 0;
            });
        }

        function filterNotes(notes, filter) {
            if (!filter.trim()) return notes;
            const f = filter.trim().toLowerCase();
            return notes.filter(n => {
                return (n.title || '').toLowerCase().includes(f) ||
                    (n.filename || '').toLowerCase().includes(f) ||
                    (n.alias || '').toLowerCase().includes(f) ||
                    (n.tags || []).some(t => t.toLowerCase().includes(f));
            });
        }

        // Get today's date in local timezone (YYYY-MM-DD)
        function getToday() {
            const d = new Date();
            return d.getFullYear() + '-' +
                String(d.getMonth() + 1).padStart(2, '0') + '-' +
                String(d.getDate()).padStart(2, '0');
        }

        // Format timestamp as relative time (e.g., "5 min ago", "2 days ago")
        function formatRelativeTime(timestampMs) {
            if (!timestampMs) return '-';
            const now = Date.now();
            const diffMs = now - timestampMs;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMs / 3600000);
            const diffDays = Math.floor(diffMs / 86400000);

            if (diffMins < 1) return 'just now';
            if (diffMins < 60) return diffMins + 'm ago';
            if (diffHours < 24) return diffHours + 'h ago';
            if (diffDays < 7) return diffDays + 'd ago';
            if (diffDays < 30) return Math.floor(diffDays / 7) + 'w ago';
            return new Date(timestampMs).toLocaleDateString();
        }

        async function api(endpoint, options = {}) {
            const res = await fetch('/api' + endpoint, options);
            return res.json();
        }

        async function loadNotebooks() {
            notebooksCache = await api('/notebooks');
            document.getElementById('notebooks').innerHTML = notebooksCache
                .map(nb => {
                    const dot = nb.color ? `<span class="color-dot" style="background:${nb.color}"></span>` : '';
                    return `<a class="nav-link" onclick="loadNotebook('${escapeJs(nb.name)}')">${dot}${escapeHtml(nb.name)} <span style="color:var(--text-dim)">(${nb.count})</span></a>`;
                })
                .join('');
        }

        function escapeHtml(str) {
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        function escapeJs(str) {
            return str.replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\\\'").replace(/"/g, '\\\\"');
        }

        // Navigate to a note from a wiki link or internal markdown link
        async function navigateToNote(target) {
            // Try to resolve the link target to an actual note path
            const result = await api('/resolve-link?target=' + encodeURIComponent(target) + (currentNotePath ? '&source=' + encodeURIComponent(currentNotePath) : ''));
            if (result.path) {
                loadNote(result.path);
            } else {
                // Link could not be resolved - show a message
                alert('Note not found: ' + target + (result.suggestion ? '\\n\\nDid you mean: ' + result.suggestion + '?' : ''));
            }
        }

        async function loadHome(pushHistory = true, fetchNotebooks = true) {
            currentNotebook = null;
            currentNotePath = null;
            document.getElementById('notes-section').style.display = 'none';
            if (pushHistory) history.pushState({ view: 'home' }, '', '#');

            if (fetchNotebooks || !notebooksCache.length) {
                notebooksCache = await api('/notebooks');
            }

            const sortedNbs = sortNotebooks(notebooksCache, homeSortBy);

            document.getElementById('content').innerHTML = `
                <h1>Notebooks</h1>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
                    <p style="color:var(--text-dim)">${sortedNbs.length} notebooks</p>
                    <select id="homeSort" style="padding:0.3rem 0.5rem;background:var(--surface);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:0.85rem">
                        <option value="alpha" ${homeSortBy === 'alpha' ? 'selected' : ''}>Alphabetical</option>
                        <option value="modified" ${homeSortBy === 'modified' ? 'selected' : ''}>Recently Modified</option>
                        <option value="viewed" ${homeSortBy === 'viewed' ? 'selected' : ''}>Recently Viewed</option>
                    </select>
                </div>
                <div class="notebook-grid">
                    ${sortedNbs.map(nb => `
                        <div class="notebook-card" onclick="loadNotebook('${escapeJs(nb.name)}')">
                            ${nb.color ? `<div class="color-bar" style="background:${nb.color}"></div>` : ''}
                            <h3>${escapeHtml(nb.name)}</h3>
                            <span class="count">${nb.count} notes</span>
                        </div>
                    `).join('')}
                </div>
            `;

            // Add event listener for sort change
            const sortSelect = document.getElementById('homeSort');
            if (sortSelect) {
                sortSelect.addEventListener('change', (e) => {
                    homeSortBy = e.target.value;
                    savePreferences();
                    loadHome(false, false);
                });
            }
        }

        async function loadNotebook(name, pushHistory = true, fetchNotes = true) {
            currentNotebook = name;
            currentNotePath = null;
            if (pushHistory) history.pushState({ view: 'notebook', name }, '', '#notebook/' + encodeURIComponent(name));

            if (fetchNotes) {
                cachedNotebookNotes = await api('/notebooks/' + encodeURIComponent(name));
            }

            // Apply filter and sort
            let displayNotes = filterNotes(cachedNotebookNotes, notebookFilter);
            displayNotes = sortNotes(displayNotes, notebookSortBy);

            document.getElementById('notes-section').style.display = 'block';
            document.getElementById('notes').innerHTML = displayNotes
                .map(n => {
                    const aliasTag = n.alias ? ` <span style="color:var(--accent);font-size:0.8em">@${escapeHtml(n.alias)}</span>` : '';
                    const linkedIcon = n.isLinked ? '<span style="color:var(--text-dim)" title="Linked note">↗</span> ' : '';
                    return `<a class="nav-link" onclick="loadNote('${escapeJs(n.path)}')">${linkedIcon}${escapeHtml(n.title)}${aliasTag}</a>`;
                })
                .join('');

            const nb = notebooksCache.find(x => x.name === name);
            const colorBar = nb && nb.color ? `<span class="color-dot" style="background:${nb.color};width:12px;height:12px"></span> ` : '';
            const isVirtualNb = name.startsWith('@');

            document.getElementById('content').innerHTML = `
                <h1>${colorBar}${escapeHtml(name)}</h1>
                <div class="header-actions">
                    ${!isVirtualNb ? `<button class="btn btn-primary" onclick="showNewNoteForm('${escapeJs(name)}')">+ New Note</button>` : ''}
                </div>
                <input type="text" class="search-box" id="notebookFilterInput" placeholder="Filter notes by title, filename, alias, or tag..." value="${escapeHtml(notebookFilter)}" style="margin:0.5rem 0">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
                    <p style="color:var(--text-dim)">${displayNotes.length} of ${cachedNotebookNotes.length} notes</p>
                    <select id="notebookSort" style="padding:0.3rem 0.5rem;background:var(--surface);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:0.85rem">
                        <option value="mtime-desc" ${notebookSortBy === 'mtime-desc' ? 'selected' : ''}>Modified (Newest)</option>
                        <option value="mtime-asc" ${notebookSortBy === 'mtime-asc' ? 'selected' : ''}>Modified (Oldest)</option>
                        <option value="viewed-desc" ${notebookSortBy === 'viewed-desc' ? 'selected' : ''}>Viewed (Newest)</option>
                        <option value="viewed-asc" ${notebookSortBy === 'viewed-asc' ? 'selected' : ''}>Viewed (Oldest)</option>
                        <option value="date-desc" ${notebookSortBy === 'date-desc' ? 'selected' : ''}>Date (Newest)</option>
                        <option value="date-asc" ${notebookSortBy === 'date-asc' ? 'selected' : ''}>Date (Oldest)</option>
                        <option value="title-asc" ${notebookSortBy === 'title-asc' ? 'selected' : ''}>Title (A-Z)</option>
                        <option value="title-desc" ${notebookSortBy === 'title-desc' ? 'selected' : ''}>Title (Z-A)</option>
                        <option value="filename" ${notebookSortBy === 'filename' ? 'selected' : ''}>Filename</option>
                        <option value="section" ${notebookSortBy === 'section' ? 'selected' : ''}>Section</option>
                    </select>
                </div>
                <div style="overflow-x:auto">
                    <table style="width:100%;border-collapse:collapse;font-size:0.9rem">
                        <thead>
                            <tr style="border-bottom:1px solid var(--border);text-align:left">
                                <th style="padding:0.5rem;color:var(--text-dim);font-weight:500">Title</th>
                                <th style="padding:0.5rem;color:var(--text-dim);font-weight:500">Path</th>
                                <th style="padding:0.5rem;color:var(--text-dim);font-weight:500;white-space:nowrap">Date</th>
                                <th style="padding:0.5rem;color:var(--text-dim);font-weight:500;white-space:nowrap">Modified</th>
                                <th style="padding:0.5rem;color:var(--text-dim);font-weight:500;white-space:nowrap">Viewed</th>
                                <th style="padding:0.5rem;color:var(--text-dim);font-weight:500">Tags</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${displayNotes.map(n => {
                                const aliasTag = n.alias ? ` <span style="color:var(--accent);font-size:0.8em">@${escapeHtml(n.alias)}</span>` : '';
                                const linkedIcon = n.isLinked ? '<span style="color:var(--text-dim)" title="Linked note">↗</span> ' : '';
                                // Format mtime as relative or date
                                const mtimeStr = n.mtime ? formatRelativeTime(n.mtime * 1000) : '-';
                                // Format lastViewed
                                const viewedStr = n.lastViewed ? formatRelativeTime(new Date(n.lastViewed).getTime()) : '-';
                                // Tags - limit to first 5
                                const tags = n.tags || [];
                                const displayTags = tags.slice(0, 5);
                                const moreTags = tags.length > 5 ? ` <span style="color:var(--text-dim)">+${tags.length - 5} more</span>` : '';
                                const tagsHtml = displayTags.map(t => `<span style="color:var(--text-dim);font-size:0.8rem;background:var(--surface);padding:0.1rem 0.3rem;border-radius:3px;margin-right:0.25rem">#${escapeHtml(t)}</span>`).join('') + moreTags;
                                // Path relative to notebook (sections + filename)
                                const relPath = (n.sections || []).length > 0 ? (n.sections.join('/') + '/' + n.filename) : n.filename;
                                return `
                                <tr style="border-bottom:1px solid var(--border)" class="note-row" onclick="loadNote('${escapeJs(n.path)}')">
                                    <td style="padding:0.5rem">
                                        <a href="javascript:void(0)" style="color:var(--accent);text-decoration:none">${linkedIcon}${escapeHtml(n.title)}</a>${aliasTag}
                                    </td>
                                    <td style="padding:0.5rem;color:var(--text-dim);font-size:0.85rem">${escapeHtml(relPath)}</td>
                                    <td style="padding:0.5rem;color:var(--text-dim);white-space:nowrap">${n.date || '-'}</td>
                                    <td style="padding:0.5rem;color:var(--text-dim);white-space:nowrap">${mtimeStr}</td>
                                    <td style="padding:0.5rem;color:var(--text-dim);white-space:nowrap">${viewedStr}</td>
                                    <td style="padding:0.5rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${tagsHtml || '-'}</td>
                                </tr>
                            `;}).join('')}
                        </tbody>
                    </table>
                </div>
            `;

            // Add event listeners for sort and filter
            const sortSelect = document.getElementById('notebookSort');
            if (sortSelect) {
                sortSelect.addEventListener('change', (e) => {
                    notebookSortBy = e.target.value;
                    savePreferences();
                    loadNotebook(name, false, false);
                });
            }

            const filterInput = document.getElementById('notebookFilterInput');
            if (filterInput) {
                filterInput.addEventListener('input', (e) => {
                    clearTimeout(notebookFilterTimeout);
                    notebookFilterTimeout = setTimeout(() => {
                        notebookFilter = e.target.value;
                        loadNotebook(name, false, false);
                    }, 300);
                });
                if (notebookFilter) {
                    filterInput.focus();
                    filterInput.setSelectionRange(filterInput.value.length, filterInput.value.length);
                }
            }

        }

        let currentNoteMarkdown = ''; // Store markdown for copy function

        async function loadNote(path, pushHistory = true) {
            currentNotePath = path;
            if (pushHistory) history.pushState({ view: 'note', path }, '', '#note/' + encodeURIComponent(path));

            // Fetch note and backlinks in parallel
            const [note, backlinks] = await Promise.all([
                api('/note?path=' + encodeURIComponent(path)),
                api('/backlinks?path=' + encodeURIComponent(path))
            ]);

            // Strip frontmatter for display
            let content = note.content;
            if (content.startsWith('---')) {
                const parts = content.split('---');
                if (parts.length >= 3) {
                    content = parts.slice(2).join('---').trim();
                }
            }

            // Store markdown for copy function
            currentNoteMarkdown = content;

            const aliasBadge = note.alias ? `<span style="color:var(--accent);font-size:0.7em;margin-left:0.75rem;vertical-align:middle">@${escapeHtml(note.alias)}</span>` : '';

            // Build backlinks panel
            let backlinksHtml = '';
            if (backlinks && backlinks.length > 0) {
                const linkTypeIcon = (type) => {
                    if (type === 'wiki') return '<span title="Wiki link" style="color:var(--green)">[[]]</span>';
                    if (type === 'markdown') return '<span title="Markdown link" style="color:var(--accent)">[]()</span>';
                    return '<span title="Frontmatter" style="color:var(--text-dim)">fm</span>';
                };
                backlinksHtml = `
                    <div class="backlinks-panel">
                        <h3>Backlinks <span style="color:var(--text-dim);font-weight:normal">(${backlinks.length})</span></h3>
                        <ul>
                            ${backlinks.map(b => `
                                <li>
                                    <a href="javascript:void(0)" onclick="loadNote('${escapeJs(b.source_path)}')">${escapeHtml(b.source_path.split('/').pop().replace('.md', ''))}</a>
                                    <span class="meta">${linkTypeIcon(b.link_type)}${b.line_number ? ` line ${b.line_number}` : ''}</span>
                                </li>
                            `).join('')}
                        </ul>
                    </div>
                `;
            }

            // Build frontmatter panel if present
            let frontmatterHtml = '';
            if (note.frontmatter && Object.keys(note.frontmatter).length > 0) {
                const formatValue = (val) => {
                    if (Array.isArray(val)) return val.join(', ');
                    if (typeof val === 'object') return JSON.stringify(val);
                    return String(val);
                };
                frontmatterHtml = `
                    <div class="frontmatter-panel">
                        <h4>Properties</h4>
                        <dl>
                            ${Object.entries(note.frontmatter).map(([key, val]) =>
                                `<div class="fm-row"><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(formatValue(val))}</dd></div>`
                            ).join('')}
                        </dl>
                    </div>
                `;
            }

            document.getElementById('content').innerHTML = `
                <div class="header-actions">
                    <button class="btn" onclick="editNote('${escapeJs(path)}')">Edit</button>
                    <button class="btn" id="copyNoteBtn" onclick="copyNote()">Copy</button>
                </div>
                ${frontmatterHtml}
                <div id="note-content">${marked.parse(content)}${aliasBadge ? `<p style="margin-top:1rem;color:var(--text-dim);font-size:0.85rem">Alias: <span style="color:var(--accent)">@${escapeHtml(note.alias || '')}</span></p>` : ''}</div>
                ${backlinksHtml}
            `;

            // Update active state in sidebar
            document.querySelectorAll('#notes .nav-link').forEach(el => {
                el.classList.toggle('active', el.textContent === note.title);
            });
        }

        async function copyNote() {
            const btn = document.getElementById('copyNoteBtn');
            const noteContent = document.getElementById('note-content');
            if (!noteContent || !currentNoteMarkdown) return;

            try {
                // Get HTML content (rendered)
                const htmlContent = noteContent.innerHTML;

                // Create clipboard items with both HTML and plain text (markdown)
                const htmlBlob = new Blob([htmlContent], { type: 'text/html' });
                const textBlob = new Blob([currentNoteMarkdown], { type: 'text/plain' });

                await navigator.clipboard.write([
                    new ClipboardItem({
                        'text/html': htmlBlob,
                        'text/plain': textBlob
                    })
                ]);

                // Show success feedback
                const originalText = btn.textContent;
                btn.textContent = 'Copied!';
                btn.style.color = 'var(--green)';
                setTimeout(() => {
                    btn.textContent = originalText;
                    btn.style.color = '';
                }, 1500);
            } catch (err) {
                // Fallback to plain text copy
                try {
                    await navigator.clipboard.writeText(currentNoteMarkdown);
                    btn.textContent = 'Copied!';
                    setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
                } catch (e) {
                    btn.textContent = 'Failed';
                    setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
                }
            }
        }

        async function editNote(path) {
            const note = await api('/note?path=' + encodeURIComponent(path));

            document.getElementById('content').innerHTML = `
                <h1>Edit Note</h1>
                <div class="note-editor">
                    <textarea id="noteContent">${escapeHtml(note.content)}</textarea>
                    <div class="editor-actions">
                        <button class="btn btn-primary" onclick="saveNote('${escapeJs(path)}')">Save</button>
                        <button class="btn" onclick="loadNote('${escapeJs(path)}')">Cancel</button>
                    </div>
                </div>
            `;
        }

        async function saveNote(path) {
            const content = document.getElementById('noteContent').value;
            await api('/note', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: path, content: content })
            });
            loadNote(path);
        }

        function showNewNoteForm(notebook) {
            document.getElementById('content').innerHTML = `
                <h1>New Note in ${escapeHtml(notebook)}</h1>
                <div style="margin-bottom:1rem">
                    <label style="display:block;margin-bottom:0.5rem;color:var(--text-dim)">Filename (without .md)</label>
                    <input type="text" id="newNoteFilename" style="width:100%;max-width:400px;padding:0.5rem;background:var(--surface);border:1px solid var(--border);border-radius:4px;color:var(--text)" placeholder="my-note">
                </div>
                <div class="note-editor">
                    <textarea id="noteContent" placeholder="# Title\\n\\nStart writing..."></textarea>
                    <div class="editor-actions">
                        <button class="btn btn-primary" onclick="createNote('${escapeJs(notebook)}')">Create</button>
                        <button class="btn" onclick="loadNotebook('${escapeJs(notebook)}')">Cancel</button>
                    </div>
                </div>
            `;
        }

        async function createNote(notebook) {
            const filename = document.getElementById('newNoteFilename').value.trim();
            if (!filename) {
                alert('Please enter a filename');
                return;
            }
            const content = document.getElementById('noteContent').value;
            const path = notebook + '/' + filename + '.md';

            const result = await api('/note', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: path, content: content, create: true })
            });

            if (result.error) {
                alert(result.error);
            } else {
                loadNotebook(notebook);
            }
        }

        let todoFilter = ''; // Filter text for todos
        let todoFilterTimeout = null;

        function filterTodos(todos, filter) {
            if (!filter.trim()) return todos;
            const f = filter.trim().toLowerCase();
            return todos.filter(t => {
                // Filter by notebook: "notebook:name" or "@name"
                if (f.startsWith('notebook:')) {
                    const nb = f.slice(9);
                    return (t.notebook || '').toLowerCase().includes(nb);
                }
                if (f.startsWith('@')) {
                    const nb = f.slice(1);
                    return (t.notebook || '').toLowerCase().includes(nb);
                }
                // Filter by tag: "#tag"
                if (f.startsWith('#')) {
                    const tag = f.slice(1);
                    return (t.tags || []).some(tg => tg.toLowerCase().includes(tag));
                }
                // Plain text: search content, notebook, and tags
                return t.content.toLowerCase().includes(f) ||
                    (t.notebook || '').toLowerCase().includes(f) ||
                    (t.tags || []).some(tg => tg.toLowerCase().includes(f));
            });
        }

        async function loadTodos(pushHistory = true) {
            currentNotebook = null;
            currentNotePath = null;
            document.getElementById('notes-section').style.display = 'none';
            if (pushHistory) history.pushState({ view: 'todos' }, '', '#todos');

            let todos = await api('/todos');
            const today = getToday();

            // Apply filter
            todos = filterTodos(todos, todoFilter);
            const checkIcon = '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="white" stroke-width="2"><path d="M2 6l3 3 5-5"/></svg>';

            // Group todos into sections
            const sections = {
                overdue: { title: 'Overdue', color: 'var(--red)', todos: [] },
                inProgress: { title: 'In Progress', color: 'var(--green)', todos: [] },
                dueToday: { title: 'Due Today', color: 'var(--orange)', todos: [] },
                dueThisWeek: { title: 'Due This Week', color: 'var(--accent)', todos: [] },
                dueLater: { title: 'Due Later', color: 'var(--text-dim)', todos: [] },
                noDueDate: { title: 'No Due Date', color: 'var(--text-dim)', todos: [] },
                completed: { title: 'Completed', color: 'var(--text-dim)', todos: [] }
            };

            todos.forEach(t => {
                if (t.status === 'completed') sections.completed.todos.push(t);
                else if (t.status === 'in_progress') sections.inProgress.todos.push(t);
                else if (t.isOverdue) sections.overdue.todos.push(t);
                else if (t.isDueToday) sections.dueToday.todos.push(t);
                else if (t.isDueThisWeek) sections.dueThisWeek.todos.push(t);
                else if (t.due) sections.dueLater.todos.push(t);
                else sections.noDueDate.todos.push(t);
            });

            // Sort function based on current sort
            function sortTodos(todoList) {
                return todoList.sort((a, b) => {
                    if (todoSortBy === 'notebook') return (a.notebook || '').localeCompare(b.notebook || '');
                    if (todoSortBy === 'due') return (a.due || '9999').localeCompare(b.due || '9999');
                    if (todoSortBy === 'priority') return (a.priority || 99) - (b.priority || 99);
                    if (todoSortBy === 'created') return (b.created || '').localeCompare(a.created || '');
                    // Default: priority then due
                    const pDiff = (a.priority || 99) - (b.priority || 99);
                    if (pDiff !== 0) return pDiff;
                    return (a.due || '9999').localeCompare(b.due || '9999');
                });
            }

            function renderTodo(t) {
                let cls = 'todo-item';
                if (t.status === 'completed') cls += ' completed';
                else if (t.status === 'in_progress') cls += ' in-progress';
                else if (t.isOverdue) cls += ' overdue';
                else if (t.isDueToday) cls += ' due-today';

                let priorityBadge = '';
                if (t.priority === 1) priorityBadge = '<span class="priority-1">!!!</span> ';
                else if (t.priority === 2) priorityBadge = '<span class="priority-2">!!</span> ';
                else if (t.priority === 3) priorityBadge = '<span class="priority-3">!</span> ';

                const isCompleted = t.status === 'completed';
                const nb = notebooksCache.find(n => n.name === t.notebook);
                const nbColor = nb && nb.color ? nb.color : 'var(--text-dim)';

                // Build editable due date element
                let dueDateHtml;
                if (t.due) {
                    if (t.isOverdue && !isCompleted) {
                        dueDateHtml = `<span class="due-date-edit" style="color:var(--red);cursor:pointer" onclick="editDueDate('${t.id}', '${t.due}')" title="Click to edit">Overdue: ${t.due}</span>`;
                    } else {
                        dueDateHtml = `<span class="due-date-edit" style="cursor:pointer" onclick="editDueDate('${t.id}', '${t.due}')" title="Click to edit">Due: ${t.due}</span>`;
                    }
                } else {
                    dueDateHtml = `<span class="due-date-edit" style="cursor:pointer;color:var(--text-dim)" onclick="editDueDate('${t.id}', '')" title="Click to add due date">No due date</span>`;
                }

                return `
                    <div class="${cls}" data-id="${t.id}">
                        <div class="checkbox" onclick="toggleTodo('${t.id}')">${checkIcon}</div>
                        <div class="todo-body">
                            <div class="content">${priorityBadge}${escapeHtml(t.content)}</div>
                            <div class="meta">
                                ${t.status === 'in_progress' ? '<span style="color:var(--green)">In Progress</span> · ' : ''}
                                ${t.notebook ? '<span class="color-dot" style="background:' + nbColor + '"></span><span style="color:var(--accent)">' + escapeHtml(t.notebook) + '</span> · ' : ''}
                                ${dueDateHtml}
                                · <span style="font-family:monospace;color:var(--text-dim);font-size:0.75rem" title="Todo ID">${t.id}</span>
                            </div>
                        </div>
                    </div>
                `;
            }

            function renderSection(key, section) {
                if (section.todos.length === 0) return '';
                return `
                    <div class="todo-section">
                        <h3 style="color:${section.color};font-size:0.85rem;text-transform:uppercase;margin:1.5rem 0 0.75rem;letter-spacing:0.05em">
                            ${section.title} (${section.todos.length})
                        </h3>
                        ${sortTodos(section.todos).map(renderTodo).join('')}
                    </div>
                `;
            }

            const openCount = todos.filter(t => t.status !== 'completed').length;

            document.getElementById('content').innerHTML = `
                <h1>Todos</h1>
                <input type="text" class="search-box" id="todoFilterInput" placeholder="Filter: notebook:name, @name, #tag, or text..." value="${escapeHtml(todoFilter)}" style="margin-bottom:0.5rem">
                <form class="add-todo-form" onsubmit="addTodo(event)">
                    <input type="text" id="newTodoInput" placeholder="Add a new todo... (use @due(date), @priority(1-3), #tags)">
                    <button type="submit">Add</button>
                </form>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
                    <p style="color:var(--text-dim)">${openCount} open, ${todos.length} total</p>
                    <select id="todoSort" onchange="changeTodoSort(this.value)" style="padding:0.3rem 0.5rem;background:var(--surface);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:0.85rem">
                        <option value="section" ${todoSortBy === 'section' ? 'selected' : ''}>Group by Status</option>
                        <option value="notebook" ${todoSortBy === 'notebook' ? 'selected' : ''}>Sort by Notebook</option>
                        <option value="due" ${todoSortBy === 'due' ? 'selected' : ''}>Sort by Due Date</option>
                        <option value="priority" ${todoSortBy === 'priority' ? 'selected' : ''}>Sort by Priority</option>
                        <option value="created" ${todoSortBy === 'created' ? 'selected' : ''}>Sort by Created</option>
                    </select>
                </div>
                ${todoSortBy === 'section' ?
                    Object.entries(sections).map(([key, section]) => renderSection(key, section)).join('')
                    : sortTodos(todos).map(renderTodo).join('')
                }
            `;

            // Add event listener for filter input (live filtering with debounce)
            const filterInput = document.getElementById('todoFilterInput');
            if (filterInput) {
                filterInput.addEventListener('input', (e) => {
                    clearTimeout(todoFilterTimeout);
                    todoFilterTimeout = setTimeout(() => {
                        todoFilter = e.target.value;
                        loadTodos(false);
                    }, 300);
                });
                // Focus at end of input if filter has value
                if (todoFilter) {
                    filterInput.focus();
                    filterInput.setSelectionRange(filterInput.value.length, filterInput.value.length);
                }
            }
        }

        function changeTodoSort(value) {
            todoSortBy = value;
            savePreferences();
            loadTodos();
        }

        async function toggleTodo(id) {
            await api('/todos/' + id + '/toggle', { method: 'POST' });
            loadTodos();
        }

        async function addTodo(event) {
            event.preventDefault();
            const input = document.getElementById('newTodoInput');
            const content = input.value.trim();
            if (!content) return;

            await api('/todos', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: content })
            });

            input.value = '';
            loadTodos();
        }

        function editDueDate(todoId, currentDate) {
            // Find the todo item and replace the due date span with an input
            const todoItem = document.querySelector(`[data-id="${todoId}"]`);
            if (!todoItem) return;

            const dueDateSpan = todoItem.querySelector('.due-date-edit');
            if (!dueDateSpan) return;

            // Create a container with date input and clear button
            const container = document.createElement('span');
            container.className = 'due-date-editor';
            container.style.cssText = 'display:inline-flex;align-items:center;gap:0.25rem';

            const input = document.createElement('input');
            input.type = 'date';
            input.value = currentDate || '';
            input.style.cssText = 'padding:0.15rem 0.3rem;background:var(--surface);border:1px solid var(--accent);border-radius:3px;color:var(--text);font-size:0.8rem';

            const clearBtn = document.createElement('button');
            clearBtn.textContent = '✕';
            clearBtn.title = 'Clear due date';
            clearBtn.style.cssText = 'padding:0.1rem 0.3rem;background:var(--surface);border:1px solid var(--border);border-radius:3px;color:var(--text-dim);font-size:0.7rem;cursor:pointer';
            clearBtn.onclick = (e) => {
                e.stopPropagation();
                saveDueDate(todoId, '');
            };

            input.onchange = () => saveDueDate(todoId, input.value);
            input.onblur = (e) => {
                // Don't reload if clicking on clear button
                if (e.relatedTarget === clearBtn) return;
                // Small delay to allow change event to fire first
                setTimeout(() => {
                    if (document.querySelector('.due-date-editor')) {
                        loadTodos(false);
                    }
                }, 100);
            };

            container.appendChild(input);
            container.appendChild(clearBtn);
            dueDateSpan.replaceWith(container);

            // Focus the input and open the picker
            input.focus();
            try { input.showPicker(); } catch(e) { /* ignore if not supported */ }
        }

        async function saveDueDate(todoId, newDate) {
            try {
                await api('/todos/' + todoId + '/due', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ due: newDate || null })
                });
                loadTodos(false);
            } catch (err) {
                console.error('Failed to update due date:', err);
                loadTodos(false);
            }
        }

        // Kanban board state
        let kanbanBoard = null;
        let draggedTodoId = null;

        async function loadKanban(pushHistory = true) {
            currentNotebook = null;
            currentNotePath = null;
            document.getElementById('notes-section').style.display = 'none';
            if (pushHistory) history.pushState({ view: 'kanban' }, '', '#kanban');

            // Load board configuration
            const boards = await api('/kanban/boards');
            kanbanBoard = boards[0];  // Use first/default board

            // Load todos for each column in parallel
            const columnDataPromises = kanbanBoard.columns.map(async col => {
                const todos = await api('/kanban/column?filters=' + encodeURIComponent(JSON.stringify(col.filters)));
                return { ...col, todos };
            });
            const columnData = await Promise.all(columnDataPromises);

            renderKanban(columnData);
        }

        function renderKanban(columns) {
            const today = getToday();

            function renderCard(t) {
                let priorityHtml = '';
                if (t.priority === 1) priorityHtml = '<span class="priority-1">!!!</span>';
                else if (t.priority === 2) priorityHtml = '<span class="priority-2">!!</span>';
                else if (t.priority === 3) priorityHtml = '<span class="priority-3">!</span>';

                let dueHtml = '';
                if (t.due) {
                    const dueDate = t.due.split('T')[0];
                    if (dueDate < today) {
                        dueHtml = `<span class="due overdue">${dueDate}</span>`;
                    } else if (dueDate === today) {
                        dueHtml = `<span class="due today">Today</span>`;
                    } else {
                        dueHtml = `<span class="due">${dueDate}</span>`;
                    }
                }

                const notebookHtml = t.notebook ? `<span class="notebook">${escapeHtml(t.notebook)}</span>` : '';

                return `
                    <div class="kanban-card"
                         draggable="true"
                         data-id="${t.id}"
                         data-status="${t.status}"
                         ondragstart="kanbanDragStart(event)"
                         ondragend="kanbanDragEnd(event)">
                        <div class="kanban-card-content">${escapeHtml(t.content)}</div>
                        <div class="kanban-card-meta">
                            ${priorityHtml}
                            ${dueHtml}
                            ${notebookHtml}
                        </div>
                    </div>
                `;
            }

            function getColumnColor(color) {
                const colorMap = {
                    'cyan': 'var(--accent)',
                    'green': '#3fb950',
                    'yellow': '#d29922',
                    'red': '#f85149',
                    'dim': 'var(--text-dim)',
                    'white': 'var(--text)'
                };
                return colorMap[color] || color;
            }

            const columnsHtml = columns.map(col => `
                <div class="kanban-column"
                     data-filters='${JSON.stringify(col.filters)}'
                     ondragover="kanbanDragOver(event)"
                     ondragleave="kanbanDragLeave(event)"
                     ondrop="kanbanDrop(event, '${escapeJs(JSON.stringify(col.filters))}')">
                    <div class="kanban-header" style="border-color: ${getColumnColor(col.color)}">
                        <span>${escapeHtml(col.name)}</span>
                        <span class="count">${col.todos.length}</span>
                    </div>
                    <div class="kanban-items">
                        ${col.todos.map(renderCard).join('')}
                    </div>
                </div>
            `).join('');

            document.getElementById('content').innerHTML = `
                <h1>Kanban Board</h1>
                <p style="color:var(--text-dim);margin-bottom:1rem">Drag cards between columns to change status</p>
                <div class="kanban-board">
                    ${columnsHtml}
                </div>
            `;
        }

        function kanbanDragStart(event) {
            draggedTodoId = event.target.dataset.id;
            event.target.classList.add('dragging');
            event.dataTransfer.effectAllowed = 'move';
        }

        function kanbanDragEnd(event) {
            event.target.classList.remove('dragging');
        }

        function kanbanDragOver(event) {
            event.preventDefault();
            event.currentTarget.classList.add('drag-over');
        }

        function kanbanDragLeave(event) {
            event.currentTarget.classList.remove('drag-over');
        }

        async function kanbanDrop(event, filtersJson) {
            event.preventDefault();
            event.currentTarget.classList.remove('drag-over');

            if (!draggedTodoId) return;

            const filters = JSON.parse(filtersJson);

            // Determine new status from column filters
            let newStatus = filters.status;
            if (!newStatus) {
                // Try to infer from other filters
                if (filters.due_today || filters.due_this_week) {
                    newStatus = 'pending';
                } else {
                    newStatus = 'pending';
                }
            }

            try {
                await api('/todos/' + draggedTodoId + '/status', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: newStatus })
                });
            } catch (err) {
                console.error('Failed to update todo status:', err);
            }

            draggedTodoId = null;
            loadKanban(false);
        }

        let graphShowTags = true;
        let graphShowNotebooks = true;

        async function loadGraph(pushHistory = true) {
            currentNotebook = null;
            currentNotePath = null;
            document.getElementById('notes-section').style.display = 'none';
            if (pushHistory) history.pushState({ view: 'graph' }, '', '#graph');

            document.getElementById('content').innerHTML = `
                <h1>Knowledge Graph</h1>
                <div class="graph-controls">
                    <label><input type="checkbox" id="showTags" ${graphShowTags ? 'checked' : ''}> Show tags</label>
                    <label><input type="checkbox" id="showNotebooks" ${graphShowNotebooks ? 'checked' : ''}> Show notebooks</label>
                    <label>Zoom: <input type="range" id="graphZoom" min="0.1" max="3" step="0.1" value="1"></label>
                    <button class="btn" onclick="resetGraphZoom()">Reset View</button>
                </div>
                <div class="graph-container" id="graphContainer">
                    <p class="loading" style="padding:1rem">Loading graph...</p>
                </div>
            `;

            const data = await api('/graph');
            renderGraph(data);

            // Add event listeners for controls
            document.getElementById('showTags').addEventListener('change', (e) => {
                graphShowTags = e.target.checked;
                loadGraph(false);
            });
            document.getElementById('showNotebooks').addEventListener('change', (e) => {
                graphShowNotebooks = e.target.checked;
                loadGraph(false);
            });
        }

        let graphZoomBehavior = null;
        let graphSvg = null;

        function resetGraphZoom() {
            if (graphSvg && graphZoomBehavior) {
                graphSvg.transition().duration(300).call(graphZoomBehavior.transform, d3.zoomIdentity);
                document.getElementById('graphZoom').value = 1;
            }
        }

        function renderGraph(data) {
            const container = document.getElementById('graphContainer');
            container.innerHTML = '';

            // Filter nodes and edges based on controls
            let nodes = data.nodes.filter(n => {
                if (n.type === 'tag' && !graphShowTags) return false;
                if (n.type === 'notebook' && !graphShowNotebooks) return false;
                return true;
            });

            const nodeIds = new Set(nodes.map(n => n.id));
            let edges = data.edges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));

            if (nodes.length === 0) {
                container.innerHTML = '<p style="padding:1rem;color:var(--text-dim)">No nodes to display. Index your notes first.</p>';
                return;
            }

            const width = container.clientWidth;
            const height = container.clientHeight || 600;

            // Color scheme
            const colors = {
                note: '#58a6ff',      // accent blue
                tag: '#a371f7',       // purple
                notebook: '#3fb950', // green (default, will use config color)
                link: '#58a6ff',
                tagEdge: '#a371f7',
                notebookEdge: '#3fb950'
            };

            // Create SVG
            const svg = d3.select(container)
                .append('svg')
                .attr('width', width)
                .attr('height', height);

            graphSvg = svg;

            // Add zoom behavior
            const g = svg.append('g');
            graphZoomBehavior = d3.zoom()
                .scaleExtent([0.1, 4])
                .on('zoom', (event) => {
                    g.attr('transform', event.transform);
                    document.getElementById('graphZoom').value = event.transform.k;
                });
            svg.call(graphZoomBehavior);

            // Zoom slider control
            document.getElementById('graphZoom').addEventListener('input', (e) => {
                const scale = parseFloat(e.target.value);
                svg.transition().duration(100).call(graphZoomBehavior.scaleTo, scale);
            });

            // Create force simulation
            const simulation = d3.forceSimulation(nodes)
                .force('link', d3.forceLink(edges).id(d => d.id).distance(d => {
                    if (d.type === 'link') return 80;
                    if (d.type === 'tag') return 60;
                    return 100;
                }))
                .force('charge', d3.forceManyBody().strength(d => {
                    if (d.type === 'notebook') return -300;
                    if (d.type === 'tag') return -100;
                    return -150;
                }))
                .force('center', d3.forceCenter(width / 2, height / 2))
                .force('collision', d3.forceCollide().radius(d => getNodeRadius(d) + 5));

            // Draw edges
            const link = g.append('g')
                .selectAll('line')
                .data(edges)
                .join('line')
                .attr('class', 'graph-link')
                .attr('stroke', d => {
                    if (d.type === 'link') return colors.link;
                    if (d.type === 'tag') return colors.tagEdge;
                    return colors.notebookEdge;
                })
                .attr('stroke-dasharray', d => {
                    if (d.type === 'tag') return '3,3';
                    if (d.type === 'notebook') return '5,5';
                    return null;
                })
                .attr('stroke-width', d => d.type === 'link' ? 1.5 : 1);

            // Draw nodes
            const node = g.append('g')
                .selectAll('g')
                .data(nodes)
                .join('g')
                .attr('class', 'graph-node')
                .call(d3.drag()
                    .on('start', dragstarted)
                    .on('drag', dragged)
                    .on('end', dragended));

            // Node circles
            node.append('circle')
                .attr('r', d => getNodeRadius(d))
                .attr('fill', d => {
                    if (d.type === 'notebook') return d.color || colors.notebook;
                    if (d.type === 'tag') return colors.tag;
                    // For notes, use notebook color if available
                    const nb = notebooksCache.find(n => n.name === d.notebook);
                    return nb && nb.color ? nb.color : colors.note;
                })
                .attr('opacity', d => d.type === 'note' ? 0.9 : 0.7);

            // Node labels
            node.append('text')
                .attr('dx', d => getNodeRadius(d) + 4)
                .attr('dy', 4)
                .text(d => d.title.length > 25 ? d.title.substring(0, 25) + '...' : d.title)
                .attr('font-size', d => d.type === 'notebook' ? '12px' : '10px')
                .attr('font-weight', d => d.type === 'notebook' ? 'bold' : 'normal');

            // Click handler for notes
            node.on('click', (event, d) => {
                if (d.type === 'note') {
                    loadNote(d.id);
                } else if (d.type === 'notebook') {
                    loadNotebook(d.title);
                }
                // Tags don't navigate anywhere
            });

            // Tooltip on hover
            node.append('title')
                .text(d => {
                    if (d.type === 'note') return `${d.title}\n(${d.notebook})`;
                    if (d.type === 'tag') return `Tag: ${d.title}`;
                    return `Notebook: ${d.title}`;
                });

            function getNodeRadius(d) {
                if (d.type === 'notebook') return 12;
                if (d.type === 'tag') return 6;
                return 8;
            }

            // Update positions on tick
            simulation.on('tick', () => {
                link
                    .attr('x1', d => d.source.x)
                    .attr('y1', d => d.source.y)
                    .attr('x2', d => d.target.x)
                    .attr('y2', d => d.target.y);

                node.attr('transform', d => `translate(${d.x},${d.y})`);
            });

            // Drag functions
            function dragstarted(event) {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                event.subject.fx = event.subject.x;
                event.subject.fy = event.subject.y;
            }

            function dragged(event) {
                event.subject.fx = event.x;
                event.subject.fy = event.y;
            }

            function dragended(event) {
                if (!event.active) simulation.alphaTarget(0);
                event.subject.fx = null;
                event.subject.fy = null;
            }
        }

        async function loadHistory(pushHistory = true) {
            currentNotebook = null;
            currentNotePath = null;
            document.getElementById('notes-section').style.display = 'none';
            if (pushHistory) history.pushState({ view: 'history' }, '', '#history');

            const historyData = await api('/history?type=' + historySortBy + '&limit=100');

            // Format timestamp for display
            function formatTimestamp(isoStr) {
                const d = new Date(isoStr);
                const now = new Date();
                const diffMs = now - d;
                const diffMins = Math.floor(diffMs / 60000);
                const diffHours = Math.floor(diffMs / 3600000);
                const diffDays = Math.floor(diffMs / 86400000);

                if (diffMins < 1) return 'just now';
                if (diffMins < 60) return diffMins + ' min ago';
                if (diffHours < 24) return diffHours + ' hour' + (diffHours > 1 ? 's' : '') + ' ago';
                if (diffDays < 7) return diffDays + ' day' + (diffDays > 1 ? 's' : '') + ' ago';
                return d.toLocaleDateString();
            }

            document.getElementById('content').innerHTML = `
                <h1>History</h1>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
                    <p style="color:var(--text-dim)">${historyData.length} entries</p>
                    <select id="historySort" style="padding:0.3rem 0.5rem;background:var(--surface);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:0.85rem">
                        <option value="viewed" ${historySortBy === 'viewed' ? 'selected' : ''}>Recently Viewed</option>
                        <option value="modified" ${historySortBy === 'modified' ? 'selected' : ''}>Recently Modified</option>
                    </select>
                </div>
                <div class="search-results">
                    ${historyData.length === 0 ? '<p style="color:var(--text-dim)">No history yet. View some notes to build your history.</p>' : ''}
                    ${historyData.map(h => {
                        const nb = notebooksCache.find(n => n.name === h.notebook);
                        const nbColor = nb && nb.color ? nb.color : 'var(--text-dim)';
                        return `
                            <div class="search-result" onclick="loadNote('${escapeJs(h.path)}')">
                                <h4>${escapeHtml(h.title || h.path.split('/').pop().replace('.md', ''))}</h4>
                                <div class="snippet">
                                    ${h.notebook ? '<span class="color-dot" style="background:' + nbColor + '"></span><span style="color:var(--accent)">' + escapeHtml(h.notebook) + '</span> · ' : ''}
                                    <span style="color:var(--text-dim)">${formatTimestamp(h.timestamp)}</span>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            `;

            // Add event listener for sort change
            const sortSelect = document.getElementById('historySort');
            if (sortSelect) {
                sortSelect.addEventListener('change', (e) => {
                    historySortBy = e.target.value;
                    savePreferences();
                    loadHistory(false);
                });
            }
        }

        async function doSearch(query) {
            if (!query.trim()) {
                loadHome();
                return;
            }

            // Build search URL with optional notebook filter
            let searchUrl = '/search?q=' + encodeURIComponent(query);
            if (currentNotebook) {
                searchUrl += '&notebook=' + encodeURIComponent(currentNotebook);
            }

            const results = await api(searchUrl);
            document.getElementById('notes-section').style.display = 'none';

            // Show scoped search indicator
            const scopeIndicator = currentNotebook
                ? `<p style="color:var(--accent);margin-bottom:0.5rem">Searching in: ${escapeHtml(currentNotebook)}</p>`
                : '';

            document.getElementById('content').innerHTML = `
                <h1>Search: ${escapeHtml(query)}</h1>
                ${scopeIndicator}
                <p style="color:var(--text-dim);margin-bottom:1rem">${results.length} results</p>
                <div class="search-results">
                    ${results.map(r => `
                        <div class="search-result" onclick="loadNote('${escapeJs(r.path)}')">
                            <h4>${escapeHtml(r.title || r.path)}</h4>
                            <div class="snippet">${escapeHtml(r.snippet)}</div>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        // Search input handler
        document.getElementById('searchInput').addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => doSearch(e.target.value), 300);
        });

        document.getElementById('searchInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                clearTimeout(searchTimeout);
                doSearch(e.target.value);
            }
        });

        // Handle browser back/forward
        window.addEventListener('popstate', (e) => {
            const state = e.state;
            if (!state || state.view === 'home') loadHome(false);
            else if (state.view === 'notebook') loadNotebook(state.name, false);
            else if (state.view === 'note') loadNote(state.path, false);
            else if (state.view === 'todos') loadTodos(false);
            else if (state.view === 'kanban') loadKanban(false);
            else if (state.view === 'graph') loadGraph(false);
            else if (state.view === 'history') loadHistory(false);
        });

        // Init - set initial state and load based on hash
        loadNotebooks();
        const hash = location.hash;
        if (hash.startsWith('#notebook/')) {
            const name = decodeURIComponent(hash.slice(10));
            history.replaceState({ view: 'notebook', name }, '', hash);
            loadNotebook(name, false);
        } else if (hash.startsWith('#note/')) {
            const path = decodeURIComponent(hash.slice(6));
            history.replaceState({ view: 'note', path }, '', hash);
            loadNote(path, false);
        } else if (hash === '#todos') {
            history.replaceState({ view: 'todos' }, '', hash);
            loadTodos(false);
        } else if (hash === '#kanban') {
            history.replaceState({ view: 'kanban' }, '', hash);
            loadKanban(false);
        } else if (hash === '#graph') {
            history.replaceState({ view: 'graph' }, '', hash);
            loadGraph(false);
        } else if (hash === '#history') {
            history.replaceState({ view: 'history' }, '', hash);
            loadHistory(false);
        } else {
            history.replaceState({ view: 'home' }, '', '#');
            loadHome(false);
        }
    </script>
</body>
</html>
"""


class NBHandler(http.server.BaseHTTPRequestHandler):
    """Request handler for nb web viewer."""

    def log_message(self, format: str, *args: object) -> None:
        pass  # Suppress default logging

    def send_json(self, data: object, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def send_html(self, html: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def read_body(self) -> dict:
        """Read JSON body from request."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        return json.loads(body) if body else {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        config = get_config()

        # Serve main page
        if path == "/" or path == "/index.html":
            self.send_html(TEMPLATE)
            return

        # API: List notebooks
        if path == "/api/notebooks":
            from nb.index.db import get_db

            db = get_db()
            nbs = []

            # Get notebook stats from database
            notebook_stats = {}
            # Get max mtime per notebook
            mtime_rows = db.fetchall(
                """SELECT notebook, MAX(mtime) as last_modified
                   FROM notes WHERE notebook IS NOT NULL
                   GROUP BY notebook"""
            )
            for row in mtime_rows:
                if row["notebook"]:
                    notebook_stats[row["notebook"]] = {
                        "last_modified": row["last_modified"],
                        "last_viewed": None,
                    }

            # Get max viewed_at per notebook
            view_rows = db.fetchall(
                """SELECT n.notebook, MAX(nv.viewed_at) as last_viewed
                   FROM note_views nv
                   JOIN notes n ON nv.note_path = n.path
                   WHERE n.notebook IS NOT NULL
                   GROUP BY n.notebook"""
            )
            for row in view_rows:
                if row["notebook"]:
                    if row["notebook"] in notebook_stats:
                        notebook_stats[row["notebook"]]["last_viewed"] = row[
                            "last_viewed"
                        ]
                    else:
                        notebook_stats[row["notebook"]] = {
                            "last_modified": None,
                            "last_viewed": row["last_viewed"],
                        }

            # Regular notebooks
            for name in list_notebooks(config.notes_root):
                notes_with_linked = get_notebook_notes_with_linked(
                    name, config.notes_root
                )
                nb_config = config.get_notebook(name)
                color = get_color_hex(nb_config.color) if nb_config else None
                stats = notebook_stats.get(name, {})
                nbs.append(
                    {
                        "name": name,
                        "count": len(notes_with_linked),
                        "color": color,
                        "isLinked": False,
                        "lastModified": stats.get("last_modified"),
                        "lastViewed": stats.get("last_viewed"),
                    }
                )

            # Virtual notebooks from linked notes
            linked_notes = list_linked_notes()
            seen_notebooks = {nb["name"] for nb in nbs}
            for linked in linked_notes:
                virtual_nb = linked.notebook or f"@{linked.alias}"
                if virtual_nb not in seen_notebooks:
                    files = scan_linked_note_files(linked)
                    stats = notebook_stats.get(virtual_nb, {})
                    nbs.append(
                        {
                            "name": virtual_nb,
                            "count": len(files),
                            "color": "#39c5cf",  # Cyan for linked notebooks
                            "isLinked": True,
                            "alias": linked.alias,
                            "lastModified": stats.get("last_modified"),
                            "lastViewed": stats.get("last_viewed"),
                        }
                    )
                    seen_notebooks.add(virtual_nb)

            self.send_json(nbs)
            return

        # API: List notes in notebook
        if path.startswith("/api/notebooks/"):
            from urllib.parse import unquote

            notebook = unquote(path.split("/")[-1])
            result = []

            # Check if it's a virtual linked notebook
            is_virtual_linked = notebook.startswith("@")
            linked_config = None

            if is_virtual_linked:
                # Find the linked note config for this virtual notebook
                for linked in list_linked_notes():
                    virtual_nb = linked.notebook or f"@{linked.alias}"
                    if virtual_nb == notebook:
                        linked_config = linked
                        break

            if linked_config:
                # List files from linked note - query database for indexed data
                from nb.index.db import get_db

                db = get_db()

                # Query notes for this virtual notebook from the database
                note_rows = db.fetchall(
                    """SELECT path, title, date, source_alias, mtime
                       FROM notes WHERE notebook = ? AND external = 1
                       ORDER BY COALESCE(date, '') DESC, mtime DESC""",
                    (notebook,),
                )

                # Get lastViewed for all notes
                # Note: note_views stores paths with OS separators, notes table uses forward slashes
                from nb.utils.hashing import normalize_path

                view_rows = db.fetchall(
                    """SELECT note_path, MAX(viewed_at) as last_viewed
                       FROM note_views
                       GROUP BY note_path""",
                )
                # Normalize paths to forward slashes for lookup
                last_viewed_map = {
                    normalize_path(row["note_path"]): row["last_viewed"]
                    for row in view_rows
                }

                if note_rows:
                    for row in note_rows:
                        note_path = Path(row["path"])
                        path_str = str(note_path).replace("\\", "/")

                        # Get tags for this note from database
                        tag_rows = db.fetchall(
                            "SELECT tag FROM note_tags WHERE note_path = ?",
                            (row["path"],),
                        )
                        tags = [t["tag"] for t in tag_rows]

                        note_alias = (
                            get_alias_for_path(note_path) or row["source_alias"]
                        )

                        result.append(
                            {
                                "path": path_str,
                                "title": row["title"] or note_path.stem,
                                "filename": note_path.name,
                                "date": row["date"],  # Already in YYYY-MM-DD format
                                "mtime": row["mtime"],  # Unix timestamp
                                "lastViewed": last_viewed_map.get(row["path"]),
                                "tags": tags,
                                "alias": note_alias,
                                "isLinked": True,
                                "sections": get_sections_for_path(note_path),
                            }
                        )
                else:
                    # Fall back to file-based scan
                    files = scan_linked_note_files(linked_config)
                    for file_path in sorted(files, reverse=True):
                        note = get_note(file_path, config.notes_root)
                        path_str = str(file_path).replace("\\", "/")
                        note_alias = get_alias_for_path(file_path)
                        # Get mtime from file stat
                        try:
                            file_mtime = file_path.stat().st_mtime
                        except OSError:
                            file_mtime = None
                        result.append(
                            {
                                "path": path_str,
                                "title": note.title if note else file_path.stem,
                                "filename": file_path.name,
                                "date": (
                                    note.date.strftime("%Y-%m-%d")
                                    if note and note.date
                                    else None
                                ),
                                "mtime": file_mtime,
                                "lastViewed": last_viewed_map.get(path_str),
                                "tags": note.tags if note else [],
                                "alias": note_alias,
                                "isLinked": True,
                                "sections": get_sections_for_path(file_path),
                            }
                        )
            else:
                # Regular notebook - query database for notes with metadata
                from nb.index.db import get_db

                db = get_db()

                # Query notes with their dates from the database
                note_rows = db.fetchall(
                    """SELECT path, title, date, external, source_alias, mtime
                       FROM notes WHERE notebook = ?
                       ORDER BY COALESCE(date, '') DESC, mtime DESC""",
                    (notebook,),
                )

                # Get lastViewed for all notes in this notebook
                # Note: note_views stores paths with OS separators, notes table uses forward slashes
                from nb.utils.hashing import normalize_path

                view_rows = db.fetchall(
                    """SELECT note_path, MAX(viewed_at) as last_viewed
                       FROM note_views
                       GROUP BY note_path""",
                )
                # Normalize paths to forward slashes for lookup
                last_viewed_map = {
                    normalize_path(row["note_path"]): row["last_viewed"]
                    for row in view_rows
                }

                if note_rows:
                    # Use database results (faster, includes indexed dates)
                    for row in note_rows:
                        note_path = Path(row["path"])
                        is_external = bool(row["external"])

                        if is_external or note_path.is_absolute():
                            # Linked/external note - use absolute path
                            full_path = (
                                note_path
                                if note_path.is_absolute()
                                else config.notes_root / note_path
                            )
                            path_str = str(full_path).replace("\\", "/")
                        else:
                            path_str = str(note_path).replace("\\", "/")

                        # Get tags for this note from database
                        tag_rows = db.fetchall(
                            "SELECT tag FROM note_tags WHERE note_path = ?",
                            (row["path"],),
                        )
                        tags = [t["tag"] for t in tag_rows]

                        # Get alias
                        check_path = (
                            note_path
                            if note_path.is_absolute()
                            else config.notes_root / note_path
                        )
                        note_alias = (
                            get_alias_for_path(check_path) or row["source_alias"]
                        )

                        result.append(
                            {
                                "path": path_str,
                                "title": row["title"] or note_path.stem,
                                "filename": note_path.name,
                                "date": row["date"],  # Already in YYYY-MM-DD format
                                "mtime": row["mtime"],  # Unix timestamp
                                "lastViewed": last_viewed_map.get(row["path"]),
                                "tags": tags,
                                "alias": note_alias,
                                "isLinked": is_external,
                                "sections": get_sections_for_path(note_path),
                            }
                        )
                else:
                    # Fall back to file-based scan (for un-indexed notes)
                    notes_with_linked = get_notebook_notes_with_linked(
                        notebook, config.notes_root
                    )
                    for note_path, is_linked, linked_alias in sorted(
                        notes_with_linked, reverse=True
                    ):
                        if is_linked:
                            full_path = (
                                note_path
                                if note_path.is_absolute()
                                else config.notes_root / note_path
                            )
                            note = get_note(full_path, config.notes_root)
                            path_str = str(full_path).replace("\\", "/")
                        else:
                            full_path = config.notes_root / note_path
                            note = get_note(note_path, config.notes_root)
                            path_str = str(note_path).replace("\\", "/")

                        check_path = (
                            note_path
                            if note_path.is_absolute()
                            else config.notes_root / note_path
                        )
                        note_alias = get_alias_for_path(check_path) or linked_alias

                        # Get mtime from file stat
                        try:
                            file_mtime = full_path.stat().st_mtime
                        except OSError:
                            file_mtime = None

                        result.append(
                            {
                                "path": path_str,
                                "title": note.title if note else note_path.stem,
                                "filename": note_path.name,
                                "date": (
                                    note.date.strftime("%Y-%m-%d")
                                    if note and note.date
                                    else None
                                ),
                                "mtime": file_mtime,
                                "lastViewed": last_viewed_map.get(
                                    str(note_path).replace("\\", "/")
                                ),
                                "tags": note.tags if note else [],
                                "alias": note_alias,
                                "isLinked": is_linked,
                                "sections": get_sections_for_path(note_path),
                            }
                        )

            self.send_json(result)
            return

        # API: Get note content
        if path == "/api/note":
            note_path_str = query.get("path", [None])[0]
            if not note_path_str:
                self.send_json({"error": "Missing path"})
                return

            # Validate path to prevent path traversal attacks
            note_full_path = _safe_note_path(config.notes_root, note_path_str)
            if not note_full_path:
                self.send_json({"error": "Invalid path"}, 400)
                return

            if not note_full_path.exists():
                self.send_json({"error": "Not found"})
                return

            content = note_full_path.read_text(encoding="utf-8")
            note = get_note(note_full_path, config.notes_root)
            note_alias = get_alias_for_path(note_full_path)

            # Parse frontmatter for display
            from datetime import date, datetime

            from nb.utils.markdown import parse_note_file

            def serialize_frontmatter(fm: dict) -> dict:
                """Convert frontmatter values to JSON-serializable types."""
                result: dict = {}
                for key, val in fm.items():
                    if isinstance(val, (date, datetime)):
                        result[key] = val.isoformat()
                    elif isinstance(val, list):
                        result[key] = [
                            v.isoformat() if isinstance(v, (date, datetime)) else v
                            for v in val
                        ]
                    else:
                        result[key] = val
                return result

            try:
                frontmatter_dict, _ = parse_note_file(note_full_path)
                frontmatter_dict = serialize_frontmatter(frontmatter_dict)
            except Exception:
                frontmatter_dict = {}

            # Record the view for history tracking
            from nb.core.notes import record_note_view

            record_note_view(note_full_path, config.notes_root)

            self.send_json(
                {
                    "content": content,
                    "title": note.title if note else note_full_path.stem,
                    "path": note_path_str,
                    "alias": note_alias,
                    "frontmatter": frontmatter_dict,
                }
            )
            return

        # API: Resolve link target to note path
        if path == "/api/resolve-link":
            from nb.core.note_links import _find_similar_note, resolve_link_target

            target = query.get("target", [None])[0]
            source = query.get("source", [None])[0]

            if not target:
                self.send_json({"error": "Missing target"}, 400)
                return

            # Determine source path for relative link resolution
            source_path = None
            if source:
                source_path = Path(source)
                if not source_path.is_absolute():
                    source_path = config.notes_root / source_path

            resolved = resolve_link_target(
                target,
                source_path or config.notes_root,
                config.notes_root,
            )

            if resolved and resolved.exists():
                # Return the path relative to notes_root or absolute for external
                try:
                    rel_path = resolved.relative_to(config.notes_root)
                    self.send_json({"path": str(rel_path).replace("\\", "/")})
                except ValueError:
                    # External path - return absolute
                    self.send_json({"path": str(resolved).replace("\\", "/")})
            else:
                # Not found - try to suggest a similar note
                suggestion = _find_similar_note(target, config.notes_root)
                self.send_json({"path": None, "suggestion": suggestion})
            return

        # API: Get graph data for visualization
        if path == "/api/graph":
            from nb.index.db import get_db

            db = get_db()

            nodes = []
            edges = []
            node_ids = set()

            # Get all notes as nodes
            note_rows = db.fetchall(
                "SELECT path, title, notebook FROM notes WHERE external = 0"
            )

            for row in note_rows:
                path_str = row["path"].replace("\\", "/")
                node_ids.add(path_str)
                nodes.append(
                    {
                        "id": path_str,
                        "title": row["title"] or Path(row["path"]).stem,
                        "type": "note",
                        "notebook": row["notebook"],
                    }
                )

            # Get all notebooks as nodes
            notebook_rows = db.fetchall(
                "SELECT DISTINCT notebook FROM notes WHERE external = 0 AND notebook IS NOT NULL"
            )
            notebook_ids = set()
            nb_config_map = {}
            for row in notebook_rows:
                nb_name = row["notebook"]
                if nb_name and nb_name not in notebook_ids:
                    notebook_ids.add(nb_name)
                    nb_id = f"notebook:{nb_name}"
                    nb_conf = config.get_notebook(nb_name)
                    color = get_color_hex(nb_conf.color) if nb_conf else None
                    nb_config_map[nb_name] = color
                    nodes.append(
                        {
                            "id": nb_id,
                            "title": nb_name,
                            "type": "notebook",
                            "color": color,
                        }
                    )

            # Get all tags as nodes
            tag_rows = db.fetchall("SELECT DISTINCT tag FROM note_tags")
            tag_ids = set()
            for row in tag_rows:
                tag = row["tag"]
                if tag and tag not in tag_ids:
                    tag_ids.add(tag)
                    nodes.append(
                        {
                            "id": f"tag:{tag}",
                            "title": f"#{tag}",
                            "type": "tag",
                        }
                    )

            # Add note → notebook edges
            for row in note_rows:
                path_str = row["path"].replace("\\", "/")
                nb_name = row["notebook"]
                if nb_name:
                    edges.append(
                        {
                            "source": path_str,
                            "target": f"notebook:{nb_name}",
                            "type": "notebook",
                        }
                    )

            # Add note → tag edges
            note_tag_rows = db.fetchall("SELECT note_path, tag FROM note_tags")
            for row in note_tag_rows:
                path_str = row["note_path"].replace("\\", "/")
                if path_str in node_ids:
                    edges.append(
                        {
                            "source": path_str,
                            "target": f"tag:{row['tag']}",
                            "type": "tag",
                        }
                    )

            # Add note → note edges (from links)
            link_rows = db.fetchall(
                """SELECT source_path, target_path FROM note_links
                   WHERE is_external = 0"""
            )

            for row in link_rows:
                source = row["source_path"].replace("\\", "/")
                target = row["target_path"].replace("\\", "/")

                # Resolve target to actual path if it's a partial reference
                if target not in node_ids:
                    # Try to find matching node
                    target_stem = Path(target).stem
                    for node_id in node_ids:
                        if Path(node_id).stem == target_stem:
                            target = node_id
                            break

                if source in node_ids and target in node_ids:
                    edges.append(
                        {
                            "source": source,
                            "target": target,
                            "type": "link",
                        }
                    )

            self.send_json({"nodes": nodes, "edges": edges})
            return

        # API: Get backlinks for a note
        if path == "/api/backlinks":
            from nb.core.note_links import get_backlinks

            note_path_str = query.get("path", [None])[0]
            if not note_path_str:
                self.send_json({"error": "Missing path"}, 400)
                return

            # Resolve to full path
            backlinks_path = _safe_note_path(config.notes_root, note_path_str)
            if not backlinks_path or not backlinks_path.exists():
                self.send_json([])
                return

            backlinks = get_backlinks(backlinks_path)
            self.send_json(
                [
                    {
                        "source_path": str(b.source_path).replace("\\", "/"),
                        "display_text": b.display_text,
                        "link_type": b.link_type,
                        "line_number": b.line_number,
                    }
                    for b in backlinks
                ]
            )
            return

        # API: Search
        if path == "/api/search":
            q = query.get("q", [""])[0]
            notebook_param = query.get("notebook", [None])[0]
            if q:
                from nb.index.search import get_search

                # Apply notebook filter if specified
                filters: dict | None = (
                    {"notebook": notebook_param} if notebook_param else None
                )
                results = get_search().search(q, k=20, filters=filters)
                self.send_json(
                    [
                        {
                            "path": r.path.replace("\\", "/"),
                            "title": r.title,
                            "snippet": r.snippet,
                        }
                        for r in results
                    ]
                )
            else:
                self.send_json([])
            return

        # API: Todos
        if path == "/api/todos":
            from datetime import date as date_type

            from nb.index.todos_repo import get_sorted_todos

            # Use the module-level flag for showing completed
            todos = get_sorted_todos(completed=None if _show_completed else False)
            today = date_type.today()

            self.send_json(
                [
                    {
                        "id": t.id,
                        "content": t.content,
                        "due": t.due_date.isoformat() if t.due_date else None,
                        "priority": t.priority.value if t.priority else None,
                        "status": t.status.value,
                        "notebook": t.notebook or "unknown",
                        "tags": t.tags or [],
                        "created": (
                            t.created_date.isoformat() if t.created_date else None
                        ),
                        # Use due_date_only for date comparisons (due_date may be datetime)
                        "isOverdue": t.due_date_only is not None
                        and t.due_date_only < today
                        and t.status.value != "completed",
                        "isDueToday": t.due_date_only == today,
                        "isDueThisWeek": t.due_date_only is not None
                        and today
                        < t.due_date_only
                        <= today + __import__("datetime").timedelta(days=7),
                    }
                    for t in todos[:100]
                ]
            )
            return

        # API: Kanban - get board configurations
        if path == "/api/kanban/boards":
            from nb.config import DEFAULT_KANBAN_COLUMNS

            boards = []
            for b in config.kanban_boards:
                boards.append(
                    {
                        "name": b.name,
                        "columns": [
                            {"name": c.name, "filters": c.filters, "color": c.color}
                            for c in b.columns
                        ],
                    }
                )

            # Add default board if none configured
            if not boards:
                boards.append(
                    {
                        "name": "default",
                        "columns": [
                            {"name": c.name, "filters": c.filters, "color": c.color}
                            for c in DEFAULT_KANBAN_COLUMNS
                        ],
                    }
                )

            self.send_json(boards)
            return

        # API: Kanban - get todos for a column
        if path == "/api/kanban/column":
            import json
            from datetime import date as date_type
            from datetime import timedelta

            from nb.index.todos_repo import query_todos
            from nb.models import TodoStatus

            filters_json = query.get("filters", ["{}"])[0]
            notebook_filter = query.get("notebook", [None])[0]

            try:
                filters = json.loads(filters_json)
            except json.JSONDecodeError:
                filters = {}

            today = date_type.today()

            # Map filter keys to query_todos parameters
            kwargs: dict = {
                "parent_only": True,
                "exclude_note_excluded": True,
            }

            if notebook_filter:
                kwargs["notebooks"] = [notebook_filter]

            # Handle status filter
            status_val = filters.get("status")
            if status_val:
                kwargs["status"] = TodoStatus(status_val)
            else:
                kwargs["completed"] = False

            # Handle due date filters
            if filters.get("due_today"):
                kwargs["due_start"] = today
                kwargs["due_end"] = today

            if filters.get("due_this_week"):
                kwargs["due_start"] = today
                kwargs["due_end"] = today + timedelta(days=7)

            if filters.get("overdue"):
                kwargs["overdue"] = True

            if filters.get("priority"):
                kwargs["priority"] = filters["priority"]

            if filters.get("tags") and len(filters["tags"]) > 0:
                kwargs["tag"] = filters["tags"][0]

            todos = query_todos(**kwargs)

            # Post-filter for no_due_date
            if filters.get("no_due_date"):
                todos = [t for t in todos if t.due_date is None]

            self.send_json(
                [
                    {
                        "id": t.id,
                        "content": t.content,
                        "status": t.status.value,
                        "due": t.due_date.isoformat() if t.due_date else None,
                        "priority": t.priority.value if t.priority else None,
                        "notebook": t.notebook,
                        "tags": t.tags,
                    }
                    for t in todos[:50]
                ]
            )
            return

        # API: History - recently viewed and modified notes
        if path == "/api/history":
            from nb.core.notes import (
                get_recently_modified_notes,
                get_recently_viewed_notes,
            )

            limit = int(query.get("limit", [50])[0])
            history_type = query.get("type", ["viewed"])[0]  # 'viewed' or 'modified'

            result = []

            if history_type == "modified":
                # Get recently modified notes
                notes = get_recently_modified_notes(limit=limit)
                for note_path, mtime in notes:
                    try:
                        rel_path = note_path.relative_to(config.notes_root)
                        path_str = str(rel_path).replace("\\", "/")
                    except ValueError:
                        # External path
                        path_str = str(note_path).replace("\\", "/")

                    # Get note metadata from database
                    from nb.index.db import get_db

                    db = get_db()
                    mod_row = db.fetchone(
                        "SELECT title, notebook FROM notes WHERE path = ?",
                        (path_str,),
                    )

                    result.append(
                        {
                            "path": path_str,
                            "title": mod_row["title"] if mod_row else note_path.stem,
                            "notebook": mod_row["notebook"] if mod_row else None,
                            "timestamp": mtime.isoformat(),
                            "type": "modified",
                        }
                    )
            else:
                # Get recently viewed notes
                views = get_recently_viewed_notes(limit=limit)
                for note_path, viewed_at in views:
                    try:
                        rel_path = note_path.relative_to(config.notes_root)
                        path_str = str(rel_path).replace("\\", "/")
                    except ValueError:
                        # External path
                        path_str = str(note_path).replace("\\", "/")

                    # Get note metadata from database
                    from nb.index.db import get_db

                    db = get_db()
                    view_row = db.fetchone(
                        "SELECT title, notebook FROM notes WHERE path = ?",
                        (path_str,),
                    )

                    result.append(
                        {
                            "path": path_str,
                            "title": view_row["title"] if view_row else note_path.stem,
                            "notebook": view_row["notebook"] if view_row else None,
                            "timestamp": viewed_at.isoformat(),
                            "type": "viewed",
                        }
                    )

            self.send_json(result)
            return

        # 404
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        config = get_config()

        # API: Toggle todo completion
        if path.startswith("/api/todos/") and path.endswith("/toggle"):
            todo_id = path.split("/")[-2]

            from nb.core.todos import toggle_todo_in_file
            from nb.index.todos_repo import get_todo_by_id, update_todo_status

            todo = get_todo_by_id(todo_id)
            if not todo:
                self.send_json({"error": "Todo not found"}, 404)
                return

            # Get absolute path for the todo's source file
            source_path = todo.source.path
            if not source_path.is_absolute():
                source_path = config.notes_root / source_path

            try:
                actual_line = toggle_todo_in_file(
                    source_path, todo.line_number, expected_content=todo.content
                )
                if actual_line is None:
                    self.send_json(
                        {"error": "Todo not found at expected location"}, 404
                    )
                    return
                # Update the database
                from nb.models import TodoStatus

                new_status = (
                    TodoStatus.COMPLETED if not todo.completed else TodoStatus.PENDING
                )
                update_todo_status(todo_id, new_status)
                self.send_json({"success": True})
            except PermissionError as e:
                self.send_json({"error": str(e)}, 403)
            return

        # API: Set todo status directly (for kanban drag-and-drop)
        if path.startswith("/api/todos/") and path.endswith("/status"):
            todo_id = path.split("/")[-2]
            body = self.read_body()
            new_status_str = body.get("status")  # "pending", "in_progress", "completed"

            if not new_status_str:
                self.send_json({"error": "Status required"}, 400)
                return

            from nb.core.todos import set_todo_status_in_file
            from nb.index.todos_repo import get_todo_by_id, update_todo_status
            from nb.models import TodoStatus

            try:
                new_status = TodoStatus(new_status_str)
            except ValueError:
                self.send_json({"error": f"Invalid status: {new_status_str}"}, 400)
                return

            todo = get_todo_by_id(todo_id)
            if not todo:
                self.send_json({"error": "Todo not found"}, 404)
                return

            # Get absolute path for the todo's source file
            source_path = todo.source.path
            if not source_path.is_absolute():
                source_path = config.notes_root / source_path

            try:
                actual_line = set_todo_status_in_file(
                    source_path,
                    todo.line_number,
                    new_status,
                    expected_content=todo.content,
                )
                if actual_line is None:
                    self.send_json(
                        {"error": "Todo not found at expected location"}, 404
                    )
                    return
                # Update the database
                update_todo_status(todo_id, new_status)
                self.send_json({"success": True, "status": new_status.value})
            except PermissionError as e:
                self.send_json({"error": str(e)}, 403)
            return

        # API: Update todo due date
        if path.startswith("/api/todos/") and path.endswith("/due"):
            todo_id = path.split("/")[-2]
            body = self.read_body()
            new_date_str = body.get("due")  # ISO date string or null/empty

            from nb.core.todos import remove_todo_due_date, update_todo_due_date
            from nb.index.todos_repo import get_todo_by_id, update_todo_due_date_db

            todo = get_todo_by_id(todo_id)
            if not todo:
                self.send_json({"error": "Todo not found"}, 404)
                return

            # Get absolute path for the todo's source file
            source_path = todo.source.path
            if not source_path.is_absolute():
                source_path = config.notes_root / source_path

            try:
                if new_date_str:
                    # Parse the date string (ISO format: YYYY-MM-DD)
                    from datetime import date as date_type

                    new_date = date_type.fromisoformat(new_date_str)
                    actual_line = update_todo_due_date(
                        source_path,
                        todo.line_number,
                        new_date,
                        expected_content=todo.content,
                    )
                    if actual_line is None:
                        self.send_json(
                            {"error": "Todo not found at expected location"}, 404
                        )
                        return
                    # Update the database
                    update_todo_due_date_db(todo_id, new_date)
                else:
                    # Remove due date
                    actual_line = remove_todo_due_date(
                        source_path,
                        todo.line_number,
                        expected_content=todo.content,
                    )
                    if actual_line is None:
                        self.send_json(
                            {"error": "Todo not found at expected location"}, 404
                        )
                        return
                    # Update the database
                    update_todo_due_date_db(todo_id, None)

                self.send_json({"success": True})
            except PermissionError as e:
                self.send_json({"error": str(e)}, 403)
            except ValueError as e:
                self.send_json({"error": f"Invalid date: {e}"}, 400)
            return

        # API: Create todo
        if path == "/api/todos":
            body = self.read_body()
            content = body.get("content", "").strip()
            if not content:
                self.send_json({"error": "Content required"}, 400)
                return

            from nb.core.todos import add_todo_to_inbox

            add_todo_to_inbox(content)
            self.send_json({"success": True})
            return

        # API: Create/update note
        if path == "/api/note":
            body = self.read_body()
            note_path = body.get("path", "")
            content = body.get("content", "")
            is_create = body.get("create", False)

            if not note_path:
                self.send_json({"error": "Path required"}, 400)
                return

            # For write operations, only allow relative paths within notes_root
            # (don't allow writing to absolute paths or path traversal)
            if Path(note_path).is_absolute():
                self.send_json({"error": "Cannot write to absolute paths"}, 400)
                return

            full_path = _safe_note_path(config.notes_root, note_path)
            if not full_path:
                self.send_json({"error": "Invalid path"}, 400)
                return

            if is_create and full_path.exists():
                self.send_json({"error": "File already exists"}, 400)
                return

            # Ensure parent directory exists
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")

            # Reindex the note in a separate thread (can be slow for large files)
            import threading

            def reindex_note():
                try:
                    from nb.index.scanner import index_note

                    index_note(full_path, config.notes_root, index_vectors=True)
                except Exception:
                    pass  # Save succeeded, don't fail if indexing fails

            threading.Thread(target=reindex_note, daemon=True).start()

            self.send_json({"success": True, "path": note_path})
            return

        # 404
        self.send_response(404)
        self.end_headers()


def run_server(
    port: int = 3000, open_browser: bool = True, show_completed: bool = False
) -> None:
    """Start the web server."""
    # Store show_completed in a module-level variable for the handler
    global _show_completed
    _show_completed = show_completed

    # Use regular TCPServer (not threaded) to avoid SQLite threading issues
    class Server(socketserver.TCPServer):
        allow_reuse_address = True

    httpd = Server(("", port), NBHandler)

    if open_browser:

        def open_delayed() -> None:
            import time

            time.sleep(0.3)
            webbrowser.open(f"http://localhost:{port}")

        threading.Thread(target=open_delayed, daemon=True).start()

    try:
        # poll_interval=0.5 allows Ctrl+C to be detected on Windows
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nStopping...")
        httpd.server_close()
        print("Stopped")


# Module-level flag for completed todos
_show_completed = False
