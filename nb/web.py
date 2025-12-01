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
from nb.core.notes import get_note


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
            max-width: 900px;
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

        /* Mobile */
        @media (max-width: 768px) {
            .sidebar { width: 100%; height: auto; position: relative; border-right: none; border-bottom: 1px solid var(--border); }
            .main { margin-left: 0; padding: 1rem; }
            .app { flex-direction: column; }
            .note-list { max-height: 30vh; }
        }
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
                <a class="nav-link" onclick="loadTodos()">Todos</a>
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

        // Get today's date in local timezone (YYYY-MM-DD)
        function getToday() {
            const d = new Date();
            return d.getFullYear() + '-' +
                String(d.getMonth() + 1).padStart(2, '0') + '-' +
                String(d.getDate()).padStart(2, '0');
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

        async function loadHome(pushHistory = true) {
            currentNotebook = null;
            currentNotePath = null;
            document.getElementById('notes-section').style.display = 'none';
            if (pushHistory) history.pushState({ view: 'home' }, '', '#');

            const nbs = notebooksCache.length ? notebooksCache : await api('/notebooks');
            document.getElementById('content').innerHTML = `
                <h1>Notebooks</h1>
                <div class="notebook-grid">
                    ${nbs.map(nb => `
                        <div class="notebook-card" onclick="loadNotebook('${escapeJs(nb.name)}')">
                            ${nb.color ? `<div class="color-bar" style="background:${nb.color}"></div>` : ''}
                            <h3>${escapeHtml(nb.name)}</h3>
                            <span class="count">${nb.count} notes</span>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        async function loadNotebook(name, pushHistory = true) {
            currentNotebook = name;
            currentNotePath = null;
            if (pushHistory) history.pushState({ view: 'notebook', name }, '', '#notebook/' + encodeURIComponent(name));
            const notes = await api('/notebooks/' + encodeURIComponent(name));

            document.getElementById('notes-section').style.display = 'block';
            document.getElementById('notes').innerHTML = notes
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
                <p style="color:var(--text-dim)">${notes.length} notes</p>
                <ul style="margin-top:1rem">
                    ${notes.map(n => {
                        const aliasTag = n.alias ? `<span style="color:var(--accent);margin-left:0.5rem">@${escapeHtml(n.alias)}</span>` : '';
                        const linkedIcon = n.isLinked ? '<span style="color:var(--text-dim)" title="Linked note">↗</span> ' : '';
                        return `
                        <li style="margin:0.5rem 0">
                            <a href="javascript:void(0)" onclick="loadNote('${escapeJs(n.path)}')">${linkedIcon}${escapeHtml(n.title)}</a>${aliasTag}
                            ${n.date ? `<span style="color:var(--text-dim);margin-left:0.5rem">${n.date}</span>` : ''}
                        </li>
                    `;}).join('')}
                </ul>
            `;
        }

        async function loadNote(path, pushHistory = true) {
            currentNotePath = path;
            if (pushHistory) history.pushState({ view: 'note', path }, '', '#note/' + encodeURIComponent(path));
            const note = await api('/note?path=' + encodeURIComponent(path));

            // Strip frontmatter for display
            let content = note.content;
            if (content.startsWith('---')) {
                const parts = content.split('---');
                if (parts.length >= 3) {
                    content = parts.slice(2).join('---').trim();
                }
            }

            const aliasBadge = note.alias ? `<span style="color:var(--accent);font-size:0.7em;margin-left:0.75rem;vertical-align:middle">@${escapeHtml(note.alias)}</span>` : '';

            document.getElementById('content').innerHTML = `
                <div class="header-actions">
                    <button class="btn" onclick="editNote('${escapeJs(path)}')">Edit</button>
                </div>
                <div id="note-content">${marked.parse(content)}${aliasBadge ? `<p style="margin-top:1rem;color:var(--text-dim);font-size:0.85rem">Alias: <span style="color:var(--accent)">@${escapeHtml(note.alias || '')}</span></p>` : ''}</div>
            `;

            // Update active state in sidebar
            document.querySelectorAll('#notes .nav-link').forEach(el => {
                el.classList.toggle('active', el.textContent === note.title);
            });
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

        let todoSortBy = 'section'; // 'section', 'notebook', 'due', 'priority', 'created'

        async function loadTodos(pushHistory = true) {
            currentNotebook = null;
            currentNotePath = null;
            document.getElementById('notes-section').style.display = 'none';
            if (pushHistory) history.pushState({ view: 'todos' }, '', '#todos');

            const todos = await api('/todos');
            const today = getToday();
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

                return `
                    <div class="${cls}" data-id="${t.id}">
                        <div class="checkbox" onclick="toggleTodo('${t.id}')">${checkIcon}</div>
                        <div class="todo-body">
                            <div class="content">${priorityBadge}${escapeHtml(t.content)}</div>
                            <div class="meta">
                                ${t.status === 'in_progress' ? '<span style="color:var(--green)">In Progress</span> · ' : ''}
                                ${t.notebook ? '<span class="color-dot" style="background:' + nbColor + '"></span><span style="color:var(--accent)">' + escapeHtml(t.notebook) + '</span> · ' : ''}
                                ${t.due ? (t.isOverdue && !isCompleted ? '<span style="color:var(--red)">Overdue: ' + t.due + '</span>' : 'Due: ' + t.due) : 'No due date'}
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
        }

        function changeTodoSort(value) {
            todoSortBy = value;
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

        async function doSearch(query) {
            if (!query.trim()) {
                loadHome();
                return;
            }

            const results = await api('/search?q=' + encodeURIComponent(query));
            document.getElementById('notes-section').style.display = 'none';

            document.getElementById('content').innerHTML = `
                <h1>Search: ${escapeHtml(query)}</h1>
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
            nbs = []
            # Regular notebooks
            for name in list_notebooks(config.notes_root):
                notes_with_linked = get_notebook_notes_with_linked(
                    name, config.notes_root
                )
                nb_config = config.get_notebook(name)
                color = get_color_hex(nb_config.color) if nb_config else None
                nbs.append(
                    {
                        "name": name,
                        "count": len(notes_with_linked),
                        "color": color,
                        "isLinked": False,
                    }
                )

            # Virtual notebooks from linked notes
            linked_notes = list_linked_notes()
            seen_notebooks = {nb["name"] for nb in nbs}
            for linked in linked_notes:
                virtual_nb = linked.notebook or f"@{linked.alias}"
                if virtual_nb not in seen_notebooks:
                    files = scan_linked_note_files(linked)
                    nbs.append(
                        {
                            "name": virtual_nb,
                            "count": len(files),
                            "color": "#39c5cf",  # Cyan for linked notebooks
                            "isLinked": True,
                            "alias": linked.alias,
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
                # List files from linked note
                files = scan_linked_note_files(linked_config)
                for file_path in sorted(files, reverse=True):
                    note = get_note(file_path, config.notes_root)
                    # Use absolute path for linked notes
                    path_str = str(file_path).replace("\\", "/")
                    note_alias = get_alias_for_path(file_path)
                    result.append(
                        {
                            "path": path_str,
                            "title": note.title if note else file_path.stem,
                            "date": (
                                note.date.strftime("%Y-%m-%d")
                                if note and note.date
                                else None
                            ),
                            "alias": note_alias,
                            "isLinked": True,
                        }
                    )
            else:
                # Regular notebook - use get_notebook_notes_with_linked to include linked notes
                notes_with_linked = get_notebook_notes_with_linked(
                    notebook, config.notes_root
                )
                for note_path, is_linked, linked_alias in sorted(
                    notes_with_linked, reverse=True
                ):
                    if is_linked:
                        # Linked note - use absolute path
                        full_path = (
                            note_path
                            if note_path.is_absolute()
                            else config.notes_root / note_path
                        )
                        note = get_note(full_path, config.notes_root)
                        path_str = str(full_path).replace("\\", "/")
                    else:
                        note = get_note(note_path, config.notes_root)
                        path_str = str(note_path).replace("\\", "/")

                    # Check for note alias
                    check_path = (
                        note_path
                        if note_path.is_absolute()
                        else config.notes_root / note_path
                    )
                    note_alias = get_alias_for_path(check_path) or linked_alias

                    result.append(
                        {
                            "path": path_str,
                            "title": note.title if note else note_path.stem,
                            "date": (
                                note.date.strftime("%Y-%m-%d")
                                if note and note.date
                                else None
                            ),
                            "alias": note_alias,
                            "isLinked": is_linked,
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
            full_path = _safe_note_path(config.notes_root, note_path_str)
            if not full_path:
                self.send_json({"error": "Invalid path"}, 400)
                return

            if not full_path.exists():
                self.send_json({"error": "Not found"})
                return

            content = full_path.read_text(encoding="utf-8")
            note = get_note(full_path, config.notes_root)
            note_alias = get_alias_for_path(full_path)

            self.send_json(
                {
                    "content": content,
                    "title": note.title if note else full_path.stem,
                    "path": note_path_str,
                    "alias": note_alias,
                }
            )
            return

        # API: Search
        if path == "/api/search":
            q = query.get("q", [""])[0]
            if q:
                from nb.index.search import get_search

                results = get_search().search(q, k=20)
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

    print(f"Serving at http://localhost:{port}")
    print("Press Ctrl+C to stop")

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
