Notes Commands
==============

Commands for creating, opening, and managing notes.

nb (default)
------------

Open today's daily note in your editor.

**Usage:** ``nb [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-s, --show``
     - Print note to console instead of opening editor
   * - ``-n, --notebook NAME``
     - Open today's note in specified notebook

**Examples:**

.. code-block:: bash

   nb                  # Open today's note
   nb -s               # Show in console instead
   nb -n work          # Today's note in work notebook

nb today
--------

Alias for the default action - open today's daily note.

**Usage:** ``nb today [OPTIONS]``

**Options:** Same as ``nb`` default.

**Examples:**

.. code-block:: bash

   nb today
   nb today -n work

nb yesterday
------------

Open yesterday's daily note.

**Usage:** ``nb yesterday [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --notebook NAME``
     - Open yesterday's note in specified notebook

**Examples:**

.. code-block:: bash

   nb yesterday              # Yesterday's note in default daily notebook
   nb yesterday -n work      # Yesterday's note in work notebook

nb open
-------

Open a note by date or name.

**Usage:** ``nb open [OPTIONS] NAME``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``NAME``
     - Date string, note name, or alias

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-s, --show``
     - Print note to console instead of opening editor
   * - ``-n, --notebook NAME``
     - Search within specified notebook
   * - ``--no-prompt``
     - Don't prompt to create if note doesn't exist

If the note doesn't exist, you'll be prompted to create it (unless ``--no-prompt`` is specified).

**Examples:**

.. code-block:: bash

   nb open "nov 25"           # Open by date
   nb open "last friday"      # Fuzzy date parsing
   nb open myproject          # Open by name
   nb open friday -n work     # Date in specific notebook
   nb open myalias            # Open by alias
   nb open newfile -n ideas   # Prompts to create if missing
   nb open newfile --no-prompt  # Fail if not found

nb show
-------

Display a note in the console with markdown formatting.

**Usage:** ``nb show [OPTIONS] [NAME]``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``NAME``
     - Date string, note name, or alias (default: today)

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --notebook NAME``
     - Search within specified notebook

**Examples:**

.. code-block:: bash

   nb show                    # Today's note
   nb show friday             # Friday's daily note
   nb show myproject -n ideas # Named note in notebook

nb last
-------

Open the most recently modified (or viewed) note.

**Usage:** ``nb last [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-s, --show``
     - Print note to console instead of opening editor
   * - ``-n, --notebook NAME``
     - Filter by notebook
   * - ``--viewed``
     - Open last viewed note instead of last modified

**Examples:**

.. code-block:: bash

   nb last                    # Last modified
   nb last -s                 # Show in console
   nb last --viewed           # Last viewed instead
   nb last -n work            # Last in specific notebook

nb history
----------

Show recently modified notes (or view history with ``--viewed``).

**Usage:** ``nb history [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-l, --limit N``
     - Number of notes to show (default: 10)
   * - ``-o, --offset N``
     - Skip first N entries
   * - ``-n, --notebook NAME``
     - Filter by notebook
   * - ``-F, --full``
     - Show full paths instead of filenames
   * - ``-g, --group``
     - Group entries by notebook
   * - ``-v, --viewed``
     - Show view history instead of modification history
   * - ``-C, --copy``
     - Copy history list to clipboard

**Examples:**

.. code-block:: bash

   nb history                 # Last 10 modified notes
   nb history --viewed        # Show view history instead
   nb history -l 50           # Last 50
   nb history -n work         # Filter by notebook
   nb history -g              # Group by notebook
   nb history -C              # Copy to clipboard

nb new
------

Create a new note.

**Usage:** ``nb new [OPTIONS] [NAME]``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``NAME``
     - Note name/path (optional for date-based notebooks)

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --notebook NAME``
     - Create in specified notebook
   * - ``-T, --template NAME``
     - Use a template (see :doc:`../reference/note-format`)

**Examples:**

.. code-block:: bash

   nb new projects/idea       # Create named note
   nb new -n work             # Today's note in notebook
   nb new -T meeting          # Use a template
   nb new idea -n ideas -T meeting

Templates support variable substitution (``{{ date }}``, ``{{ title }}``, etc.) and can be set as defaults per notebook. See :doc:`../reference/note-format` for details and :doc:`management` for template commands.

nb add
------

Append content to a note.

**Usage:** ``nb add [OPTIONS] [CONTENT]``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``CONTENT``
     - Text to append (optional if piping from stdin)

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``--note, -N NAME``
     - Append to specific note instead of today's
   * - ``-n, --notebook NAME``
     - Notebook for today's note
   * - ``-p, --paste``
     - Read content from clipboard

**Examples:**

.. code-block:: bash

   nb add "Quick thought"                    # Append to today
   nb add "Note" --note myproject            # Append to named note
   nb add "Note" --note work/myproject       # Notebook/note format
   nb add --paste                            # Append clipboard to today
   nb add --paste --note work/project        # Paste to specific note

Supports stdin piping:

.. code-block:: bash

   echo "random thought" | nb add
   git diff --stat | nb add --note work/log
   pbpaste | nb add                          # macOS clipboard

nb log
------

Append timestamped content to a note.

**Usage:** ``nb log [OPTIONS] [TEXT]``

Prepends a timestamp using your configured ``date_format`` and ``time_format`` settings.

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``TEXT``
     - Content to log (optional if piping from stdin)

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``--note, -N NAME``
     - Log to specific note instead of today's
   * - ``-n, --notebook NAME``
     - Notebook context for resolving note
   * - ``-p, --paste``
     - Read content from clipboard

**Examples:**

.. code-block:: bash

   nb log "Started working on feature X"     # Today's daily note
   nb log "Meeting notes" --note work/log    # Specific note
   nb log "Entry" -N proj                    # Using alias
   nb log --paste                            # Log clipboard with timestamp

Supports stdin piping:

.. code-block:: bash

   git diff --stat | nb log --note work/changes
   echo "Completed task" | nb log

nb clip
-------

Clip content from a URL or file to a note.

**Usage:** ``nb clip [OPTIONS] SOURCE``

Fetches content from a URL or converts a local file to markdown and saves it.
By default appends to today's daily note.

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``SOURCE``
     - URL or local file path

**Supported file types:** PDF, DOCX, DOC, PPTX, XLSX, ODT, EPUB, RTF, HTML, and more.

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --notebook NAME``
     - Create new note in this notebook
   * - ``--to NAME``
     - Append to specific note (path, alias, or notebook/note format)
   * - ``-t, --tag NAME``
     - Add tags (repeatable)
   * - ``-s, --section NAME``
     - Extract only this section from the page (supports wildcards)
   * - ``-T, --title NAME``
     - Custom title (overrides extracted title)
   * - ``--no-domain-tag``
     - Don't auto-tag with source domain

**Examples:**

.. code-block:: bash

   # Web clipping
   nb clip https://example.com/article              # Append to today
   nb clip https://example.com/article -n bookmarks # New note in notebook
   nb clip https://example.com/article --to research.md  # Append to note
   nb clip https://example.com/article --tag python --tag tutorial
   nb clip https://docs.python.org --section "Installation"

   # Local file conversion
   nb clip ~/Documents/report.pdf
   nb clip ./meeting-notes.docx -n work
   nb clip presentation.pptx --title "Q4 Presentation"

nb edit
-------

Open an existing note in the editor.

**Usage:** ``nb edit NAME``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``NAME``
     - Note path or name

**Examples:**

.. code-block:: bash

   nb edit daily/2025-11-27
   nb edit myproject -n ideas

nb list
-------

List notes across notebooks.

**Usage:** ``nb list [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-l, --limit N``
     - Notes to show per notebook (default: 5)
   * - ``--all``
     - List all notes (not just recent)
   * - ``--week``
     - List this week's daily notes
   * - ``--month``
     - List this month's notes
   * - ``-n, --notebook NAME``
     - Filter by notebook
   * - ``-F, --full``
     - Show full paths
   * - ``-d, --details``
     - Show extra details (todo count, mtime, excluded status)
   * - ``-T, --tree``
     - Display as tree grouped by subdirectory sections
   * - ``-S, --section NAME``
     - Filter by path section/subdirectory (repeatable)
   * - ``-xs, --exclude-section NAME``
     - Exclude notes from this section (repeatable)

By default, shows the most recently modified notes per notebook (grouped).
With ``--details``, also shows:

- Todo count (incomplete todos in the note)
- Last modified time (relative, e.g., "2h ago")
- Note date (from frontmatter)
- Excluded status (if note is excluded from ``nb todo``)

**Examples:**

.. code-block:: bash

   nb list                    # Recently modified per notebook
   nb list -l 10              # 10 notes per notebook
   nb list --all              # All notes
   nb list --week             # This week's daily notes
   nb list -n work            # Specific notebook
   nb list -F                 # Show full paths
   nb list -d                 # Show extra details
   nb list -n work -d         # Notebook with details
   nb list -T                 # Display as tree
   nb list -S tasks           # Filter by section
   nb list -xs archive        # Exclude a section

.. image:: /_static/examples/note-list.svg
   :alt: nb list output
   :width: 60%

nb stream
---------

Browse notes interactively with keyboard navigation.

By default shows recently modified notes (most recent first). When piped,
outputs plain text without the TUI.

**Usage:** ``nb stream [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --notebook NAME``
     - Filter by notebook
   * - ``-w, --when RANGE``
     - Date range (e.g., "last week", "last 2 weeks")
   * - ``--by-date``
     - Sort by note date instead of modification time
   * - ``--recent``
     - Browse recently viewed notes
   * - ``-l, --limit N``
     - Number of notes to browse
   * - ``-c, --continuous``
     - Show all notes in continuous flow (maximized content)
   * - ``-r, --reverse``
     - Show oldest first

**Examples:**

.. code-block:: bash

   nb stream                  # Recently modified notes (default)
   nb stream --by-date        # Sort by note date
   nb stream -n daily         # Daily notes only
   nb stream -w "last week"   # Date range
   nb stream --recent         # Recently viewed
   nb stream -c               # Continuous mode
   nb stream | head -100      # Pipe mode (plain text)

**Keyboard shortcuts:**

- ``j/k`` or ``n/p`` - Navigate between notes
- ``g/G`` - Jump to first/last note
- ``/`` - Search notes by title or content
- ``e`` - Edit note in-app
- ``E`` - Edit in external editor
- ``Escape`` - Clear search filter or quit
- ``q`` - Quit

nb alias
--------

Create an alias for a note.

**Usage:** ``nb alias NAME PATH``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``NAME``
     - Alias name
   * - ``PATH``
     - Note path

**Examples:**

.. code-block:: bash

   nb alias readme projects/README
   nb alias standup daily/2025-11-29

nb aliases
----------

List all note aliases.

**Usage:** ``nb aliases``

nb unalias
----------

Remove a note alias.

**Usage:** ``nb unalias NAME``

nb pin
------

Pin a note for quick access.

**Usage:** ``nb pin [OPTIONS] NOTE_REF``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``NOTE_REF``
     - Note path, name, alias, or date

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --notebook NAME``
     - Notebook containing the note

**Examples:**

.. code-block:: bash

   nb pin readme              # Pin a note
   nb pin myproject -n work   # Pin work/myproject.md
   nb pin daily/friday        # Pin Friday's daily note

nb unpin
--------

Unpin a note.

**Usage:** ``nb unpin [OPTIONS] NOTE_REF``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``NOTE_REF``
     - Note path, name, alias, or date

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --notebook NAME``
     - Notebook containing the note

**Examples:**

.. code-block:: bash

   nb unpin readme
   nb unpin myproject -n work

nb pinned
---------

List all pinned notes.

**Usage:** ``nb pinned [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --notebook NAME``
     - Filter by notebook

**Examples:**

.. code-block:: bash

   nb pinned                  # List all pinned notes
   nb pinned -n work          # Only show pinned notes in work notebook

nb delete
---------

Delete a note from the filesystem and database.

**Usage:** ``nb delete [OPTIONS] NAME``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``NAME``
     - Note name or path

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --notebook NAME``
     - Notebook containing the note
   * - ``-f, --force``
     - Skip confirmation prompt

**Examples:**

.. code-block:: bash

   nb delete myproject -n ideas
   nb delete daily/2025-11-27
   nb delete friday -f          # Skip confirmation

Note: Linked notes cannot be deleted. Use ``nb unlink`` to remove them.

nb mv
-----

Move a note to a new location.

**Usage:** ``nb mv [OPTIONS] SOURCE_REF DEST_REF``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``SOURCE_REF``
     - Source note path, name, or alias
   * - ``DEST_REF``
     - Destination path (notebook/note format)

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-f, --force``
     - Overwrite destination if it exists

Moving a note will:

- Move the file to the new location
- Update the database index
- Generate new todo IDs (since IDs include the source path)

**Examples:**

.. code-block:: bash

   nb mv work/old-project archive/old-project
   nb mv friday archive/2025-01-10
   nb mv work/draft work/final -f          # Overwrite if exists

Note: Linked notes cannot be moved. Use ``nb unlink`` first.

nb cp
-----

Copy a note to a new location.

**Usage:** ``nb cp SOURCE_REF DEST_REF``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``SOURCE_REF``
     - Source note path, name, or alias
   * - ``DEST_REF``
     - Destination path (notebook/note format)

Copying a note will:

- Create a copy at the new location
- Index the new note
- Generate new todo IDs for the copy (since IDs include the source path)

**Examples:**

.. code-block:: bash

   nb cp work/template work/new-project
   nb cp daily/friday archive/backup

nb where
--------

Print the full filesystem path to a notebook, note, or alias.

**Usage:** ``nb where [OPTIONS] REF``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``REF``
     - Notebook name, note name/path/date, or alias

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --notebook NAME``
     - Notebook context for resolving note

**Examples:**

.. code-block:: bash

   nb where daily              # Path to daily notebook directory
   nb where friday             # Path to Friday's daily note
   nb where myalias            # Path to aliased note
   nb where myproject -n work  # Path to work/myproject.md

Useful for scripting and integrations. When multiple matches exist, all paths are printed (one per line).

Command aliases
---------------

.. list-table::
   :header-rows: 1

   * - Alias
     - Command
   * - ``t``
     - ``today``
   * - ``y``
     - ``yesterday``
   * - ``l``
     - ``last``
   * - ``o``
     - ``open``
   * - ``s``
     - ``search``
   * - ``ss``
     - ``search --semantic``
   * - ``ls``
     - ``list``
   * - ``nbs``
     - ``notebooks``
   * - ``td``
     - ``todo``
   * - ``ta``
     - ``todo add``
   * - ``tdd``
     - ``todo done``
   * - ``now``
     - ``todo --today``
   * - ``rec``
     - ``record``
   * - ``c``
     - ``clip``

Additionally, ``nbt`` is a standalone executable that works exactly like ``nb todo``.
