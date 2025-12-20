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