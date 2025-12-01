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
   * - ``-s, --show``
     - Print note to console instead of opening editor
   * - ``-n, --notebook NAME``
     - Use specified notebook

**Examples:**

.. code-block:: bash

   nb yesterday
   nb yesterday -n work

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

**Examples:**

.. code-block:: bash

   nb open "nov 25"           # Open by date
   nb open "last friday"      # Fuzzy date parsing
   nb open myproject          # Open by name
   nb open friday -n work     # Date in specific notebook
   nb open myalias            # Open by alias

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

Show recently viewed notes.

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
   * - ``-f, --full``
     - Show full paths instead of filenames
   * - ``-g, --group``
     - Group entries by notebook

**Examples:**

.. code-block:: bash

   nb history                 # Last 10 viewed
   nb history -l 50           # Last 50
   nb history -n work         # Filter by notebook
   nb history -g              # Group by notebook

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

**Examples:**

.. code-block:: bash

   nb add "Quick thought"                    # Append to today
   nb add "Note" --note myproject            # Append to named note
   nb add "Note" --note work/myproject       # Notebook/note format

Supports stdin piping:

.. code-block:: bash

   echo "random thought" | nb add
   git diff --stat | nb add --note work/log
   pbpaste | nb add                          # macOS clipboard

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
   * - ``--all``
     - List all notes (not just recent)
   * - ``--week``
     - List this week's daily notes
   * - ``--month``
     - List this month's notes
   * - ``-n, --notebook NAME``
     - Filter by notebook
   * - ``-f, --full``
     - Show full paths

**Examples:**

.. code-block:: bash

   nb list                    # Latest 3 per notebook
   nb list --all              # All notes
   nb list --week             # This week's daily notes
   nb list -n work            # Specific notebook
   nb list -f                 # Show full paths

nb stream
---------

Browse notes interactively with keyboard navigation.

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
   * - ``--recent``
     - Browse recently viewed notes
   * - ``--recently-modified``
     - Browse recently modified notes
   * - ``-l, --limit N``
     - Number of notes to browse

**Examples:**

.. code-block:: bash

   nb stream                  # All notes
   nb stream -n daily         # Daily notes only
   nb stream -w "last week"   # Date range
   nb stream --recent         # Recently viewed

**Keyboard shortcuts:**

- ``j/k`` - Navigate up/down
- ``Enter`` - Open in editor
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

**Examples:**

.. code-block:: bash

   nb delete myproject -n ideas
   nb delete daily/2025-11-27

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
