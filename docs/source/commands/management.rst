Management Commands
===================

Commands for managing notebooks, configuration, and maintenance.

Notebooks
---------

nb notebooks
^^^^^^^^^^^^

List and manage notebooks.

**Usage:** ``nb notebooks [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-v, --verbose``
     - Show note counts for each notebook

**Example:**

.. code-block:: bash

   nb notebooks               # List all notebooks
   nb notebooks -v            # Verbose with note counts

nb notebooks create
^^^^^^^^^^^^^^^^^^^

Create a new notebook.

**Usage:** ``nb notebooks create [OPTIONS] NAME``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``NAME``
     - Notebook name

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``--date-based``
     - Use week-based date organization
   * - ``--todo-exclude``
     - Exclude from ``nb todo`` by default
   * - ``--from PATH``
     - Link an external directory

**Examples:**

.. code-block:: bash

   nb notebooks create ideas
   nb notebooks create work-log --date-based
   nb notebooks create personal --todo-exclude
   nb notebooks create vault --from ~/Obsidian

nb notebooks remove
^^^^^^^^^^^^^^^^^^^

Remove a notebook from config (does not delete files).

**Usage:** ``nb notebooks remove NAME``

**Example:**

.. code-block:: bash

   nb notebooks remove old-project

Linked Files
------------

Link external markdown files or directories to index alongside your notes.

nb link add
^^^^^^^^^^^

Link an external file or directory.

**Usage:** ``nb link add [OPTIONS] PATH``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``PATH``
     - Path to file or directory

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``--alias, -a NAME``
     - Short name for the link (defaults to filename/dirname)
   * - ``--notebook, -n NAME``
     - Virtual notebook name (defaults to ``@alias``)
   * - ``--sync/--no-sync``
     - Sync todo completions back to source (default: sync)
   * - ``--todo-exclude``
     - Hide todos from ``nb todo``
   * - ``--no-recursive``
     - Don't scan subdirectories (for directory links)

**Examples:**

.. code-block:: bash

   nb link add ~/code/project/TODO.md
   nb link add ~/docs/wiki
   nb link add ~/vault --alias vault -n @vault
   nb link add ~/docs --no-recursive

nb link list
^^^^^^^^^^^^

Show all linked files.

**Usage:** ``nb link list``

nb link sync
^^^^^^^^^^^^

Re-scan and update the index.

**Usage:** ``nb link sync [ALIAS]``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``ALIAS``
     - Optional: sync only this link

**Examples:**

.. code-block:: bash

   nb link sync               # Sync all
   nb link sync wiki          # Sync specific link

nb link remove
^^^^^^^^^^^^^^

Stop tracking a linked file.

**Usage:** ``nb link remove ALIAS``

**Example:**

.. code-block:: bash

   nb link remove wiki

Managing link options
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   nb link exclude-todos wiki    # Hide todos from nb todo
   nb link include-todos wiki    # Show todos in nb todo
   nb link disable-sync wiki     # Stop syncing completions
   nb link enable-sync wiki      # Resume syncing

Templates
---------

Create reusable templates for new notes. See :doc:`../reference/note-format` for template variables and examples.

nb template list
^^^^^^^^^^^^^^^^

List available templates.

**Usage:** ``nb template list``

nb template new
^^^^^^^^^^^^^^^

Create a new template.

**Usage:** ``nb template new NAME``

**Example:**

.. code-block:: bash

   nb template new meeting

nb template edit
^^^^^^^^^^^^^^^^

Edit an existing template.

**Usage:** ``nb template edit NAME``

**Example:**

.. code-block:: bash

   nb template edit meeting

nb template show
^^^^^^^^^^^^^^^^

Display template contents.

**Usage:** ``nb template show NAME``

**Example:**

.. code-block:: bash

   nb template show meeting

nb template remove
^^^^^^^^^^^^^^^^^^

Delete a template.

**Usage:** ``nb template remove NAME``

**Example:**

.. code-block:: bash

   nb template remove meeting

Configuration
-------------

nb config
^^^^^^^^^

Open config file in editor.

**Usage:** ``nb config``

nb config get
^^^^^^^^^^^^^

Get a configuration value.

**Usage:** ``nb config get KEY``

**Examples:**

.. code-block:: bash

   nb config get editor
   nb config get notebook.work.color

nb config set
^^^^^^^^^^^^^

Set a configuration value.

**Usage:** ``nb config set KEY VALUE``

**Available settings:**

.. list-table::
   :widths: 40 60
   :header-rows: 1

   * - Setting
     - Description
   * - ``editor``
     - Text editor command (e.g., ``vim``, ``code``)
   * - ``date_format``
     - Date display format (e.g., ``%Y-%m-%d``)
   * - ``time_format``
     - Time display format (e.g., ``%H:%M``)
   * - ``embeddings.provider``
     - Embeddings provider (``ollama`` or ``openai``)
   * - ``embeddings.model``
     - Model name (e.g., ``nomic-embed-text``)
   * - ``embeddings.base_url``
     - Custom endpoint URL
   * - ``embeddings.api_key``
     - API key (for OpenAI)
   * - ``notebook.NAME.color``
     - Notebook display color
   * - ``notebook.NAME.icon``
     - Notebook icon (emoji or alias)

**Examples:**

.. code-block:: bash

   nb config set editor vim
   nb config set embeddings.provider ollama
   nb config set notebook.work.color blue
   nb config set notebook.daily.icon calendar

nb config list
^^^^^^^^^^^^^^

List all configurable settings.

**Usage:** ``nb config list``

nb config exclude/include
^^^^^^^^^^^^^^^^^^^^^^^^^

Manage todo exclusion.

**Usage:** ``nb config exclude NAME`` or ``nb config include NAME``

**Examples:**

.. code-block:: bash

   nb config exclude personal          # Exclude notebook
   nb config include personal          # Include notebook
   nb config exclude projects/old      # Exclude note
   nb config include projects/old      # Include note

Index & Maintenance
-------------------

nb index
^^^^^^^^

Rebuild the notes and todos index.

**Usage:** ``nb index [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``--force``
     - Force full reindex (ignore cache)
   * - ``-n, --notebook NAME``
     - Only reindex specific notebook
   * - ``--rebuild``
     - Drop and recreate database (for schema changes)
   * - ``--embeddings``
     - Rebuild search embeddings
   * - ``--vectors-only``
     - Rebuild only vectors (skip file indexing)

**Examples:**

.. code-block:: bash

   nb index                    # Incremental update
   nb index --force            # Full reindex
   nb index -n daily           # Specific notebook
   nb index --rebuild          # Recreate database
   nb index --embeddings       # Rebuild embeddings

Note Linking
------------

Commands for exploring connections between notes.

nb links
^^^^^^^^

Show outgoing links from a note.

**Usage:** ``nb links [OPTIONS] NOTE_REF``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``NOTE_REF``
     - Note name, path, or alias

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``--internal``
     - Show only internal (note) links
   * - ``--external``
     - Show only external (URL) links
   * - ``--json``
     - Output as JSON
   * - ``--check``
     - Check for broken internal links

**Examples:**

.. code-block:: bash

   nb links today                  # Links from today's note
   nb links projects/myproject     # Links from specific note
   nb links today --internal       # Only internal links
   nb links today --external       # Only external links
   nb links --check                # Check all notes for broken links
   nb links today --check          # Check specific note

nb backlinks
^^^^^^^^^^^^

Show notes linking TO a note (incoming links).

**Usage:** ``nb backlinks [OPTIONS] NOTE_REF``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``NOTE_REF``
     - Note name, path, or alias

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``--count``
     - Just show the count
   * - ``--json``
     - Output as JSON

**Examples:**

.. code-block:: bash

   nb backlinks projects/myproject # What notes link to this?
   nb backlinks today --count      # Just show the count
   nb backlinks myproject --json   # Output as JSON

nb graph
^^^^^^^^

Visualize note connections in the terminal.

**Usage:** ``nb graph [OPTIONS] [NOTE_REF]``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``NOTE_REF``
     - Optional note to center the graph on

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-d, --depth N``
     - Levels of connections to show (default: 1)
   * - ``--no-tags``
     - Don't show tag connections
   * - ``--links-only``
     - Only show note-to-note links

**Examples:**

.. code-block:: bash

   nb graph                    # Overview of entire knowledge graph
   nb graph today              # Connections for today's note
   nb graph myproject -d 2     # 2 levels of connections
   nb graph --no-tags          # Hide tag connections

nb related
^^^^^^^^^^

Find notes related to a given note.

**Usage:** ``nb related [OPTIONS] NOTE_REF``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``NOTE_REF``
     - Note name, path, or alias

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-l, --limit N``
     - Number of related notes to show (default: 10)
   * - ``--links-only``
     - Only by direct links
   * - ``--tags-only``
     - Only by shared tags
   * - ``--semantic-only``
     - Only by content similarity

**Scoring weights:**

- Direct links: 1.0 (outgoing), 0.9 (backlinks)
- Shared tags: 0.3 per tag
- Semantic similarity: 0.5 × score

**Examples:**

.. code-block:: bash

   nb related today              # Related to today's note
   nb related myproject -l 5     # Top 5 related
   nb related today --links-only # Only by direct links
   nb related today --tags-only  # Only by shared tags

Statistics
----------

nb stats
^^^^^^^^

View todo statistics dashboard.

**Usage:** ``nb stats [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``--compact``
     - Single panel summary only
   * - ``--by-notebook``
     - Show breakdown by notebook
   * - ``--by-priority``
     - Show breakdown by priority
   * - ``--by-tag``
     - Show top tags by usage
   * - ``-n, --notebook NAME``
     - Filter to specific notebooks (repeatable)
   * - ``--days N``
     - Activity period in days (default: 30)
   * - ``-x, --exclude NAME``
     - Exclude notebooks from stats

**Examples:**

.. code-block:: bash

   nb stats                    # Full dashboard
   nb stats --compact          # Summary only
   nb stats --by-notebook      # Breakdown by notebook
   nb stats -n work -n daily   # Specific notebooks
   nb stats --days 7           # Week activity
   nb stats -x personal        # Exclude notebooks

.. image:: /_static/examples/stats.svg
   :alt: nb stats output
   :width: 60%

Tags
----

nb tags
^^^^^^^

List tags with usage counts.

**Usage:** ``nb tags [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``--sort alpha``
     - Sort alphabetically (default: by count)
   * - ``--sources``
     - Show which notebooks/notes use each tag
   * - ``-n, --notebook NAME``
     - Filter to specific notebook
   * - ``--limit N``
     - Limit to top N tags
   * - ``--open``
     - Only count open (non-completed) todos

**Examples:**

.. code-block:: bash

   nb tags                     # All tags by count
   nb tags --sort alpha        # Alphabetical
   nb tags --sources           # Show sources
   nb tags -n work             # Specific notebook
   nb tags --limit 10          # Top 10

.. image:: /_static/examples/tags.svg
   :alt: nb tags output
   :width: 50%

Attachments
-----------

nb attach file
^^^^^^^^^^^^^^

Attach a file to a note.

**Usage:** ``nb attach file [OPTIONS] PATH``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``--to NOTE``
     - Attach to specific note (default: today's)
   * - ``--copy``
     - Copy file to ``.nb/attachments/``

**Examples:**

.. code-block:: bash

   nb attach file ./doc.pdf              # Attach to today's note
   nb attach file ./img.png --to note.md
   nb attach file ./ref.pdf --copy

nb attach url
^^^^^^^^^^^^^

Attach a URL to a note.

**Usage:** ``nb attach url URL``

**Example:**

.. code-block:: bash

   nb attach url https://example.com

nb attach list
^^^^^^^^^^^^^^

List attachments.

**Usage:** ``nb attach list``

nb attach open
^^^^^^^^^^^^^^

Open an attachment.

**Usage:** ``nb attach open NOTE [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``--line N``
     - Open attachment at specific line

Export
------

nb export
^^^^^^^^^

Export a note or notebook to PDF, DOCX, or HTML.

**Usage:** ``nb export [OPTIONS] NOTE_REF OUTPUT``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``NOTE_REF``
     - Note name, path, date, alias, or notebook name (with trailing ``/``)
   * - ``OUTPUT``
     - Destination filename (format inferred from extension)

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-f, --format``
     - Output format: ``pdf``, ``docx``, or ``html`` (inferred from extension if not provided)
   * - ``-n, --notebook NAME``
     - Notebook containing the note
   * - ``-s, --sort``
     - Sort order for notebook export: ``date`` (default), ``modified``, or ``name``
   * - ``-r, --reverse``
     - Reverse sort order (newest/last first)

**Single Note Export:**

.. code-block:: bash

   nb export friday report.pdf              # Export to PDF
   nb export work/project documentation.docx  # Export to Word
   nb export myalias output.html            # Export to HTML
   nb export daily/friday report.pdf --format pdf

**Notebook Export:**

Export all notes in a notebook concatenated into a single file. Notes are sorted
by date (oldest first) by default.

.. code-block:: bash

   nb export daily/ journal.pdf             # Export entire notebook
   nb export work/ work-notes.docx          # Export to Word
   nb export daily/ archive.pdf --sort modified  # Sort by modification time
   nb export daily/ archive.pdf --sort name      # Sort alphabetically
   nb export daily/ archive.pdf --reverse        # Newest first

Web Viewer
----------

nb web
^^^^^^

Browse notebooks in a browser.

**Usage:** ``nb web [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``--port N``
     - Server port (default: 3000)
   * - ``--no-open``
     - Don't open browser automatically
   * - ``-c, --completed``
     - Include completed todos

**Examples:**

.. code-block:: bash

   nb web                      # Start and open browser
   nb web --port 8080          # Custom port
   nb web --no-open            # Don't open browser
   nb web -c                   # Include completed todos

**Features:**

- Browse notebooks and notes with colors
- Create and edit notes in browser
- Markdown rendering with syntax highlighting
- Full-text search
- Todo management
- Dark theme, mobile responsive

Press ``Ctrl+C`` to stop the server.

Help
----

nb help
^^^^^^^

Display the README in rich formatting.

**Usage:** ``nb help``
